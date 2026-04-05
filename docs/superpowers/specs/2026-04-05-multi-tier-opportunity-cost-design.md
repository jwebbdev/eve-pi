# Multi-Tier Opportunity Cost for Allocator

## Problem

The allocator subtracts opportunity cost for P1->P2 chains (what feeder extraction colonies could earn selling P1 directly), but P2->P3 and P3->P4 chains have no opportunity cost adjustment. This makes higher-tier chains appear more profitable than they really are, because the colonies dedicated to feeding them could earn ISK independently.

## Approach: Flat Per-Colony Opportunity Cost

After building standalone P1 units (Step 1) and P1->P2 chain units (Step 2), build a lookup of the best ISK/colony achievable per planet type. For each colony in a P2->P3 or P3->P4 chain, look up that colony's planet type in the lookup and sum the opportunity cost across all colonies. Subtract from chain ISK/day.

### Lookup Construction

Built once after Step 2 completes, before Step 3 begins.

For each scored unit (standalone or chain), compute ISK/colony. Group by planet type. Keep the max ISK/colony per planet type.

- Standalone P1 units contribute their own ISK/colony for their planet type.
- P1->P2 chain units contribute their ISK/colony (already opportunity-cost-adjusted) for the factory planet's type. The feeder extraction colonies in those chains also establish values for their respective planet types.

Result: `best_isk_per_colony: Dict[str, float]` mapping planet type name to best ISK/colony/day.

### Application to P2->P3 Chains (Step 3)

For each P2->P3 chain candidate:

1. Identify all colonies: 1 P2->P3 factory + N P1->P2 intermediate factories + M extraction feeders.
2. For each colony, look up `best_isk_per_colony[planet_type]`. If a planet type has no entry (no viable standalone/chain option), use 0.
3. Sum all looked-up values = total opportunity cost.
4. Subtract from chain_isk: `chain_isk -= total_opportunity_cost`.
5. If chain_isk <= 0, skip the chain.

### Application to P3->P4 Chains (Step 4)

Same as P2->P3. Every colony in the chain (P3->P4 factory, P2->P3 intermediate factories, P1->P2 intermediate factories, extraction feeders) gets its opportunity cost looked up and summed.

### What Doesn't Change

- P1->P2 chain opportunity cost (Step 2) stays as-is. It already correctly subtracts feeder P1 standalone value.
- Fill-then-next allocation logic.
- Sorting by ISK/colony/day.
- Manufacturing needs / minimal chain builder (separate code path).

## Edge Cases

- **Planet type not in lookup**: Colony has no viable alternative. Opportunity cost = 0 for that colony.
- **Chain ISK goes negative**: Chain is not worth building. Skip it (already handled by existing `if chain_isk <= 0: continue`).
- **Factory planet opportunity cost**: The factory planet itself has an alternative use (e.g., standalone P1 or a P1->P2 chain). Its opportunity cost is included, same as any other colony in the chain.

## Testing

- Existing tests should continue to pass (P1->P2 opportunity cost unchanged).
- New tests: verify P2->P3 and P3->P4 chains have lower ISK/colony after opportunity cost subtraction.
- Verify a chain that looked profitable without opportunity cost gets skipped when feeders have high standalone value.
