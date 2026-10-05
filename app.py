from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from unstuck.engine import UnstuckEngine
from unstuck.geocoding import address_index, geocoder, street_index
from unstuck.models import Place, SearchBrief, SearchState
from unstuck.origins import public_origin_payload
from unstuck.providers import FixtureTasteProvider, NoTasteProvider, QlooTransport, RealQlooProvider
from unstuck.routing import route_transit, route_walk


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"


def google_place_media(place_id: str, allowed_ids: set[str]) -> dict:
    """Fetch transient Google Places presentation data without persisting it."""
    if place_id not in allowed_ids:
        raise ValueError("Unknown Google place ID")
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    enabled = os.environ.get("GOOGLE_PLACES_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    maps_uri = (
        "https://www.google.com/maps/search/?api=1"
        f"&query={quote(place_id)}&query_place_id={quote(place_id)}"
    )
    if not enabled:
        return {
            "available": False,
            "reason": "GOOGLE_PLACES_DISABLED",
            "google_maps_uri": maps_uri,
        }
    if not key:
        return {
            "available": False,
            "reason": "GOOGLE_PLACES_API_KEY is not set",
            "google_maps_uri": maps_uri,
        }

    detail_url = f"https://places.googleapis.com/v1/places/{quote(place_id)}"
    request = Request(
        detail_url,
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "rating,userRatingCount,photos,googleMapsUri",
            "User-Agent": "Unstuck/0.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            details = json.loads(response.read(512_000).decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GOOGLE_PLACES_HTTP_{exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("GOOGLE_PLACES_UNAVAILABLE") from exc

    photo_payload = None
    photos = details.get("photos") or []
    if photos:
        photo = photos[0]
        photo_name = str(photo.get("name", "")).strip()
        if photo_name:
            media_url = (
                f"https://places.googleapis.com/v1/{quote(photo_name, safe='/')}/media"
                "?maxWidthPx=900&skipHttpRedirect=true"
            )
            media_request = Request(
                media_url,
                headers={"X-Goog-Api-Key": key, "User-Agent": "Unstuck/0.1"},
                method="GET",
            )
            try:
                with urlopen(media_request, timeout=5) as response:
                    media = json.loads(response.read(128_000).decode("utf-8"))
                if media.get("photoUri"):
                    photo_payload = {
                        "uri": media["photoUri"],
                        "author_attributions": photo.get("authorAttributions") or [],
                    }
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                photo_payload = None

    return {
        "available": True,
        "google_maps_uri": details.get("googleMapsUri") or maps_uri,
        "rating": details.get("rating"),
        "user_rating_count": details.get("userRatingCount"),
        "photo": photo_payload,
    }


def load_places(path: Path) -> list[Place]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Place.from_dict(row) for row in payload["places"]]


def build_engine(mode: str, catalog: str = "real") -> UnstuckEngine:
    if catalog not in {"real", "fixture"}:
        raise ValueError("catalog must be real or fixture")
    if mode == "live" and catalog != "real":
        raise ValueError("live Qloo mode requires the real catalog")
    places_path = DATA / ("places_warsaw.json" if catalog == "real" else "places_fixture.json")
    if not places_path.exists():
        raise RuntimeError("BLOCKED_NO_REAL_CATALOG" if catalog == "real" else "MISSING_FIXTURE_CATALOG")
    places = load_places(places_path)
    if mode == "live":
        provider = RealQlooProvider(QlooTransport())
    elif mode == "baseline":
        provider = NoTasteProvider()
    else:
        provider = FixtureTasteProvider(DATA / "taste_fixtures.json")
    engine = UnstuckEngine(places, provider)
    engine.catalog_mode = catalog
    return engine


class AppState:
    def __init__(self, engine: UnstuckEngine):
        self.engine = engine
        self.sessions: dict[str, SearchState] = {}
        self.lock = threading.Lock()

    def create(self, brief: SearchBrief) -> tuple[str, dict]:
        session_id = uuid.uuid4().hex
        state = SearchState(brief=brief)
        with self.lock:
            self.sessions[session_id] = state
        return session_id, self.engine.search(state)

    def get(self, session_id: str) -> SearchState:
        with self.lock:
            state = self.sessions.get(session_id)
        if state is None:
            raise KeyError("Unknown session")
        return state


