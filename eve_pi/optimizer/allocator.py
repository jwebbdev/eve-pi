"""Colony allocation optimizer. Greedy allocation with feasibility-first approach."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.data.loader import GameData
from eve_pi.market.esi import MarketData
from eve_pi.models.characters import Character
from eve_pi.models.planets import SolarSystem
from eve_pi.optimizer.feasibility import FeasibleOption, build_feasibility_matrix
from eve_pi.optimizer.profitability import (
    calculate_extraction_profit, calculate_factory_profit, calculate_r0_p2_profit,
)


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
        return _allocate_self_sufficient(scored, constraints, market_data, game_data)
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


def _allocate_self_sufficient(scored, constraints, market_data, game_data):
    """Allocate for self-sufficient mode. All inputs from local extraction."""
    result = OptimizationResult()
    colonies_used = 0
    volume_used = 0.0
    max_colonies = constraints.total_colonies
    max_volume = constraints.max_volume_per_day
    allocated_products = set()
    extraction_options = [
        s for s in scored
        if s.option.setup in (SetupType.R0_TO_P1, SetupType.R0_TO_P2)
    ]
    for s in extraction_options:
        if colonies_used >= max_colonies:
            break
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
            details=f"{s.option.setup.value} on {s.option.planet.planet_type.name}",
        ))
        colonies_used += 1
        volume_used += s.volume_per_day
        allocated_products.add(s.option.product)
    result.total_isk_per_day = sum(a.isk_per_day for a in result.assignments)
    result.total_volume_per_day = sum(a.volume_per_day for a in result.assignments)
    return result
