from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OUTPUT = Path(r"D:\Unstuck\data\origins_warsaw.json")


SEEDS: dict[str, list[str]] = {
    "Śródmieście": ["Warszawa Centralna", "Metro Centrum", "Metro Świętokrzyska", "Rondo ONZ", "Nowy Świat-Uniwersytet", "Plac Zbawiciela", "Plac Konstytucji", "Plac Trzech Krzyży", "Hala Mirowska", "Metro Politechnika", "Metro Centrum Nauki Kopernik", "Powiśle PKP", "Plac Bankowy", "Krucza / Hoża", "Marszałkowska / Wilcza"],
    "Mokotów": ["Metro Pole Mokotowskie", "Metro Racławicka", "Metro Wierzbno", "Metro Wilanowska", "Metro Służew", "Westfield Mokotów", "Domaniewska / Postępu", "Królikarnia", "Sadyba Best Mall", "Stegny", "Sielce", "Czerniakowska / Bartycka"],
    "Wola": ["Metro Rondo Daszyńskiego", "Metro Płocka", "Metro Młynów", "Metro Księcia Janusza", "Warsaw Spire", "Wola Park", "Fort Wola", "Koło", "Moczydło", "Rondo Kercelak", "Muzeum Powstania Warszawskiego"],
    "Ochota": ["Plac Narutowicza", "Warszawa Zachodnia", "Blue City", "Park Szczęśliwicki", "Hala Banacha", "Plac Zawiszy", "Filtry", "Grójecka / Bitwy Warszawskiej 1920 r."],
    "Żoliborz": ["Metro Plac Wilsona", "Metro Marymont", "Plac Inwalidów", "Westfield Arkadia", "Sady Żoliborskie", "Cytadela Warszawska", "Potok / Gwiaździsta"],
    "Bielany": ["Metro Młociny", "Metro Wawrzyszew", "Metro Stare Bielany", "Metro Słodowiec", "AWF Warszawa", "Galeria Młociny", "Chomiczówka", "Huta Warszawa", "Plac Konfederacji", "Radiowo"],
    "Bemowo": ["Metro Bemowo", "Metro Ulrychów", "Fort Bema", "Bemowo Lotnisko", "Boernerowo", "Chrzanów Bemowo", "Lazurowa / Górczewska", "Hala Wola", "Jelonki"],
    "Ursus": ["PKP Warszawa Ursus", "PKP Warszawa Ursus Niedźwiadek", "Skorosze", "Czechowice Ursus", "Factory Ursus", "Plac Czerwca 1976 roku"],
    "Włochy": ["Lotnisko Chopina", "PKP Warszawa Włochy", "PKP Warszawa Rakowiec", "Okęcie", "Stare Włochy", "Nowe Włochy", "Salomea"],
    "Ursynów": ["Metro Kabaty", "Metro Natolin", "Metro Imielin", "Metro Stokłosy", "Metro Ursynów", "SGGW", "Kopa Cwila", "Las Kabacki", "Ursynów Północny", "Pyry", "Jeziorki Południowe", "Dąbrówka Ursynowska"],
    "Wilanów": ["Miasteczko Wilanów", "Pałac w Wilanowie", "Royal Wilanów", "Świątynia Opatrzności Bożej", "Zawady", "Plac Vogla", "Powsin", "Kępa Zawadowska"],
    "Praga-Północ": ["Metro Dworzec Wileński", "Metro Szwedzka", "Centrum Praskie Koneser", "Ulica Ząbkowska", "Plac Hallera", "Warszawskie Zoo", "Nowa Praga", "Szmulowizna"],
    "Praga-Południe": ["Rondo Wiatraczna", "Saska Kępa", "Ulica Francuska", "Plac Szembeka", "Promenada Warszawa", "Stadion Narodowy", "Kamionek", "Grochów", "Gocław", "Gocławek", "Ostrobramska / Fieldorfa", "Olszynka Grochowska"],
    "Targówek": ["Metro Trocka", "Metro Targówek Mieszkaniowy", "Metro Zacisze", "Metro Kondratowicza", "Metro Bródno", "Atrium Targówek", "Factory Annopol", "Bródno", "Elsnerów", "Utrata Targówek"],
    "Białołęka": ["Galeria Północna", "Tarchomin", "Nowodwory", "Żerań", "PKP Warszawa Płudy", "PKP Warszawa Choszczówka", "Białołęka Dworska", "Kobiałka", "Henryków Białołęka", "Dąbrówka Szlachecka", "Marcelin Białołęka", "Modlińska / Światowida"],
    "Rembertów": ["PKP Warszawa Rembertów", "Akademia Sztuki Wojennej", "Stary Rembertów", "Nowy Rembertów", "Kawęczyn-Wygoda", "Poligon Rembertów"],
    "Wawer": ["PKP Warszawa Wawer", "PKP Warszawa Anin", "PKP Warszawa Międzylesie", "PKP Warszawa Radość", "PKP Warszawa Falenica", "PKP Warszawa Miedzeszyn", "Marysin Wawerski", "Zerzeń", "Las Wawerski", "Aleksandrów Wawer", "Nadwiśle", "Międzylesie Centrum Zdrowia Dziecka"],
    "Wesoła": ["PKP Warszawa Wesoła", "Stara Miłosna", "Zielona-Grzybowa", "Wola Grzybowska", "Groszówka Wesoła", "Plac Wojska Polskiego Wesoła", "Wesoła Centrum"],
}


