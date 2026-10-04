from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "places_warsaw.json"
OVERPASS_QUERY = (
    '[out:json][timeout:180];'
    'area(3600336074)->.a;'
    'nwr(area.a)["amenity"="restaurant"];'
    'out center tags;'
)
OVERPASS_ENDPOINTS = (
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
)
DAY_INDEX = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}


def fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def fetch_overpass() -> dict:
    body = urlencode({"data": OVERPASS_QUERY}).encode()
    headers = {
        "User-Agent": "UnstuckHackathon/0.1 (https://github.com/MeowRona/Unstuck)",
        "Accept": "application/json",
    }
    failures: list[str] = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            request = Request(endpoint, data=body, headers=headers, method="POST")
            with urlopen(request, timeout=240) as response:
                payload = json.load(response)
            if payload.get("elements"):
                return payload
            failures.append(f"{endpoint}: empty response")
        except Exception as exc:  # noqa: BLE001 - CLI should try the next mirror.
            failures.append(f"{endpoint}: {type(exc).__name__}: {exc}")
    raise RuntimeError("All Overpass mirrors failed: " + " | ".join(failures))


def element_point(element: dict) -> tuple[float, float] | None:
    if element.get("lat") is not None and element.get("lon") is not None:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if center.get("lat") is not None and center.get("lon") is not None:
        return float(center["lat"]), float(center["lon"])
    return None


def osm_url(element: dict) -> str:
    return f"https://www.openstreetmap.org/{element.get('type', 'node')}/{element['id']}"


def address_from_tags(tags: dict) -> str:
    street = str(tags.get("addr:street") or "").strip()
    house = str(tags.get("addr:housenumber") or "").strip()
    place = " ".join(x for x in (street, house) if x).strip()
    return f"{place}, Warsaw" if place else "Warsaw"


def fallback_name(element: dict, tags: dict) -> str:
    for key in ("name", "name:pl", "brand", "operator"):
        value = str(tags.get(key) or "").strip()
        if value:
            return value
    street = str(tags.get("addr:street") or "").strip()
    house = str(tags.get("addr:housenumber") or "").strip()
    if street or house:
        return "Restaurant · " + " ".join(x for x in (street, house) if x)
    return f"Restaurant · OSM {element.get('type', 'feature')} {element['id']}"


def expand_days(token: str) -> list[int] | None:
    token = token.strip()
    if not token:
        return list(range(7))
    days: list[int] = []
    for part in token.split(","):
        part = part.strip()
        if part in DAY_INDEX:
            days.append(DAY_INDEX[part])
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            if start not in DAY_INDEX or end not in DAY_INDEX:
                return None
            cursor = DAY_INDEX[start]
            days.append(cursor)
            while cursor != DAY_INDEX[end]:
                cursor = (cursor + 1) % 7
                days.append(cursor)
            continue
        return None
    return sorted(set(days))


def parse_opening_hours(raw: str) -> dict[str, list[list[str]]] | None:
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return None
    if text == "24/7":
        return {str(day): [["00:00", "24:00"]] for day in range(7)}
    if any(token in text for token in ("PH", "sunrise", "sunset", "week", "open", "closed")):
        return None

    result: dict[str, list[list[str]]] = {}
    for segment in text.split(";"):
        segment = segment.strip()
        if not segment or " off" in segment or segment.endswith(" off"):
            continue
        match = re.fullmatch(
            r"(?:(?P<days>(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?(?:,(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?)*)\s+)?(?P<times>\d{1,2}:\d{2}-\d{1,2}:\d{2}(?:,\d{1,2}:\d{2}-\d{1,2}:\d{2})*)",
            segment,
        )
        if not match:
            return None
        days = expand_days(match.group("days") or "")
        if days is None:
            return None
        windows: list[list[str]] = []
        for window in match.group("times").split(","):
            start, end = window.split("-", 1)
            try:
                sh, sm = map(int, start.split(":"))
                eh, em = map(int, end.split(":"))
            except ValueError:
                return None
            if not (0 <= sh <= 24 and 0 <= eh <= 24 and 0 <= sm < 60 and 0 <= em < 60):
                return None
            if sh == 24 and sm != 0 or eh == 24 and em != 0:
                return None
            windows.append([f"{sh:02d}:{sm:02d}", f"{eh:02d}:{em:02d}"])
        for day in days:
            result.setdefault(str(day), []).extend(windows)
    return result or None


