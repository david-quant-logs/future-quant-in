"""SimNow session via openctp-ctp (has Windows Python 3.12 wheels)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ctp.config import CtpConfig
from ctp.session import AccountSnap, PositionSnap, TickSnap
from ctp.symbols import to_ctp_symbol

ROOT = Path(__file__).resolve().parents[1]
FLOW_DIR = ROOT / "data" / "processed" / "ctp_flow"


def _subscribe_md(md, symbol: str) -> None:
    """openctp SWIG: char*[] + count. Some wheels want a plain str instead of a list."""
    inst = str(symbol)
    last_exc: Exception | None = None
    for args in ((inst, 1), ([inst], 1), ((inst,), 1)):
        try:
            md.SubscribeMarketData(*args)
            return
        except TypeError as exc:
            last_exc = exc
    if last_exc is not None:
        raise last_exc


def _drop_http_proxy() -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)


def _msg(info) -> str:
    if info is None:
        return ""
    raw = getattr(info, "ErrorMsg", "") or ""
    if isinstance(raw, bytes):
        return raw.decode("gbk", errors="replace").strip()
    text = str(raw)
    try:
        return text.encode("latin1").decode("gbk").strip()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text.strip()


def _err(info) -> int:
    if info is None:
        return 0
    return int(getattr(info, "ErrorID", 0) or 0)


class OpenCtpSession:
    def __init__(self, cfg: CtpConfig):
        try:
            from openctp_ctp import mdapi, tdapi
        except ImportError as exc:
            raise RuntimeError("未安装 openctp-ctp。执行：pip install openctp-ctp") from exc
        self.cfg = cfg
        self._tdapi_mod = tdapi
        self._mdapi_mod = mdapi
        self._lock = threading.Lock()
        self._login_ok = threading.Event()
        self._md_ok = threading.Event()
        self._last_error = ""
        self._accounts: list[AccountSnap] = []
        self._positions: list[PositionSnap] = []
        self._ticks: dict[str, TickSnap] = {}
        self._td = None
        self._md = None
        self._td_spi = None
        self._md_spi = None
        self._req = 0

    def _next_req(self) -> int:
        self._req += 1
        return self._req

    def connect(self, wait_s: float = 15.0) -> None:
        _drop_http_proxy()
        td_dir = FLOW_DIR / "td"
        md_dir = FLOW_DIR / "md"
        td_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)
        for folder in (td_dir, md_dir):
            for leftover in folder.glob("*"):
                if leftover.is_file():
                    leftover.unlink(missing_ok=True)

        tdapi = self._tdapi_mod
        mdapi = self._mdapi_mod
        session = self

        class TdSpi(tdapi.CThostFtdcTraderSpi):
            def OnFrontConnected(self):
                session._last_error = "已连上交易前置，正在认证…"
                req = tdapi.CThostFtdcReqAuthenticateField()
                req.BrokerID = cfg.brokerid
                req.UserID = cfg.userid
                req.AppID = cfg.appid
                req.AuthCode = cfg.auth_code
                session._td.ReqAuthenticate(req, session._next_req())

            def OnFrontDisconnected(self, reason: int):
                session._last_error = f"交易前置断开 {reason}"
                session._login_ok.clear()

            def OnRspAuthenticate(self, field, info, req_id, last):
                if _err(info):
                    session._last_error = f"认证失败 {_err(info)} {_msg(info)}"
                    return
                session._last_error = "认证通过，正在登录…"
                req = tdapi.CThostFtdcReqUserLoginField()
                req.BrokerID = cfg.brokerid
                req.UserID = cfg.userid
                req.Password = cfg.password
                session._td.ReqUserLogin(req, session._next_req())

            def OnRspUserLogin(self, field, info, req_id, last):
                if _err(info):
                    session._last_error = f"登录失败 {_err(info)} {_msg(info)}"
                    return
                req = tdapi.CThostFtdcSettlementInfoConfirmField()
                req.BrokerID = cfg.brokerid
                req.InvestorID = cfg.userid
                session._td.ReqSettlementInfoConfirm(req, session._next_req())

            def OnRspSettlementInfoConfirm(self, field, info, req_id, last):
                if _err(info):
                    session._last_error = f"结算确认失败 {_err(info)} {_msg(info)}"
                    return
                session._login_ok.set()
                session._query_account()
                time.sleep(0.8)
                session._query_positions()

            def OnRspQryTradingAccount(self, field, info, req_id, last):
                if _err(info):
                    session._last_error = f"查资金失败 {_err(info)} {_msg(info)}"
                    return
                if field is None:
                    return
                snap = AccountSnap(
                    balance=float(getattr(field, "Balance", 0) or 0),
                    available=float(getattr(field, "Available", 0) or 0),
                    frozen=float(getattr(field, "FrozenCash", 0) or 0),
                )
                with session._lock:
                    session._accounts = [snap]

            def OnRspQryInvestorPosition(self, field, info, req_id, last):
                if _err(info) or field is None:
                    return
                vol = float(getattr(field, "Position", 0) or 0)
                if vol <= 0:
                    return
                pos = PositionSnap(
                    symbol=str(getattr(field, "InstrumentID", "") or ""),
                    exchange=str(getattr(field, "ExchangeID", "") or ""),
                    direction=str(getattr(field, "PosiDirection", "") or ""),
                    volume=vol,
                    price=float(getattr(field, "OpenCost", 0) or 0),
                    pnl=float(getattr(field, "PositionProfit", 0) or 0),
                )
                with session._lock:
                    session._positions.append(pos)

            def OnRspError(self, info, req_id, last):
                if _err(info):
                    session._last_error = f"CTP {_err(info)} {_msg(info)}"

        class MdSpi(mdapi.CThostFtdcMdSpi):
            def OnFrontConnected(self):
                req = mdapi.CThostFtdcReqUserLoginField()
                req.BrokerID = cfg.brokerid
                req.UserID = cfg.userid
                req.Password = cfg.password
                session._md.ReqUserLogin(req, session._next_req())

            def OnRspUserLogin(self, field, info, req_id, last):
                if _err(info):
                    session._last_error = session._last_error or f"行情登录失败 {_err(info)} {_msg(info)}"
                    return
                session._md_ok.set()

            def OnRtnDepthMarketData(self, tick):
                if tick is None:
                    return
                symbol = str(tick.InstrumentID)
                exch = str(getattr(tick, "ExchangeID", "") or "")
                snap = TickSnap(
                    symbol=symbol,
                    last=float(tick.LastPrice or 0),
                    bid=float(getattr(tick, "BidPrice1", 0) or 0),
                    ask=float(getattr(tick, "AskPrice1", 0) or 0),
                    volume=float(tick.Volume or 0),
                    open_interest=float(getattr(tick, "OpenInterest", 0) or 0),
                )
                with session._lock:
                    session._ticks[f"{symbol}.{exch}" if exch else symbol] = snap
                    session._ticks[symbol] = snap

        cfg = self.cfg
        self._td_spi = TdSpi()
        self._td = tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi(str(td_dir) + os.sep)
        self._td.RegisterSpi(self._td_spi)
        self._td.SubscribePrivateTopic(tdapi.THOST_TERT_QUICK)
        self._td.SubscribePublicTopic(tdapi.THOST_TERT_QUICK)
        self._td.RegisterFront(self.cfg.td_front)
        self._td.Init()

        self._md_spi = MdSpi()
        self._md = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(str(md_dir) + os.sep)
        self._md.RegisterSpi(self._md_spi)
        self._md.RegisterFront(self.cfg.md_front)
        self._md.Init()

        if not self._login_ok.wait(timeout=wait_s):
            raise RuntimeError(self._last_error or f"交易登录超时（当前 {self.cfg.td_front}）。盘后第一套会关；7x24 用 40001。")
        deadline = time.time() + min(8.0, wait_s)
        while time.time() < deadline:
            if self.accounts():
                return
            time.sleep(0.3)

    def _query_account(self) -> None:
        tdapi = self._tdapi_mod
        req = tdapi.CThostFtdcQryTradingAccountField()
        req.BrokerID = self.cfg.brokerid
        req.InvestorID = self.cfg.userid
        self._td.ReqQryTradingAccount(req, self._next_req())

    def _query_positions(self) -> None:
        with self._lock:
            self._positions = []
        tdapi = self._tdapi_mod
        req = tdapi.CThostFtdcQryInvestorPositionField()
        req.BrokerID = self.cfg.brokerid
        req.InvestorID = self.cfg.userid
        self._td.ReqQryInvestorPosition(req, self._next_req())

    def close(self) -> None:
        for api in (self._td, self._md):
            if api is None:
                continue
            try:
                api.RegisterSpi(None)
            except Exception:
                pass
            try:
                api.Release()
            except Exception:
                pass
        self._td = None
        self._md = None

    def accounts(self) -> list[AccountSnap]:
        with self._lock:
            return list(self._accounts)

    def positions(self) -> list[PositionSnap]:
        with self._lock:
            return list(self._positions)

    def subscribe_lab_contract(self, lab_contract: str) -> str:
        symbol, exch = to_ctp_symbol(lab_contract)
        vt = f"{symbol}.{exch}"
        if self._md is None:
            return vt
        self._md_ok.wait(timeout=5)
        _subscribe_md(self._md, symbol)
        return vt

    def last_tick(self, vt_symbol: str) -> TickSnap | None:
        with self._lock:
            if vt_symbol in self._ticks:
                return self._ticks[vt_symbol]
            symbol = vt_symbol.split(".")[0]
            return self._ticks.get(symbol)

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
        tdapi = self._tdapi_mod
        symbol, exch = to_ctp_symbol(lab_contract)
        req = tdapi.CThostFtdcInputOrderField()
        req.BrokerID = self.cfg.brokerid
        req.InvestorID = self.cfg.userid
        req.InstrumentID = symbol
        req.ExchangeID = exch
        req.Direction = tdapi.THOST_FTDC_D_Buy if direction == "long" else tdapi.THOST_FTDC_D_Sell
        req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open if offset == "open" else tdapi.THOST_FTDC_OF_Close
        req.CombHedgeFlag = tdapi.THOST_FTDC_HF_Speculation
        req.OrderPriceType = tdapi.THOST_FTDC_OPT_LimitPrice
        req.LimitPrice = float(price)
        req.VolumeTotalOriginal = int(volume)
        req.TimeCondition = tdapi.THOST_FTDC_TC_GFD
        req.VolumeCondition = tdapi.THOST_FTDC_VC_AV
        req.MinVolume = 1
        req.ContingentCondition = tdapi.THOST_FTDC_CC_Immediately
        req.ForceCloseReason = tdapi.THOST_FTDC_FCC_NotForceClose
        req.IsAutoSuspend = 0
        req.UserForceClose = 0
        n = self._next_req()
        req.OrderRef = str(n)
        self._td.ReqOrderInsert(req, n)
        return req.OrderRef
