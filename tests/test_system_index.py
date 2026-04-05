from eve_pi.data.loader import GameData


def test_system_index_loads():
    gd = GameData.load()
    assert len(gd.system_index) > 0, "System index should not be empty"


def test_system_entry_structure():
    gd = GameData.load()
    system_id, entry = next(iter(gd.system_index.items()))
    assert "name" in entry
    assert "security" in entry
    assert "planets" in entry
    assert isinstance(entry["planets"], dict)
    assert len(entry["planets"]) > 0


def test_wormhole_systems_have_class():
    gd = GameData.load()
    j_systems = {sid: e for sid, e in gd.system_index.items() if e["name"].startswith("J")}
    with_class = [e for e in j_systems.values() if "wh_class" in e]
    assert len(with_class) > 0, "Some J-space systems should have wh_class"
