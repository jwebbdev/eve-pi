# Multi-Tier Opportunity Cost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subtract opportunity cost from P2->P3 and P3->P4 chains so they only appear profitable when they beat each colony's best independent alternative.

**Architecture:** After building standalone P1 units (Step 1) and P1->P2 chains (Step 2), build a `best_isk_per_colony` lookup keyed by planet type name. For each colony in a P2->P3 or P3->P4 chain, look up its planet type's best ISK/colony and sum across all colonies as opportunity cost. Subtract from chain_isk before computing ISK/colony.

**Tech Stack:** Python, pytest

---

### Task 1: Build the opportunity cost lookup

**Files:**
- Modify: `eve_pi/optimizer/allocator.py:259-404` (`_build_production_units`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_allocator.py`:

```python
from eve_pi.optimizer.allocator import _build_production_units, _build_opportunity_cost_lookup, OptimizationConstraints, ScoredOption
from eve_pi.optimizer.feasibility import build_feasibility_matrix
from eve_pi.optimizer.allocator import _score_options


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_allocator.py::test_opportunity_cost_lookup_populated -v`
Expected: FAIL with `ImportError: cannot import name '_build_opportunity_cost_lookup'`

- [ ] **Step 3: Implement `_build_opportunity_cost_lookup`**

Add this function to `eve_pi/optimizer/allocator.py` after the `_build_production_units` function (after line 721):

```python
def _build_opportunity_cost_lookup(units: list) -> Dict[str, float]:
    """Build a lookup of best ISK/colony/day by planet type from standalone and chain units.

    For standalone units, the planet type comes from the unit's factory_option.
    For chain units (P1->P2), the ISK/colony is spread across all colonies, so
    the factory planet gets that ISK/colony, and each feeder's planet type also
    gets its standalone ISK/colony if it's higher.
    """
    best: Dict[str, float] = {}

    for unit in units:
        if unit.kind == "standalone":
            pt = unit.factory_option.option.planet.planet_type.name
            isk_per_colony = unit.isk_per_day / unit.total_colonies
            if isk_per_colony > best.get(pt, 0.0):
                best[pt] = isk_per_colony
        elif unit.kind == "chain" and unit.setup == SetupType.P1_TO_P2:
            # Chain ISK/colony for the factory planet type
            isk_per_colony = unit.isk_per_day / unit.total_colonies
            factory_pt = unit.factory_option.option.planet.planet_type.name
            if isk_per_colony > best.get(factory_pt, 0.0):
                best[factory_pt] = isk_per_colony

    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_opportunity_cost_lookup_populated -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add eve_pi/optimizer/allocator.py tests/test_allocator.py
git commit -m "Add opportunity cost lookup by planet type for multi-tier chains"
```

---

### Task 2: Apply opportunity cost to P2->P3 chains

**Files:**
- Modify: `eve_pi/optimizer/allocator.py:406-533` (Step 3: P2->P3 factory chains)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_allocator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_allocator.py::test_p2_to_p3_chain_opportunity_cost -v`
Expected: The low-price assertion should FAIL because without opportunity cost subtraction, even cheap P3 chains show positive ISK.

- [ ] **Step 3: Apply opportunity cost to P2->P3 chains**

In `eve_pi/optimizer/allocator.py`, in the `_build_production_units` function, modify the P2->P3 chain section. The current code at approximately line 517 has:

```python
        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0
```

Move the `_build_opportunity_cost_lookup` call to happen after Step 2 units are added but before Step 3 begins. Then apply opportunity cost in Step 3.

First, after Step 2's loop ends (after line 404, before the `# Step 3:` comment on line 406), insert:

```python
    # Build opportunity cost lookup from standalone + P1->P2 chain units
    opp_cost_lookup = _build_opportunity_cost_lookup(units)
```

Then, in the P2->P3 chain section, replace the block at lines 514-518:

```python
        if not feasible:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0
```

with:

```python
        if not feasible:
            continue

        # Subtract opportunity cost: what each colony could earn independently
        opportunity_cost = 0.0
        # Factory planet
        factory_pt = p3_opt.planet.planet_type.name
        opportunity_cost += opp_cost_lookup.get(factory_pt, 0.0)
        # All feeder colonies
        for _, colonies_needed, feeder_scored, _ in feeder_details:
            feeder_pt = feeder_scored.option.planet.planet_type.name
            opportunity_cost += opp_cost_lookup.get(feeder_pt, 0.0) * colonies_needed
        chain_isk -= opportunity_cost

        if chain_isk <= 0:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_p2_to_p3_chain_opportunity_cost -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All 85+ tests pass. The existing `test_self_sufficient_p2_to_p3_chains` test may need its P3 prices adjusted if opportunity cost now eliminates those chains. If it fails, increase the P3 prices in that test's market data to compensate.

- [ ] **Step 6: Commit**

```bash
git add eve_pi/optimizer/allocator.py tests/test_allocator.py
git commit -m "Add opportunity cost to P2->P3 chains"
```

---

### Task 3: Apply opportunity cost to P3->P4 chains

**Files:**
- Modify: `eve_pi/optimizer/allocator.py:535-719` (Step 4: P3->P4 factory chains)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_allocator.py`:

```python
def test_p3_to_p4_chain_opportunity_cost():
    """P3->P4 chains with low P4 prices should be eliminated by opportunity cost."""
    gd = GameData.load()
    # Need Barren or Temperate for P4 factory, plus enough diversity for full chain
    system = SolarSystem(name="TestP4Opp", system_id=99960, planets=[
        Planet(planet_id=i, planet_type=gd.planet_types[pt], radius_km=5000.0)
        for i, pt in enumerate([
            "Gas", "Gas", "Gas", "Gas", "Gas",
            "Lava", "Lava", "Lava",
            "Barren", "Barren", "Barren",
            "Temperate", "Temperate",
            "Plasma", "Plasma",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_allocator.py::test_p3_to_p4_chain_opportunity_cost -v`
Expected: FAIL — without opportunity cost, the P4 chain may still show positive ISK.

- [ ] **Step 3: Apply opportunity cost to P3->P4 chains**

In `eve_pi/optimizer/allocator.py`, in the P3->P4 chain section, replace the block at lines 700-704:

```python
        if not feasible:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0
```

with:

```python
        if not feasible:
            continue

        # Subtract opportunity cost: what each colony could earn independently
        opportunity_cost = 0.0
        # Factory planet (P3->P4)
        factory_pt = p4_opt.planet.planet_type.name
        opportunity_cost += opp_cost_lookup.get(factory_pt, 0.0)
        # All feeder colonies
        for _, colonies_needed, feeder_scored, _ in feeder_details:
            feeder_pt = feeder_scored.option.planet.planet_type.name
            opportunity_cost += opp_cost_lookup.get(feeder_pt, 0.0) * colonies_needed
        chain_isk -= opportunity_cost

        if chain_isk <= 0:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_p3_to_p4_chain_opportunity_cost -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add eve_pi/optimizer/allocator.py tests/test_allocator.py
git commit -m "Add opportunity cost to P3->P4 chains"
```

---

### Task 4: Update design spec open items

**Files:**
- Modify: `docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md`

- [ ] **Step 1: Mark item 2 as done in the Open Items section**

In `docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md`, change line 103:

```
2. Opportunity cost on P2→P3 and P3→P4 chains (currently only P1→P2)
```

to:

```
2. ~~Opportunity cost on P2→P3 and P3→P4 chains~~ (done — flat per-colony lookup from standalone + P1→P2 units)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md
git commit -m "Mark multi-tier opportunity cost as complete in design spec"
```
