# MVP acceptance criteria

This document defines deterministic pass/fail gates for the Perth PSP router MVP.

## Goal

Ensure the router consistently:

1. gets onto dedicated cycling infrastructure quickly,
2. stays on dedicated infrastructure for the corridor phase, and
3. exits late with minimal on-road exposure.

## Test command

Run the automated suite against a live local API:

1. `cd api`
2. `python3 scripts/route_regression.py --api-url http://127.0.0.1:8000`

The script exits non-zero if any case fails.

## Required passing cases

The case definitions live in `api/tests/data/route_regression_cases.json`.

Current required cases:

- `armadale_psp_case_a`
- `armadale_psp_case_b`
- `west_perth_wilson`
- `kwinana_psp_corridor`

## Case-level gates

Each case can define deterministic gates:

- `min_psp_share`
- `max_busy_road_m`
- `max_on_road_m` (optional)
- `max_response_ms`
- `forbid_warning_types`

Typical forbidden warnings for hard-anchor validation:

- `hard_anchor_unavailable`
- `council_overlay_not_used` (for council-critical cases)

## Manual browser checks

After automated checks pass, verify interactively in the web client:

1. Set A and B on the map.
2. Test quick presets and high PSP weighting.
3. Set manual PSP via-point (`P`) and confirm corridor shaping effect.
4. Select preferred councils and verify route/warning behaviour.
5. Download GPX/GeoJSON and spot-check geometry.

## Release recommendation

Treat MVP as releasable only if:

- all automated regression cases pass,
- no route request times out in normal metro-scale tests,
- manual checks confirm deterministic hard-anchor behaviour.
