"""Run lightweight route regression checks against the live API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def load_cases(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases", [])


def request_route(api_url: str, case: dict) -> dict:
    preferences = {
        "psp_priority": 1.0,
        "psp_weight": 100,
        "routing_mode": "hard_psp_anchor",
        "avoid_busy_roads": True,
        "max_detour_ratio": 1.25,
        "phase_search_radius_m": 2500,
        "phase_candidate_limit": 1,
        "preferred_councils": [],
    }
    preferences.update(case.get("preferences", {}))
    body = {
        "origin": case["origin"],
        "destination": case["destination"],
        "waypoints": case.get("waypoints", []),
        "preferences": preferences,
        "alternatives": int(case.get("alternatives", 1)),
        "format": "geojson",
    }
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/v1/route",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    payload["_elapsed_ms"] = elapsed_ms
    return payload


def evaluate_case(case: dict, response: dict) -> tuple[bool, list[str]]:
    summary = response.get("summary", {})
    psp_share = float(summary.get("psp_share", 0.0))
    busy_road_m = float(summary.get("busy_road_m", 0.0))
    on_road_m = float(summary.get("on_road_m", 0.0))
    elapsed_ms = float(response.get("_elapsed_ms", 0.0))
    warning_types = {str(w.get("type")) for w in response.get("warnings", [])}
    errors = []

    if psp_share < float(case.get("min_psp_share", 0.0)):
        errors.append(
            f"psp_share={psp_share:.3f} below threshold {float(case['min_psp_share']):.3f}"
        )
    if busy_road_m > float(case.get("max_busy_road_m", 1e9)):
        errors.append(
            f"busy_road_m={busy_road_m:.1f} above threshold {float(case['max_busy_road_m']):.1f}"
        )
    if "max_on_road_m" in case and on_road_m > float(case["max_on_road_m"]):
        errors.append(f"on_road_m={on_road_m:.1f} above threshold {float(case['max_on_road_m']):.1f}")
    if "max_response_ms" in case and elapsed_ms > float(case["max_response_ms"]):
        errors.append(
            f"response_ms={elapsed_ms:.0f} above threshold {float(case['max_response_ms']):.0f}"
        )
    for warning_type in case.get("forbid_warning_types", []):
        if warning_type in warning_types:
            errors.append(f"warning present but forbidden: {warning_type}")
    return (len(errors) == 0), errors


def main():
    parser = argparse.ArgumentParser(description="Route regression checker")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Base API URL",
    )
    parser.add_argument(
        "--cases-file",
        default=str(Path(__file__).resolve().parent.parent / "tests" / "data" / "route_regression_cases.json"),
        help="Path to regression case JSON",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.cases_file))
    if not cases:
        print("No regression cases found.")
        return

    failed = 0
    for case in cases:
        response: dict = {}
        try:
            response = request_route(args.api_url, case)
            ok, errors = evaluate_case(case, response)
        except Exception as exc:
            ok = False
            errors = [f"request failed: {exc}"]

        status = "PASS" if ok else "FAIL"
        summary = response.get("summary", {})
        print(
            f"[{status}] {case['id']} "
            f"psp_share={float(summary.get('psp_share', 0.0)):.3f} "
            f"busy_road_m={float(summary.get('busy_road_m', 0.0)):.1f} "
            f"response_ms={float(response.get('_elapsed_ms', 0.0)):.0f}"
        )
        if not ok:
            failed += 1
            for err in errors:
                print(f"  - {err}")

    if failed:
        print(f"\nRegression failed: {failed} case(s) out of {len(cases)}")
        sys.exit(1)
    print(f"\nRegression passed: {len(cases)} case(s)")


if __name__ == "__main__":
    main()
