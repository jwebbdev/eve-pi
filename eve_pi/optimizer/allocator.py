"""Colony allocation optimizer. Greedy allocation with feasibility-first approach."""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.data.loader import GameData
from eve_pi.extraction.yield_calc import yield_ratio_vs_baseline
from eve_pi.market.esi import MarketData
from eve_pi.models.characters import Character
from eve_pi.models.planets import SolarSystem
from eve_pi.optimizer.feasibility import FeasibleOption, build_feasibility_matrix
from eve_pi.optimizer.profitability import (
    calculate_extraction_profit, calculate_factory_profit, calculate_r0_p2_profit,
)
from eve_pi.optimizer.supply_chain import get_supply_requirements


@dataclass
class OptimizationConstraints:
    system: SolarSystem
    characters: List[Character]
    mode: str  # "self_sufficient", "import", "hybrid"
    cycle_days: float = 4.0
    hauling_trips_per_week: int = 2
    cargo_capacity_m3: float = 60000.0
    tax_rate: float = 0.05

    @property
    def total_colonies(self) -> int:
        return sum(c.max_planets for c in self.characters)

    @property
    def max_volume_per_week(self) -> float:
        return self.hauling_trips_per_week * self.cargo_capacity_m3

    @property
    def max_volume_per_day(self) -> float:
        return self.max_volume_per_week / 7.0


@dataclass
class ColonyAssignment:
    planet_id: int
    planet_type: str
    setup: SetupType
    product: str
    num_factories: int
    isk_per_day: float
    volume_per_day: float
    details: str = ""
    category: str = "ship"  # "ship", "feed", "stockpile"
    feeds: str = ""  # for feed colonies: what they're feeding, e.g. "-> Coolant factory"


@dataclass
class OptimizationResult:
    assignments: List[ColonyAssignment] = field(default_factory=list)
    total_isk_per_day: float = 0.0
    total_volume_per_day: float = 0.0

    @property
    def total_isk_per_week(self) -> float:
        return self.total_isk_per_day * 7

    @property
    def total_volume_per_week(self) -> float:
        return self.total_volume_per_day * 7

    @property
    def shipped_assignments(self) -> List[ColonyAssignment]:
        return [a for a in self.assignments if a.category == "ship"]

    @property
    def shipped_isk_per_day(self) -> float:
        return sum(a.isk_per_day for a in self.shipped_assignments)

    @property
    def shipped_isk_per_week(self) -> float:
        return self.shipped_isk_per_day * 7

    @property
    def shipped_volume_per_day(self) -> float:
        return sum(a.volume_per_day for a in self.shipped_assignments)

    @property
    def shipped_volume_per_week(self) -> float:
        return self.shipped_volume_per_day * 7

    @property
    def stockpile_assignments(self) -> List[ColonyAssignment]:
        return [a for a in self.assignments if a.category == "stockpile"]

    @property
    def stockpile_isk_per_day(self) -> float:
        return sum(a.isk_per_day for a in self.stockpile_assignments)

    @property
    def feed_assignments(self) -> List[ColonyAssignment]:
        return [a for a in self.assignments if a.category == "feed"]


def optimize(
    constraints: OptimizationConstraints,
    market_data: Dict[str, MarketData],
    game_data: GameData,
) -> OptimizationResult:
    """Main optimization entry point."""
    ccu_level = max(c.ccu_level for c in constraints.characters)
    matrix = build_feasibility_matrix(constraints.system, ccu_level, game_data)
    scored = _score_options(matrix, constraints, market_data, game_data)
    if constraints.mode == "self_sufficient":
        return _allocate_self_sufficient(scored, constraints, market_data, game_data, matrix)
    else:
        return _allocate_import(scored, constraints)


@dataclass
class ScoredOption:
    option: FeasibleOption
    isk_per_day: float
    isk_per_colony: float
    volume_per_day: float


