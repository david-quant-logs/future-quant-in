from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd

from localbt import PRODUCT_MONTHS

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
_FOLDER = {"C": "corn", "M": "m", "CS": "cs", "MA": "ma", "TA": "ta"}
_COLS = ("date", "product", "contract", "open", "high", "low", "close", "volume", "open_interest")
_MAIN = {"C": "C0", "M": "M0", "CS": "CS0", "MA": "MA0", "TA": "TA0"}


def contract_re(product: str) -> re.Pattern[str]:
    if product == "C":
        return re.compile(r"^C\d{4}$")
    if product == "M":
        return re.compile(r"^M\d{4}$")
    return re.compile(rf"^{re.escape(product)}\d{{4}}$")


def product_symbols(product: str, start_year: int, end_year: int) -> list[str]:
    months = PRODUCT_MONTHS[product]
    out: list[str] = []
    for year in range(start_year, end_year + 1):
        yy = year % 100
        for month in months:
            out.append(f"{product}{yy:02d}{month:02d}")
    return out


def load_or_fetch(
    product: str,
    *,
    start: str = "2016-01-01",
    end: str | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    folder = RAW_DIR / _FOLDER.get(product, product.lower())
    folder.mkdir(parents=True, exist_ok=True)
    cache_path = folder / "contracts.csv"
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    if cache and cache_path.exists():
        df = pd.read_csv(cache_path, parse_dates=["date"])
        if "product" not in df.columns:
            df["product"] = product
        clipped = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        if not clipped.empty:
            return clipped.reset_index(drop=True)

    try:
        raw = _fetch_sina_contracts(product, start, end)
    except RuntimeError:
        raw = _fetch_main_continuous(product, start, end)
    if raw.empty:
        raise RuntimeError(f"No {product} futures bars from Sina.")
    if cache:
        raw.to_csv(cache_path, index=False)
    return raw[(raw["date"] >= start) & (raw["date"] <= end)].reset_index(drop=True)


def load_or_fetch_universe(
    products: tuple[str, ...] | list[str],
    *,
    start: str = "2016-01-01",
    end: str | None = None,
    cache: bool = True,
) -> dict[str, pd.DataFrame]:
    return {p: load_or_fetch(p, start=start, end=end, cache=cache) for p in products}


def load_or_fetch_corn(**kwargs) -> pd.DataFrame:
    return load_or_fetch("C", **kwargs)


def _fetch_sina_contracts(product: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    symbols = product_symbols(product, start_ts.year - 1, end_ts.year + 1)
    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for i, symbol in enumerate(symbols):
        try:
            hist = ak.futures_zh_daily_sina(symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
            continue
        parsed = _normalize_sina(hist, product, symbol)
        if parsed.empty:
            continue
        frames.append(parsed)
        if i % 8 == 7:
            time.sleep(0.2)

    if not frames:
        raise RuntimeError(f"{product} Sina fetch failed. " + " | ".join(errors[:8]))
    out = pd.concat(frames, ignore_index=True)
    out = out[(out["date"] >= start_ts) & (out["date"] <= end_ts)]
    out = out.drop_duplicates(["date", "contract"]).sort_values(["date", "contract"])
    return out.reset_index(drop=True)


def _fetch_main_continuous(product: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    symbol = _MAIN[product]
    hist = ak.futures_main_sina(symbol=symbol, start_date=_compact(start), end_date=_compact(end))
    parsed = _normalize_sina(hist, product, symbol)
    parsed["contract"] = symbol
    return parsed


def _compact(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _normalize_sina(df: pd.DataFrame, product: str, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_COLS)
    rename = {
        "日期": "date",
        "开盘价": "open",
        "最高价": "high",
        "最低价": "low",
        "收盘价": "close",
        "成交量": "volume",
        "持仓量": "open_interest",
        "date": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "open_interest": "open_interest",
        "hold": "open_interest",
        "持仓": "open_interest",
    }
    work = df.rename(columns={c: rename.get(c, c) for c in df.columns}).copy()
    if "date" not in work.columns:
        return pd.DataFrame(columns=_COLS)
    if "open_interest" not in work.columns:
        work["open_interest"] = 0
    keep = [c for c in ("date", "open", "high", "low", "close", "volume", "open_interest") if c in work.columns]
    work = work[keep]
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume", "open_interest"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["date", "open", "close"])
    work = work[(work["open"] > 0) & (work["close"] > 0)]
    work["contract"] = symbol.upper()
    work["product"] = product
    work["volume"] = work["volume"].fillna(0)
    work["open_interest"] = work["open_interest"].fillna(0)
    return work.loc[:, list(_COLS)]


def build_dominant_map(bars: pd.DataFrame, product: str = "C") -> pd.Series:
    eligible = bars[bars["contract"].str.match(contract_re(product), na=False)].copy()
    if eligible.empty and (bars["contract"] == _MAIN.get(product, "")).any():
        picked = bars[bars["contract"] == _MAIN[product]].drop_duplicates("date")
        return picked.set_index("date")["contract"].sort_index()
    eligible = eligible[eligible["volume"].fillna(0) > 0]
    if eligible.empty:
        raise RuntimeError(f"No volume-positive {product} contracts to pick a dominant.")
    ranked = eligible.sort_values(
        ["date", "open_interest", "volume"],
        ascending=[True, False, False],
    )
    picked = ranked.drop_duplicates("date", keep="first")
    return picked.set_index("date")["contract"].sort_index()


def contract_month_index(product: str, contract: str) -> int | None:
    """YYMM code → year*12+month. M2501 → 2025*12+1."""
    text = str(contract).upper()
    prefix = product.upper()
    if not text.startswith(prefix):
        return None
    rest = text[len(prefix) :]
    if len(rest) != 4 or not rest.isdigit():
        return None
    yy, mm = int(rest[:2]), int(rest[2:])
    if mm < 1 or mm > 12:
        return None
    return (2000 + yy) * 12 + mm


def delivery_mid(month_index: int) -> pd.Timestamp:
    year, month = divmod(int(month_index), 12)
    if month == 0:
        year -= 1
        month = 12
    return pd.Timestamp(year=year, month=month, day=15)


def build_next_map(bars: pd.DataFrame, dominant: pd.Series, product: str) -> pd.Series:
    """Later-dated contract with the highest open interest (next liquid deferred)."""
    eligible = bars[bars["contract"].str.match(contract_re(product), na=False)].copy()
    if eligible.empty:
        return pd.Series(dtype=object, name="next")
    eligible["ym"] = eligible["contract"].map(lambda c: contract_month_index(product, str(c)))
    eligible = eligible.dropna(subset=["ym"])
    rows: dict[pd.Timestamp, str] = {}
    for day, grp in eligible.groupby("date"):
        if day not in dominant.index:
            continue
        near = str(dominant.loc[day])
        near_ym = contract_month_index(product, near)
        if near_ym is None:
            continue
        later = grp[grp["ym"] > near_ym]
        if later.empty:
            continue
        later = later.sort_values(["open_interest", "volume"], ascending=[False, False])
        rows[pd.Timestamp(day)] = str(later.iloc[0]["contract"])
    return pd.Series(rows, name="next").sort_index()


def annualized_roll(
    near_close: float,
    far_close: float,
    near_contract: str,
    far_contract: str,
    product: str,
) -> float | None:
    """(F_near - F_far) / F_far * 365/days. Positive = backwardation."""
    if far_close <= 0 or near_close <= 0:
        return None
    near_ym = contract_month_index(product, near_contract)
    far_ym = contract_month_index(product, far_contract)
    if near_ym is None or far_ym is None:
        return None
    days = (delivery_mid(far_ym) - delivery_mid(near_ym)).days
    if days <= 0:
        return None
    return (near_close - far_close) / far_close * (365.0 / days)
