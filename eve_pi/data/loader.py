from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml
from eve_pi.models.materials import Material, Recipe
from eve_pi.models.planets import PlanetType
from eve_pi.models.colonies import Facility, CommandCenterLevel

DATA_DIR = Path(__file__).parent


@dataclass
class GameData:
    materials: Dict[str, Material] = field(default_factory=dict)
    recipes: Dict[str, Dict[str, Recipe]] = field(default_factory=dict)
    planet_types: Dict[str, PlanetType] = field(default_factory=dict)
    facilities: Dict[str, Facility] = field(default_factory=dict)
    command_center_levels: Dict[int, CommandCenterLevel] = field(default_factory=dict)
    link_formulas: Dict[str, float] = field(default_factory=dict)
    decay_constants: Dict[str, float] = field(default_factory=dict)
    default_extraction_rates: Dict[str, int] = field(default_factory=dict)
    system_index: Dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "GameData":
        gd = cls()
        gd._load_materials()
        gd._load_recipes()
        gd._load_planet_types()
        gd._load_facilities()
        gd._load_system_index()
        return gd

    def _load_materials(self):
        with open(DATA_DIR / "materials.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for tier, mats in data.items():
            for name, info in mats.items():
                self.materials[name] = Material(
                    name=name, tier=tier,
                    type_id=info["type_id"], volume_m3=info["volume_m3"],
                )

    def _load_recipes(self):
        with open(DATA_DIR / "recipes.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        tier_map = {
            "r0_to_p1": ("r0", "p1"),
            "p1_to_p2": ("p1", "p2"),
            "p2_to_p3": ("p2", "p3"),
            "p3_to_p4": ("p3", "p4"),
        }
        for tier_key, recipes in data.items():
            tier_from, tier_to = tier_map[tier_key]
            self.recipes[tier_key] = {}
            for product, info in recipes.items():
                if tier_key == "r0_to_p1":
                    inputs = [(info["input"], info["r0_per_cycle"])]
                    output_per_cycle = info["p1_per_cycle"]
                else:
                    inputs = [(name, qty) for name, qty in info["inputs"]]
                    output_per_cycle = info["output_per_cycle"]
                self.recipes[tier_key][product] = Recipe(
                    output=product, tier_from=tier_from, tier_to=tier_to,
                    inputs=inputs, output_per_cycle=output_per_cycle,
                    cycle_seconds=info["cycle_seconds"],
                )

    def _load_planet_types(self):
        with open(DATA_DIR / "planet_types.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for name, info in data["planet_types"].items():
            self.planet_types[name] = PlanetType(
                name=name, type_id=info["type_id"],
                p4_capable=info.get("p4_capable", False),
                resources=info["resources"], structures=info["structures"],
            )
        self.default_extraction_rates = data.get("default_extraction_rates", {})

    def _load_facilities(self):
        with open(DATA_DIR / "facilities.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for key, info in data["facilities"].items():
            self.facilities[key] = Facility(
                name=info["name"], cpu_tf=info["cpu_tf"],
                power_mw=info["power_mw"], storage_m3=info.get("storage_m3", 0),
            )
        for level, info in data["command_center_levels"].items():
            self.command_center_levels[int(level)] = CommandCenterLevel(
                level=int(level), cpu_tf=info["cpu_tf"],
                power_mw=info["power_mw"], storage_m3=info["storage_m3"],
            )
        self.link_formulas = data["link_formulas"]
        self.decay_constants = data["extraction_decay"]

    def _load_system_index(self):
        index_path = DATA_DIR / "system_index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                self.system_index = json.load(f)

    def get_recipe(self, tier_key: str, product: str) -> Optional[Recipe]:
        return self.recipes.get(tier_key, {}).get(product)

    def planet_types_for_r0(self, r0_name: str) -> List[str]:
        return [pt.name for pt in self.planet_types.values() if r0_name in pt.resources]

    def r0_for_p1(self, p1_name: str) -> Optional[str]:
        recipe = self.get_recipe("r0_to_p1", p1_name)
        if recipe:
            return recipe.inputs[0][0]
        return None

    def get_material_tier(self, name: str) -> Optional[str]:
        mat = self.materials.get(name)
        return mat.tier if mat else None