def _score_options(matrix, constraints, market_data, game_data):
    scored = []
    for opt in matrix:
        if opt.setup == SetupType.R0_TO_P1:
            r0_name = game_data.r0_for_p1(opt.product)
            rate = game_data.default_extraction_rates.get(r0_name, 60000)
            profit = calculate_extraction_profit(
                p1_name=opt.product, market_data=market_data,
                extraction_rate_r0_per_hour=rate, cycle_days=constraints.cycle_days,
                num_factories=opt.max_factories, tax_rate=constraints.tax_rate, game_data=game_data,
            )
            scored.append(ScoredOption(option=opt, isk_per_day=profit, isk_per_colony=profit,
                                       volume_per_day=opt.output_volume_per_day))
        elif opt.setup == SetupType.R0_TO_P2:
            profit = calculate_r0_p2_profit(
                p2_name=opt.product, market_data=market_data,
                extraction_rate_r0_per_hour=12000, cycle_days=constraints.cycle_days,
                tax_rate=constraints.tax_rate, game_data=game_data,
            )
            scored.append(ScoredOption(option=opt, isk_per_day=profit, isk_per_colony=profit,
                                       volume_per_day=opt.output_volume_per_day))
        elif opt.setup in (SetupType.P1_TO_P2, SetupType.P2_TO_P3, SetupType.P3_TO_P4):
            profit = calculate_factory_profit(
                product_name=opt.product, setup=opt.setup, num_factories=opt.max_factories,
                market_data=market_data, tax_rate=constraints.tax_rate, game_data=game_data,
            )
            scored.append(ScoredOption(option=opt, isk_per_day=profit, isk_per_colony=profit,
                                       volume_per_day=opt.output_volume_per_day))
    scored = [s for s in scored if s.isk_per_day > 0]
    scored.sort(key=lambda s: s.isk_per_colony, reverse=True)
    return scored


def _allocate_import(scored, constraints):
    result = OptimizationResult()
    colonies_used = 0
    volume_used = 0.0
    max_colonies = constraints.total_colonies
    max_volume = constraints.max_volume_per_day
    allocated_products = set()
    for s in scored:
        if colonies_used >= max_colonies:
            break
        if s.option.setup in (SetupType.R0_TO_P1, SetupType.R0_TO_P2):
            continue
        if s.option.product in allocated_products:
            continue
        if volume_used + s.volume_per_day > max_volume:
            continue
        result.assignments.append(ColonyAssignment(
            planet_id=s.option.planet.planet_id,
            planet_type=s.option.planet.planet_type.name,
            setup=s.option.setup, product=s.option.product,
            num_factories=s.option.max_factories,
            isk_per_day=s.isk_per_day, volume_per_day=s.volume_per_day,
            details=f"{s.option.setup.value} on {s.option.planet.planet_type.name} ({s.option.max_factories} factories)",
        ))
        colonies_used += 1
        volume_used += s.volume_per_day
        allocated_products.add(s.option.product)
    result.total_isk_per_day = sum(a.isk_per_day for a in result.assignments)
    result.total_volume_per_day = sum(a.volume_per_day for a in result.assignments)
    return result


# ---------------------------------------------------------------------------
# Self-sufficient allocation: factory chains + standalone extraction
# ---------------------------------------------------------------------------

@dataclass
class _ProductionUnit:
    """A production unit: either a standalone extraction colony or a factory chain."""
    kind: str  # "standalone" or "chain"
    # The main scored option (extraction or factory)
    factory_option: Optional[ScoredOption]
    # For chains: the feeder extraction options (one per P1 input needed)
    feeder_options: List[ScoredOption] = field(default_factory=list)
    # How many extraction colonies are needed for feeders
    feeder_colony_count: int = 0
    # Total colonies this unit consumes
    total_colonies: int = 1
    # ISK/day for the whole unit (factory revenue - no input cost for chains)
    isk_per_day: float = 0.0
    # Volume/day of the exportable output
    volume_per_day: float = 0.0
    # ISK per m3 of output (for sorting)
    isk_per_m3: float = 0.0
    # Product name
    product: str = ""
    # Setup type
    setup: SetupType = SetupType.R0_TO_P1
    # For chains: list of (p1_name, colonies_needed, best_extraction_option) per input
    feeder_details: List[Tuple] = field(default_factory=list)


def _calc_extraction_p1_per_hour(scored_opt: ScoredOption, game_data: GameData, cycle_days: float) -> float:
    """Calculate the effective P1/hour output of an extraction colony with yield decay."""
    recipe = game_data.get_recipe("r0_to_p1", scored_opt.option.product)
    if not recipe:
        return 0.0
    p1_per_hour_base = recipe.output_per_hour * scored_opt.option.max_factories
    ratio = yield_ratio_vs_baseline(program_duration_hours=cycle_days * 24)
    return p1_per_hour_base * ratio


