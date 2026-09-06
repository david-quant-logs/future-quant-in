"""Map lab contract codes (M2501) to CTP (m2501.DCE)."""

from __future__ import annotations

import re

DCE_PRODUCTS = {"C": "c", "M": "m", "CS": "cs"}
CZCE_PRODUCTS = {"MA": "MA", "TA": "TA", "RM": "RM"}


class SymbolError(ValueError):
    pass


def to_ctp_symbol(contract: str) -> tuple[str, str]:
    """Return (ctp_symbol, exchange_name) e.g. ('m2501', 'DCE')."""
    text = str(contract).split(".")[0].upper()
    match = re.match(r"^([A-Z]+)(\d{3,4})$", text)
    if not match:
        raise SymbolError(f"无法解析合约 {contract!r}")
    product, digits = match.group(1), match.group(2)
    if product in DCE_PRODUCTS:
        if len(digits) != 4:
            raise SymbolError(f"大商所合约应为 4 位年月：{contract}")
        return f"{DCE_PRODUCTS[product]}{digits}", "DCE"
    if product in CZCE_PRODUCTS:
        # CZCE: TA605 = 2026-05. Lab codes are TA2605 → drop the millenium digit.
        if len(digits) == 4:
            digits = digits[1:]
        return f"{CZCE_PRODUCTS[product]}{digits}", "CZCE"
    raise SymbolError(f"未配置品种 {product} 的 CTP 代码")


def from_ctp_symbol(symbol: str, exchange: str = "DCE") -> str:
    """Inverse of to_ctp_symbol for DCE/CZCE lab codes we actually trade."""
    text = str(symbol).split(".")[0]
    exch = str(exchange).upper().replace("EXCHANGE.", "")
    if exch in {"DCE", "XDCE"}:
        return text.upper()
    if exch in {"CZCE", "XZCE"}:
        match = re.match(r"^([A-Za-z]+)(\d{3})$", text)
        if match:
            product, yym = match.group(1).upper(), match.group(2)
            return f"{product}2{yym}"
        return text.upper()
    return text.upper()
