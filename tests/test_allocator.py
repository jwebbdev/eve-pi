from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.data.loader import GameData
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.models.characters import Character
from eve_pi.market.esi import MarketData
from eve_pi.optimizer.allocator import (
    optimize, OptimizationConstraints, OptimizationResult,
    _build_production_units, _build_opportunity_cost_lookup, _score_options,
    _snapshot_allocation_state, _restore_allocation_state,
)
from eve_pi.optimizer.feasibility import build_feasibility_matrix


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
    # Set P2 prices very high relative to P1 to make chains profitable after opportunity cost
    market = _make_fake_market()
    # Lower P1 prices
    for p1_name in market:
        if market[p1_name].buy_price < 1000:
            market[p1_name] = MarketData(
                type_id=0, name=p1_name, buy_price=100,
                sell_orders=[{"price": 95, "volume_remain": 100000}],
            )
    # Raise P2 prices very high
    for p2_name in ["Coolant", "Construction Blocks", "Enriched Uranium",
                     "Mechanical Parts", "Rocket Fuel", "Superconductors"]:
        if p2_name in market:
            market[p2_name] = MarketData(
                type_id=0, name=p2_name, buy_price=100000,
                sell_orders=[{"price": 95000, "volume_remain": 100000}],
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


def test_colony_count_never_exceeds_limit():
    """With many characters and planets, total colonies must not exceed the limit."""
    gd = GameData.load()
    system = SolarSystem(name="BigSystem", system_id=99980, planets=[
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Barren", "Barren", "Barren",
            "Gas", "Gas",
            "Temperate", "Temperate",
            "Lava", "Plasma", "Ice", "Storm",
        ], start=1)
    ])
    market = _make_fake_market()
    # 14 characters × 6 planets = 84 colony slots
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(14)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=0, cargo_capacity_m3=0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    max_allowed = sum(c.max_planets for c in characters)
    assert len(result.assignments) <= max_allowed, (
        f"Allocated {len(result.assignments)} colonies but limit is {max_allowed}"
    )


def test_p2_to_p3_chain_opportunity_cost():
    """P2->P3 chains should be less profitable after opportunity cost subtraction."""
    gd = GameData.load()
    system = SolarSystem(name="TestOppCost", system_id=99970, planets=[
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Gas", "Gas", "Gas", "Gas", "Gas",
            "Lava", "Lava", "Lava",
            "Barren", "Barren",
            "Temperate", "Temperate",
            "Plasma", "Plasma",
        ], start=1)
    ])
    market = _make_fake_market()
    # Set P3 prices to a moderate level — high enough that chains are built,
    # but low enough that opportunity cost could eliminate marginal ones
    for p3_name in ["Robotics", "Guidance Systems"]:
        market[p3_name] = MarketData(
            type_id=0, name=p3_name, buy_price=200000,
            sell_orders=[{"price": 190000, "volume_remain": 100000}],
        )
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(10)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=0, cargo_capacity_m3=0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    # Any P2->P3 chain that was allocated should have positive ISK/day
    # (chains that went negative after opp cost are excluded)
    for a in result.assignments:
        if a.setup == SetupType.P2_TO_P3:
            assert a.isk_per_day > 0, f"P2->P3 chain {a.product} has non-positive ISK/day"
    # The P2->P3 chains should have lower ISK/colony than without opportunity cost.
    # We verify this indirectly: if P3 prices are set just barely above P1 standalone value,
    # chains should NOT appear. Set P3 low to verify.
    market_low = dict(market)
    for p3_name in ["Robotics", "Guidance Systems"]:
        market_low[p3_name] = MarketData(
            type_id=0, name=p3_name, buy_price=5000,
            sell_orders=[{"price": 4750, "volume_remain": 100000}],
        )
    result_low = optimize(constraints, market_low, gd)
    p3_low = [a for a in result_low.assignments if a.setup == SetupType.P2_TO_P3]
    assert len(p3_low) == 0, (
        f"Low-price P3 chains should be eliminated by opportunity cost but got: "
        f"{[(a.product, a.isk_per_day) for a in p3_low]}"
    )


