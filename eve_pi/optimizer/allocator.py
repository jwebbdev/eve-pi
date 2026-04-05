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
class ManufacturingNeed:
    product: str
    quantity_per_week: int


@dataclass
class OptimizationConstraints:
    system: SolarSystem
    characters: List[Character]
    mode: str  # "self_sufficient", "import", "hybrid"
    cycle_days: float = 4.0
    hauling_trips_per_week: int = 2
    cargo_capacity_m3: float = 60000.0
    tax_rate: float = 0.05
    manufacturing_needs: List[ManufacturingNeed] = field(default_factory=list)

    @property
    def total_colonies(self) -> int:
        return sum(c.max_planets for c in self.characters)

    @property
    def volume_unlimited(self) -> bool:
        return self.hauling_trips_per_week <= 0 or self.cargo_capacity_m3 <= 0

    @property
    def max_volume_per_week(self) -> float:
        if self.volume_unlimited:
            return float('inf')
        return self.hauling_trips_per_week * self.cargo_capacity_m3

    @property
    def max_volume_per_day(self) -> float:
        if self.volume_unlimited:
            return float('inf')
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
    category: str = "ship"  # "ship", "feed", "stockpile", "manufacturing"
    feeds: str = ""  # for feed colonies: what they're feeding, e.g. "-> Coolant factory"
    character: str = ""  # assigned character name


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

    @property
    def manufacturing_assignments(self) -> List[ColonyAssignment]:
        return [a for a in self.assignments if a.category == "manufacturing"]

    @property
    def manufacturing_isk_per_day(self) -> float:
        return sum(a.isk_per_day for a in self.manufacturing_assignments)


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
    # For chains: list of (material_name, colonies_needed, scored_option, setup_type) per input
    # setup_type: SetupType.R0_TO_P1 for extraction feeders, SetupType.P1_TO_P2 for intermediate factories
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
    # No deduplication: each planet×product combo is a separate unit
    for s in scored:
        if s.option.setup not in (SetupType.R0_TO_P1, SetupType.R0_TO_P2):
            continue
        if s.isk_per_day <= 0:
            continue
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
            feeder_details.append((input_name, colonies_needed, ext_opt, SetupType.R0_TO_P1))
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

    # Step 3: P2->P3 factory chains
    # A P2->P3 chain: 1 P2->P3 factory + N P1->P2 intermediate factories + M extraction colonies
    p2_to_p3_factory_options: Dict[str, FeasibleOption] = {}
    for opt in matrix:
        if opt.setup == SetupType.P2_TO_P3:
            if opt.product not in p2_to_p3_factory_options or opt.max_factories > p2_to_p3_factory_options[opt.product].max_factories:
                p2_to_p3_factory_options[opt.product] = opt

    # Index: best P1->P2 factory option per P2 product (for intermediate factories)
    p1_to_p2_factory_by_product: Dict[str, FeasibleOption] = {}
    for opt in matrix:
        if opt.setup == SetupType.P1_TO_P2:
            if opt.product not in p1_to_p2_factory_by_product or opt.max_factories > p1_to_p2_factory_by_product[opt.product].max_factories:
                p1_to_p2_factory_by_product[opt.product] = opt

    for p3_product, p3_opt in p2_to_p3_factory_options.items():
        p3_scored = ScoredOption(option=p3_opt, isk_per_day=0.0, isk_per_colony=0.0,
                                 volume_per_day=p3_opt.output_volume_per_day)
        p3_recipe = game_data.get_recipe("p2_to_p3", p3_product)
        if not p3_recipe:
            continue
        output_mkt = market_data.get(p3_product)
        if not output_mkt or output_mkt.buy_price <= 0:
            continue

        num_p3_factories = p3_opt.max_factories
        p3_output_per_hour = p3_recipe.output_per_hour * num_p3_factories
        daily_output = p3_output_per_hour * 24
        revenue = daily_output * output_mkt.buy_price
        export_tax = revenue * constraints.tax_rate
        chain_isk = revenue - export_tax
        if chain_isk <= 0:
            continue

        p3_mat = game_data.materials.get(p3_product)
        vol_per_unit = p3_mat.volume_m3 if p3_mat else 1.5
        chain_volume = daily_output * vol_per_unit

        # For each P2 input the P3 recipe needs, figure out intermediate P1->P2 factories
        # and their extraction feeder colonies
        feeder_details = []
        total_feeder_colonies = 0
        feasible = True
        feeder_options_list = []

        for p2_input_name, p2_qty_per_cycle in p3_recipe.inputs:
            # P2 demand from the P3 factory
            p2_per_hour = p2_qty_per_cycle * (3600 / p3_recipe.cycle_seconds) * num_p3_factories

            # Find the best P1->P2 factory option for this P2
            p2_factory_opt = p1_to_p2_factory_by_product.get(p2_input_name)
            if not p2_factory_opt:
                feasible = False
                break

            # How much P2/hr does one P1->P2 colony produce?
            p2_recipe = game_data.get_recipe("p1_to_p2", p2_input_name)
            if not p2_recipe:
                feasible = False
                break
            p2_per_hour_per_colony = p2_recipe.output_per_hour * p2_factory_opt.max_factories

            # How many P1->P2 colonies needed to supply this P2 input?
            p2_colonies_needed = math.ceil(p2_per_hour / p2_per_hour_per_colony)
            p2_colonies_needed = max(1, p2_colonies_needed)

            # Create a scored option wrapper for the P1->P2 intermediate factory
            p2_factory_scored = ScoredOption(
                option=p2_factory_opt, isk_per_day=0.0, isk_per_colony=0.0,
                volume_per_day=p2_factory_opt.output_volume_per_day,
            )
            feeder_details.append((p2_input_name, p2_colonies_needed, p2_factory_scored, SetupType.P1_TO_P2))
            feeder_options_list.append(p2_factory_scored)
            total_feeder_colonies += p2_colonies_needed

            # Now figure out extraction feeders for each P1 input of this P2 recipe
            for p1_input_name, p1_qty_per_cycle in p2_recipe.inputs:
                # Total P1 demand across all P1->P2 colonies for this P2 input
                p1_per_hour = p1_qty_per_cycle * (3600 / p2_recipe.cycle_seconds) * p2_factory_opt.max_factories * p2_colonies_needed

                r0_name = game_data.r0_for_p1(p1_input_name)
                if not r0_name:
                    feasible = False
                    break
                planet_types_for_r0 = game_data.planet_types_for_r0(r0_name)
                if not any(pt in system_planet_type_names for pt in planet_types_for_r0):
                    feasible = False
                    break

                ext_opt = extraction_by_p1.get(p1_input_name)
                if not ext_opt:
                    feasible = False
                    break

                p1_per_hour_per_colony = _calc_extraction_p1_per_hour(ext_opt, game_data, constraints.cycle_days)
                if p1_per_hour_per_colony <= 0:
                    feasible = False
                    break
                ext_colonies_needed = math.ceil(p1_per_hour / p1_per_hour_per_colony)
                ext_colonies_needed = max(1, ext_colonies_needed)

                feeder_details.append((p1_input_name, ext_colonies_needed, ext_opt, SetupType.R0_TO_P1))
                feeder_options_list.append(ext_opt)
                total_feeder_colonies += ext_colonies_needed

            if not feasible:
                break

        if not feasible:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0

        unit = _ProductionUnit(
            kind="chain",
            factory_option=p3_scored,
            feeder_options=feeder_options_list,
            feeder_colony_count=total_feeder_colonies,
            total_colonies=total_colonies,
            isk_per_day=chain_isk,
            volume_per_day=chain_volume,
            isk_per_m3=isk_per_m3,
            product=p3_product,
            setup=SetupType.P2_TO_P3,
            feeder_details=feeder_details,
        )
        units.append(unit)

    # Step 4: P3->P4 factory chains (only on p4_capable planets)
    p3_to_p4_factory_options: Dict[str, FeasibleOption] = {}
    for opt in matrix:
        if opt.setup == SetupType.P3_TO_P4:
            if opt.product not in p3_to_p4_factory_options or opt.max_factories > p3_to_p4_factory_options[opt.product].max_factories:
                p3_to_p4_factory_options[opt.product] = opt

    # Index: best P2->P3 factory option per P3 product
    p2_to_p3_factory_by_product: Dict[str, FeasibleOption] = {}
    for opt in matrix:
        if opt.setup == SetupType.P2_TO_P3:
            if opt.product not in p2_to_p3_factory_by_product or opt.max_factories > p2_to_p3_factory_by_product[opt.product].max_factories:
                p2_to_p3_factory_by_product[opt.product] = opt

    for p4_product, p4_opt in p3_to_p4_factory_options.items():
        p4_scored = ScoredOption(option=p4_opt, isk_per_day=0.0, isk_per_colony=0.0,
                                 volume_per_day=p4_opt.output_volume_per_day)
        p4_recipe = game_data.get_recipe("p3_to_p4", p4_product)
        if not p4_recipe:
            continue
        output_mkt = market_data.get(p4_product)
        if not output_mkt or output_mkt.buy_price <= 0:
            continue

        num_p4_factories = p4_opt.max_factories
        p4_output_per_hour = p4_recipe.output_per_hour * num_p4_factories
        daily_output = p4_output_per_hour * 24
        revenue = daily_output * output_mkt.buy_price
        export_tax = revenue * constraints.tax_rate
        chain_isk = revenue - export_tax
        if chain_isk <= 0:
            continue

        p4_mat = game_data.materials.get(p4_product)
        vol_per_unit = p4_mat.volume_m3 if p4_mat else 100.0
        chain_volume = daily_output * vol_per_unit

        feeder_details = []
        total_feeder_colonies = 0
        feasible = True
        feeder_options_list = []

        for input_name, input_qty_per_cycle in p4_recipe.inputs:
            input_tier = game_data.get_material_tier(input_name)

            if input_tier == "p3":
                # P3 input: need P2->P3 intermediate factories, which need P1->P2, which need extraction
                p3_per_hour = input_qty_per_cycle * (3600 / p4_recipe.cycle_seconds) * num_p4_factories

                p3_factory_opt = p2_to_p3_factory_by_product.get(input_name)
                if not p3_factory_opt:
                    feasible = False
                    break

                p3_recipe = game_data.get_recipe("p2_to_p3", input_name)
                if not p3_recipe:
                    feasible = False
                    break
                p3_per_hour_per_colony = p3_recipe.output_per_hour * p3_factory_opt.max_factories

                p3_colonies_needed = math.ceil(p3_per_hour / p3_per_hour_per_colony)
                p3_colonies_needed = max(1, p3_colonies_needed)

                p3_factory_scored = ScoredOption(
                    option=p3_factory_opt, isk_per_day=0.0, isk_per_colony=0.0,
                    volume_per_day=p3_factory_opt.output_volume_per_day,
                )
                feeder_details.append((input_name, p3_colonies_needed, p3_factory_scored, SetupType.P2_TO_P3))
                feeder_options_list.append(p3_factory_scored)
                total_feeder_colonies += p3_colonies_needed

                # Now each P3 factory needs P2 inputs
                for p2_input_name, p2_qty_per_cycle in p3_recipe.inputs:
                    p2_per_hour = p2_qty_per_cycle * (3600 / p3_recipe.cycle_seconds) * p3_factory_opt.max_factories * p3_colonies_needed

                    p2_factory_opt = p1_to_p2_factory_by_product.get(p2_input_name)
                    if not p2_factory_opt:
                        feasible = False
                        break
                    p2_recipe = game_data.get_recipe("p1_to_p2", p2_input_name)
                    if not p2_recipe:
                        feasible = False
                        break
                    p2_per_hour_per_colony = p2_recipe.output_per_hour * p2_factory_opt.max_factories

                    p2_colonies_needed = math.ceil(p2_per_hour / p2_per_hour_per_colony)
                    p2_colonies_needed = max(1, p2_colonies_needed)

                    p2_factory_scored = ScoredOption(
                        option=p2_factory_opt, isk_per_day=0.0, isk_per_colony=0.0,
                        volume_per_day=p2_factory_opt.output_volume_per_day,
                    )
                    feeder_details.append((p2_input_name, p2_colonies_needed, p2_factory_scored, SetupType.P1_TO_P2))
                    feeder_options_list.append(p2_factory_scored)
                    total_feeder_colonies += p2_colonies_needed

                    # Extraction feeders for each P1 input of this P2
                    for p1_input_name, p1_qty_per_cycle in p2_recipe.inputs:
                        p1_per_hour = p1_qty_per_cycle * (3600 / p2_recipe.cycle_seconds) * p2_factory_opt.max_factories * p2_colonies_needed

                        r0_name = game_data.r0_for_p1(p1_input_name)
                        if not r0_name:
                            feasible = False
                            break
                        planet_types_for_r0 = game_data.planet_types_for_r0(r0_name)
                        if not any(pt in system_planet_type_names for pt in planet_types_for_r0):
                            feasible = False
                            break

                        ext_opt = extraction_by_p1.get(p1_input_name)
                        if not ext_opt:
                            feasible = False
                            break

                        p1_per_hour_per_colony = _calc_extraction_p1_per_hour(ext_opt, game_data, constraints.cycle_days)
                        if p1_per_hour_per_colony <= 0:
                            feasible = False
                            break
                        ext_colonies_needed = math.ceil(p1_per_hour / p1_per_hour_per_colony)
                        ext_colonies_needed = max(1, ext_colonies_needed)

                        feeder_details.append((p1_input_name, ext_colonies_needed, ext_opt, SetupType.R0_TO_P1))
                        feeder_options_list.append(ext_opt)
                        total_feeder_colonies += ext_colonies_needed

                    if not feasible:
                        break

                if not feasible:
                    break

            elif input_tier == "p1":
                # P1 input directly to P4 (e.g., Reactive Metals for Nano-Factory)
                p1_per_hour = input_qty_per_cycle * (3600 / p4_recipe.cycle_seconds) * num_p4_factories

                r0_name = game_data.r0_for_p1(input_name)
                if not r0_name:
                    feasible = False
                    break
                planet_types_for_r0 = game_data.planet_types_for_r0(r0_name)
                if not any(pt in system_planet_type_names for pt in planet_types_for_r0):
                    feasible = False
                    break

                ext_opt = extraction_by_p1.get(input_name)
                if not ext_opt:
                    feasible = False
                    break

                p1_per_hour_per_colony = _calc_extraction_p1_per_hour(ext_opt, game_data, constraints.cycle_days)
                if p1_per_hour_per_colony <= 0:
                    feasible = False
                    break
                ext_colonies_needed = math.ceil(p1_per_hour / p1_per_hour_per_colony)
                ext_colonies_needed = max(1, ext_colonies_needed)

                feeder_details.append((input_name, ext_colonies_needed, ext_opt, SetupType.R0_TO_P1))
                feeder_options_list.append(ext_opt)
                total_feeder_colonies += ext_colonies_needed

            else:
                # Unexpected tier
                feasible = False
                break

        if not feasible:
            continue

        total_colonies = 1 + total_feeder_colonies
        isk_per_m3 = chain_isk / chain_volume if chain_volume > 0 else 0.0

        unit = _ProductionUnit(
            kind="chain",
            factory_option=p4_scored,
            feeder_options=feeder_options_list,
            feeder_colony_count=total_feeder_colonies,
            total_colonies=total_colonies,
            isk_per_day=chain_isk,
            volume_per_day=chain_volume,
            isk_per_m3=isk_per_m3,
            product=p4_product,
            setup=SetupType.P3_TO_P4,
            feeder_details=feeder_details,
        )
        units.append(unit)

    return units


