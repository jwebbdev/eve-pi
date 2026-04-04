"""CLI handler for the optimize command."""
from eve_pi.cli.formatters import format_result
from eve_pi.data.loader import GameData
from eve_pi.market.esi import ESIClient
from eve_pi.models.characters import Character
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.optimizer.allocator import OptimizationConstraints, optimize

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


def run_optimize(args):
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
    characters = _parse_characters(args.characters, args.ccu_level, args.max_planets)
    print("Fetching market data...")
    market = esi.fetch_all_pi_market_data(gd.materials)
    print(f"Loaded market data for {len(market)} materials")
    print("Optimizing...")
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode=args.mode,
        cycle_days=args.cycle_days, hauling_trips_per_week=args.trips_per_week,
        cargo_capacity_m3=args.cargo_m3, tax_rate=args.tax_rate,
    )
    result = optimize(constraints, market, gd)
    print(format_result(result, constraints))
