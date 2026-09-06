from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctp.config import CtpConfigError, assert_sim_fronts, load_ctp_config, vnpy_setting
from ctp.intent import CtpFillState, plan_fq002
from ctp.symbols import SymbolError, from_ctp_symbol, to_ctp_symbol
from localbt import SPEC_FQ002, FQ002Spec
from localbt.engine import latest_fq002_signal
from localbt.fetch import build_dominant_map, build_next_map

from tests.test_carry import _two_contracts


def test_dce_and_czce_symbol_map():
    assert to_ctp_symbol("M2501") == ("m2501", "DCE")
    assert to_ctp_symbol("M2501.XDCE") == ("m2501", "DCE")
    assert to_ctp_symbol("C2601") == ("c2601", "DCE")
    assert to_ctp_symbol("TA2605") == ("TA605", "CZCE")
    assert from_ctp_symbol("m2501", "DCE") == "M2501"
    assert from_ctp_symbol("TA605", "CZCE") == "TA2605"


def test_unknown_product_rejected():
    with pytest.raises(SymbolError):
        to_ctp_symbol("IF2509")


def test_simnow_fronts_ok_live_rejected():
    assert_sim_fronts(
        "tcp://182.254.243.31:30001",
        "tcp://182.254.243.31:30011",
        "simnow",
    )
    with pytest.raises(CtpConfigError, match="实盘"):
        assert_sim_fronts("tcp://1.2.3.4:10000", "tcp://1.2.3.4:10001", "live")
    with pytest.raises(CtpConfigError, match="允许名单"):
        assert_sim_fronts("tcp://1.2.3.4:30001", "tcp://1.2.3.4:30011", "simnow")


def test_load_config_from_tmp(tmp_path: Path, monkeypatch):
    path = tmp_path / "ctp.json"
    path.write_text(
        json.dumps(
            {
                "environment": "simnow",
                "userid": "123456",
                "password": "secret",
                "brokerid": "9999",
                "appid": "simnow_client_test",
                "auth_code": "0000000000000000",
                "td_front": "tcp://182.254.243.31:30001",
                "md_front": "tcp://182.254.243.31:30011",
                "counter_env": "实盘",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CTP_CONFIG", str(path))
    cfg = load_ctp_config()
    assert cfg.userid == "123456"
    setting = vnpy_setting(cfg)
    assert setting["用户名"] == "123456"
    assert "密码" in setting
    assert setting["柜台环境"] == "实盘"


def test_placeholder_config_rejected(tmp_path: Path, monkeypatch):
    path = tmp_path / "ctp.json"
    path.write_text(Path("ctp/config.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("CTP_CONFIG", str(path))
    with pytest.raises(CtpConfigError, match="userid"):
        load_ctp_config()


def test_example_and_repo_have_no_live_secrets():
    example = json.loads(Path("ctp/config.example.json").read_text(encoding="utf-8"))
    assert str(example["userid"]).startswith("你的")
    assert str(example["password"]).startswith("你的")
    assert not Path("ctp/config.local.json").exists()
    assert not Path("ctp/config.json").exists()


def test_latest_signal_uses_last_bar_as_t1():
    bars, dominant, nxt = _two_contracts(near_px=3100, far_px=3000)
    signal = latest_fq002_signal(bars, dominant, nxt, SPEC_FQ002)
    assert signal.contract == "M2005"
    assert signal.far_contract == "M2007"
    assert signal.roll is not None and signal.roll > 0
    assert signal.target == 1
    assert signal.last_close == 3100


def test_intent_opens_one_lot_then_flattens_on_contango():
    bars, dominant, nxt = _two_contracts(near_px=3100, far_px=3000, n=5)
    long_sig = latest_fq002_signal(bars, dominant, nxt, SPEC_FQ002)
    opened = plan_fq002(long_sig, CtpFillState(), SPEC_FQ002)
    assert opened.target == 1
    assert len(opened.orders) == 1
    assert opened.orders[0].offset == "open"
    assert opened.orders[0].volume == 1
    assert opened.next_state.lots == 1

    bars2, dominant2, nxt2 = _two_contracts(near_px=3000, far_px=3200, n=5)
    flat_sig = latest_fq002_signal(bars2, dominant2, nxt2, SPEC_FQ002)
    held = CtpFillState(
        contract="M2005",
        direction=1,
        lots=1,
        bars_held=3,
        entry=3000,
    )
    closed = plan_fq002(flat_sig, held, SPEC_FQ002)
    assert closed.target == 0
    assert closed.allow
    assert closed.orders[0].offset == "close"
    assert closed.next_state.lots == 0


def test_v1_hold_window_blocks_early_flatten():
    bars, dominant, nxt = _two_contracts(near_px=3000, far_px=3200, n=5)
    spec = FQ002Spec(hold_bars=20, stop_frac=0.99, flatten_on_contango=False)
    sig = latest_fq002_signal(bars, dominant, nxt, spec)
    held = CtpFillState(contract="M2005", direction=1, lots=1, bars_held=3, entry=3100)
    plan = plan_fq002(sig, held, spec)
    assert not plan.allow
    assert plan.orders == ()
    assert plan.next_state.lots == 1
    assert plan.next_state.bars_held == 4
