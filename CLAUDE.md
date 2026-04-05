# EVE PI Optimizer - Developer Guide

## Project Overview

EVE Online Planetary Interaction optimizer. Python library + FastAPI web UI at https://pi.pwnjitsu.org.
85 tests: `python -m pytest tests/`
Start server: `python -m eve_pi.web.app --port 8000 --reload` (reload watches `eve_pi/version.txt` only)
Caddy SSL: `caddy run` from project root (needs admin terminal)
Design spec: `docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md`

## Critical Values (Verified In-Game)

### PI Material Volumes (NOT what most wikis say)
- R0: **0.005** m³ (many sources incorrectly say 0.01)
- P1: **0.19** m³ (many sources incorrectly say 0.38)
- P2: 0.75 m³
- P3: **3.0** m³ (many sources incorrectly say 1.5)
- P4: **50.0** m³ (many sources incorrectly say 100.0)
- Verified via ESI `/universe/types/{id}/` endpoint

### High-Tech Factory Structure IDs
Only Barren and Temperate planets can build P4:
- Barren: **2475** (verified via ESI)
- Temperate: **2482** (verified via ESI)
- All other planet types: **null** — they do NOT have high-tech factories
- WARNING: The original pi_templates.py had bogus IDs (e.g., 2488 = Warrior II drone!)
- The Fuzzwork SDE `planetSchematicsPinMap.csv` confirms only 2475 and 2482

### ECU (Extractor Control Unit) Costs
- Base structure: **400 CPU + 2600 MW** (this is huge on power!)
- Per head: **110 CPU + 550 MW**
- Total 10-head ECU: 1500 CPU + 8100 MW
- ECUs are **locked to one R0 type** — cannot be swapped. Need 2 separate ECUs for R0→P2.

### Command Center Levels
```
Level 0: 1,675 CPU, 6,000 MW
Level 4: 21,315 CPU, 17,000 MW
Level 5: 25,415 CPU, 19,000 MW
```

### Link Cost Formulas (empirical, from original codebase)
```
min_link_distance_km = -0.7716 + 0.012182 * radius_km
link_power_mw = 10.9952 + 0.1433 * distance_km
link_cpu_tf = 15.6475 + 0.1995 * distance_km
```

### CCP Extraction Decay Formula
Source: https://developers.eveonline.com/docs/guides/pi/
- decay_factor = 0.012 (Dogma attribute 1683)
- noise_factor = 0.8 (Dogma attribute 1687)
- Hyperbolic decay: `yield = base / (1 + t * 0.012)` with oscillating noise
- `qty_per_cycle` (base rate) comes from ESI authenticated endpoint or estimated defaults

### Default Extraction Rates (WH space estimates)
Most R0: 60,000/hr. Exceptions: Autotrophs/Ionic Solutions/Planktic Colonies: 50,000/hr. Complex Organisms: 40,000/hr. Suspended Plasma: 55,000/hr.

## EVE Template JSON Format

### Requirements for game import
1. **All La/Lo/Diam values MUST be floats** — `3.0` not `3`. JavaScript's `JSON.stringify` drops `.0` on whole numbers. The web UI has `ensureFloats()` to patch clipboard output.
2. **R0 routes CANNOT go through Basic Industry Facilities** — R0 must flow ECU → Storage/Launchpad → Factory. Routes through factories fail silently.
3. **Single-line compact JSON** on clipboard for paste import.
4. **Pin references are 1-indexed** in links and routes (not 0-indexed).
5. **Diam field** represents view diameter — the game scales templates to fit the actual planet.

### Template generation approach
- Use a single unified hex grid for ALL structures (LPs + factories) — never place them independently or they'll overlap
- True hex geometry: `row_height = step * 0.866025`
- Sort cells by ring (distance from center) then by angle for clean concentric fill
- LPs get center cells, factories get outer cells
- Tree topology: each factory links to nearest already-placed neighbor closer to center
- BFS pathfinding for routes through the link tree