def heuristic_taste_tags(tags: dict) -> list[str]:
    haystack = " ".join(
        str(tags.get(key) or "")
        for key in ("cuisine", "name", "description", "brand", "operator")
    ).casefold()
    result: list[str] = []

    def add(*values: str) -> None:
        for value in values:
            if value not in result:
                result.append(value)

    if any(x in haystack for x in ("italian", "polish", "bistro", "pizza", "mediterranean")):
        add("cozy")
    if any(x in haystack for x in ("italian", "french", "wine", "mediterranean")):
        add("romantic")
    if any(x in haystack for x in ("japanese", "sushi", "ramen", "fusion", "steak", "fine_dining")):
        add("stylish")
    if any(x in haystack for x in ("japanese", "sushi", "ramen")):
        add("minimal")
    if any(x in haystack for x in ("vegan", "vegetarian", "fusion", "ethiopian", "georgian")):
        add("artsy")
    if any(x in haystack for x in ("steak", "grill", "barbecue", "bbq")):
        add("moody")
    opening = str(tags.get("opening_hours") or "")
    if any(x in opening for x in ("24:00", "01:00", "02:00", "03:00", "04:00")):
        add("night")
    return result


def restaurant_row(element: dict, snapshot_date: str, existing: dict | None) -> dict | None:
    point = element_point(element)
    if point is None:
        return None
    lat, lon = point
    if not (52.05 <= lat <= 52.40 and 20.75 <= lon <= 21.35):
        return None

    element_id = f"warsaw:osm:{element.get('type', 'node')}:{element['id']}"
    tags = element.get("tags") or {}
    source = osm_url(element)
    if existing:
        row = dict(existing)
        row["lat"] = lat
        row["lon"] = lon
        row["location_source_url"] = source
        return row

    hours_raw = str(tags.get("opening_hours") or "").strip()
    hours = parse_opening_hours(hours_raw)
    website = str(tags.get("website") or tags.get("contact:website") or "").strip()
    cuisine = str(tags.get("cuisine") or "").replace(";", ", ").strip()
    checked_hours = str(tags.get("check_date:opening_hours") or tags.get("check_date") or snapshot_date).strip()
    return {
        "id": element_id,
        "name": fallback_name(element, tags),
        "city": "Warsaw",
        "category": "restaurant",
        "serves_meal": True,
        "address": address_from_tags(tags),
        "lat": lat,
        "lon": lon,
        "location_source_url": source,
        "location_checked_at": snapshot_date,
        "price": {
            "min": None,
            "max": None,
            "currency": "PLN",
            "status": "unknown",
            "source_url": website or source,
            "checked_at": snapshot_date,
            "basis": "Price not verified; hard-budget fit requires checking.",
        },
        "hours": hours or {},
        "date_exceptions": {},
        "hours_status": "estimated" if hours else "unknown",
        "hours_source_url": source if hours_raw else None,
        "hours_checked_at": checked_hours if hours_raw else None,
        "ambience": [cuisine] if cuisine else [],
        "taste_tags": heuristic_taste_tags(tags),
        "qloo_entity_id": None,
        "google_place_id": None,
        "source_note": (
            f"OSM restaurant discovery from Overpass snapshot {snapshot_date}. "
            "Price is unknown unless separately curated. Any taste_tags are deterministic fixture heuristics only, not Qloo output."
        ),
        "demo_fixture": False,
    }


def curated_address_key(row: dict) -> tuple[str, str] | None:
    address = str(row.get("address") or "").split(",", 1)[0].strip()
    match = re.match(r"^(.*?)[ ,]+(\d+[\w/.-]*)$", address)
    if not match:
        return None
    return fold(match.group(1)), fold(match.group(2))