def test_opportunity_cost_lookup_populated():
    """The lookup should have an entry for each planet type with viable standalone/chain units."""
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name="Char1", ccu_level=5, max_planets=6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=2, cargo_capacity_m3=60000, tax_rate=0.05,
    )
    matrix = build_feasibility_matrix(system, 5, gd)
    scored = _score_options(matrix, constraints, market, gd)
    units = _build_production_units(scored, constraints, market, gd, matrix)
    lookup = _build_opportunity_cost_lookup(units)
    # Test system has Barren, Gas, Lava, Temperate, Ice — all should have entries
    assert len(lookup) > 0
    for planet_type_name, isk_per_colony in lookup.items():
        assert isk_per_colony > 0, f"{planet_type_name} has non-positive opportunity cost"
    # Every planet type in the system should appear (all have viable P1 extraction)
    system_types = {p.planet_type.name for p in system.planets}
    for pt in system_types:
        assert pt in lookup, f"Missing planet type {pt} in opportunity cost lookup"


def test_p3_to_p4_chain_opportunity_cost():
    """P3->P4 chains with low P4 prices should be eliminated by opportunity cost."""
    gd = GameData.load()
    # Need Barren or Temperate for P4 factory, plus enough diversity for full chain
    system = SolarSystem(name="TestP4Opp", system_id=99960, planets=[
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Gas", "Gas", "Gas", "Gas",
            "Lava", "Lava", "Lava",
            "Barren", "Barren", "Barren",
            "Temperate", "Temperate",
            "Plasma", "Plasma",
            "Ice",
        ], start=1)
    ])
    market = _make_fake_market()
    # Set P4 price low — should not be worth building after opportunity cost
    market["Broadcast Node"] = MarketData(
        type_id=0, name="Broadcast Node", buy_price=50000,
        sell_orders=[{"price": 47500, "volume_remain": 100000}],
    )
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(10)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=0, cargo_capacity_m3=0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)
    p4_assignments = [a for a in result.assignments if a.setup == SetupType.P3_TO_P4]
    assert len(p4_assignments) == 0, (
        f"Low-price P4 chains should be eliminated by opportunity cost but got: "
        f"{[(a.product, a.isk_per_day) for a in p4_assignments]}"
    )


def test_swap_pass_improves_shipped_isk():
    """When volume-constrained, swap pass should replace high-volume colonies with
    multiple low-volume colonies for more total shipped ISK."""
    gd = GameData.load()
    # System with Temperate (high ISK/colony R0->P1) and Plasma (R0->P2 lower ISK but tiny volume)
    system = SolarSystem(name="SwapTest", system_id=99950, planets=[
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Temperate", "Temperate", "Temperate",
            "Plasma", "Plasma", "Plasma",
            "Barren", "Barren",
            "Gas", "Gas",
            "Lava", "Lava",
        ], start=1)
    ])
    market = _make_fake_market()
    # Many characters = many colony slots, tight volume budget
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(6)]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=1, cargo_capacity_m3=20000, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)

    shipped = [a for a in result.assignments if a.category == "ship"]
    stockpiled = [a for a in result.assignments if a.category == "stockpile"]

    # With a tight volume budget (20,000 m3/week = ~2,857 m3/day), a single R0->P1
    # colony uses ~1,824 m3/day. The swap pass should find that replacing it with
    # many R0->P2 colonies (90 m3/day each) yields more total ISK.
    # Verify: shipped set should contain R0->P2 colonies if swap was effective.
    r0_p2_shipped = [a for a in shipped if a.setup == SetupType.R0_TO_P2]
    r0_p1_shipped = [a for a in shipped if a.setup == SetupType.R0_TO_P1]

    # The swap should have included at least some R0->P2 in shipped
    # (without swap pass, pure ISK/colony would only ship R0->P1)
    total_shipped_isk = sum(a.isk_per_day for a in shipped)
    assert total_shipped_isk > 0

    # With such a tight budget, we expect the swap pass to have replaced at least
    # one R0->P1 with multiple R0->P2 colonies
    assert len(r0_p2_shipped) > 0, (
        f"Expected R0->P2 in shipped set after swap optimization but got: "
        f"{[(a.product, a.setup.value, a.isk_per_day, a.volume_per_day) for a in shipped]}"
    )


