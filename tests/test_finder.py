from eve_pi.data.loader import GameData
from eve_pi.systems.finder import find_matching_systems, get_system_products


def test_find_matching_systems_kspace():
    gd = GameData.load()
    # Aqueous Liquids is on many planet types, should find K-space matches
    matches = find_matching_systems(
        gd.system_index, ["Aqueous Liquids"], gd.planet_types_for_r0, space="k"
    )
    assert len(matches) > 0
    assert all(m.wh_class is None for m in matches)


def test_find_matching_systems_jspace():
    gd = GameData.load()
    matches = find_matching_systems(
        gd.system_index, ["Aqueous Liquids"], gd.planet_types_for_r0, space="j"
    )
    assert len(matches) > 0
    assert all(m.wh_class is not None for m in matches)


def test_find_matching_systems_wh_class_filter():
    gd = GameData.load()
    matches = find_matching_systems(
        gd.system_index, ["Aqueous Liquids"], gd.planet_types_for_r0,
        space="j", wh_classes={1, 2}
    )
    assert all(m.wh_class in {1, 2} for m in matches)


def test_find_matching_systems_unknown_r0():
    gd = GameData.load()
    matches = find_matching_systems(
        gd.system_index, ["Nonexistent Resource"], gd.planet_types_for_r0, space="k"
    )
    assert len(matches) == 0


def test_get_system_products():
    gd = GameData.load()
    # Temperate planet has Aqueous Liquids, Autotrophs, etc.
    products = get_system_products({"Temperate": 1, "Gas": 1}, gd)
    assert len(products["p1"]) > 0
    assert "Water" in products["p1"]  # Aqueous Liquids -> Water


def test_get_system_products_empty():
    gd = GameData.load()
    products = get_system_products({}, gd)
    assert all(len(v) == 0 for v in products.values())
