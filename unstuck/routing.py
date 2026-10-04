from __future__ import annotations

import json
import math
import threading
import time
from collections import OrderedDict
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .transit import get_transit_index


VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
CLIENT_ID = "github.com/MeowRona/Unstuck"


def _decode_valhalla_polyline(value: str, precision: int = 6) -> list[list[float]]:
    coords: list[list[float]] = []
    index = lat = lon = 0
    factor = 10**precision
    while index < len(value):
        result = shift = 0
        while True:
            byte = ord(value[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = shift = 0
        while True:
            byte = ord(value[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lon += ~(result >> 1) if result & 1 else result >> 1
        coords.append([lat / factor, lon / factor])
    return coords


class PedestrianRouter:
    def __init__(self, *, max_cache: int = 128):
        self._cache: OrderedDict[tuple[float, float, float, float], dict] = OrderedDict()
        self._lock = threading.Lock()
        self.max_cache = max_cache

    @staticmethod
    def _key(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float, float, float]:
        return tuple(round(x, 5) for x in (*start, *end))  # type: ignore[return-value]

    def route(self, start: tuple[float, float], end: tuple[float, float]) -> dict:
        key = self._key(start, end)
        with self._lock:
            cached = self._cache.get(key)
            if cached:
                self._cache.move_to_end(key)
                return cached
        payload = {
            "locations": [
                {"lat": start[0], "lon": start[1]},
                {"lat": end[0], "lon": end[1]},
            ],
            "costing": "pedestrian",
            "units": "kilometers",
            "directions_options": {"units": "kilometers"},
        }
        url = VALHALLA_URL + "?" + urlencode({"json": json.dumps(payload, separators=(",", ":"))})
        request = Request(
            url,
            headers={
                "User-Agent": "UnstuckHackathon/0.1",
                "X-Client-Id": CLIENT_ID,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=8) as response:
                body = json.loads(response.read(2_000_000).decode("utf-8"))
            leg = body["trip"]["legs"][0]
            summary = body["trip"]["summary"]
            result = {
                "mode": "walk",
                "duration_minutes": max(1, math.ceil(float(summary["time"]) / 60)),
                "distance_km": round(float(summary["length"]), 2),
                "geometry": _decode_valhalla_polyline(leg["shape"]),
                "maneuvers": [
                    {
                        "instruction": row.get("instruction", ""),
                        "length_km": row.get("length"),
                        "time_seconds": row.get("time"),
                    }
                    for row in leg.get("maneuvers", [])[:40]
                ],
                "source": {
                    "name": "Valhalla pedestrian routing / OpenStreetMap",
                    "url": "https://valhalla.openstreetmap.de",
                    "attribution": "© OpenStreetMap contributors",
                    "realtime": False,
                },
            }
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("WALK_ROUTING_UNAVAILABLE") from exc
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_cache:
                self._cache.popitem(last=False)
        return result


_pedestrian_router = PedestrianRouter()


def route_walk(start: tuple[float, float], end: tuple[float, float]) -> dict:
    return _pedestrian_router.route(start, end)


def route_transit(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    service_date: date,
    departure_time: str,
) -> dict:
    router = get_transit_index()
    result = router.route(
        origin=start,
        destination=end,
        service_date=service_date,
        departure_time=departure_time,
    )
    if not result:
        raise RuntimeError("TRANSIT_ROUTE_NOT_FOUND")
    # Replace only the access/egress geometry with actual street routing when available.
    for leg in result["legs"]:
        if leg.get("type") != "walk" or leg.get("role") not in {"access", "egress"}:
            continue
        geometry = leg.get("geometry") or []
        if len(geometry) < 2:
            continue
        a = tuple(geometry[0])
        b = tuple(geometry[-1])
        try:
            walk = route_walk(a, b)  # cache keeps repeat selections cheap
        except RuntimeError:
            continue
        leg["geometry"] = walk["geometry"]
        leg["duration_minutes"] = walk["duration_minutes"]
        leg["distance_km"] = walk["distance_km"]
        leg["geometry_source"] = "Valhalla / OpenStreetMap"
    return result
