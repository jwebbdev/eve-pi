# Volume-Aware Shipping Optimization (Knapsack)

## Problem

The current allocator sorts production units by ISK/colony/day and greedily fills the shipping budget. This is optimal when hauling is unlimited, but when volume-constrained, it leads to suboptimal results. High-ISK/colony products like R0→P1 (e.g., Industrial Fibers at 4M ISK/day, 1,824 m³/day) consume disproportionate volume compared to R0→P2 products (e.g., Enriched Uranium at 700K ISK/day, 90 m³/day). One R0→P1 colony uses the volume of ~20 R0→P2 colonies but only earns ~6x more. Colonies that could ship profitably are instead stockpiled because volume budget is exhausted by high-volume products.

Real example: 9 Industrial Fibers colonies fill nearly all 120,000 m³/week budget, leaving 15 colonies stockpiled. Swapping 1 IF for ~15 R0→P2 colonies would net +6.4M ISK/day.

## Solution: Two-Pass Shipping with Swap Optimization

### When It Applies

Only when volume is constrained (`hauling_trips_per_week > 0` and `cargo_capacity_m3 > 0`). Unlimited hauling keeps the existing ISK/colony greedy approach unchanged.

### Pass 1: Greedy ISK/Colony Fill (Existing)

Sort production units by ISK/colony/day descending. Greedily allocate to shipping until volume budget is full. This produces the baseline shipped set — the current behavior.

### Pass 2: Swap Optimization (New)

1. Sort shipped colonies by ISK/m³ ascending (worst volume efficiency first).
2. Pop the worst ISK/m³ shipped colony. Fully deallocate it — release the character slot(s), planet slot(s), and freed volume. If the unit is a chain, all feeder colonies are also freed.
3. Collect ALL free colony slots: the freed slot(s) from step 2 + any previously unallocated slots (would-be stockpile slots). These are unconstrained character slots — not bound to any planet, just limited by available planets in the system and already-allocated planets.
4. From the full production unit list, greedily fill the freed volume by ISK/m³ descending. All unit types are eligible: standalone R0→P1, R0→P2, P1→P2 chains, P2→P3 chains, P3→P4 chains. Units are allocated normally — any available planet/character combination, respecting existing allocations.
5. Compare total shipped ISK/day (new set vs. before the swap):
   - If ISK increases: accept the swap. Re-sort shipped colonies by ISK/m³ and repeat from step 1.
   - If ISK does not increase: restore the popped colony, stop the swap pass. Shipping is finalized.
6. If all would-be stockpile slots are consumed during swaps, skip the stockpile pass.

### Pass 3: Stockpile Fill (Existing)

Only runs if there are unallocated slots remaining after Pass 2. Fills remaining slots ignoring volume, sorted by ISK/colony. Unchanged from current behavior.

## What Doesn't Change

- Production unit building (`_build_production_units`)
- Opportunity cost calculations (P1→P2, P2→P3, P3→P4)
- Manufacturing pass (priority allocation)
- Unlimited hauling mode (pure ISK/colony)
- Scoring and feasibility logic

## Edge Cases

- **Chain units in swap:** When a chain is popped, all its colonies (factory + feeders) are freed. When filling by ISK/m³, chains can also be selected — they consume multiple free slots but may have excellent ISK/m³.
- **No improving swap found on first try:** Pass 2 exits immediately, results are identical to current behavior. This is the common case when volume isn't a bottleneck.
- **All slots consumed by shipping:** Stockpile pass is skipped entirely. Every colony is shipping.
- **Manufacturing colonies:** Never swapped. Pass 2 only considers colonies allocated in the shipping pass.

## Testing

- Existing tests should pass unchanged (most use unlimited hauling or don't hit the swap threshold).
- New test: volume-constrained scenario where ISK/colony sort produces suboptimal shipping, verify swap pass improves total shipped ISK.
- New test: verify swap pass is a no-op when volume is unlimited.
- New test: verify a chain unit can be selected during the ISK/m³ fill in Pass 2.
