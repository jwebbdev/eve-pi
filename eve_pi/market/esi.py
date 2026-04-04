"""ESI API client for market data and system info."""
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from eve_pi.market.cache import FileCache

JITA_REGION_ID = 10000002
DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent / ".pi_cache"


@dataclass
class MarketData:
    type_id: int
    name: str
    buy_price: float = 0.0
    sell_orders: List[Dict] = field(default_factory=list)

    def get_purchase_cost(self, quantity_needed: int) -> Tuple[float, float, bool]:
        """
        Calculate cost to purchase a given quantity from sell orders.
        Returns: (avg_price_per_unit, total_cost, sufficient_volume)
        """
        if quantity_needed <= 0:
            return 0.0, 0.0, True
        total_cost = 0.0
        remaining = quantity_needed
        for order in self.sell_orders:
            if remaining <= 0:
                break
            take = min(order["volume_remain"], remaining)
            total_cost += take * order["price"]
            remaining -= take
        sufficient = remaining <= 0
        purchased = quantity_needed - remaining
        avg_price = total_cost / purchased if purchased > 0 else 0.0
        if not sufficient and self.sell_orders:
            highest = self.sell_orders[-1]["price"] * 1.10
            total_cost += remaining * highest
            avg_price = total_cost / quantity_needed
        return avg_price, total_cost, sufficient


class ESIClient:
    """Fetches market data and system info from EVE ESI API."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, cache_ttl: int = 900):
        self.cache = FileCache(cache_dir, ttl_seconds=cache_ttl)
        self.user_agent = "EVE-PI-Optimizer/2.0"

    def _fetch_json(self, url: str, timeout: int = 30) -> Optional[dict]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, Exception):
            return None

    def _fetch_json_post(self, url: str, body: any, timeout: int = 30) -> Optional[dict]:
        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json", "User-Agent": self.user_agent},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, Exception):
            return None

    def fetch_market_orders(self, type_id: int, order_type: str) -> List[Dict]:
        cache_key = f"orders_{type_id}_{order_type}"
        cached = self.cache.load(cache_key)
        if cached is not None:
            return cached
        url = (
            f"https://esi.evetech.net/latest/markets/{JITA_REGION_ID}/orders/"
            f"?datasource=tranquility&order_type={order_type}&type_id={type_id}"
        )
        for attempt in range(3):
            result = self._fetch_json(url)
            if result is not None:
                self.cache.save(cache_key, result)
                return result
            time.sleep(2 ** attempt)
        self.cache.save(cache_key, [])
        return []

    def fetch_market_data(self, type_id: int, name: str) -> MarketData:
        buy_orders = self.fetch_market_orders(type_id, "buy")
        buy_price = max((o["price"] for o in buy_orders), default=0.0)
        sell_orders = self.fetch_market_orders(type_id, "sell")
        sell_orders.sort(key=lambda x: x["price"])
        return MarketData(type_id=type_id, name=name, buy_price=buy_price, sell_orders=sell_orders)

    def fetch_all_pi_market_data(self, materials: Dict) -> Dict[str, MarketData]:
        result = {}
        for name, mat in materials.items():
            result[name] = self.fetch_market_data(mat.type_id, name)
        return result

    def resolve_system_id(self, system_name: str) -> Optional[int]:
        url = "https://esi.evetech.net/latest/universe/ids/?datasource=tranquility"
        result = self._fetch_json_post(url, [system_name])
        if result and "systems" in result and result["systems"]:
            return result["systems"][0]["id"]
        return None

    def fetch_system_planets(self, system_id: int) -> List[Dict]:
        url = f"https://esi.evetech.net/latest/universe/systems/{system_id}/?datasource=tranquility"
        data = self._fetch_json(url)
        if not data or "planets" not in data:
            return []
        planets = []
        for p in data["planets"]:
            planet_id = p["planet_id"]
            planet_url = f"https://esi.evetech.net/latest/universe/planets/{planet_id}/?datasource=tranquility"
            pdata = self._fetch_json(planet_url)
            if pdata:
                planets.append({
                    "planet_id": planet_id,
                    "type_id": pdata.get("type_id"),
                    "name": pdata.get("name", f"Planet {planet_id}"),
                })
        return planets