def slug(value: str) -> str:
    table = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    normalized = value.translate(table).lower()
    chars = [ch if ch.isalnum() else "-" for ch in normalized]
    return "-".join(part for part in "".join(chars).split("-") if part)


def geocode(query: str) -> dict | None:
    params = urlencode({"format": "jsonv2", "limit": 1, "countrycodes": "pl", "q": query})
    req = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "UnstuckHackathon/0.1 origins-catalog local-build"},
    )
    with urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload[0] if payload else None


def save(rows: list[dict], failures: list[dict]) -> None:
    OUTPUT.write_text(json.dumps({
        "city": "Warsaw",
        "generated_at": "2026-10-04",
        "note": "Curated recognizable start points geocoded once from OpenStreetMap Nominatim; no runtime geocoding dependency.",
        "origins": rows,
        "failures": failures,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    existing = {}
    if OUTPUT.exists():
        existing = {row["id"]: row for row in json.loads(OUTPUT.read_text(encoding="utf-8")).get("origins", [])}
    rows: list[dict] = []
    failures: list[dict] = []
    total = sum(len(v) for v in SEEDS.values())
    done = 0
    for district, labels in SEEDS.items():
        for label in labels:
            done += 1
            oid = f"warsaw:{slug(district)}:{slug(label)}"
            if oid in existing:
                rows.append(existing[oid])
                print(f"[{done}/{total}] cached {district} / {label}", flush=True)
                continue
            result = None
            used_query = ""
            for query in (f"{label}, {district}, Warszawa, Polska", f"{label}, Warszawa, Polska"):
                used_query = query
                try:
                    result = geocode(query)
                except Exception as exc:
                    print(f"[{done}/{total}] ERROR {label}: {exc}", flush=True)
                time.sleep(1.05)
                if result:
                    break
            if not result:
                failures.append({"district": district, "label": label})
                print(f"[{done}/{total}] MISS {district} / {label}", flush=True)
                save(rows, failures)
                continue
            rows.append({
                "id": oid,
                "label": label,
                "district": district,
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": result.get("display_name", ""),
                "source": "OpenStreetMap Nominatim",
                "source_url": "https://nominatim.openstreetmap.org/",
                "checked_at": "2026-10-04",
                "query": used_query,
            })
            save(rows, failures)
            print(f"[{done}/{total}] OK {district} / {label}", flush=True)
    rows.sort(key=lambda row: (row["district"], row["label"]))
    save(rows, failures)
    print(f"DONE origins={len(rows)} failures={len(failures)} -> {OUTPUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
