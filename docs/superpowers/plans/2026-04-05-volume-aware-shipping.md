# Volume-Aware Shipping Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When volume-constrained, swap high-volume/low-ISK-per-m³ shipped colonies for multiple low-volume colonies to maximize total shipped ISK.

**Architecture:** After the existing shipping pass (Pass 1), add a swap pass (Pass 2) that iteratively tries removing the worst ISK/m³ shipped colony and re-filling the freed volume + all free slots by ISK/m³. Uses snapshot/restore of allocation state to test swaps without permanent side effects. Only runs when hauling is constrained.

**Tech Stack:** Python, pytest

---

## File Structure

- `eve_pi/optimizer/allocator.py` — All changes go here. Add `_swap_optimize_shipping()` function and call it from `_allocate_self_sufficient()`. The file is already large (~1200 lines) but the swap pass is tightly coupled to the allocation state (`planet_character_map`, `character_colony_counts`, etc.) so keeping it in the same file avoids exposing internals.
- `tests/test_allocator.py` — New tests for swap optimization.

---

### Task 1: Add allocation state snapshot/restore helpers

**Files:**
- Modify: `eve_pi/optimizer/allocator.py`
- Test: `tests/test_allocator.py`

The swap pass needs to try a swap, check if it improves ISK, and roll back if it doesn't. We need helpers to snapshot and restore the mutable allocation state.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_allocator.py`:

```python
from eve_pi.optimizer.allocator import _snapshot_allocation_state, _restore_allocation_state


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_allocator.py::test_snapshot_restore_allocation_state -v`
Expected: FAIL with `ImportError: cannot import name '_snapshot_allocation_state'`

- [ ] **Step 3: Implement snapshot/restore**

Add to `eve_pi/optimizer/allocator.py` after the `_build_opportunity_cost_lookup` function (after line ~776):

```python
import copy


def _snapshot_allocation_state(result, planet_character_map, character_colony_counts,
                                feeder_p1_colonies):
    """Snapshot the mutable allocation state for rollback."""
    return {
        "assignments": list(result.assignments),
        "planet_character_map": {k: set(v) for k, v in planet_character_map.items()},
        "character_colony_counts": dict(character_colony_counts),
        "feeder_p1_colonies": dict(feeder_p1_colonies),
    }


def _restore_allocation_state(snapshot, result, planet_character_map,
                                character_colony_counts, feeder_p1_colonies):
    """Restore allocation state from a snapshot."""
    result.assignments[:] = snapshot["assignments"]
    planet_character_map.clear()
    planet_character_map.update({k: set(v) for k, v in snapshot["planet_character_map"].items()})
    character_colony_counts.clear()
    character_colony_counts.update(snapshot["character_colony_counts"])
    feeder_p1_colonies.clear()
    feeder_p1_colonies.update(snapshot["feeder_p1_colonies"])
```

Note: add `import copy` at the top of the file if not already there (it's not currently imported, but we don't actually need it — the manual copies above are sufficient and more explicit).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_snapshot_restore_allocation_state -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (88 existing + 1 new = 89).

- [ ] **Step 6: Commit**

```bash
git add eve_pi/optimizer/allocator.py tests/test_allocator.py
git commit -m "Add allocation state snapshot/restore helpers for swap optimization"
```

---

### Task 2: Implement the swap optimization pass

**Files:**
- Modify: `eve_pi/optimizer/allocator.py`
- Test: `tests/test_allocator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_allocator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_allocator.py::test_swap_pass_improves_shipped_isk -v`
Expected: FAIL — without the swap pass, the shipping pass only picks the highest ISK/colony units (R0→P1) and no R0→P2 gets shipped.

- [ ] **Step 3: Implement `_swap_optimize_shipping`**

Add to `eve_pi/optimizer/allocator.py` after the `_restore_allocation_state` function:

