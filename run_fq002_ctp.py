"""FQ-002-v2 → CTP SimNow. Default is dry-run (no send)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / "data" / "processed" / "fq002_ctp_state.json"
INTENT_PATH = ROOT / "data" / "processed" / "fq002_ctp_intent.json"
LOG_PATH = ROOT / "data" / "processed" / "fq002_ctp.log"
HEARTBEAT_PATH = ROOT / "data" / "processed" / "fq002_ctp_heartbeat.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="FQ-002 CTP sim (dry-run default)")
    parser.add_argument("--refresh", action="store_true", help="Refresh Sina bars before the signal")
    parser.add_argument("--connect", action="store_true", help="Log in and show account; still no send")
    parser.add_argument("--send", action="store_true", help="Send 1-lot limits on SimNow only")
    parser.add_argument("--commit-state", action="store_true", help="Persist hold state after a dry-run")
    parser.add_argument("--wait", type=float, default=15.0)
    args = parser.parse_args()

    hb = {
        "ok": False,
        "send": bool(args.send),
        "as_of": None,
        "contract": None,
        "target": None,
        "note": None,
        "balance": None,
        "orders": 0,
        "error": None,
    }
    code = 1
    try:
        code = _run(args, hb)
        hb["ok"] = code == 0
        return code
    except Exception as exc:
        hb["error"] = str(exc)
        hb["ok"] = False
        print(exc, file=sys.stderr)
        return 1
    finally:
        _write_heartbeat(hb)
        _append_log(
            f"exit={code} send={args.send} ok={hb.get('ok')} "
            f"target={hb.get('target')} contract={hb.get('contract')} err={hb.get('error') or '-'}"
        )


def _run(args, hb: dict) -> int:
    from localbt import SPEC_FQ002
    from localbt.engine import latest_fq002_signal
    from localbt.fetch import build_dominant_map, build_next_map, load_or_fetch

    from ctp.intent import plan_fq002
    from ctp.symbols import to_ctp_symbol

    spec = SPEC_FQ002
    bars = load_or_fetch(spec.underlying, start="2016-01-01", cache=not args.refresh)
    dominant = build_dominant_map(bars, spec.underlying)
    nxt = build_next_map(bars, dominant, spec.underlying)
    signal = latest_fq002_signal(bars, dominant, nxt, spec)
    ctp_symbol, exch = to_ctp_symbol(signal.contract)
    state = _load_state()
    plan = plan_fq002(signal, state, spec, mark=signal.last_close)

    print(f"FQ-002-{spec.version} as_of={signal.as_of.date()} contract={signal.contract} -> {ctp_symbol}.{exch}")
    roll_txt = "n/a" if signal.roll is None else f"{signal.roll:.2%}"
    print(f"roll={roll_txt} target={signal.target} last_close={signal.last_close} note={plan.note}")
    if not plan.orders:
        print("orders: (none)")
    for order in plan.orders:
        print(
            f"order {order.reason} {order.offset} {order.direction} "
            f"{order.volume}x {order.lab_contract}"
        )
    INTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    INTENT_PATH.write_text(
        json.dumps(
            {
                "as_of": plan.signal_as_of,
                "contract": plan.contract,
                "ctp": f"{ctp_symbol}.{exch}",
                "roll": signal.roll,
                "target": plan.target,
                "note": plan.note,
                "orders": [order.__dict__ for order in plan.orders],
                "send": bool(args.send),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {INTENT_PATH}")
    hb["as_of"] = plan.signal_as_of
    hb["contract"] = plan.contract
    hb["target"] = plan.target
    hb["note"] = plan.note
    hb["orders"] = len(plan.orders)

    if not args.connect and not args.send:
        if args.commit_state:
            _save_state(plan.next_state)
            print(f"committed dry-run state -> {STATE_PATH}")
        else:
            print("dry-run: 未下单。加 --connect 测登录，或 --send 在 SimNow 发 1 手限价。")
        return 0

    from ctp.config import CtpConfigError, load_ctp_config
    from ctp.session import CtpNotInstalled, CtpSession

    try:
        cfg = load_ctp_config()
    except CtpConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.send and cfg.environment == "live":
        print("拒绝实盘发单。", file=sys.stderr)
        return 2

    try:
        session = CtpSession(cfg)
    except CtpNotInstalled as exc:
        print(exc, file=sys.stderr)
        return 3

    try:
        session.connect(wait_s=args.wait)
        accs = session.accounts()
        if not accs:
            print("登录超时：资金账户仍为空。", file=sys.stderr)
            return 1
        equity = accs[0].balance or state.equity
        hb["balance"] = accs[0].balance
        for acc in accs:
            print(f"account balance={acc.balance:.2f} available={acc.available:.2f}")
        positions = session.positions()
        synced = _sync_state_from_positions(state, positions)
        synced.equity = equity
        if synced.lots != state.lots or synced.contract != state.contract:
            print(f"synced CTP position -> {synced.contract} dir={synced.direction} lots={synced.lots}")
        plan = plan_fq002(signal, synced, spec, mark=signal.last_close)
        vt = session.subscribe_lab_contract(signal.contract)
        tick = session.wait_tick(vt)
        if tick is None or tick.last <= 0:
            print(f"no tick for {vt}; 盘后可登录查账，但不能可靠发单")
            if args.send and plan.orders:
                print("abort send: no last price", file=sys.stderr)
                return 1
        else:
            print(f"tick {vt} last={tick.last} bid={tick.bid} ask={tick.ask}")
            plan = plan_fq002(signal, synced, spec, mark=tick.last)

        if not args.send:
            print("connected, no orders sent")
            return 0

        if not plan.orders:
            _save_state(plan.next_state)
            print("nothing to send")
            return 0

        for order in plan.orders:
            price = _limit_price(tick, order.direction)
            if price <= 0:
                print("abort send: missing bid/ask/last", file=sys.stderr)
                return 1
            oid = session.send_limit(
                order.lab_contract,
                direction=order.direction,
                offset=order.offset,
                volume=order.volume,
                price=price,
            )
            print(f"sent {oid} {order.offset} {order.direction} {order.volume}x {order.lab_contract} @{price}")
        time.sleep(2.0)
        for pos in session.positions():
            if pos.volume:
                print(f"position {pos.symbol}.{pos.exchange} {pos.direction} vol={pos.volume}")
        _save_state(plan.next_state)
        print(f"wrote {STATE_PATH}")
        hb["orders"] = len(plan.orders)
        hb["note"] = plan.note
        return 0
    finally:
        session.close()


def _append_log(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def _write_heartbeat(hb: dict) -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(hb)
    payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    HEARTBEAT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _limit_price(tick, direction: str) -> float:
    if tick is None:
        return 0.0
    if direction == "long":
        return tick.ask or tick.last
    return tick.bid or tick.last


def _load_state():
    from ctp.intent import CtpFillState

    if not STATE_PATH.exists():
        return CtpFillState()
    return CtpFillState.from_json(json.loads(STATE_PATH.read_text(encoding="utf-8")))


def _save_state(state) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_state_from_positions(state, positions):
    from ctp.intent import CtpFillState
    from ctp.symbols import from_ctp_symbol

    long_lots = 0.0
    short_lots = 0.0
    symbol = None
    price = state.entry
    for pos in positions:
        if not pos.volume:
            continue
        text = str(pos.symbol)
        if not text.lower().startswith("m") or not text[1:2].isdigit():
            continue
        symbol = from_ctp_symbol(pos.symbol, pos.exchange)
        d = str(pos.direction).lower()
        if d in {"long", "多", "direction.long"}:
            long_lots += pos.volume
            price = pos.price or price
        elif d in {"short", "空", "direction.short"}:
            short_lots += pos.volume
            price = pos.price or price
    net = int(long_lots - short_lots)
    if net == 0 and symbol is None:
        return state
    if net == 0:
        return CtpFillState(as_of=state.as_of, contract=symbol, equity=state.equity)
    direction = 1 if net > 0 else -1
    return CtpFillState(
        as_of=state.as_of,
        contract=symbol or state.contract,
        direction=direction,
        lots=abs(net),
        bars_held=state.bars_held,
        entry=price or state.entry,
        cooldown=state.cooldown,
        equity=state.equity,
    )


if __name__ == "__main__":
    raise SystemExit(main())