## Allocator Design

### Sorting
**Always sort by ISK/colony/day.** Volume budget is a constraint (skip if over), not the sort key.

Previous attempt: sorting by ISK/m³ — this is wrong because a 72-colony chain producing 1 m³ of P4 has amazing ISK/m³ but terrible ISK/colony.

### Fill Pattern
For each unit in sorted order, **fill ALL available slots** on that planet before moving to the next unit. Previous approach was round-robin (one of each per pass) which caused lower-value products to steal slots from the best product.

### Opportunity Cost
Chain ISK must subtract what feeder colonies could earn selling P1 directly. Without this, chains appear 2-5x more profitable than they actually are. A Polyaramids chain showed 49M ISK/day but the net benefit over selling P1 was only ~27M across 11 colonies.

### Manufacturing Needs
Full-capacity chains can require 100+ colonies (e.g., Nano-Factory at max capacity = 103 colonies). The `_build_minimal_chain()` function builds chains with 1 factory per tier instead, typically needing 10-20 colonies.

### Heads vs Factories Balance
Factories must not exceed head count — a factory without R0 feed is 100% idle. Previous code maximized factories (18) with minimal heads (1), which is mathematically optimal for CPU/PG but produces zero output from 17 idle factories.

## Data Sources

### Fuzzwork SDE (Static Data Export)
- URL: `https://www.fuzzwork.co.uk/dump/latest/`
- `mapDenormalize.csv.bz2` — planet radii (radius field, in meters, divide by 1000 for km)
- `planetSchematicsPinMap.csv` — maps schematics to valid pin types
- Cached for 7 days in `.pi_cache/sde_planet_radius.json`

### ESI (EVE Swagger Interface)
- Market orders: `GET /markets/{region_id}/orders/?type_id={id}&order_type=buy|sell`
- System lookup: `POST /universe/ids/` with JSON body `["system_name"]`
- Planet info: `GET /universe/planets/{planet_id}/`
- Type info: `GET /universe/types/{type_id}/` — use this to verify structure IDs and volumes
- Cached for 15 minutes in `.pi_cache/`

### Reference Templates
- 83 templates from https://github.com/DalShooth/EVE_PI_Templates
- Note: some have cross-planet-type structures (e.g., Ice Launchpad on Barren planet) — the game handles this but the converter must check all planet types as fallback

## Paths Tried and Rejected

1. **Sorting by ISK/m³ for shipping** — leads to tiny-volume chains stealing all slots. ISK/colony is the correct metric.
2. **Product deduplication in allocator** — prevented the best product from filling multiple planets. Removed.
3. **LP count based on storage volume** — tried calculating LPs from `factory_throughput × cycle_days ÷ 10,000`. Too aggressive (showed 6+ LPs). Real usage: LPs are delivery/pickup points, not long-term storage. Made it a user dropdown instead.
4. **Separate placement of LPs and factories** — caused overlapping positions. Unified hex grid solves this.
5. **Row height = step (not 0.866)** — tried to avoid visual overlap but produced non-uniform spacing. True hex geometry (0.866) works fine; the structures have enough visual clearance.
6. **Restock days as form input** — removed because LP count is now a direct user choice, and the capacity model no longer uses restock days.
7. **Server-side config storage** — replaced with browser localStorage for per-user separation without auth.

## Common Gotchas

- **Starlette 1.0 TemplateResponse** — use `templates.TemplateResponse(request, template_name, context)` not the old dict-as-second-arg pattern
- **Windows Python path issues** — `reload_dirs` needs absolute paths; `reload_includes` needs relative glob patterns within the reload dir
- **Git not configured** — the machine has no global git user.name/email. Set per-repo with `git config user.email/name`.
- **Background commands die** — Claude Code's `run_in_background` bash commands get killed when the task "completes". The user must run long-lived servers (uvicorn, caddy) in their own terminal.
- **Market cache** — 15-minute TTL. Delete `.pi_cache/orders_*.json` to force fresh fetch.