```python
def _swap_optimize_shipping(result, units, scored, matrix, game_data,
                             planet_character_map, character_colony_counts,
                             feeder_p1_colonies, constraints):
    """Pass 2: Swap high-volume shipped colonies for multiple low-volume ones.

    Iteratively removes the worst ISK/m³ shipped colony and re-fills
    the freed volume (plus any unallocated slots) by ISK/m³ descending.
    Accepts the swap if total shipped ISK increases, otherwise restores
    and stops.
    """
    max_volume_per_day = constraints.max_volume_per_day

    # Sort units by ISK/m³ for the fill phase
    units_by_isk_per_m3 = sorted(
        [u for u in units if u.volume_per_day > 0],
        key=lambda u: u.isk_per_day / u.volume_per_day,
        reverse=True,
    )

    improved = True
    while improved:
        improved = False

        # Find shipped colonies sorted by ISK/m³ ascending (worst first)
        shipped = [a for a in result.assignments if a.category == "ship"]
        if not shipped:
            break

        shipped_by_efficiency = sorted(
            shipped,
            key=lambda a: a.isk_per_day / a.volume_per_day if a.volume_per_day > 0 else float('inf'),
        )

        for candidate in shipped_by_efficiency:
            # Snapshot state before attempting swap
            snapshot = _snapshot_allocation_state(result, planet_character_map,
                                                  character_colony_counts, feeder_p1_colonies)
            old_shipped_isk = sum(a.isk_per_day for a in result.assignments if a.category == "ship")

            # Remove candidate and all its feeders from allocations
            candidate_planet_id = candidate.planet_id
            candidate_character = candidate.character
            candidate_volume = candidate.volume_per_day

            # Find all assignments related to this shipped colony
            # (the colony itself + any feed colonies that reference its product)
            to_remove = [candidate]
            # If this is a chain factory, find its feeders
            if candidate.category == "ship":
                feed_label = f"-> {candidate.product} factory"
                to_remove.extend(
                    a for a in result.assignments
                    if a.category == "feed" and a.feeds == feed_label
                )

            # Deallocate each removed assignment
            for a in to_remove:
                if a in result.assignments:
                    result.assignments.remove(a)
                    if a.planet_id in planet_character_map and a.character in planet_character_map[a.planet_id]:
                        planet_character_map[a.planet_id].discard(a.character)
                        if not planet_character_map[a.planet_id]:
                            del planet_character_map[a.planet_id]
                    character_colony_counts[a.character] -= 1
                    # Update feeder tracking
                    if a.category == "feed":
                        key = (a.product, a.setup)
                        if key in feeder_p1_colonies:
                            feeder_p1_colonies[key] = max(0, feeder_p1_colonies[key] - 1)

            # Calculate freed volume and current shipped volume
            current_shipped_volume = sum(
                a.volume_per_day for a in result.assignments if a.category == "ship"
            )
            available_volume = max_volume_per_day - current_shipped_volume

            # Fill freed volume by ISK/m³ with all available units
            for unit in units_by_isk_per_m3:
                if sum(character_colony_counts.values()) >= constraints.total_colonies:
                    break
                while sum(character_colony_counts.values()) < constraints.total_colonies:
                    if unit.volume_per_day > available_volume:
                        break
                    used = _try_allocate_unit(
                        unit, result, "ship", scored, matrix, game_data,
                        planet_character_map, character_colony_counts,
                        constraints, feeder_p1_colonies,
                    )
                    if used > 0:
                        available_volume -= unit.volume_per_day
                    else:
                        break

            new_shipped_isk = sum(a.isk_per_day for a in result.assignments if a.category == "ship")

            if new_shipped_isk > old_shipped_isk:
                # Swap improved things — accept and try again
                improved = True
                break  # restart the while loop with new shipped set
            else:
                # Swap didn't help — restore and try next candidate
                _restore_allocation_state(snapshot, result, planet_character_map,
                                          character_colony_counts, feeder_p1_colonies)
                continue

        # If we tried all candidates and none improved, improved stays False and we exit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_swap_pass_improves_shipped_isk -v`
Expected: FAIL — we haven't wired it into `_allocate_self_sufficient` yet. Proceed to step 5.

- [ ] **Step 5: Wire swap pass into `_allocate_self_sufficient`**

In `eve_pi/optimizer/allocator.py`, in `_allocate_self_sufficient`, insert the swap pass call between the shipping pass (step 4) and the stockpile pass (step 5). Find the line:

```python
    # 5. Stockpile pass: fill remaining slots ignoring volume, same approach as shipping
```

Insert before it:

```python
    # 5. Swap optimization pass: when volume-constrained, try replacing high-volume
    #    shipped colonies with multiple low-volume ones for more total shipped ISK
    if not constraints.volume_unlimited:
        _swap_optimize_shipping(result, units, scored, matrix, game_data,
                                 planet_character_map, character_colony_counts,
                                 feeder_p1_colonies, constraints)

```

Update the stockpile pass comment from `# 5.` to `# 6.`:

```python
    # 6. Stockpile pass: fill remaining slots ignoring volume, same approach as shipping
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_allocator.py::test_swap_pass_improves_shipped_isk -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. Existing tests that use unlimited hauling should be unaffected. Tests with volume constraints may see different (improved) allocations — verify they still pass or adjust expectations.

- [ ] **Step 8: Commit**

```bash
git add eve_pi/optimizer/allocator.py tests/test_allocator.py
git commit -m "Add swap optimization pass for volume-constrained shipping"
```

---

### Task 3: Test swap pass is a no-op for unlimited hauling

**Files:**
- Test: `tests/test_allocator.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_allocator.py`:

```python
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
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_allocator.py::test_swap_pass_noop_unlimited_hauling -v`
Expected: PASS (swap pass is skipped via `if not constraints.volume_unlimited`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_allocator.py
git commit -m "Add test verifying swap pass is no-op for unlimited hauling"
```

---

### Task 4: Update design spec open items

**Files:**
- Modify: `docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md`

- [ ] **Step 1: Mark item 1 as done**

In `docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md`, change line 103:

```
1. Hauling budget as knapsack problem — chains compress volume, should be preferred when volume-constrained
```

to:

```
1. ~~Hauling budget as knapsack problem~~ (done — swap optimization pass replaces high-volume shipped colonies with multiple low-volume ones)
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-04-eve-pi-optimizer-rewrite-design.md
git commit -m "Mark hauling budget optimization as complete in design spec"
```
