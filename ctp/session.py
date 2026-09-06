"""Headless SimNow session via vn.py CTP gateway."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from ctp.config import CtpConfig, vnpy_setting
from ctp.symbols import to_ctp_symbol


class CtpNotInstalled(RuntimeError):
    pass


@dataclass
class AccountSnap:
    balance: float = 0.0
    available: float = 0.0
    frozen: float = 0.0


@dataclass
class PositionSnap:
    symbol: str
    exchange: str
    direction: str
    volume: float
    price: float
    pnl: float


@dataclass
class TickSnap:
    symbol: str
    last: float
    bid: float
    ask: float
    volume: float
    open_interest: float


def require_vnpy() -> None:
    try:
        import vnpy  # noqa: F401
        import vnpy_ctp  # noqa: F401
    except ImportError as exc:
        raise CtpNotInstalled("vn.py 不可用") from exc


def make_session(cfg: CtpConfig):
    """vn.py if installed; otherwise openctp-ctp (Python 3.12 Windows wheels)."""
    try:
        require_vnpy()
        return VnpyCtpSession(cfg)
    except CtpNotInstalled:
        try:
            from ctp.openctp import OpenCtpSession

            return OpenCtpSession(cfg)
        except Exception as exc:
            raise CtpNotInstalled(
                "未安装 CTP 绑定。Python 3.12 请执行：pip install openctp-ctp"
            ) from exc


def CtpSession(cfg: CtpConfig):
    return make_session(cfg)


def _drop_http_proxy() -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)


def _tick_snap(tick) -> TickSnap:
    return TickSnap(
        symbol=str(tick.symbol),
        last=float(tick.last_price or 0),
        bid=float(getattr(tick, "bid_price_1", 0) or 0),
        ask=float(getattr(tick, "ask_price_1", 0) or 0),
        volume=float(tick.volume or 0),
        open_interest=float(getattr(tick, "open_interest", 0) or 0),
    )


def _load_gateway():
    try:
        from vnpy_ctp import CtpGateway
    except ImportError:
        from vnpy_ctp.gateway import CtpGateway
    return CtpGateway


class VnpyCtpSession:
    def __init__(self, cfg: CtpConfig):
        require_vnpy()
        from vnpy.event import EventEngine
        from vnpy.trader.engine import MainEngine

        self.cfg = cfg
        self._event_engine = EventEngine()
        self._main = MainEngine(self._event_engine)
        self._main.add_gateway(_load_gateway())
        self._gateway_name = "CTP"

    def connect(self, wait_s: float = 12.0) -> None:
        _drop_http_proxy()
        self._main.connect(vnpy_setting(self.cfg), self._gateway_name)
        time.sleep(min(wait_s, 4.0))
        gateway = self._main.get_gateway(self._gateway_name)
        if gateway is not None:
            for name in ("query_account", "query_position"):
                fn = getattr(gateway, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.accounts():
                return
            time.sleep(0.4)

    def close(self) -> None:
        try:
            self._main.close()
        finally:
            stop = getattr(self._event_engine, "stop", None)
            if callable(stop):
                stop()

    def accounts(self) -> list[AccountSnap]:
        out = []
        for acc in self._main.get_all_accounts():
            out.append(
                AccountSnap(
                    balance=float(getattr(acc, "balance", 0) or 0),
                    available=float(getattr(acc, "available", 0) or 0),
                    frozen=float(getattr(acc, "frozen", 0) or 0),
                )
            )
        return out

    def positions(self) -> list[PositionSnap]:
        out = []
        for pos in self._main.get_all_positions():
            out.append(
                PositionSnap(
                    symbol=str(pos.symbol),
                    exchange=str(pos.exchange.value if hasattr(pos.exchange, "value") else pos.exchange),
                    direction=str(pos.direction.value if hasattr(pos.direction, "value") else pos.direction),
                    volume=float(pos.volume or 0),
                    price=float(getattr(pos, "price", 0) or 0),
                    pnl=float(getattr(pos, "pnl", 0) or 0),
                )
            )
        return out

    def subscribe_lab_contract(self, lab_contract: str) -> str:
        from vnpy.trader.constant import Exchange
        from vnpy.trader.object import SubscribeRequest

        symbol, exch = to_ctp_symbol(lab_contract)
        self._main.subscribe(
            SubscribeRequest(symbol=symbol, exchange=Exchange[exch]),
            self._gateway_name,
        )
        return f"{symbol}.{exch}"

    def last_tick(self, vt_symbol: str) -> TickSnap | None:
        tick = self._main.get_tick(vt_symbol)
        if tick is None:
            return None
        return _tick_snap(tick)

    def wait_tick(self, vt_symbol: str, timeout: float = 8.0) -> TickSnap | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            snap = self.last_tick(vt_symbol)
            if snap is not None and snap.last > 0:
                return snap
            time.sleep(0.3)
        return self.last_tick(vt_symbol)

    def send_limit(
        self, lab_contract: str, *, direction: str, offset: str, volume: int, price: float
    ) -> str:
        from vnpy.trader.constant import Direction, Exchange, Offset, OrderType
        from vnpy.trader.object import OrderRequest

        symbol, exch = to_ctp_symbol(lab_contract)
        off = Offset.OPEN if offset == "open" else Offset.CLOSE
        req = OrderRequest(
            symbol=symbol,
            exchange=Exchange[exch],
            direction=Direction.LONG if direction == "long" else Direction.SHORT,
            offset=off,
            type=OrderType.LIMIT,
            price=float(price),
            volume=int(volume),
            reference="FQ-002",
        )
        return str(self._main.send_order(req, self._gateway_name))
