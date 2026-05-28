"""Skill catalog loader.

The catalog is a JSON file today; later it can be sourced from a GitHub
manifest with the same shape — only this loader would change.
"""
import functools
import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "skills" / "catalog.json"


@functools.lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    with _CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def catalog_by_key() -> dict[str, dict]:
    return {s["key"]: s for s in load_catalog()}


def valid_key(key: str) -> bool:
    return key in catalog_by_key()
