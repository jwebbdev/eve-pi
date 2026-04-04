from eve_pi.capacity.planet_capacity import SetupType
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


def test_self_sufficient_uses_all_colonies():
    """Self-sufficient mode should fill all colony slots, not stop at volume limit."""
    gd = GameData.load()
    # System with many planet types for diverse extraction options
    system = SolarSystem(name="TestFill", system_id=99999, planets=[
        Planet(planet_id=1, planet_type=gd.planet_types["Barren"], radius_km=5000.0),
        Planet(planet_id=2, planet_type=gd.planet_types["Gas"], radius_km=5000.0),
        Planet(planet_id=3, planet_type=gd.planet_types["Lava"], radius_km=5000.0),
        Planet(planet_id=4, planet_type=gd.planet_types["Temperate"], radius_km=5000.0),
        Planet(planet_id=5, planet_type=gd.planet_types["Ice"], radius_km=5000.0),
        Planet(planet_id=6, planet_type=gd.planet_types["Storm"], radius_km=5000.0),
    ])
    market = _make_fake_market()
    # Many colonies with very small hauling budget to force stockpile usage
    characters = [Character(name="Char1", ccu_level=4, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=1, cargo_capacity_m3=5000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert len(result.assignments) == constraints.total_colonies


def test_self_sufficient_factory_chains():
    """Should consider factory chains, not just standalone extraction."""
    gd = GameData.load()
    # System with planets that have the R0 resources for Coolant's inputs
    # Coolant needs Electrolytes (Ionic Solutions) + Water (Aqueous Liquids)
    # Gas has both Ionic Solutions and Aqueous Liquids
    # Give plenty of planets and generous hauling budget
    system = SolarSystem(name="TestChain", system_id=99998, planets=[
        Planet(planet_id=1, planet_type=gd.planet_types["Gas"], radius_km=10000.0),
        Planet(planet_id=2, planet_type=gd.planet_types["Gas"], radius_km=10000.0),
        Planet(planet_id=3, planet_type=gd.planet_types["Gas"], radius_km=10000.0),
        Planet(planet_id=4, planet_type=gd.planet_types["Gas"], radius_km=10000.0),
        Planet(planet_id=5, planet_type=gd.planet_types["Gas"], radius_km=10000.0),
        Planet(planet_id=6, planet_type=gd.planet_types["Barren"], radius_km=10000.0),
        Planet(planet_id=7, planet_type=gd.planet_types["Lava"], radius_km=10000.0),
        Planet(planet_id=8, planet_type=gd.planet_types["Temperate"], radius_km=10000.0),
        Planet(planet_id=9, planet_type=gd.planet_types["Ice"], radius_km=10000.0),
        Planet(planet_id=10, planet_type=gd.planet_types["Storm"], radius_km=10000.0),
    ])
    # Set P2 prices high to make factory chains attractive
    market = _make_fake_market()
    for p2_name in ["Coolant", "Construction Blocks", "Enriched Uranium",
                     "Mechanical Parts", "Rocket Fuel", "Superconductors"]:
        if p2_name in market:
            market[p2_name] = MarketData(
                type_id=0, name=p2_name, buy_price=25000,
                sell_orders=[{"price": 23750, "volume_remain": 100000}],
            )
    characters = [
        Character(name="Char1", ccu_level=4, max_planets=6),
        Character(name="Char2", ccu_level=4, max_planets=6),
    ]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=3, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    factory_assignments = [a for a in result.assignments if a.setup == SetupType.P1_TO_P2]
    assert len(factory_assignments) > 0, (
        f"Expected factory chain assignments but got none. "
        f"Assignments: {[(a.product, a.setup.value, a.category) for a in result.assignments]}"
    )


def test_self_sufficient_has_shipping_and_stockpile():
    """Result should have both shipping and stockpile categories."""
    gd = GameData.load()
    system = SolarSystem(name="TestCategories", system_id=99997, planets=[
        Planet(planet_id=1, planet_type=gd.planet_types["Barren"], radius_km=5000.0),
        Planet(planet_id=2, planet_type=gd.planet_types["Gas"], radius_km=5000.0),
        Planet(planet_id=3, planet_type=gd.planet_types["Lava"], radius_km=5000.0),
        Planet(planet_id=4, planet_type=gd.planet_types["Temperate"], radius_km=5000.0),
        Planet(planet_id=5, planet_type=gd.planet_types["Ice"], radius_km=5000.0),
        Planet(planet_id=6, planet_type=gd.planet_types["Storm"], radius_km=5000.0),
    ])
    market = _make_fake_market()
    # Budget fits ~4 R0→P2 colonies (90 m³/day × 7 = 630/wk each, budget = 3000/wk)
    # but 12 colonies total, so rest must stockpile
    characters = [
        Character(name="Char1", ccu_level=4, max_planets=6),
        Character(name="Char2", ccu_level=4, max_planets=6),
    ]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=1, cargo_capacity_m3=3000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    assert len(result.shipped_assignments) > 0, "Expected at least one shipped assignment"
    assert result.shipped_volume_per_week <= constraints.max_volume_per_week, (
        f"Shipped volume {result.shipped_volume_per_week} exceeds budget {constraints.max_volume_per_week}"
    )
    # With only 5000 m3/week budget and 6 colonies, we should get stockpile too
    assert len(result.stockpile_assignments) > 0, (
        f"Expected stockpile assignments with tight volume budget. "
        f"Assignments: {[(a.product, a.category) for a in result.assignments]}"
    )


def test_self_sufficient_colony_assignment_categories():
    """ColonyAssignment should have category and feeds fields."""
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name="Char1", ccu_level=4, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    for a in result.assignments:
        assert a.category in ("ship", "feed", "stockpile"), f"Invalid category: {a.category}"
        assert isinstance(a.feeds, str)


def test_self_sufficient_respects_planet_slots():
    """Each character can only use each physical planet once.
    With 2 characters and 3 planets, max 6 colonies total.
    No planet should have more colonies than characters."""
    gd = GameData.load()
    system = SolarSystem(name="SmallSystem", system_id=99990, planets=[
        Planet(planet_id=101, planet_type=gd.planet_types["Barren"], radius_km=3000.0),
        Planet(planet_id=102, planet_type=gd.planet_types["Gas"], radius_km=5000.0),
        Planet(planet_id=103, planet_type=gd.planet_types["Lava"], radius_km=4000.0),
    ])
    market = _make_fake_market()
    characters = [
        Character(name="Char1", ccu_level=4, max_planets=6),
        Character(name="Char2", ccu_level=4, max_planets=6),
    ]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)

    # Count colonies per planet_id
    planet_colony_counts = {}
    for a in result.assignments:
        planet_colony_counts[a.planet_id] = planet_colony_counts.get(a.planet_id, 0) + 1

    num_characters = len(characters)
    for planet_id, count in planet_colony_counts.items():
        assert count <= num_characters, (
            f"Planet {planet_id} has {count} colonies but only {num_characters} characters. "
            f"Each character can only use each planet once."
        )

    # Total colonies should not exceed characters * planets (but also capped by total_colonies)
    max_possible = min(
        sum(c.max_planets for c in characters),
        len(system.planets) * num_characters,
    )
    assert len(result.assignments) <= max_possible


def test_self_sufficient_p2_to_p3_chains():
    """Should build P2->P3 chains when profitable."""
    gd = GameData.load()
    # Need a system with enough planet diversity for a full P3 chain
    system = SolarSystem(name="TestP3", system_id=99985, planets=[
        # Need planets that can produce both P1 inputs for at least one P2,
        # and a P2 that feeds into a P3 recipe
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Gas", "Gas", "Gas", "Gas", "Gas",  # Ionic Solutions, Reactive Gas, Noble Gas, etc.
            "Lava", "Lava", "Lava",  # Felsic Magma, Non-CS Crystals, etc.
            "Barren", "Barren",  # factory planets
            "Temperate", "Temperate",
            "Plasma", "Plasma",
        ], start=1)
    ])
    # Set P3 prices very high to make chains attractive
    market = _make_fake_market()
    for p3_name in ["Robotics", "Guidance Systems"]:
        market[p3_name] = MarketData(
            type_id=0, name=p3_name, buy_price=200000,
            sell_orders=[{"price": 190000, "volume_remain": 100000}],
        )
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(10)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    p3_assignments = [a for a in result.assignments if a.setup == SetupType.P2_TO_P3]
    assert len(p3_assignments) > 0, (
        f"Expected P2->P3 chain but got: {[(a.product, a.setup.value) for a in result.assignments if a.category == 'ship']}"
    )
