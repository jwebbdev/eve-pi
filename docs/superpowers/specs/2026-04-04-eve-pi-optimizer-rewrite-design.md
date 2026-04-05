# EVE Online PI Optimizer - Design Spec (Updated 2026-04-05)

## Overview

A modular Python library with CLI and web UI for optimizing EVE Online Planetary Interaction. Hosted at https://pi.pwnjitsu.org with Caddy SSL. 85 tests passing.

## Core Question

> "If I'm willing to make X trips from highsec to my wormhole in a ship with Y m3 per week, and I reset my extractors every Z days, what are the most profitable colony layouts on the planets in my system?"

## Operating Modes

- **Self-Sufficient**: All PI materials from local extraction, no Jita imports
- **Import**: Buy inputs from Jita, run factory planets
- **Hybrid**: Optimizer decides per-material (not yet fully implemented)
- **Unlimited hauling**: Leave trips/cargo empty — no volume constraint, everything ships

## Architecture

```
eve-pi/
├── eve_pi/
│   ├── models/          # Material, Recipe, Planet, Character dataclasses
│   ├── data/            # YAML game data (single source of truth)
│   ├── extraction/      # CCP decay formula, yield calculations
│   ├── market/          # ESI client, file cache, MarketData
│   ├── capacity/        # CPU/PG budget, link costs, factory limits
│   ├── optimizer/       # Feasibility, profitability, allocator, supply chain
│   ├── templates/       # Topology, skin, converter, programmatic generator
│   ├── cli/             # Argparse CLI with config file support
│   └── web/             # FastAPI + Jinja2 web UI
├── reference_templates/ # 83 DalShooth templates
├── tests/               # 85 tests
├── Caddyfile            # SSL reverse proxy config
└── pyproject.toml
```

## Key Design Decisions

### Allocator (self-sufficient mode)
- **Sort by ISK/colony/day** — always. Volume budget is a constraint, not a sort key.
- **Fill-then-next**: For each production unit, fill ALL available slots on that planet before moving to the next unit. Prevents lower-value products stealing slots.
- **Opportunity cost**: Chain ISK subtracts what feeder colonies could earn selling P1 directly.
- **Minimal chains**: For manufacturing needs, builds chains with 1 factory per tier (not max capacity). A Nano-Factory needs ~15 colonies, not 103.
- **No product dedup**: Each planet×product combo is a separate unit. Multiple planets produce same P1.
- **Three passes**: manufacturing (priority) → shipping (within volume budget) → stockpile (remaining slots)
- **Pricing option**: Sell to buy orders (instant, lower) vs create sell orders (wait, higher)

### Capacity Model
- ECU base: 400 CPU + 2600 MW per ECU (plus 110 CPU + 550 MW per head)
- Balanced heads vs factories: cap factories at head count (idle factories waste slots)
- LP count: user-selectable dropdown (1-4), defaults vary by tier (P1→P2: 4, P2→P3: 3, P3→P4: 2)
- Factory count rounded to multiple of LP count for even distribution
- Link costs: `min_link = -0.77 + 0.012 * radius_km`, `power = 11.0 + 0.143 * distance_km`

### Template Generator
- Unified hex grid: ALL structures (LPs + factories) placed in single grid, no overlaps
- True hex geometry: row_height = step × sqrt(3)/2
- Ring-sorted fill: concentric rings from center, clockwise within each ring
- LPs at center cells, factories radiate outward
- Tree topology: each factory links to nearest neighbor closer to center
- BFS pathfinding for routes
- Round-robin factory→LP assignment for even load distribution
- Supports all types: R0→P1, R0→P2, P1→P2, P2→P3, P3→P4, P2→P4

### EVE Template Format Requirements
- Diam, La, Lo MUST be floats (3.0 not 3) — JS `ensureFloats()` patches clipboard output
- R0 routes CANNOT go through Basic Industry Facilities — only through Storage/LP hubs
- ECUs locked to one R0 type — need 2 ECUs for R0→P2
- Single-line compact JSON for clipboard import

### Correct PI Material Volumes
- R0: 0.005 m³
- P1: 0.19 m³
- P2: 0.75 m³
- P3: 3.0 m³
- P4: 50.0 m³

### Correct High-Tech Factory IDs (only Barren + Temperate)
- Barren: 2475
- Temperate: 2482
- Other planet types: null (not P4 capable)

## Web UI Features
- Optimizer form with character management, saved configs (localStorage)
- Session storage auto-restore on back navigation
- Manufacturing needs with system product filtering ("Load System Products")
- Results with shipping/stockpile/manufacturing sections
- Template generation buttons with LP count dropdown
- Template converter page
- Feedback form (bug reports/feature requests)
- Buy Me a Coffee link, DEV BUILD indicator
- Auto-reload via version.txt trigger (`--reload` flag)

## Data Sources
- **Game data**: YAML files (recipes, planet types, facilities, materials)
- **Market prices**: ESI API with 15-minute file cache
- **Planet radii**: Fuzzwork SDE dump (mapDenormalize.csv.bz2), 7-day cache
- **Planet composition**: ESI system/planet endpoints
- **Extraction formula**: CCP official (decay_factor=0.012, noise_factor=0.8)

## Open Items
1. ~~Hauling budget as knapsack problem~~ (done — swap optimization pass replaces high-volume shipped colonies with multiple low-volume ones)
2. ~~Opportunity cost on P2→P3 and P3→P4 chains~~ (done — flat per-colony lookup from standalone + P1→P2 units)
3. Hybrid manufacturing — allow importing intermediates when full chain too large
4. P2→P4 template in-game testing
5. Railway deployment for public hosting
6. PI product browser page (system→products and products→systems)
7. ESI SSO for actual character colony data
8. Template optimizer — calculated optimal pin positions for minimum link cost