def _try_allocate_unit(unit, result, category, scored, matrix, game_data,
                       planet_character_map, character_colony_counts,
                       constraints, feeder_p1_colonies) -> int:
    """Try to allocate a production unit. Returns number of colonies used (0 if failed)."""
    num_characters = len(constraints.characters)

    def _planet_has_slot(planet_id: int) -> bool:
        used = planet_character_map.get(planet_id, set())
        return len(used) < num_characters

    def _assign_character(planet_id: int) -> str:
        used = planet_character_map.get(planet_id, set())
        available = [
            c for c in constraints.characters
            if c.name not in used and character_colony_counts[c.name] < c.max_planets
        ]
        if not available:
            return ""
        best = max(available, key=lambda c: c.max_planets - character_colony_counts[c.name])
        if planet_id not in planet_character_map:
            planet_character_map[planet_id] = set()
        planet_character_map[planet_id].add(best.name)
        character_colony_counts[best.name] += 1
        return best.name

    factory_planet_id = unit.factory_option.option.planet.planet_id

    if not _planet_has_slot(factory_planet_id):
        return 0

    # Check global colony limit
    max_colonies = constraints.total_colonies
    current_used = sum(character_colony_counts.values())
    if current_used >= max_colonies:
        return 0

    if unit.kind == "standalone":
        char_name = _assign_character(factory_planet_id)
        if not char_name:
            return 0
        result.assignments.append(ColonyAssignment(
            planet_id=factory_planet_id,
            planet_type=unit.factory_option.option.planet.planet_type.name,
            setup=unit.factory_option.option.setup,
            product=unit.product,
            num_factories=unit.factory_option.option.max_factories,
            isk_per_day=unit.isk_per_day,
            volume_per_day=unit.volume_per_day,
            details=f"{unit.factory_option.option.setup.value} on {unit.factory_option.option.planet.planet_type.name}",
            category=category,
            character=char_name,
        ))
        return 1

    # Chain allocation: check feeder feasibility first
    additional_feeders = 0
    feeder_plan = []
    for material_name, colonies_needed, feeder_opt, feeder_setup in unit.feeder_details:
        already_allocated = feeder_p1_colonies.get((material_name, feeder_setup), 0)
        new_needed = max(0, colonies_needed - already_allocated)
        if feeder_setup == SetupType.R0_TO_P1:
            total_available = sum(
                num_characters - len(planet_character_map.get(s.option.planet.planet_id, set()))
                for s in scored
                if s.option.setup == SetupType.R0_TO_P1 and s.option.product == material_name
            )
        else:
            total_available = sum(
                num_characters - len(planet_character_map.get(opt.planet.planet_id, set()))
                for opt in matrix
                if opt.setup == feeder_setup and opt.product == material_name
            )
        if new_needed > total_available:
            return 0
        additional_feeders += new_needed
        feeder_plan.append((material_name, colonies_needed, new_needed, feeder_opt, feeder_setup))

    total_new_colonies = 1 + additional_feeders
    max_colonies = constraints.total_colonies
    current_used = sum(character_colony_counts.values())
    if current_used + total_new_colonies > max_colonies:
        return 0

    # Allocate factory colony
    char_name = _assign_character(factory_planet_id)
    if not char_name:
        return 0
    details_suffix = f" ({unit.factory_option.option.max_factories} factories)" if unit.kind == "chain" else ""
    result.assignments.append(ColonyAssignment(
        planet_id=factory_planet_id,
        planet_type=unit.factory_option.option.planet.planet_type.name,
        setup=unit.setup,
        product=unit.product,
        num_factories=unit.factory_option.option.max_factories,
        isk_per_day=unit.isk_per_day,
        volume_per_day=unit.volume_per_day,
        details=f"{unit.setup.value} on {unit.factory_option.option.planet.planet_type.name}{details_suffix}",
        category=category,
        character=char_name,
    ))
    colonies_allocated = 1

    # Allocate feeder colonies
    for material_name, total_needed, new_needed, feeder_opt, feeder_setup in feeder_plan:
        if feeder_setup == SetupType.R0_TO_P1:
            candidates = [
                s for s in scored
                if s.option.setup == SetupType.R0_TO_P1
                and s.option.product == material_name
                and s.isk_per_day > 0
            ]
            placed = 0
            for ext in candidates:
                if placed >= new_needed:
                    break
                while placed < new_needed and _planet_has_slot(ext.option.planet.planet_id):
                    fc_name = _assign_character(ext.option.planet.planet_id)
                    result.assignments.append(ColonyAssignment(
                        planet_id=ext.option.planet.planet_id,
                        planet_type=ext.option.planet.planet_type.name,
                        setup=SetupType.R0_TO_P1,
                        product=material_name,
                        num_factories=ext.option.max_factories,
                        isk_per_day=0.0, volume_per_day=0.0,
                        details=f"r0_to_p1 on {ext.option.planet.planet_type.name} (feeding {unit.product})",
                        category="feed", feeds=f"-> {unit.product} factory",
                        character=fc_name,
                    ))
                    colonies_allocated += 1
                    placed += 1
        else:
            candidates_raw = [
                opt for opt in matrix
                if opt.setup == feeder_setup and opt.product == material_name
            ]
            placed = 0
            for fopt in candidates_raw:
                if placed >= new_needed:
                    break
                while placed < new_needed and _planet_has_slot(fopt.planet.planet_id):
                    fc_name = _assign_character(fopt.planet.planet_id)
                    result.assignments.append(ColonyAssignment(
                        planet_id=fopt.planet.planet_id,
                        planet_type=fopt.planet.planet_type.name,
                        setup=feeder_setup, product=material_name,
                        num_factories=fopt.max_factories,
                        isk_per_day=0.0, volume_per_day=0.0,
                        details=f"{feeder_setup.value} on {fopt.planet.planet_type.name} (feeding {unit.product})",
                        category="feed", feeds=f"-> {unit.product} factory",
                        character=fc_name,
                    ))
                    colonies_allocated += 1
                    placed += 1
        feeder_p1_colonies[(material_name, feeder_setup)] = feeder_p1_colonies.get((material_name, feeder_setup), 0) + placed

    return colonies_allocated


