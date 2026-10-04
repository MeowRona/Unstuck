from __future__ import annotations

import bisect
import gzip
import heapq
import json
import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "data" / "transit_warsaw.json.gz"


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _walk_seconds(distance_km: float) -> int:
    # Intentionally conservative for access to a scheduled departure.
    return max(60, int(math.ceil(distance_km / 4.0 * 3600 + 45)))


def _time_seconds(text: str) -> int:
    hour, minute = map(int, text.split(":"))
    return hour * 3600 + minute * 60


def _clock(seconds: int) -> str:
    seconds %= 86400
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def _decode_polyline(value: str, precision: int = 5) -> list[list[float]]:
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


def _service_type(day: date) -> str:
    weekday = day.weekday()
    if weekday <= 3:
        return "mon_thu"
    if weekday == 4:
        return "fri"
    if weekday == 5:
        return "sat"
    return "sun"


@dataclass(frozen=True)
class TransitState:
    stop_id: str
    boardings: int


class TransitIndex:
    def __init__(self, path: Path = DEFAULT_INDEX):
        if not path.exists():
            raise RuntimeError("TRANSIT_INDEX_MISSING")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            self.data: dict[str, Any] = json.load(handle)
        self.path = path
        self.stops: dict[str, dict[str, Any]] = self.data["stops"]
        self.routes: dict[str, dict[str, Any]] = self.data["routes"]
        self.patterns: list[dict[str, Any]] = self.data["patterns"]
        self.shapes: dict[str, str] = self.data.get("shapes", {})
        self.stop_to_patterns: dict[str, list[tuple[int, int]]] = {}
        self.service_patterns: dict[str, set[int]] = {}
        for pattern_index, pattern in enumerate(self.patterns):
            self.service_patterns.setdefault(pattern["service"], set()).add(pattern_index)
            for stop_index, stop_id in enumerate(pattern["stops"]):
                self.stop_to_patterns.setdefault(stop_id, []).append((pattern_index, stop_index))
        self.transfer_neighbors = self._build_transfer_neighbors()
        self._shape_cache: dict[str, list[list[float]]] = {}

    @property
    def generated_at(self) -> str:
        return str(self.data.get("generated_at", "unknown"))

    def _build_transfer_neighbors(self) -> dict[str, list[tuple[str, int]]]:
        groups: dict[str, list[str]] = {}
        for stop_id, stop in self.stops.items():
            key = " ".join(str(stop.get("name", "")).casefold().split())
            if key:
                groups.setdefault(key, []).append(stop_id)
        result: dict[str, list[tuple[str, int]]] = {}
        for stop_ids in groups.values():
            if len(stop_ids) < 2:
                continue
            for source in stop_ids:
                a = self.stops[source]
                neighbors: list[tuple[str, int]] = []
                for target in stop_ids:
                    if target == source:
                        continue
                    b = self.stops[target]
                    distance = _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                    if distance <= 0.55:
                        neighbors.append((target, max(45, int(distance / 4.0 * 3600 + 30))))
                if neighbors:
                    result[source] = neighbors
        return result

    def nearest_stops(
        self,
        lat: float,
        lon: float,
        *,
        limit: int = 10,
        radius_km: float = 1.2,
    ) -> list[tuple[str, float]]:
        rows: list[tuple[float, str]] = []
        for stop_id, stop in self.stops.items():
            distance = _haversine_km(lat, lon, stop["lat"], stop["lon"])
            if distance <= radius_km:
                rows.append((distance, stop_id))
        rows.sort()
        return [(stop_id, distance) for distance, stop_id in rows[:limit]]

    @staticmethod
    def _next_start(pattern: dict[str, Any], stop_index: int, ready: int) -> int | None:
        offset = int(pattern["dep"][stop_index])
        required_start = ready - offset
        starts = pattern.get("starts") or []
        best: int | None = None
        if starts:
            pos = bisect.bisect_left(starts, required_start)
            if pos < len(starts):
                best = int(starts[pos])
        for window in pattern.get("freq") or []:
            begin, end, headway = map(int, window)
            if required_start <= begin:
                candidate = begin
            else:
                steps = math.ceil((required_start - begin) / headway)
                candidate = begin + steps * headway
            if candidate <= end and (best is None or candidate < best):
                best = candidate
        return best

    def _shape_segment(self, pattern: dict[str, Any], board_index: int, alight_index: int) -> list[list[float]]:
        shape_id = str(pattern.get("shape") or "")
        encoded = self.shapes.get(shape_id)
        if not encoded:
            return [
                [self.stops[pattern["stops"][board_index]]["lat"], self.stops[pattern["stops"][board_index]]["lon"]],
                [self.stops[pattern["stops"][alight_index]]["lat"], self.stops[pattern["stops"][alight_index]]["lon"]],
            ]
        points = self._shape_cache.get(shape_id)
        if points is None:
            points = _decode_polyline(encoded)
            self._shape_cache[shape_id] = points
            if len(self._shape_cache) > 128:
                self._shape_cache.pop(next(iter(self._shape_cache)))
        start_stop = self.stops[pattern["stops"][board_index]]
        end_stop = self.stops[pattern["stops"][alight_index]]
        start_at = min(
            range(len(points)),
            key=lambda idx: _haversine_km(start_stop["lat"], start_stop["lon"], points[idx][0], points[idx][1]),
        )
        end_at = min(
            range(len(points)),
            key=lambda idx: _haversine_km(end_stop["lat"], end_stop["lon"], points[idx][0], points[idx][1]),
        )
        if start_at <= end_at:
            segment = points[start_at : end_at + 1]
        else:
            segment = list(reversed(points[end_at : start_at + 1]))
        if len(segment) > 260:
            stride = max(1, len(segment) // 220)
            segment = segment[::stride] + ([segment[-1]] if segment[-1] != segment[::stride][-1] else [])
        return segment

    def route(
        self,
        *,
        origin: tuple[float, float],
        destination: tuple[float, float],
        service_date: date,
        departure_time: str,
        max_boardings: int = 3,
    ) -> dict[str, Any] | None:
        service = _service_type(service_date)
        active_patterns = self.service_patterns.get(service, set())
        if not active_patterns:
            return None
        departure_sec = _time_seconds(departure_time)
        access = self.nearest_stops(*origin, limit=10, radius_km=1.2)
        egress = self.nearest_stops(*destination, limit=12, radius_km=1.35)
        if not access or not egress:
            return None
        egress_walk = {stop_id: _walk_seconds(distance) for stop_id, distance in egress}
        heap: list[tuple[int, int, str]] = []
        best: dict[TransitState, int] = {}
        prev: dict[TransitState, dict[str, Any]] = {}
        for stop_id, distance in access:
            state = TransitState(stop_id, 0)
            arrival = departure_sec + _walk_seconds(distance)
            if arrival < best.get(state, 10**12):
                best[state] = arrival
                prev[state] = {
                    "kind": "access",
                    "origin": origin,
                    "to_stop": stop_id,
                    "seconds": arrival - departure_sec,
                }
                heapq.heappush(heap, (arrival, 0, stop_id))

        best_destination: tuple[int, TransitState] | None = None
        processed: dict[TransitState, int] = {}
        while heap:
            at, boardings, stop_id = heapq.heappop(heap)
            state = TransitState(stop_id, boardings)
            if at != best.get(state):
                continue
            if processed.get(state, 10**12) <= at:
                continue
            processed[state] = at
            if best_destination and at >= best_destination[0]:
                continue
            if stop_id in egress_walk:
                total = at + egress_walk[stop_id]
                if best_destination is None or total < best_destination[0]:
                    best_destination = (total, state)

            for neighbor, walk_seconds in self.transfer_neighbors.get(stop_id, ()):
                next_state = TransitState(neighbor, boardings)
                next_at = at + walk_seconds
                if next_at < best.get(next_state, 10**12):
                    best[next_state] = next_at
                    prev[next_state] = {
                        "kind": "transfer",
                        "from": state,
                        "from_stop": stop_id,
                        "to_stop": neighbor,
                        "seconds": walk_seconds,
                    }
                    heapq.heappush(heap, (next_at, boardings, neighbor))

            if boardings >= max_boardings:
                continue
            for pattern_index, stop_index in self.stop_to_patterns.get(stop_id, ()):
                if pattern_index not in active_patterns:
                    continue
                pattern = self.patterns[pattern_index]
                trip_start = self._next_start(pattern, stop_index, at)
                if trip_start is None:
                    continue
                board_depart = trip_start + int(pattern["dep"][stop_index])
                # Avoid very long waits that are not useful for an outing planner.
                if board_depart - at > 45 * 60:
                    continue
                for alight_index in range(stop_index + 1, len(pattern["stops"])):
                    next_stop = pattern["stops"][alight_index]
                    next_at = trip_start + int(pattern["arr"][alight_index])
                    next_state = TransitState(next_stop, boardings + 1)
                    if next_at >= best.get(next_state, 10**12):
                        continue
                    best[next_state] = next_at
                    prev[next_state] = {
                        "kind": "transit",
                        "from": state,
                        "pattern": pattern_index,
                        "board_index": stop_index,
                        "alight_index": alight_index,
                        "trip_start": trip_start,
                        "departure": board_depart,
                        "arrival": next_at,
                    }
                    heapq.heappush(heap, (next_at, boardings + 1, next_stop))

        if best_destination is None:
            return None
        destination_at, state = best_destination
        chain: list[dict[str, Any]] = []
        cursor = state
        while True:
            step = prev.get(cursor)
            if not step:
                break
            chain.append(step)
            if step["kind"] == "access":
                break
            cursor = step["from"]
        chain.reverse()

        legs: list[dict[str, Any]] = []
        for step in chain:
            if step["kind"] == "access":
                stop = self.stops[step["to_stop"]]
                legs.append(
                    {
                        "type": "walk",
                        "role": "access",
                        "from": "Start",
                        "to": stop["name"],
                        "duration_minutes": max(1, round(step["seconds"] / 60)),
                        "geometry": [list(origin), [stop["lat"], stop["lon"]]],
                    }
                )
            elif step["kind"] == "transfer":
                a = self.stops[step["from_stop"]]
                b = self.stops[step["to_stop"]]
                same_named_stop = " ".join(str(a.get("name", "")).casefold().split()) == " ".join(
                    str(b.get("name", "")).casefold().split()
                )
                legs.append(
                    {
                        "type": "transfer" if same_named_stop else "walk",
                        "role": "transfer",
                        "from": a["name"],
                        "to": b["name"],
                        "duration_minutes": max(1, round(step["seconds"] / 60)),
                        "geometry": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]],
                    }
                )
            else:
                pattern = self.patterns[step["pattern"]]
                board_index = step["board_index"]
                alight_index = step["alight_index"]
                from_stop = self.stops[pattern["stops"][board_index]]
                to_stop = self.stops[pattern["stops"][alight_index]]
                route = self.routes.get(pattern["route"], {})
                intermediate = [
                    self.stops[stop_id]["name"]
                    for stop_id in pattern["stops"][board_index + 1 : alight_index]
                ]
                legs.append(
                    {
                        "type": "transit",
                        "route_id": pattern["route"],
                        "route": route.get("short") or pattern["route"],
                        "route_long_name": route.get("long") or "",
                        "route_type": route.get("type"),
                        "color": route.get("color") or "275DE8",
                        "headsign": pattern.get("headsign") or "",
                        "from": from_stop["name"],
                        "to": to_stop["name"],
                        "departure": _clock(step["departure"]),
                        "arrival": _clock(step["arrival"]),
                        "stop_count": alight_index - board_index,
                        "intermediate_stops": intermediate[:16],
                        "geometry": self._shape_segment(pattern, board_index, alight_index),
                    }
                )

        final_stop = self.stops[state.stop_id]
        final_walk_seconds = egress_walk[state.stop_id]
        legs.append(
            {
                "type": "walk",
                "role": "egress",
                "from": final_stop["name"],
                "to": "Destination",
                "duration_minutes": max(1, round(final_walk_seconds / 60)),
                "geometry": [[final_stop["lat"], final_stop["lon"]], list(destination)],
            }
        )
        boardings = [leg for leg in legs if leg["type"] == "transit"]
        return {
            "mode": "transit",
            "scheduled": True,
            "realtime": False,
            "service_type": service,
            "departure": _clock(departure_sec),
            "arrival": _clock(destination_at),
            "duration_minutes": max(1, math.ceil((destination_at - departure_sec) / 60)),
            "transfers": max(0, len(boardings) - 1),
            "summary": " + ".join(leg["route"] for leg in boardings) if boardings else "Walk",
            "legs": legs,
            "source": {
                "name": "Warsaw GTFS schedule",
                "generated_at": self.generated_at,
                "url": self.data.get("source_url"),
                "attribution": self.data.get("attribution"),
            },
        }


@lru_cache(maxsize=1)
def get_transit_index() -> TransitIndex:
    return TransitIndex()