def _build_production_units(scored, constraints, market_data, game_data, matrix):
    """Build all candidate production units: standalone extractions and P1->P2 factory chains."""
    units = []
    system = constraints.system
    system_planet_type_names = {p.planet_type.name for p in system.planets}

    # Index: best extraction option per P1 product
    extraction_by_p1: Dict[str, ScoredOption] = {}
    for s in scored:
        if s.option.setup == SetupType.R0_TO_P1 and s.isk_per_day > 0:
            if s.option.product not in extraction_by_p1 or s.isk_per_day > extraction_by_p1[s.option.product].isk_per_day:
                extraction_by_p1[s.option.product] = s

    # Step 1: Standalone extraction units (R0->P1 and R0->P2)
    seen_standalone = set()
    for s in scored:
        if s.option.setup not in (SetupType.R0_TO_P1, SetupType.R0_TO_P2):
            continue
        if s.isk_per_day <= 0:
            continue
        key = (s.option.product, s.option.setup)
        if key in seen_standalone:
            continue
        seen_standalone.add(key)
        isk_per_m3 = s.isk_per_day / s.volume_per_day if s.volume_per_day > 0 else 0.0
        unit = _ProductionUnit(
            kind="standalone",
            factory_option=s,
            total_colonies=1,
            isk_per_day=s.isk_per_day,
            volume_per_day=s.volume_per_day,
            isk_per_m3=isk_per_m3,
            product=s.option.product,
            setup=s.option.setup,
        )
        units.append(unit)

    # Step 2: P1->P2 factory chains
    # Use the raw feasibility matrix for factory options since _score_options may filter out
    # factories with negative import-mode profit (but they're profitable when inputs are free)
    factory_options_by_product: Dict[str, FeasibleOption] = {}
    for opt in matrix:
        if opt.setup == SetupType.P1_TO_P2:
            if opt.product not in factory_options_by_product or opt.max_factories > factory_options_by_product[opt.product].max_factories:
                factory_options_by_product[opt.product] = opt

    for product_name, opt in factory_options_by_product.items():
        # Create a dummy ScoredOption wrapper for the factory option
        s = ScoredOption(option=opt, isk_per_day=0.0, isk_per_colony=0.0, volume_per_day=opt.output_volume_per_day)
        recipe = game_data.get_recipe("p1_to_p2", s.option.product)
        if not recipe:
            continue
        # Calculate factory output revenue (no input cost since inputs are self-extracted)
        output_mkt = market_data.get(s.option.product)
        if not output_mkt or output_mkt.buy_price <= 0:
            continue
        num_factories = s.option.max_factories
        output_per_hour = recipe.output_per_hour * num_factories
        daily_output = output_per_hour * 24
        revenue = daily_output * output_mkt.buy_price
        export_tax = revenue * constraints.tax_rate
        chain_isk = revenue - export_tax
        if chain_isk <= 0:
            continue

        # Calculate volume/day of the P2 output
        p2_mat = game_data.materials.get(s.option.product)
        vol_per_unit = p2_mat.volume_m3 if p2_mat else 0.75
        chain_volume = daily_output * vol_per_unit

        # Figure out feeder extraction colonies needed for each P1 input
        feeder_details = []
        total_feeder_colonies = 0
        feasible = True
        feeder_options_list = []

        for input_name, qty_per_cycle in recipe.inputs:
            # P1 demand: qty_per_cycle per cycle_seconds, times num_factories
            p1_per_hour = qty_per_cycle * (3600 / recipe.cycle_seconds) * num_factories

            # Check if we can extract this P1 in this system
            r0_name = game_data.r0_for_p1(input_name)
            if not r0_name:
                feasible = False
                break
            planet_types_for_r0 = game_data.planet_types_for_r0(r0_name)
            if not any(pt in system_planet_type_names for pt in planet_types_for_r0):
                feasible = False
                break

            # Find best extraction option for this P1
            ext_opt = extraction_by_p1.get(input_name)
            if not ext_opt:
                feasible = False
                break

            # Calculate how many extraction colonies needed
            p1_per_hour_per_colony = _calc_extraction_p1_per_hour(ext_opt, game_data, constraints.cycle_days)
            if p1_per_hour_per_colony <= 0:
                feasible = False
                break
            colonies_needed = math.ceil(p1_per_hour / p1_per_hour_per_colony)
            colonies_needed = max(1, colonies_needed)

            total_feeder_colonies += colonies_needed
            feeder_details.append((input_name, colonies_needed, ext_opt))
            feeder_options_list.append(ext_opt)

        if not feasible:
            continue

        total_colonies = 1 + total_feeder_colonies  # 1 factory + N feeders
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0

        unit = _ProductionUnit(
            kind="chain",
            factory_option=s,
            feeder_options=feeder_options_list,
            feeder_colony_count=total_feeder_colonies,
            total_colonies=total_colonies,
            isk_per_day=chain_isk,
            volume_per_day=chain_volume,
            isk_per_m3=isk_per_m3,
            product=s.option.product,
            setup=s.option.setup,
            feeder_details=feeder_details,
        )
        units.append(unit)

    return units


