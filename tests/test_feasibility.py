from eve_pi.data.loader import GameData
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.optimizer.feasibility import build_feasibility_matrix, FeasibleOption


def _make_test_system(game_data: GameData) -> SolarSystem:
    return SolarSystem(name="J153003", system_id=31002229, planets=[
        Planet(planet_id=1, planet_type=game_data.planet_types["Barren"], radius_km=2220.0),
        Planet(planet_id=2, planet_type=game_data.planet_types["Gas"], radius_km=39773.0),
        Planet(planet_id=3, planet_type=game_data.planet_types["Gas"], radius_km=39773.0),
        Planet(planet_id=4, planet_type=game_data.planet_types["Lava"], radius_km=3910.0),
        Planet(planet_id=5, planet_type=game_data.planet_types["Temperate"], radius_km=6420.0),
    ])


def test_build_feasibility_matrix():
    gd = GameData.load()
    system = _make_test_system(gd)
    matrix = build_feasibility_matrix(system, ccu_level=4, game_data=gd)
    assert len(matrix) > 0
    for opt in matrix:
        assert opt.max_factories > 0


def test_extraction_options_match_planet_resources():
    gd = GameData.load()
    system = _make_test_system(gd)
    matrix = build_feasibility_matrix(system, ccu_level=4, game_data=gd)
    lava_extractions = [
        opt for opt in matrix
        if opt.planet.planet_id == 4 and opt.setup == SetupType.R0_TO_P1
    ]
    lava_r0s = {opt.product for opt in lava_extractions}
    assert "Silicon" in lava_r0s or "Reactive Metals" in lava_r0s


def test_factory_options_for_all_planets():
    gd = GameData.load()
    system = _make_test_system(gd)
    matrix = build_feasibility_matrix(system, ccu_level=4, game_data=gd)
    planet_ids_with_factories = {
        opt.planet.planet_id for opt in matrix
        if opt.setup in (SetupType.P1_TO_P2, SetupType.P2_TO_P3)
    }
    assert len(planet_ids_with_factories) == len(system.planets)


def test_r0_to_p2_options_exist():
    gd = GameData.load()
    system = _make_test_system(gd)
    matrix = build_feasibility_matrix(system, ccu_level=4, game_data=gd)
    r0_p2_options = [opt for opt in matrix if opt.setup == SetupType.R0_TO_P2]
    assert len(r0_p2_options) > 0
