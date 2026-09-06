"""Login to SimNow: account, positions, one tick. Does not send orders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="CTP SimNow probe (no orders)")
    parser.add_argument("--subscribe", default="", help="Lab contract, e.g. M2509")
    parser.add_argument("--wait", type=float, default=15.0)
    args = parser.parse_args()

    from ctp.config import CtpConfigError, load_ctp_config
    from ctp.session import CtpNotInstalled, CtpSession

    try:
        cfg = load_ctp_config()
    except CtpConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        session = CtpSession(cfg)
    except CtpNotInstalled as exc:
        print(exc, file=sys.stderr)
        return 3

    print(f"environment={cfg.environment} userid={cfg.userid} broker={cfg.brokerid}")
    print(f"td={cfg.td_front} md={cfg.md_front} counter_env={cfg.counter_env}")
    try:
        session.connect(wait_s=args.wait)
        accs = session.accounts()
        if not accs:
            extra = getattr(session, "_last_error", "")
            print("登录超时：资金账户仍为空。看行情/交易前置、是否仍走 HTTP 代理。" + (f" {extra}" if extra else ""))
            return 1
        for acc in accs:
            print(f"account balance={acc.balance:.2f} available={acc.available:.2f} frozen={acc.frozen:.2f}")
        positions = [p for p in session.positions() if p.volume]
        if not positions:
            print("positions: (none)")
        for pos in positions:
            print(
                f"position {pos.symbol}.{pos.exchange} {pos.direction} "
                f"vol={pos.volume} px={pos.price} pnl={pos.pnl}"
            )
        contract = args.subscribe.strip()
        if not contract:
            contract = _guess_meal_contract()
        if contract:
            try:
                vt = session.subscribe_lab_contract(contract)
                tick = session.wait_tick(vt)
            except Exception as exc:
                print(f"subscribe skipped ({exc})")
                vt, tick = contract, None
            if tick is None or tick.last <= 0:
                print(f"subscribed {vt} but no tick yet (盘后或未开市正常)")
            else:
                print(
                    f"tick {vt} last={tick.last} bid={tick.bid} ask={tick.ask} "
                    f"oi={tick.open_interest}"
                )
        else:
            print("no contract to subscribe; pass --subscribe M2601")
        print("probe ok (no orders sent)")
        return 0
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        session.close()


def _guess_meal_contract() -> str:
    try:
        from localbt import SPEC_FQ002
        from localbt.engine import latest_fq002_signal
        from localbt.fetch import build_dominant_map, build_next_map, load_or_fetch

        bars = load_or_fetch(SPEC_FQ002.underlying, cache=True)
        dominant = build_dominant_map(bars, SPEC_FQ002.underlying)
        nxt = build_next_map(bars, dominant, SPEC_FQ002.underlying)
        return latest_fq002_signal(bars, dominant, nxt, SPEC_FQ002).contract
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
