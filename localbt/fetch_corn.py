"""Compatibility wrapper. New code should import localbt.fetch."""

from localbt.fetch import build_dominant_map, load_or_fetch_corn

__all__ = ["build_dominant_map", "load_or_fetch_corn"]
