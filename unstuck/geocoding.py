from __future__ import annotations

import gzip
import json
import math
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
STREETS_PATH = ROOT / "data" / "streets_warsaw.json"
ADDRESSES_PATH = ROOT / "data" / "addresses_warsaw.json.gz"
WARSAW_BOUNDS = (52.05, 20.75, 52.40, 21.35)


def _fold(value: str) -> str:
    polish = str.maketrans("ąćęłńóśźż", "acelnoszz")
    text = unicodedata.normalize("NFKD", value.casefold().translate(polish))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text if not unicodedata.combining(ch)).split())


class StreetIndex:
    def __init__(self, path: Path = STREETS_PATH):
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.source = payload.get("source")
        self.checked_at = payload.get("checked_at")
        self.rows = [(name, _fold(name)) for name in payload.get("streets", []) if isinstance(name, str)]

    @property
    def count(self) -> int:
        return len(self.rows)

    def suggest(self, query: str, limit: int = 12) -> list[str]:
        needle = _fold(query)
        if len(needle) < 2:
            return []
        scored: list[tuple[int, int, str]] = []
        for name, folded in self.rows:
            if folded.startswith(needle):
                score = 0
            elif any(part.startswith(needle) for part in folded.split()):
                score = 1
            elif needle in folded:
                score = 2
            else:
                continue
            scored.append((score, len(name), name))
        scored.sort(key=lambda row: (row[0], row[1], row[2].casefold()))
        return [row[2] for row in scored[:limit]]


class AddressIndex:
    def __init__(self, path: Path = ADDRESSES_PATH):
        self.path = path
        self.source = "OpenStreetMap"
        self.source_url = "https://www.openstreetmap.org/copyright"
        self.checked_at = None
        self.rows: dict[str, list] = {}
        self.points: list[tuple[float, float, str, str]] = []
        if not path.exists():
            return
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.source = str(payload.get("source") or self.source)
        self.source_url = str(payload.get("source_url") or self.source_url)
        self.checked_at = payload.get("checked_at")
        rows = payload.get("addresses") or {}
        if isinstance(rows, dict):
            self.rows = rows
            for row in rows.values():
                if not isinstance(row, list) or len(row) < 4:
                    continue
                try:
                    lat, lon = float(row[2]), float(row[3])
                except (TypeError, ValueError):
                    continue
                self.points.append((lat, lon, str(row[0]), str(row[1])))

    @property
    def count(self) -> int:
        return len(self.rows)

    def nearest(self, lat: float, lon: float, *, max_distance_m: float = 250.0) -> dict | None:
        lat = float(lat)
        lon = float(lon)
        if not (
            WARSAW_BOUNDS[0] <= lat <= WARSAW_BOUNDS[2]
            and WARSAW_BOUNDS[1] <= lon <= WARSAW_BOUNDS[3]
        ):
            raise ValueError("Coordinates must stay inside the Warsaw pilot area")
        lat_scale = 111_320.0
        lon_scale = lat_scale * math.cos(math.radians(lat))
        best: tuple[float, str, str, float, float] | None = None
        for row_lat, row_lon, street, number in self.points:
            north_m = (row_lat - lat) * lat_scale
            east_m = (row_lon - lon) * lon_scale
            distance_sq = north_m * north_m + east_m * east_m
            if best is None or distance_sq < best[0]:
                best = (distance_sq, street, number, row_lat, row_lon)
        if best is None:
            return None
        distance_m = math.sqrt(best[0])
        if distance_m > max_distance_m:
            return None
        return {
            "label": f"{best[1]} {best[2]}, Warszawa",
            "lat": best[3],
            "lon": best[4],
            "distance_m": round(distance_m),
            "source": self.source,
            "source_url": self.source_url,
            "checked_at": self.checked_at,
            "local_index": True,
        }

    @staticmethod
    def _split_exact(value: str) -> tuple[str, str] | None:
        clean = " ".join(str(value).strip().split())
        if not clean:
            return None
        local = clean.split(",", 1)[0].strip()
        matches = list(re.finditer(r"(?<!\w)(\d+[\w/-]*)(?!\w)", local, flags=re.UNICODE))
        if not matches:
            return None
        match = matches[-1]
        street = local[: match.start()].strip(" ,")
        number = match.group(1).strip()
        if not street or not number:
            return None
        street = re.sub(r"^(?:ul\.?\s+)", "", street, flags=re.IGNORECASE)
        return street, number

    def lookup(self, value: str) -> dict | None:
        parsed = self._split_exact(value)
        if not parsed:
            return None
        street, number = parsed
        row = self.rows.get(f"{_fold(street)}|{_fold(number)}")
        if not row or len(row) < 4:
            return None
        canonical_street, canonical_number, lat, lon = row[:4]
        return {
            "label": f"{canonical_street} {canonical_number}, Warszawa",
            "lat": float(lat),
            "lon": float(lon),
            "type": "address",
            "source": self.source,
            "source_url": self.source_url,
            "checked_at": self.checked_at,
            "local_index": True,
        }


