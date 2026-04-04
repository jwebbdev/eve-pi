from eve_pi.data.loader import GameData
from eve_pi.capacity.planet_capacity import link_costs, min_link_distance, can_fit, SetupType


def test_min_link_distance():
    assert abs(min_link_distance(2220) - 26.27) < 1.0
    assert abs(min_link_distance(6420) - 77.45) < 1.0


def test_link_costs():
    power, cpu = link_costs(27.0)
    assert abs(power - 14.86) < 0.5
    assert abs(cpu - 21.03) < 0.5


def test_can_fit_p1_to_p2_small_planet():
    gd = GameData.load()
    fits, max_factories, details = can_fit(
        radius_km=2220.0, ccu_level=4, setup=SetupType.P1_TO_P2, game_data=gd,
    )
    assert fits
    assert max_factories > 0
    assert max_factories <= 25


def test_can_fit_p3_to_p4():
    gd = GameData.load()
    fits, max_factories, details = can_fit(
        radius_km=6420.0, ccu_level=4, setup=SetupType.P3_TO_P4, game_data=gd,
    )
    assert fits
    assert max_factories > 0


def test_can_fit_extraction():
    gd = GameData.load()
    fits, max_factories, details = can_fit(
        radius_km=3910.0, ccu_level=4, setup=SetupType.R0_TO_P1, game_data=gd,
    )
    assert fits
    assert max_factories >= 8
    assert "extractor_heads" in details


def test_cannot_fit_at_low_ccu():
    gd = GameData.load()
    fits, max_factories, details = can_fit(
        radius_km=6420.0, ccu_level=0, setup=SetupType.P1_TO_P2, game_data=gd,
    )
    assert not fits or max_factories == 0


def test_r0_to_p2_fits():
    gd = GameData.load()
    fits, max_factories, details = can_fit(
        radius_km=3910.0, ccu_level=4, setup=SetupType.R0_TO_P2, game_data=gd,
    )
    assert fits
    assert details.get("advanced_factories", 0) == 1
