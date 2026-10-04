from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "origins_warsaw.json"

# Keep the original three values valid for old sessions/tests even if the catalog
# has not been generated yet.
LEGACY_ORIGINS = {
    "Warsaw Central": (52.2297, 21.0122),
    "Old Town": (52.2497, 21.0122),
    "Rondo Daszynskiego": (52.2306, 20.9847),
}


def _comparable(value: str) -> str:
    polish = str.maketrans("ąćęłńóśźż", "acelnoszz")
    folded = unicodedata.normalize("NFKD", value.casefold().translate(polish))
    without_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in without_marks).split())


@lru_cache(maxsize=1)
def load_origin_rows() -> tuple[dict, ...]:
    if not DATA_PATH.exists():
        return ()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rows = payload.get("origins", [])
    if not isinstance(rows, list):
        raise RuntimeError("Invalid origins_warsaw.json: origins must be a list")
    return tuple(row for row in rows if isinstance(row, dict))


@lru_cache(maxsize=1)
def origin_lookup() -> dict[str, tuple[float, float]]:
    lookup: dict[str, tuple[float, float]] = {}
    for key, coords in LEGACY_ORIGINS.items():
        lookup[key] = coords
        lookup[_comparable(key)] = coords
    for row in load_origin_rows():
        try:
            coords = (float(row["lat"]), float(row["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        for key in (row.get("id"), row.get("label")):
            if isinstance(key, str) and key.strip():
                clean = key.strip()
                lookup[clean] = coords
                lookup[_comparable(clean)] = coords
    return lookup


def resolve_origin(value: str) -> tuple[float, float]:
    key = value.strip()
    lookup = origin_lookup()
    coords = lookup.get(key) or lookup.get(_comparable(key))
    if coords is None:
        raise ValueError(f"Unknown start location: {value}")
    return coords


def public_origin_payload() -> dict:
    rows = list(load_origin_rows())
    districts: dict[str, int] = {}
    for row in rows:
        district = str(row.get("district", "Other"))
        districts[district] = districts.get(district, 0) + 1
    return {
        "city": "Warsaw",
        "count": len(rows),
        "districts": districts,
        "origins": [
            {
                "id": row.get("id"),
                "label": row.get("label"),
                "district": row.get("district"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
            }
            for row in rows
        ],
    }
