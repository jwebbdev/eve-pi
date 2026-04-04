"""
End-to-end integration test using fake market data.
Verifies the full pipeline: data loading -> feasibility -> profitability -> allocation -> output.
"""
from eve_pi.cli.formatters import format_result
from eve_pi.data.loader import GameData
from eve_pi.market.esi import MarketData
from eve_pi.models.characters import Character
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.optimizer.allocator import OptimizationConstraints, optimize


def _build_full_market(game_data: GameData) -> dict:
    """Build market data for all materials with plausible prices."""
    tier_prices = {"r0": 5, "p1": 500, "p2": 10000, "p3": 70000, "p4": 900000}
    market = {}
    for name, mat in game_data.materials.items():
        base_price = tier_prices.get(mat.tier, 500)
        market[name] = MarketData(
            type_id=mat.type_id, name=name, buy_price=base_price,
            sell_orders=[{"price": base_price * 0.95, "volume_remain": 100000}],
        )
    return market


def test_full_pipeline_self_sufficient():
    gd = GameData.load()
    market = _build_full_market(gd)
    system = SolarSystem(name="TestSystem", system_id=1, planets=[
        Planet(1, gd.planet_types["Barren"], 2220.0),
        Planet(2, gd.planet_types["Gas"], 39773.0),
        Planet(3, gd.planet_types["Gas"], 39773.0),
        Planet(4, gd.planet_types["Lava"], 3910.0),
        Planet(5, gd.planet_types["Temperate"], 6420.0),
        Planet(6, gd.planet_types["Ice"], 8580.0),
        Planet(7, gd.planet_types["Storm"], 13890.0),
    ])
    characters = [
        Character(name=f"Char{i+1}", ccu_level=4, max_planets=6)
        for i in range(3)
    ]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000.0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert len(result.assignments) > 0
    assert len(result.assignments) <= sum(c.max_planets for c in characters)
    assert result.total_isk_per_day > 0
    assert result.total_volume_per_day > 0
    assert result.total_volume_per_week <= constraints.max_volume_per_week
    output = format_result(result)
    assert "OPTIMIZATION RESULT" in output
    assert "ISK/day" in output


def test_full_pipeline_import_mode():
    gd = GameData.load()
    market = _build_full_market(gd)
    system = SolarSystem(name="TestSystem", system_id=1, planets=[
        Planet(1, gd.planet_types["Barren"], 2220.0),
        Planet(2, gd.planet_types["Temperate"], 6420.0),
    ])
    characters = [Character(name="Char1", ccu_level=4, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="import",
        cycle_days=1.0, hauling_trips_per_week=5, cargo_capacity_m3=60000.0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert len(result.assignments) > 0
    assert result.total_isk_per_day > 0
