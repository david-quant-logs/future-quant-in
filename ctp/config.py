"""CTP SimNow settings. Never print passwords. Live fronts are refused by default."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

SIMNOW_HOSTS = frozenset(
    {
        "182.254.243.31",
        "180.168.146.187",
        "218.202.237.33",
    }
)
_FRONT = re.compile(r"^tcp://([^:/]+):(\d+)$", re.I)

SECRETS_PATH = Path.home() / ".cursor" / "secrets" / "ctp_simnow.json"


@dataclass(frozen=True)
class CtpConfig:
    environment: str
    userid: str
    password: str
    brokerid: str
    appid: str
    auth_code: str
    td_front: str
    md_front: str
    counter_env: str


class CtpConfigError(RuntimeError):
    pass


def front_host(front: str) -> str:
    match = _FRONT.match(front.strip())
    if not match:
        raise CtpConfigError(f"前置地址必须是 tcp://host:port，收到 {front!r}")
    return match.group(1)


def assert_sim_fronts(td_front: str, md_front: str, environment: str) -> None:
    env = environment.strip().lower()
    if env == "live":
        raise CtpConfigError("拒绝实盘柜台。CTP 通道只接 SimNow / 期货公司仿真。")
    if env not in {"simnow", "broker_sim"}:
        raise CtpConfigError("environment 只能是 simnow 或 broker_sim")
    td_host = front_host(td_front)
    md_host = front_host(md_front)
    if env == "simnow":
        if td_host not in SIMNOW_HOSTS or md_host not in SIMNOW_HOSTS:
            raise CtpConfigError(
                f"SimNow 前置不在允许名单：td={td_host} md={md_host}。"
                "请对照 simnow.com.cn 当前地址，或把 environment 改成 broker_sim（仍是仿真）。"
            )


def load_ctp_config(path: Path | None = None) -> CtpConfig:
    path = path or _default_path()
    if not path.exists():
        raise CtpConfigError(
            f"找不到 CTP 配置 {path}。复制 ctp/config.example.json 到该路径并填 SimNow 账号。"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = CtpConfig(
        environment=str(raw.get("environment", "simnow")),
        userid=str(raw.get("userid", "")).strip(),
        password=str(raw.get("password", "")),
        brokerid=str(raw.get("brokerid", "9999")).strip(),
        appid=str(raw.get("appid", "simnow_client_test")).strip(),
        auth_code=str(raw.get("auth_code", "0000000000000000")).strip(),
        td_front=str(raw.get("td_front", "")).strip(),
        md_front=str(raw.get("md_front", "")).strip(),
        counter_env=str(raw.get("counter_env", "实盘")).strip(),
    )
    if not cfg.userid or cfg.userid.startswith("你的") or not cfg.password or cfg.password.startswith("你的"):
        raise CtpConfigError("请填写真实的 SimNow userid / password。")
    assert_sim_fronts(cfg.td_front, cfg.md_front, cfg.environment)
    return cfg


def vnpy_setting(cfg: CtpConfig) -> dict:
    return {
        "用户名": cfg.userid,
        "密码": cfg.password,
        "经纪商代码": cfg.brokerid,
        "交易服务器": cfg.td_front,
        "行情服务器": cfg.md_front,
        "产品名称": cfg.appid,
        "授权编码": cfg.auth_code,
        "柜台环境": cfg.counter_env,
    }


def _default_path() -> Path:
    override = os.environ.get("CTP_CONFIG")
    if override:
        return Path(override)
    return SECRETS_PATH