class NominatimGeocoder:
    def __init__(self, *, max_cache: int = 512):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._last_request = 0.0
        self.max_cache = max_cache

    def geocode(self, address: str) -> dict:
        clean = " ".join(str(address).strip().split())
        if len(clean) < 3 or len(clean) > 180:
            raise ValueError("Enter a valid Warsaw street/address")
        local = address_index.lookup(clean)
        if local is not None:
            return local
        key = _fold(clean)
        with self._lock:
            cached = self._cache.get(key)
            if cached:
                self._cache.move_to_end(key)
                return cached
            # Public Nominatim policy: absolute max 1 request/sec. We also cache results.
            wait = 1.05 - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            requested_number_match = re.search(r"\b\d+[A-Za-z]?\b", clean)
            requested_number = requested_number_match.group(0).casefold() if requested_number_match else None
            params = {
                "format": "jsonv2",
                "limit": 5,
                "countrycodes": "pl",
                "addressdetails": 1,
                "layer": "address",
                "bounded": 1,
                "viewbox": "20.75,52.40,21.35,52.05",
            }
            if requested_number:
                params.update({"street": clean, "city": "Warszawa"})
            else:
                query = clean if "warszaw" in key else f"{clean}, Warszawa, Polska"
                params["q"] = query
            request = Request(
                "https://nominatim.openstreetmap.org/search?" + urlencode(params),
                headers={
                    "User-Agent": "UnstuckHackathon/0.1 (https://github.com/MeowRona/Unstuck)",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=8) as response:
                    rows = json.loads(response.read(512_000).decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise RuntimeError("GEOCODER_UNAVAILABLE") from exc
            finally:
                self._last_request = time.monotonic()
            result = None
            for row in rows if isinstance(rows, list) else []:
                try:
                    lat, lon = float(row["lat"]), float(row["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if WARSAW_BOUNDS[0] <= lat <= WARSAW_BOUNDS[2] and WARSAW_BOUNDS[1] <= lon <= WARSAW_BOUNDS[3]:
                    result_address = row.get("address") or {}
                    if requested_number:
                        returned_number = str(result_address.get("house_number") or "").casefold()
                        if returned_number != requested_number:
                            continue
                    result = {
                        "label": row.get("display_name") or clean,
                        "lat": lat,
                        "lon": lon,
                        "type": row.get("type"),
                        "source": "OpenStreetMap Nominatim",
                        "source_url": "https://www.openstreetmap.org/copyright",
                    }
                    break
            if result is None:
                if requested_number:
                    raise ValueError(
                        "That exact house number is not available in OpenStreetMap for the Warsaw pilot. "
                        "Choose another exact address or a saved landmark; Unstuck will not substitute a street midpoint."
                    )
                raise ValueError("Address was not found inside the Warsaw pilot area")
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_cache:
                self._cache.popitem(last=False)
            return result


street_index = StreetIndex()
address_index = AddressIndex()
geocoder = NominatimGeocoder()