def osm_address_key(tags: dict) -> tuple[str, str] | None:
    street = fold(str(tags.get("addr:street") or ""))
    house = fold(str(tags.get("addr:housenumber") or ""))
    return (street, house) if street and house else None


def build(payload: dict, current_catalog: dict, build_date: str) -> dict:
    snapshot = str((payload.get("osm3s") or {}).get("timestamp_osm_base") or "")[:10] or build_date
    current_places = current_catalog.get("places") or []
    existing_osm = {row["id"]: row for row in current_places if str(row.get("id", "")).startswith("warsaw:osm:")}
    curated = [row for row in current_places if not str(row.get("id", "")).startswith("warsaw:osm:")]
    curated_restaurants = [row for row in curated if row.get("category") == "restaurant"]
    curated_names = {fold(str(row.get("name") or "")) for row in curated_restaurants}
    curated_addresses = {key for row in curated_restaurants if (key := curated_address_key(row))}

    imported: list[dict] = []
    skipped_curated_duplicates = 0
    no_point = 0
    for element in payload.get("elements") or []:
        if (element.get("tags") or {}).get("amenity") != "restaurant":
            continue
        tags = element.get("tags") or {}
        name_fold = fold(fallback_name(element, tags))
        addr_key = osm_address_key(tags)
        if name_fold in curated_names or (addr_key and addr_key in curated_addresses):
            skipped_curated_duplicates += 1
            continue
        element_id = f"warsaw:osm:{element.get('type', 'node')}:{element['id']}"
        row = restaurant_row(element, snapshot, existing_osm.get(element_id))
        if row is None:
            no_point += 1
            continue
        imported.append(row)

    imported.sort(key=lambda row: (fold(row["name"]), row["id"]))
    places = curated + imported
    restaurant_count = sum(1 for row in places if row.get("category") == "restaurant")
    result = {
        "catalog": {
            "city": "Warsaw",
            "checked_at": build_date,
            "scope": (
                "Warsaw pilot catalog. Restaurant discovery includes every OSM amenity=restaurant feature returned by the recorded Overpass snapshot, "
                "with separately curated records taking precedence over duplicate OSM entries."
            ),
            "location_method": (
                f"Restaurant discovery generated from OpenStreetMap Overpass snapshot {snapshot}; curated venue facts keep their per-field sources."
            ),
            "taste_note": (
                "taste_tags on non-Qloo discovery rows are deterministic fixture heuristics used only when live Qloo is inactive. "
                "They are not venue claims and are not Qloo output."
            ),
            "osm_restaurant_snapshot": snapshot,
            "osm_restaurant_feature_count": sum(
                1 for element in payload.get("elements") or [] if (element.get("tags") or {}).get("amenity") == "restaurant"
            ),
            "osm_restaurant_imported_count": len(imported),
            "curated_restaurant_count": len(curated_restaurants),
            "curated_duplicate_replacements": skipped_curated_duplicates,
        },
        "places": places,
        "catalog_note": (
            f"Warsaw pilot: {len(places)} places, including {restaurant_count} restaurants. "
            f"OSM discovery snapshot contains {len(imported) + skipped_curated_duplicates} usable restaurant features; "
            "uncurated prices are unknown and never treated as hard-budget confirmed."
        ),
    }
    if no_point:
        result["catalog"]["osm_restaurant_missing_coordinates"] = no_point
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the complete Warsaw OSM restaurant discovery layer for Unstuck.")
    parser.add_argument("--input", type=Path, help="Saved Overpass JSON; omitted = fetch from mirrors.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--checked-at", default=date.today().isoformat())
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8")) if args.input else fetch_overpass()
    current = json.loads(args.catalog.read_text(encoding="utf-8"))
    result = build(payload, current, args.checked_at)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = result["catalog"]
    print(
        f"Wrote {len(result['places'])} places / "
        f"{sum(1 for row in result['places'] if row.get('category') == 'restaurant')} restaurants; "
        f"OSM features={meta['osm_restaurant_feature_count']} imported={meta['osm_restaurant_imported_count']} "
        f"curated replacements={meta['curated_duplicate_replacements']} snapshot={meta['osm_restaurant_snapshot']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
