from eve_pi.systems.pathfinding import jump_distance


def test_same_system():
    adj = {"1": ["2"], "2": ["1"]}
    assert jump_distance(1, 1, adj) == 0


def test_direct_neighbor():
    adj = {"1": ["2"], "2": ["1"]}
    assert jump_distance(1, 2, adj) == 1


def test_two_jumps():
    adj = {"1": ["2"], "2": ["1", "3"], "3": ["2"]}
    assert jump_distance(1, 3, adj) == 2


def test_no_route():
    adj = {"1": ["2"], "2": ["1"], "3": ["4"], "4": ["3"]}
    assert jump_distance(1, 3, adj) is None


def test_unknown_system():
    adj = {"1": ["2"], "2": ["1"]}
    assert jump_distance(1, 999, adj) is None


def test_max_jumps_exceeded():
    adj = {"1": ["2"], "2": ["1", "3"], "3": ["2", "4"], "4": ["3"]}
    assert jump_distance(1, 4, adj, max_jumps=2) is None
    assert jump_distance(1, 4, adj, max_jumps=3) == 3


def test_real_data():
    """Test with actual game data if available."""
    from eve_pi.data.loader import GameData
    gd = GameData.load()
    if not gd.system_jumps:
        return  # Skip if no jump data
    # Jita (30000142) should be reachable from itself
    assert jump_distance(30000142, 30000142, gd.system_jumps) == 0
    # Jita to Perimeter should be 1 jump (they're neighbors)
    result = jump_distance(30000142, 30000144, gd.system_jumps)
    assert result is not None and result > 0