def _allocate_self_sufficient(scored, constraints, market_data, game_data, matrix=None):
    """Allocate for self-sufficient mode with factory chains and stockpile filling."""
    result = OptimizationResult()
    max_colonies = constraints.total_colonies
    max_volume_per_day = constraints.max_volume_per_day

    if matrix is None:
        matrix = []

    # 1. Build production units (one per planet x product, no dedup)
    units = _build_production_units(scored, constraints, market_data, game_data, matrix)
    if not units:
        return result

    # 2. Sort by ISK/colony/day (true value metric)
    units.sort(key=lambda u: u.isk_per_day / u.total_colonies if u.total_colonies > 0 else 0.0, reverse=True)

    # Shared state for tracking allocations
    num_characters = len(constraints.characters)
    planet_character_map: Dict[int, set] = {}
    character_colony_counts: Dict[str, int] = {}
    for c in constraints.characters:
        character_colony_counts[c.name] = 0
    feeder_p1_colonies: Dict[tuple, int] = {}

    def _colonies_used():
        return sum(character_colony_counts.values())

    # 3. Manufacturing pass: allocate manufacturing needs first
    for need in constraints.manufacturing_needs:
        if _colonies_used() >= max_colonies:
            break
        matching = sorted(
            [u for u in units if u.product == need.product],
            key=lambda u: u.isk_per_day, reverse=True,
        )
        for unit in matching:
            used = _try_allocate_unit(
                unit, result, "manufacturing", scored, matrix, game_data,
                planet_character_map, character_colony_counts,
                constraints, feeder_p1_colonies,
            )
            if used > 0:
                # Update the details to include manufacturing need info
                for a in result.assignments:
                    if a.category == "manufacturing" and a.product == unit.product and "(mfg need:" not in a.details:
                        a.details = a.details.rstrip(")") if a.details.endswith(")") else a.details
                        a.details += f" (mfg need: {need.quantity_per_week}/wk)"
                break

    # 4. Shipping pass: for each unit (sorted by ISK/colony), fill all available
    #    slots on that unit's planet before moving to the next unit.
    volume_used = 0.0
    for unit in units:
        if _colonies_used() >= max_colonies:
            break
        # Try to allocate this unit repeatedly until the planet is full
        while _colonies_used() < max_colonies:
            if volume_used + unit.volume_per_day > max_volume_per_day:
                break
            used = _try_allocate_unit(
                unit, result, "ship", scored, matrix, game_data,
                planet_character_map, character_colony_counts,
                constraints, feeder_p1_colonies,
            )
            if used > 0:
                volume_used += unit.volume_per_day
            else:
                break  # planet full or no characters available

    # 5. Stockpile pass: fill remaining slots ignoring volume, same approach as shipping
    if not constraints.volume_unlimited:
        for unit in units:
            if _colonies_used() >= max_colonies:
                break
            while _colonies_used() < max_colonies:
                used = _try_allocate_unit(
                    unit, result, "stockpile", scored, matrix, game_data,
                    planet_character_map, character_colony_counts,
                    constraints, feeder_p1_colonies,
                )
                if used <= 0:
                    break

    # Build totals: total_volume_per_day counts only shipped volume
    result.total_isk_per_day = sum(a.isk_per_day for a in result.assignments)
    result.total_volume_per_day = sum(
        a.volume_per_day for a in result.assignments if a.category == "ship"
    )
    return result
