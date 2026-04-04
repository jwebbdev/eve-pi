from eve_pi.data.loader import GameData
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.models.characters import Character
from eve_pi.market.esi import MarketData
from eve_pi.optimizer.allocator import optimize, OptimizationConstraints, OptimizationResult


def _make_test_system(gd: GameData) -> SolarSystem:
    return SolarSystem(name="J153003", system_id=31002229, planets=[
        Planet(planet_id=1, planet_type=gd.planet_types["Barren"], radius_km=2220.0),
        Planet(planet_id=2, planet_type=gd.planet_types["Gas"], radius_km=39773.0),
        Planet(planet_id=3, planet_type=gd.planet_types["Lava"], radius_km=3910.0),
        Planet(planet_id=4, planet_type=gd.planet_types["Temperate"], radius_km=6420.0),
        Planet(planet_id=5, planet_type=gd.planet_types["Ice"], radius_km=8580.0),
    ])


def _make_fake_market() -> dict:
    prices = {
        "Water": 500, "Electrolytes": 550, "Bacteria": 420, "Reactive Metals": 430,
        "Toxic Metals": 330, "Silicon": 800, "Precious Metals": 600, "Biofuels": 300,
        "Proteins": 860, "Oxygen": 370, "Chiral Structures": 650, "Biomass": 800,
        "Oxidizing Compound": 710, "Plasmoids": 480, "Industrial Fibers": 820,
        "Coolant": 12000, "Construction Blocks": 11000, "Enriched Uranium": 13000,
        "Mechanical Parts": 10500, "Rocket Fuel": 12500, "Superconductors": 10800,
        "Polyaramids": 17000, "Supertensile Plastics": 13500,
        "Robotics": 78000, "Guidance Systems": 45000,
        "Broadcast Node": 900000,
    }
    market = {}
    for name, price in prices.items():
        market[name] = MarketData(
            type_id=0, name=name, buy_price=price,
            sell_orders=[{"price": price * 0.95, "volume_remain": 100000}],
        )
    return market


def test_optimize_self_sufficient():
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name="Char1", ccu_level=4, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert isinstance(result, OptimizationResult)
    assert len(result.assignments) > 0
    assert result.total_isk_per_week > 0


def test_optimize_import_mode():
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name="Char1", ccu_level=4, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="import",
        cycle_days=1.0, hauling_trips_per_week=3, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert isinstance(result, OptimizationResult)
    assert len(result.assignments) > 0


def test_optimize_respects_colony_limit():
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name="Char1", ccu_level=4, max_planets=3)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="import",
        cycle_days=1.0, hauling_trips_per_week=5, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert len(result.assignments) <= 3
