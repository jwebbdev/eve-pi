"""CLI handler for the optimize command."""
import json
from pathlib import Path

from eve_pi.cli.formatters import format_result
from eve_pi.data.loader import GameData
from eve_pi.market.esi import ESIClient
from eve_pi.models.characters import Character
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.optimizer.allocator import ManufacturingNeed, OptimizationConstraints, optimize

PLANET_TYPE_IDS = {
    11: "Temperate", 12: "Ice", 13: "Gas", 2014: "Oceanic",
    2015: "Lava", 2016: "Barren", 2017: "Storm", 2063: "Plasma",
}


def _parse_characters(char_input: str, default_ccu: int, default_planets: int):
    """Parse character input string into Character objects.

    Formats:
        "6"                              -> 6 characters named Char1-6, all defaults
        "Alice,Bob,Charlie"              -> 3 named characters with defaults
        "Alice:5,Bob:4,Charlie:4"        -> CCU level per character
        "Alice:5:6,Bob:4:5,Charlie:4:4"  -> CCU level and max planets (IC skill) per character

    The per-character format is name:ccu or name:ccu:planets where:
        - ccu = Command Center Upgrades skill level (0-5)
        - planets = max planets from Interplanetary Consolidation (1-6, default 6 = IC V)
    """
    char_input = char_input.strip()

    # Try plain integer (backward compatible)
    try:
        count = int(char_input)
        return [Character(name=f"Char{i+1}", ccu_level=default_ccu, max_planets=default_planets)
                for i in range(count)]
    except ValueError:
        pass

    # Comma-separated names with optional :ccu and :ccu:planets suffixes
    characters = []
    for part in char_input.split(","):
        part = part.strip()
        pieces = part.split(":")
        name = pieces[0].strip()
        ccu = int(pieces[1]) if len(pieces) > 1 else default_ccu
        planets = int(pieces[2]) if len(pieces) > 2 else default_planets
        characters.append(Character(name=name, ccu_level=ccu, max_planets=planets))
    return characters


def _load_config(config_path: str) -> dict:
    """Load optimization config from a JSON file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_config(args, config: dict):
    """Apply config file values as defaults — CLI args override."""
    # Characters from config (only if CLI didn't specify non-default)
    if "characters" in config and args.characters == "1":
        chars = []
        for c in config["characters"]:
            chars.append(Character(
                name=c["name"],
                ccu_level=c.get("ccu_level", 5),
                max_planets=c.get("max_planets", 6),
            ))
        args._config_characters = chars
    else:
        args._config_characters = None

    # Scalar defaults from config (CLI overrides if explicitly set)
    defaults = {
        "cycle_days": "cycle_days",
        "trips_per_week": "trips_per_week",
        "cargo_capacity_m3": "cargo_m3",
        "tax_rate": "tax_rate",
        "mode": "mode",
        "system": "system",
    }
    for config_key, arg_key in defaults.items():
        if config_key in config:
            # Only apply if the arg is still at its parser default
            current = getattr(args, arg_key, None)
            parser_defaults = {
                "cycle_days": 4.0, "trips_per_week": 2, "cargo_m3": 60000.0,
                "tax_rate": 0.05, "mode": "self_sufficient", "system": None,
            }
            if arg_key in parser_defaults and current == parser_defaults[arg_key]:
                setattr(args, arg_key, config[config_key])


def run_optimize(args):
    # Load config file if provided
    config = {}
    if hasattr(args, "config") and args.config:
        config = _load_config(args.config)
        _apply_config(args, config)

    if not args.system:
        print("Error: --system is required (or set 'system' in config file)")
        return

    print("Loading game data...")
    gd = GameData.load()
    esi = ESIClient()
    print(f"Resolving system '{args.system}'...")
    system_id = esi.resolve_system_id(args.system)
    if not system_id:
        print(f"Error: Could not find system '{args.system}'")
        return
    print("Fetching planet data...")
    raw_planets = esi.fetch_system_planets(system_id)
    planets = []
    for rp in raw_planets:
        type_name = PLANET_TYPE_IDS.get(rp["type_id"])
        if type_name and type_name in gd.planet_types:
            planets.append(Planet(
                planet_id=rp["planet_id"],
                planet_type=gd.planet_types[type_name],
                radius_km=3000.0,
            ))
    system = SolarSystem(name=args.system, system_id=system_id, planets=planets)
    print(f"Found {len(planets)} planets")

    # Build characters: config file takes priority, then CLI parsing
    if hasattr(args, "_config_characters") and args._config_characters:
        characters = args._config_characters
    else:
        characters = _parse_characters(args.characters, args.ccu_level, args.max_planets)

    print(f"Characters: {', '.join(f'{c.name} (CC{c.ccu_level} IC{c.max_planets})' for c in characters)}")
    print(f"Total colony slots: {sum(c.max_planets for c in characters)}")

    print("Fetching market data...")
    market = esi.fetch_all_pi_market_data(gd.materials)
    print(f"Loaded market data for {len(market)} materials")
    print("Optimizing...")
    # Parse manufacturing needs from config
    mfg_needs = []
    if "manufacturing_needs" in config:
        for item in config["manufacturing_needs"]:
            mfg_needs.append(ManufacturingNeed(
                product=item["product"],
                quantity_per_week=item["quantity_per_week"],
            ))
        if mfg_needs:
            print(f"Manufacturing needs: {', '.join(f'{n.product} x{n.quantity_per_week}/wk' for n in mfg_needs)}")

    constraints = OptimizationConstraints(
        system=system, characters=characters, mode=args.mode,
        cycle_days=args.cycle_days, hauling_trips_per_week=args.trips_per_week,
        cargo_capacity_m3=args.cargo_m3, tax_rate=args.tax_rate,
        manufacturing_needs=mfg_needs,
    )
    result = optimize(constraints, market, gd)
    print(format_result(result, constraints))