def test_snapshot_restore_allocation_state():
    """Snapshot and restore should preserve allocation state exactly."""
    from eve_pi.optimizer.allocator import OptimizationResult, ColonyAssignment
    from eve_pi.capacity.planet_capacity import SetupType

    result = OptimizationResult()
    result.assignments.append(ColonyAssignment(
        planet_id=1, planet_type="Temperate", setup=SetupType.R0_TO_P1,
        product="Industrial Fibers", num_factories=18, isk_per_day=4000000,
        volume_per_day=1824, category="ship", character="Char1",
    ))
    planet_character_map = {1: {"Char1"}}
    character_colony_counts = {"Char1": 1, "Char2": 0}
    feeder_p1_colonies = {("Biomass", SetupType.R0_TO_P1): 2}

    snapshot = _snapshot_allocation_state(result, planet_character_map,
                                          character_colony_counts, feeder_p1_colonies)

    # Mutate everything
    result.assignments.clear()
    planet_character_map[1].add("Char2")
    planet_character_map[99] = {"Char2"}
    character_colony_counts["Char1"] = 5
    character_colony_counts["Char2"] = 3
    feeder_p1_colonies[("Biomass", SetupType.R0_TO_P1)] = 10

    _restore_allocation_state(snapshot, result, planet_character_map,
                               character_colony_counts, feeder_p1_colonies)

    assert len(result.assignments) == 1
    assert result.assignments[0].product == "Industrial Fibers"
    assert planet_character_map == {1: {"Char1"}}
    assert character_colony_counts == {"Char1": 1, "Char2": 0}
    assert feeder_p1_colonies == {("Biomass", SetupType.R0_TO_P1): 2}


def test_swap_pass_noop_unlimited_hauling():
    """With unlimited hauling, swap pass should not run — results are identical."""
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    characters = [Character(name=f"Char{i}", ccu_level=5, max_planets=6) for i in range(6)]

    # Unlimited hauling: trips=0, cargo=0
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=0, cargo_capacity_m3=0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)

    # With unlimited hauling, no colonies should be stockpiled — everything ships
    stockpiled = [a for a in result.assignments if a.category == "stockpile"]
    assert len(stockpiled) == 0, (
        f"Unlimited hauling should have no stockpiled colonies but got: "
        f"{[(a.product, a.setup.value) for a in stockpiled]}"
    )


def test_ccu_correction_adjusts_profit():
    """Characters with lower CCU should show lower ISK/day than max CCU characters."""
    gd = GameData.load()
    system = _make_test_system(gd)
    market = _make_fake_market()
    # Mix of CCU levels: one CCU4, one CCU5
    characters = [
        Character(name="LowCCU", ccu_level=4, max_planets=5),
        Character(name="HighCCU", ccu_level=5, max_planets=5),
    ]
    constraints = OptimizationConstraints(
        system=system, characters=characters, mode="self_sufficient",
        cycle_days=4.0, hauling_trips_per_week=0, cargo_capacity_m3=0, tax_rate=0.05,
    )
    result = optimize(constraints, market, gd)

    # Find assignments on the same planet with different characters
    low_assignments = [a for a in result.assignments if a.character == "LowCCU" and a.isk_per_day > 0]
    high_assignments = [a for a in result.assignments if a.character == "HighCCU" and a.isk_per_day > 0]
    assert len(low_assignments) > 0
    assert len(high_assignments) > 0

    # Find a planet that has both a CCU4 and CCU5 assignment with the same setup
    for low in low_assignments:
        for high in high_assignments:
            if low.planet_id == high.planet_id and low.setup == high.setup and low.product == high.product:
                # CCU4 should have fewer factories and lower ISK
                assert low.num_factories <= high.num_factories, (
                    f"CCU4 should have <= factories than CCU5 on same planet: "
                    f"{low.num_factories} vs {high.num_factories}"
                )
                if low.num_factories < high.num_factories:
                    assert low.isk_per_day < high.isk_per_day, (
                        f"CCU4 with fewer factories should have lower ISK: "
                        f"{low.isk_per_day} vs {high.isk_per_day}"
                    )
                return  # found a matching pair, test passes

    # If no same-planet pair found, just verify CCU4 assignments have reasonable factory counts
    from eve_pi.capacity.planet_capacity import can_fit
    planet_radii = {p.planet_id: p.radius_km for p in system.planets}
    for a in low_assignments:
        radius = planet_radii.get(a.planet_id)
        if radius:
            _, expected_factories, _ = can_fit(radius, 4, a.setup, gd, a.product, 4.0)
            assert a.num_factories == expected_factories, (
                f"CCU4 assignment should have {expected_factories} factories but has {a.num_factories}"
            )
