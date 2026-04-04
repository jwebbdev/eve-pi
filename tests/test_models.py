from eve_pi.data.loader import GameData


def test_load_game_data():
    gd = GameData.load()
    assert len(gd.materials) > 80
    assert "Water" in gd.materials
    assert gd.materials["Water"].tier == "p1"
    assert gd.materials["Water"].type_id == 3645
    assert gd.materials["Water"].volume_m3 == 0.38


def test_r0_to_p1_recipe():
    gd = GameData.load()
    recipe = gd.get_recipe("r0_to_p1", "Water")
    assert recipe is not None
    assert recipe.output == "Water"
    assert recipe.inputs == [("Aqueous Liquids", 3000)]
    assert recipe.output_per_cycle == 20
    assert recipe.cycle_seconds == 1800


def test_p1_to_p2_recipe():
    gd = GameData.load()
    recipe = gd.get_recipe("p1_to_p2", "Coolant")
    assert recipe is not None
    assert recipe.output == "Coolant"
    assert ("Electrolytes", 40) in recipe.inputs
    assert ("Water", 40) in recipe.inputs
    assert recipe.output_per_cycle == 5


def test_planet_type():
    gd = GameData.load()
    pt = gd.planet_types["Gas"]
    assert pt.type_id == 13
    assert "Reactive Gas" in pt.resources
    assert pt.structures["launchpad"] == 2543


def test_planet_types_for_r0():
    gd = GameData.load()
    types = gd.planet_types_for_r0("Aqueous Liquids")
    assert "Temperate" in types
    assert "Gas" in types
    assert "Lava" not in types


def test_facility_costs():
    gd = GameData.load()
    assert gd.facilities["launchpad"].cpu_tf == 3600
    assert gd.facilities["launchpad"].power_mw == 700


def test_command_center_level():
    gd = GameData.load()
    cc = gd.command_center_levels[4]
    assert cc.cpu_tf == 21315
    assert cc.power_mw == 17000
