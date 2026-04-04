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
    characters = [
        Character(name=f"Char{i+1}", ccu_level=args.ccu_level, max_planets=args.max_planets)
        for i in range(args.characters)
    ]
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
