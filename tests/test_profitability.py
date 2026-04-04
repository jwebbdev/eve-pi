from eve_pi.data.loader import GameData
from eve_pi.market.esi import MarketData
from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.optimizer.profitability import (
    calculate_extraction_profit,
    calculate_factory_profit,
    calculate_r0_p2_profit,
)


def _make_market_data() -> dict:
    return {
        "Water": MarketData(type_id=3645, name="Water", buy_price=500.0,
                            sell_orders=[{"price": 450.0, "volume_remain": 100000}]),
        "Electrolytes": MarketData(type_id=2390, name="Electrolytes", buy_price=550.0,
                                   sell_orders=[{"price": 500.0, "volume_remain": 100000}]),
        "Coolant": MarketData(type_id=9832, name="Coolant", buy_price=12000.0,
                              sell_orders=[{"price": 11000.0, "volume_remain": 100000}]),
        "Silicon": MarketData(type_id=9828, name="Silicon", buy_price=800.0,
                              sell_orders=[{"price": 750.0, "volume_remain": 100000}]),
    }


def test_extraction_profit():
    gd = GameData.load()
    market = _make_market_data()
    profit = calculate_extraction_profit(
        p1_name="Water", market_data=market,
        extraction_rate_r0_per_hour=60000, cycle_days=1.0,
        num_factories=10, tax_rate=0.05, game_data=gd,
    )
    assert profit > 0


def test_factory_profit_p1_to_p2():
    gd = GameData.load()
    market = _make_market_data()
    profit = calculate_factory_profit(
        product_name="Coolant", setup=SetupType.P1_TO_P2,
        num_factories=20, market_data=market,
        tax_rate=0.05, game_data=gd,
    )
    assert isinstance(profit, float)


def test_r0_p2_profit():
    gd = GameData.load()
    market = _make_market_data()
    profit = calculate_r0_p2_profit(
        p2_name="Coolant", market_data=market,
        extraction_rate_r0_per_hour=12000, cycle_days=1.0,
        tax_rate=0.05, game_data=gd,
    )
    assert isinstance(profit, float)