def _allocate_self_sufficient(scored, constraints, market_data, game_data, matrix=None):
    """Allocate for self-sufficient mode with factory chains and stockpile filling."""
    result = OptimizationResult()
    max_colonies = constraints.total_colonies
    max_volume_per_day = constraints.max_volume_per_day

    if matrix is None:
        matrix = []

    # Build all candidate production units
    units = _build_production_units(scored, constraints, market_data, game_data, matrix)
    if not units:
        return result

    # Sort by ISK per m3 of output (best value density first)
    units.sort(key=lambda u: u.isk_per_m3, reverse=True)

    colonies_used = 0
    volume_used = 0.0
    allocated_products = set()
    # Track P1 extraction colonies already allocated as feeders to avoid double-counting
    # Key: p1_name -> number of feeder colonies allocated
    feeder_p1_colonies: Dict[str, int] = {}
    # Track which extraction products have standalone colonies
    standalone_extraction_products = set()
    # Track colonies per physical planet (max = num_characters per planet)
    num_characters = len(constraints.characters)
    planet_colony_counts: Dict[int, int] = {}  # planet_id -> count

    def _planet_has_slot(planet_id: int) -> bool:
        return planet_colony_counts.get(planet_id, 0) < num_characters

    def _use_planet_slot(planet_id: int):
        planet_colony_counts[planet_id] = planet_colony_counts.get(planet_id, 0) + 1

    # --- Step 2: Hauling-optimized allocation ---
    for unit in units:
        if colonies_used >= max_colonies:
            break
        if unit.product in allocated_products:
            continue
        if volume_used + unit.volume_per_day > max_volume_per_day:
            continue

        if unit.kind == "standalone":
            if colonies_used + 1 > max_colonies:
                continue
            if not _planet_has_slot(unit.factory_option.option.planet.planet_id):
                continue
            result.assignments.append(ColonyAssignment(
                planet_id=unit.factory_option.option.planet.planet_id,
                planet_type=unit.factory_option.option.planet.planet_type.name,
                setup=unit.factory_option.option.setup,
                product=unit.product,
                num_factories=unit.factory_option.option.max_factories,
                isk_per_day=unit.isk_per_day,
                volume_per_day=unit.volume_per_day,
                details=f"{unit.factory_option.option.setup.value} on {unit.factory_option.option.planet.planet_type.name}",
                category="ship",
            ))
            colonies_used += 1
            _use_planet_slot(unit.factory_option.option.planet.planet_id)
            volume_used += unit.volume_per_day
            allocated_products.add(unit.product)
            standalone_extraction_products.add(unit.product)

        elif unit.kind == "chain":
            # Check factory planet has a slot
            if not _planet_has_slot(unit.factory_option.option.planet.planet_id):
                continue

            # Calculate actual additional feeder colonies needed (sharing with existing feeders)
            # Check total planet slot availability across ALL planets that can produce each P1
            additional_feeders = 0
            feeder_plan = []
            chain_feasible = True
            for p1_name, colonies_needed, ext_opt in unit.feeder_details:
                already_allocated = feeder_p1_colonies.get(p1_name, 0)
                new_needed = max(0, colonies_needed - already_allocated)
                # Count total available slots across all planets that produce this P1
                total_available = 0
                for s in scored:
                    if s.option.setup == SetupType.R0_TO_P1 and s.option.product == p1_name:
                        total_available += num_characters - planet_colony_counts.get(s.option.planet.planet_id, 0)
                if new_needed > total_available:
                    chain_feasible = False
                    break
                additional_feeders += new_needed
                feeder_plan.append((p1_name, colonies_needed, new_needed, ext_opt))

            if not chain_feasible:
                continue

            total_new_colonies = 1 + additional_feeders  # 1 factory + new feeders
            if colonies_used + total_new_colonies > max_colonies:
                continue

            # Allocate factory colony
            result.assignments.append(ColonyAssignment(
                planet_id=unit.factory_option.option.planet.planet_id,
                planet_type=unit.factory_option.option.planet.planet_type.name,
                setup=SetupType.P1_TO_P2,
                product=unit.product,
                num_factories=unit.factory_option.option.max_factories,
                isk_per_day=unit.isk_per_day,
                volume_per_day=unit.volume_per_day,
                details=f"p1_to_p2 on {unit.factory_option.option.planet.planet_type.name} ({unit.factory_option.option.max_factories} factories)",
                category="ship",
            ))
            colonies_used += 1
            _use_planet_slot(unit.factory_option.option.planet.planet_id)

            # Allocate feeder extraction colonies, spreading across planets
            for p1_name, total_needed, new_needed, ext_opt in feeder_plan:
                # Find all extraction options for this P1 product
                p1_extraction_options = [
                    s for s in scored
                    if s.option.setup == SetupType.R0_TO_P1
                    and s.option.product == p1_name
                    and s.isk_per_day > 0
                ]
                placed = 0
                for ext in p1_extraction_options:
                    if placed >= new_needed:
                        break
                    while placed < new_needed and _planet_has_slot(ext.option.planet.planet_id):
                        result.assignments.append(ColonyAssignment(
                            planet_id=ext.option.planet.planet_id,
                            planet_type=ext.option.planet.planet_type.name,
                            setup=SetupType.R0_TO_P1,
                            product=p1_name,
                            num_factories=ext.option.max_factories,
                            isk_per_day=0.0,
                            volume_per_day=0.0,
                            details=f"r0_to_p1 on {ext.option.planet.planet_type.name} (feeding {unit.product})",
                            category="feed",
                            feeds=f"-> {unit.product} factory",
                        ))
                        colonies_used += 1
                        _use_planet_slot(ext.option.planet.planet_id)
                        placed += 1
                feeder_p1_colonies[p1_name] = feeder_p1_colonies.get(p1_name, 0) + placed
                allocated_products.add(p1_name)

            volume_used += unit.volume_per_day
            allocated_products.add(unit.product)

    # --- Step 3: Fill remaining slots with stockpile extraction ---
    if colonies_used < max_colonies:
        # Get all standalone extraction options sorted by profitability
        extraction_options = [
            s for s in scored
            if s.option.setup in (SetupType.R0_TO_P1, SetupType.R0_TO_P2)
            and s.isk_per_day > 0
        ]
        extraction_options.sort(key=lambda s: s.isk_per_day, reverse=True)
        stockpile_products = set()
        for s in extraction_options:
            if colonies_used >= max_colonies:
                break
            # Skip if already allocated as shipped or as feed
            if s.option.product in allocated_products:
                continue
            if s.option.product in stockpile_products:
                continue
            if not _planet_has_slot(s.option.planet.planet_id):
                continue
            result.assignments.append(ColonyAssignment(
                planet_id=s.option.planet.planet_id,
                planet_type=s.option.planet.planet_type.name,
                setup=s.option.setup,
                product=s.option.product,
                num_factories=s.option.max_factories,
                isk_per_day=s.isk_per_day,
                volume_per_day=s.volume_per_day,
                details=f"{s.option.setup.value} on {s.option.planet.planet_type.name}",
                category="stockpile",
            ))
            colonies_used += 1
            _use_planet_slot(s.option.planet.planet_id)
            stockpile_products.add(s.option.product)

    # Build totals: total_volume_per_day counts only shipped volume (within hauling budget)
    result.total_isk_per_day = sum(a.isk_per_day for a in result.assignments)
    result.total_volume_per_day = sum(
        a.volume_per_day for a in result.assignments if a.category == "ship"
    )
    return result