class Handler(BaseHTTPRequestHandler):
    app_state: AppState
    server_version = "Unstuck/0.1"

    def log_message(self, format: str, *args) -> None:
        print(f"[http] {self.address_string()} {format % args}")

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 256_000:
            raise ValueError("Request too large")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/version":
            self._json(
                200,
                {
                    "git_commit": os.environ.get("RENDER_GIT_COMMIT", "local"),
                    "git_branch": os.environ.get("RENDER_GIT_BRANCH", "local"),
                    "git_repo": os.environ.get("RENDER_GIT_REPO_SLUG", "MeowRona/Unstuck"),
                    "render_service_id": os.environ.get("RENDER_SERVICE_ID", "local"),
                },
            )
            return
        if path == "/api/health":
            origins = public_origin_payload()
            self._json(
                200,
                {
                    "ok": True,
                    "provider_mode": self.app_state.engine.taste_provider.mode,
                    "catalog_mode": getattr(self.app_state.engine, "catalog_mode", "unknown"),
                    "qloo_api_key_present": bool(os.environ.get("QLOO_API_KEY")),
                    "google_places_api_key_present": bool(os.environ.get("GOOGLE_PLACES_API_KEY")),
                    "google_places_enabled": os.environ.get("GOOGLE_PLACES_ENABLED", "false").strip().lower()
                    in {"1", "true", "yes", "on"},
                    "origin_count": origins["count"],
                    "street_count": street_index.count,
                    "address_count": address_index.count,
                    "transit_index_present": (DATA / "transit_warsaw.json.gz").exists(),
                },
            )
            return
        if path == "/api/origins":
            self._json(200, public_origin_payload())
            return
        if path == "/api/streets":
            query = str((parse_qs(parsed.query).get("q") or [""])[0]).strip()
            self._json(
                200,
                {
                    "query": query,
                    "suggestions": street_index.suggest(query),
                    "count": street_index.count,
                    "source": "OpenStreetMap local street index",
                },
            )
            return
        if path == "/api/place-media":
            query = parse_qs(parsed.query)
            place_id = str((query.get("place_id") or [""])[0]).strip()
            if not place_id:
                self._json(400, {"error": "place_id is required"})
                return
            allowed_ids = {
                place.google_place_id
                for place in self.app_state.engine.places
                if place.google_place_id
            }
            try:
                self._json(200, google_place_media(place_id, allowed_ids))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(503, {"error": str(exc)})
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/":
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        try:
            target.relative_to(STATIC.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/geocode":
                address = str(payload.get("address", "")).strip()
                self._json(200, geocoder.geocode(address))
                return
            if path == "/api/route":
                try:
                    start = (float(payload["origin_lat"]), float(payload["origin_lon"]))
                    end = (float(payload["destination_lat"]), float(payload["destination_lon"]))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("Route requires numeric origin/destination coordinates") from exc
                for lat, lon in (start, end):
                    if not (52.05 <= lat <= 52.40 and 20.75 <= lon <= 21.35):
                        raise ValueError("Route coordinates must stay inside the Warsaw pilot area")
                mode = str(payload.get("mode", "transit")).strip().lower()
                if mode == "walk":
                    result = route_walk(start, end)
                elif mode == "transit":
                    from datetime import date as _date

                    try:
                        service_date = _date.fromisoformat(str(payload.get("date", "")))
                    except ValueError as exc:
                        raise ValueError("date must use YYYY-MM-DD") from exc
                    departure_time = str(payload.get("start_time", "")).strip()
                    if len(departure_time) != 5 or departure_time[2] != ":":
                        raise ValueError("start_time must use HH:MM")
                    result = route_transit(
                        start,
                        end,
                        service_date=service_date,
                        departure_time=departure_time,
                    )
                else:
                    raise ValueError("mode must be walk or transit")
                self._json(200, result)
                return
            if path == "/api/search":
                brief = SearchBrief.from_payload(payload)
                session_id, result = self.app_state.create(brief)
                self._json(200, {"session_id": session_id, **result})
                return
            if path == "/api/reject":
                state = self.app_state.get(str(payload.get("session_id", "")))
                place_id = str(payload.get("place_id", "")).strip()
                if not place_id:
                    raise ValueError("place_id is required")
                state.reject(place_id)
                self._json(200, {"session_id": payload["session_id"], **self.app_state.engine.search(state)})
                return
            if path == "/api/update":
                state = self.app_state.get(str(payload.get("session_id", "")))
                patch = payload.get("patch")
                if not isinstance(patch, dict):
                    raise ValueError("patch must be an object")
                state.update_brief(patch)
                self._json(200, {"session_id": payload["session_id"], **self.app_state.engine.search(state)})
                return
            self._json(404, {"error": "Not found"})
        except KeyError as exc:
            self._json(404, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Internal error: {type(exc).__name__}"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Unstuck local web app")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8817")))
    parser.add_argument("--mode", choices=("fixture", "baseline", "live"), default=os.environ.get("UNSTUCK_MODE", "fixture"))
    parser.add_argument("--catalog", choices=("real", "fixture"), default=os.environ.get("UNSTUCK_CATALOG", "real"))
    args = parser.parse_args()
    try:
        engine = build_engine(args.mode, args.catalog)
    except RuntimeError as exc:
        if str(exc) == "BLOCKED_NO_API_KEY":
            print("BLOCKED_NO_API_KEY: set QLOO_API_KEY to run live mode.")
            return 2
        raise
    Handler.app_state = AppState(engine)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Unstuck running at http://{args.host}:{args.port} ({args.mode} mode)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
