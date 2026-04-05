import json
import tempfile
from pathlib import Path
from eve_pi.market.cache import FileCache
from eve_pi.market.esi import MarketData


def test_file_cache_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(Path(tmpdir), ttl_seconds=60)
        cache.save("test_key", {"price": 100})
        result = cache.load("test_key")
        assert result == {"price": 100}


def test_file_cache_expired():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(Path(tmpdir), ttl_seconds=0)
        cache.save("test_key", {"price": 100})
        result = cache.load("test_key")
        assert result is None


def test_file_cache_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(Path(tmpdir), ttl_seconds=60)
        result = cache.load("nonexistent")
        assert result is None


def test_market_data_purchase_cost():
    md = MarketData(
        type_id=3645, name="Water", buy_price=500.0,
        sell_orders=[
            {"price": 400.0, "volume_remain": 1000},
            {"price": 450.0, "volume_remain": 2000},
            {"price": 500.0, "volume_remain": 5000},
        ],
    )
    avg_price, total_cost, sufficient = md.get_purchase_cost(1500)
    assert sufficient
    assert abs(avg_price - 416.67) < 1.0
    assert abs(total_cost - 625000) < 1.0


def test_market_data_insufficient_volume():
    md = MarketData(
        type_id=3645, name="Water", buy_price=500.0,
        sell_orders=[{"price": 400.0, "volume_remain": 100}],
    )
    avg_price, total_cost, sufficient = md.get_purchase_cost(1000)
    assert not sufficient


def test_fetch_route_returns_jump_count():
    """Test that fetch_route returns an integer jump count (requires network)."""
    from eve_pi.market.esi import ESIClient
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        esi = ESIClient(cache_dir=Path(tmpdir))
        # Jita (30000142) to Amarr (30002187) — well-known route
        jumps = esi.fetch_route(30000142, 30002187)
        assert jumps is not None
        assert isinstance(jumps, int)
        assert jumps > 0  # Jita to Amarr is ~30+ jumps
