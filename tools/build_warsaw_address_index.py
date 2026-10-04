from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "addresses_warsaw.json.gz"
OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
OVERPASS_QUERY = (
    '[out:json][timeout:180];'
    'area(3600336074)->.a;'
    '(nwr(area.a)["addr:housenumber"]["addr:street"];);'
    'out center tags;'
)


def fold(value: str) -> str:
    polish = str.maketrans("ąćęłńóśźż", "acelnoszz")
    text = unicodedata.normalize("NFKD", str(value).casefold().translate(polish))
    return " ".join(
        "".join(
            ch if ch.isalnum() else " "
            for ch in text
            if not unicodedata.combining(ch)
        ).split()
    )


def fetch() -> dict:
    request = Request(
        OVERPASS_URL + "?" + urlencode({"data": OVERPASS_QUERY}),
        headers={
            "User-Agent": "UnstuckHackathon/0.1 (https://github.com/MeowRona/Unstuck)",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=240) as response:
        return json.loads(response.read().decode("utf-8"))


def build(payload: dict) -> dict:
    rows: dict[str, list] = {}
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        street = str(tags.get("addr:street") or "").strip()
        numbers = str(tags.get("addr:housenumber") or "").strip()
        if not street or not numbers:
            continue
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        if not (52.05 <= lat <= 52.40 and 20.75 <= lon <= 21.35):
            continue
        for number in re.split(r"\s*;\s*", numbers):
            number = number.strip()
            if not number:
                continue
            key = f"{fold(street)}|{fold(number)}"
            rows.setdefault(
                key,
                [street, number, round(lat, 7), round(lon, 7)],
            )
    return {
        "city": "Warsaw",
        "source": "OpenStreetMap Overpass",
        "source_url": "https://www.openstreetmap.org/copyright",
        "count": len(rows),
        "addresses": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Unstuck's compact Warsaw exact-address index from OpenStreetMap."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Optional saved Overpass JSON. If omitted, fetch current Warsaw address data.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--checked-at",
        default="",
        help="Optional YYYY-MM-DD source check date stored in the generated metadata.",
    )
    args = parser.parse_args()

    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        payload = fetch()
    result = build(payload)
    result["checked_at"] = args.checked_at or date.today().isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(result, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {result['count']:,} exact addresses to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
