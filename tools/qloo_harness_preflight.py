from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIN_NODE = (22, 19, 0)
MIN_HARNESS = (0, 1, 26)


def version_tuple(text: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    return completed.returncode, completed.stdout.strip()


def curated_rank_template() -> dict:
    payload = json.loads((ROOT / "data" / "places_warsaw.json").read_text(encoding="utf-8"))
    names = [
        row["name"]
        for row in payload.get("places", [])
        if row.get("category") == "restaurant" and not str(row.get("id", "")).startswith("warsaw:osm:")
    ][:10]
    return {
        "options": names,
        "option_type": "place",
        "signals": ["Amelie", "Radiohead"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-safe Qloo Hackathon Kit readiness check for Unstuck.")
    parser.add_argument(
        "--write-template",
        action="store_true",
        help="Write a non-secret qloo_rank input example under .cache/.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    node = shutil.which("node")
    if not node:
        failures.append("Node.js is not installed.")
    else:
        code, output = run([node, "--version"])
        detected = version_tuple(output)
        print(f"Node: {output or 'unknown'}")
        if code or detected < MIN_NODE:
            failures.append("Qloo harness requires Node.js 22.19.0 or newer.")

    qloo = shutil.which("qloo")
    if not qloo:
        failures.append("qloo harness is not installed globally. Install with: npm install --global @qloo/qloo-harness")
    else:
        code, output = run([qloo, "--version"])
        detected = version_tuple(output)
        print(f"Qloo harness: {output or 'unknown'}")
        if code or detected < MIN_HARNESS:
            failures.append("Qloo harness must be 0.1.26 or newer.")
        else:
            # Both commands are documented as non-mutating/offline-safe readiness checks.
            status_code, status = run([qloo, "setup", "--status", "--json"])
            doctor_code, doctor = run([qloo, "doctor"])
            print("setup --status:")
            print(status or f"exit {status_code}")
            print("doctor:")
            print(doctor or f"exit {doctor_code}")

    if args.write_template:
        target = ROOT / ".cache" / "qloo_rank_input.example.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(curated_rank_template(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote non-secret rank template: {target}")

    if failures:
        print("\nBLOCKED:")
        for failure in failures:
            print(f"- {failure}")
        return 2

    print("\nQloo harness preflight is ready. No live Qloo workflow was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
