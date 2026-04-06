# eve-pi

Python library and CLI for EVE Online Planetary Interaction (PI) optimization.

Given a solar system and your characters, eve-pi calculates the most profitable colony setup — which planets to use, what to extract, what to manufacture, and how to allocate across characters. It fetches live market data from ESI and generates importable templates you can paste directly into the game.

## Features

- **Colony optimizer** — greedy + swap allocation across multiple characters, with self-sufficient, import, and hybrid modes
- **Live market data** — fetches Jita buy/sell prices from ESI with local caching
- **Template generator** — produces EVE-importable JSON templates for any setup (extraction, factory, R0-to-P2)
- **Template converter** — re-targets existing templates to different planet types or products
- **System finder** — searches a pre-built index of ~8000 systems by planet composition, security status, and wormhole class
- **Jump distance** — instant BFS pathfinding using local stargate adjacency data (no ESI calls)
- **Extraction yield** — models CCP's official decay formula for accurate long-cycle planning
- **Capacity calculator** — CPU/PG budgeting, factory limits, link costs per planet radius and CCU level

## Installation

```bash
pip install git+https://github.com/jwebbdev/eve-pi.git@main
```

For development:

```bash
git clone https://github.com/jwebbdev/eve-pi.git
cd eve-pi
pip install -e ".[dev]"
```

## CLI Usage

### Optimize

```bash
eve-pi optimize --system Jita --characters "Alice:5:6,Bob:4:5" --mode self_sufficient
```

Options:
- `--system` — solar system name
- `--characters` — character specs as `name:ccu:planets` (e.g., `Alice:5:6,Bob:4:5`)
- `--ccu-level` — default CCU level when not specified per character (0-5, default 5)
- `--max-planets` — default max planets per character (1-6, default 6)
- `--cycle-days` — extractor restart cadence in days (default 4)
- `--trips-per-week` — hauling trips per week (default 2)
- `--cargo-m3` — cargo capacity in m3 (default 60000)
- `--mode` — `self_sufficient`, `import`, or `hybrid`
- `--tax-rate` — POCO tax rate (default 0.05)

### Templates

```bash
eve-pi template --setup r0_to_p1 --planet-type Gas --product Oxygen
```

## Library Usage

```python
from eve_pi.data.loader import GameData
from eve_pi.market.esi import ESIClient
from eve_pi.systems import find_matching_systems, get_system_products, jump_distance

# Load game data (materials, recipes, planet types, system index)
gd = GameData.load()

# Find systems that can produce specific R0 resources
matches = find_matching_systems(
    gd.system_index,
    required_r0s=["Aqueous Liquids", "Base Metals"],
    planet_types_for_r0=gd.planet_types_for_r0,
    space="k",  # K-space only
)

# Calculate jump distance between systems (instant, local BFS)
jumps = jump_distance(30000142, 30002187, gd.system_jumps)  # Jita to Amarr

# Get all products a system can produce from its planet composition
products = get_system_products({"Temperate": 2, "Gas": 1}, gd)
# Returns: {"p1": ["Water", ...], "p2": [...], "p3": [...], "p4": [...]}

# Fetch live market data
esi = ESIClient()
market = esi.fetch_all_pi_market_data(gd.materials)
```

## Project Structure

```
eve_pi/
  data/           Game data (YAML) and loaders
    materials.yaml      76 PI products (R0-P4) with type IDs and volumes
    recipes.yaml        Production recipes across 4 tier transitions
    planet_types.yaml   8 planet types with resources and structures
    facilities.yaml     CPU/PG/storage specs for all PI facilities
    system_index.json   ~8000 systems with planet compositions (from SDE)
    system_jumps.json   Stargate adjacency graph (from SDE)
    loader.py           GameData class — loads everything at startup
  models/         Data classes (Material, Recipe, PlanetType, Planet, Character, etc.)
  optimizer/      Colony allocation, feasibility matrix, profitability, supply chain
  market/         ESI API client with file-based caching
  capacity/       CPU/PG budget calculations, factory limits
  extraction/     Yield decay simulation
  systems/        System finder, product availability, BFS pathfinding
  templates/      Template generation and conversion
  cli/            Command-line interface
```

## Data Sources

- **Market prices** — [EVE ESI API](https://esi.evetech.net/) (live, cached 15 min)
- **System/planet data** — [Fuzzwork SDE](https://www.fuzzwork.co.uk/dump/latest/) (pre-built, static)
- **Game mechanics** — CCP's published formulas for extraction decay, facility specs, recipes

## Web Interface

This library powers the tools at [pwnjitsu.dev](https://pwnjitsu.dev):

- **PI Optimizer** — web UI for the colony optimizer with interactive results and one-click templates
- **PI Product Browser** — explore production chains, find systems by planet composition

## License

Apache 2.0
