"""FastAPI web UI for the EVE PI Optimizer."""
import json
import traceback
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from eve_pi.cli.optimize import PLANET_TYPE_IDS
from eve_pi.data.loader import GameData
from eve_pi.market.esi import ESIClient
from eve_pi.models.characters import Character
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.optimizer.allocator import (
    ColonyAssignment,
    ManufacturingNeed,
    OptimizationConstraints,
    OptimizationResult,
    optimize,
)
from eve_pi.templates.converter import convert_template
import html
import re
from datetime import datetime

app = FastAPI(title="EVE PI Optimizer")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Load game data once at startup
game_data = GameData.load()

# Feedback storage
FEEDBACK_DIR = Path(__file__).parent.parent.parent / "feedback"
FEEDBACK_DIR.mkdir(exist_ok=True)

MAX_FEEDBACK_LENGTH = 5000



def _get_product_lists() -> dict:
    """Build categorized product lists from game data."""
    products_by_tier = {"p1": [], "p2": [], "p3": [], "p4": []}
    for name, mat in game_data.materials.items():
        if mat.tier in products_by_tier:
            products_by_tier[mat.tier].append(name)
    for tier in products_by_tier:
        products_by_tier[tier].sort()
    return products_by_tier


def _get_planet_type_names() -> list:
    """Get sorted list of planet type names."""
    return sorted(game_data.planet_types.keys())


def _render(request, template_name, **context):
    """Helper to render a template with Starlette 1.0 compatible args."""
    return templates.TemplateResponse(request, template_name, context)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    products_by_tier = _get_product_lists()
    all_products = []
    for tier in ("p1", "p2", "p3", "p4"):
        all_products.extend(products_by_tier[tier])

    return _render(request, "index.html",
                   products_by_tier=products_by_tier,
                   all_products=all_products,
                   planet_types=_get_planet_type_names())


@app.post("/optimize", response_class=HTMLResponse)
async def run_optimization(request: Request):
    form = await request.form()

    # Parse form data
    system_name = form.get("system", "").strip()
    mode = form.get("mode", "self_sufficient")
    cycle_days = float(form.get("cycle_days", 4))
    trips_per_week = int(form.get("trips_per_week", 2))
    cargo_m3 = float(form.get("cargo_m3", 60000))
    tax_rate = float(form.get("tax_rate", 0.05))

    # Parse characters from dynamic form fields
    char_names = form.getlist("char_name")
    char_ccus = form.getlist("char_ccu")
    char_planets = form.getlist("char_max_planets")

    characters = []
    for i in range(len(char_names)):
        name = char_names[i].strip() if i < len(char_names) else f"Char{i+1}"
        ccu = int(char_ccus[i]) if i < len(char_ccus) else 5
        max_p = int(char_planets[i]) if i < len(char_planets) else 6
        if name:
            characters.append(Character(name=name, ccu_level=ccu, max_planets=max_p))

    if not characters:
        characters = [Character(name="Char1", ccu_level=5, max_planets=6)]

    # Parse manufacturing needs
    mfg_products = form.getlist("mfg_product")
    mfg_quantities = form.getlist("mfg_quantity")
    manufacturing_needs = []
    for i in range(len(mfg_products)):
        product = mfg_products[i].strip() if i < len(mfg_products) else ""
        qty = int(mfg_quantities[i]) if i < len(mfg_quantities) else 0
        if product and qty > 0:
            manufacturing_needs.append(ManufacturingNeed(product=product, quantity_per_week=qty))

    # Preserve form values for re-rendering
    form_values = {
        "system": system_name,
        "mode": mode,
        "cycle_days": cycle_days,
        "trips_per_week": trips_per_week,
        "cargo_m3": cargo_m3,
        "tax_rate": tax_rate,
        "characters": [{"name": c.name, "ccu_level": c.ccu_level, "max_planets": c.max_planets} for c in characters],
        "manufacturing_needs": [{"product": m.product, "quantity_per_week": m.quantity_per_week} for m in manufacturing_needs],
    }

    products_by_tier = _get_product_lists()
    all_products = []
    for tier in ("p1", "p2", "p3", "p4"):
        all_products.extend(products_by_tier[tier])

    base_ctx = dict(
        form_values=form_values,
        products_by_tier=products_by_tier,
        all_products=all_products,
        planet_types=_get_planet_type_names(),
    )

    if not system_name:
        return _render(request, "index.html", error="System name is required.", **base_ctx)

    error = None
    result = None
    constraints = None

    try:
        esi = ESIClient()

        # Resolve system
        system_id = esi.resolve_system_id(system_name)
        if not system_id:
            return _render(request, "index.html",
                           error=f"Could not find system '{system_name}'. Check spelling and try again.",
                           **base_ctx)

        # Fetch planets with real radii
        raw_planets = esi.fetch_system_planets(system_id)
        radii = esi.fetch_planet_radii()
        planets = []
        for rp in raw_planets:
            type_name = PLANET_TYPE_IDS.get(rp["type_id"])
            if type_name and type_name in game_data.planet_types:
                radius_km = radii.get(rp["planet_id"], 3000.0)
                planets.append(Planet(
                    planet_id=rp["planet_id"],
                    planet_type=game_data.planet_types[type_name],
                    radius_km=radius_km,
                ))
        system = SolarSystem(name=system_name, system_id=system_id, planets=planets)

        # Fetch market data
        market = esi.fetch_all_pi_market_data(game_data.materials)

        # Build constraints and optimize
        constraints = OptimizationConstraints(
            system=system,
            characters=characters,
            mode=mode,
            cycle_days=cycle_days,
            hauling_trips_per_week=trips_per_week,
            cargo_capacity_m3=cargo_m3,
            tax_rate=tax_rate,
            manufacturing_needs=manufacturing_needs,
        )
        result = optimize(constraints, market, game_data)

    except Exception as e:
        error = f"Optimization failed: {str(e)}"

    if error:
        return _render(request, "index.html", error=error, **base_ctx)

    # Build feed map for display grouping
    feed_by_factory = {}
    for a in result.feed_assignments:
        factory_product = a.feeds.replace("-> ", "").replace(" factory", "") if a.feeds else ""
        if factory_product not in feed_by_factory:
            feed_by_factory[factory_product] = []
        feed_by_factory[factory_product].append(a)

    return _render(request, "results.html",
                   result=result,
                   constraints=constraints,
                   feed_by_factory=feed_by_factory,
                   form_values=form_values)


@app.get("/template-converter", response_class=HTMLResponse)
async def template_converter_page(request: Request):
    products_by_tier = _get_product_lists()
    converter_products = []
    for tier in ("p2", "p3", "p4"):
        converter_products.extend(products_by_tier[tier])
    return _render(request, "template_converter.html",
                   planet_types=_get_planet_type_names(),
                   products=converter_products)


@app.post("/template/convert", response_class=JSONResponse)
async def convert_template_route(request: Request):
    form = await request.form()
    template_json = form.get("template_json", "").strip()
    to_planet_type = form.get("to_planet_type", "").strip() or None
    to_product = form.get("to_product", "").strip() or None

    if not template_json:
        return JSONResponse({"error": "Template JSON is required."}, status_code=400)

    try:
        template = json.loads(template_json)
    except json.JSONDecodeError as e:
        return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)

    try:
        result = convert_template(template, to_planet_type, to_product, game_data)
        if "Diam" in result:
            result["Diam"] = float(result["Diam"])
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": f"Conversion failed: {str(e)}"}, status_code=500)



REFERENCE_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "reference_templates"


def _find_reference_template(product: str, setup_value: str) -> Optional[dict]:
    """Find a reference template for a product and convert it."""
    if not REFERENCE_TEMPLATES_DIR.exists():
        return None

    # For extraction (r0_to_p1), look for Miner templates
    if setup_value == "r0_to_p1":
        for prefix in ["Miner - 00 - ", "Miner - LS - "]:
            path = REFERENCE_TEMPLATES_DIR / f"{prefix}{product}.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        # Try fuzzy match (e.g., "Chiral Stuctures" typo in repo)
        for fname in REFERENCE_TEMPLATES_DIR.glob("Miner - 00 - *.json"):
            if product.lower().replace(" ", "") in fname.stem.lower().replace(" ", ""):
                with open(fname, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None

    # R0→P2: generate programmatically
    if setup_value == "r0_to_p2":
        return None  # handled separately in generate_template()

    # For factories (p1_to_p2, p2_to_p3, p3_to_p4), look for Factory templates
    path = REFERENCE_TEMPLATES_DIR / f"Factory - {product}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _generate_r0_to_p2_template(planet_type_name: str, p2_product: str,
                                radius_km: float = 5000.0, ccu_level: int = 5) -> dict:
    """Generate an R0->P2 template sized to fit the planet and CCU level."""
    from eve_pi.capacity.planet_capacity import can_fit, SetupType, min_link_distance

    pt = game_data.planet_types[planet_type_name]
    p2_recipe = game_data.get_recipe("p1_to_p2", p2_product)
    if not p2_recipe:
        return None

    p1_a_name = p2_recipe.inputs[0][0]
    p1_b_name = p2_recipe.inputs[1][0]
    r0_a_name = game_data.r0_for_p1(p1_a_name)
    r0_b_name = game_data.r0_for_p1(p1_b_name)
    if not r0_a_name or not r0_b_name:
        return None

    # Use capacity model to determine how many basics/heads fit
    fits, _, details = can_fit(radius_km, ccu_level, SetupType.R0_TO_P2, game_data)
    if not fits:
        return None

    num_basics = details.get("basic_factories", 4)
    num_heads_total = details.get("extractor_heads", 4)
    basics_per_type = num_basics // 2  # split evenly between P1-A and P1-B
    heads_per_ecu = min(num_heads_total // 2, 10)

    if basics_per_type < 1:
        basics_per_type = 1

    p2_id = game_data.materials[p2_product].type_id
    p1_a_id = game_data.materials[p1_a_name].type_id
    p1_b_id = game_data.materials[p1_b_name].type_id
    r0_a_id = game_data.materials[r0_a_name].type_id
    r0_b_id = game_data.materials[r0_b_name].type_id

    # Calculate angular step from planet radius for tight placement
    min_link_km = max(1.0, min_link_distance(radius_km))
    step = (min_link_km / radius_km) * 1.1  # slight padding
    step = max(step, 0.005)  # minimum step to avoid overlapping pins
    cx, cy = 1.5, 3.0

    # Build pins: LP(1), Storage(2), Advanced(3), Basic-A(4...), Basic-B(...), ECU-A, ECU-B
    pins = [
        {"H": 0, "La": cx, "Lo": cy, "S": None, "T": pt.structures["launchpad"]},
        {"H": 0, "La": round(cx+step, 5), "Lo": cy, "S": None, "T": pt.structures["storage"]},
        {"H": 0, "La": round(cx-step, 5), "Lo": cy, "S": p2_id, "T": pt.structures["advanced_factory"]},
    ]
    links = [
        {"D": 2, "Lv": 0, "S": 1},  # LP -> Storage
        {"D": 3, "Lv": 0, "S": 1},  # LP -> Advanced
    ]

    # Place Basic-A factories along the +Lo side, alternating LP/Storage connections
    basic_a_start = len(pins) + 1  # 1-indexed pin number
    for i in range(basics_per_type):
        row = i // 2
        col = i % 2
        la = round(cx + (col - 0.5) * step, 5)
        lo = round(cy + step * (1 + row), 5)
        pins.append({"H": 0, "La": la, "Lo": lo, "S": p1_a_id, "T": pt.structures["basic_factory"]})
        # Alternate connections: even->LP(1), odd->Storage(2)
        parent = 1 if i % 2 == 0 else 2
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # Place Basic-B factories along the -Lo side
    basic_b_start = len(pins) + 1
    for i in range(basics_per_type):
        row = i // 2
        col = i % 2
        la = round(cx + (col - 0.5) * step, 5)
        lo = round(cy - step * (1 + row), 5)
        pins.append({"H": 0, "La": la, "Lo": lo, "S": p1_b_id, "T": pt.structures["basic_factory"]})
        parent = 1 if i % 2 == 0 else 2
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # ECUs
    ecu_a_pin = len(pins) + 1
    pins.append({"H": heads_per_ecu, "La": round(cx+step*2, 5), "Lo": cy,
                 "S": r0_a_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_a_pin, "Lv": 0, "S": 2})  # -> Storage

    ecu_b_pin = len(pins) + 1
    pins.append({"H": heads_per_ecu, "La": round(cx-step*2, 5), "Lo": cy,
                 "S": r0_b_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_b_pin, "Lv": 0, "S": 2})  # -> Storage

    # Build routes
    routes = []

    # R0-A: Storage -> each Basic-A factory
    for i in range(basics_per_type):
        pin = basic_a_start + i
        parent = 1 if i % 2 == 0 else 2
        path = [2, 1, pin] if parent == 1 else [2, pin]
        routes.append({"P": path, "Q": 3000, "T": r0_a_id})

    # R0-B: Storage -> each Basic-B factory
    for i in range(basics_per_type):
        pin = basic_b_start + i
        parent = 1 if i % 2 == 0 else 2
        path = [2, 1, pin] if parent == 1 else [2, pin]
        routes.append({"P": path, "Q": 3000, "T": r0_b_id})

    # P1-A: Basic-A factories -> Advanced(3)
    for i in range(basics_per_type):
        pin = basic_a_start + i
        parent = 1 if i % 2 == 0 else 2
        path = [pin, 1, 3] if parent == 1 else [pin, 2, 1, 3]
        routes.append({"P": path, "Q": 20, "T": p1_a_id})

    # P1-B: Basic-B factories -> Advanced(3)
    for i in range(basics_per_type):
        pin = basic_b_start + i
        parent = 1 if i % 2 == 0 else 2
        path = [pin, 1, 3] if parent == 1 else [pin, 2, 1, 3]
        routes.append({"P": path, "Q": 20, "T": p1_b_id})

    # P2 output: Advanced -> Launchpad
    routes.append({"P": [3, 1], "Q": 5, "T": p2_id})

    # ECU program routes
    routes.append({"P": [ecu_a_pin, 2], "Q": 3000, "T": r0_a_id})
    routes.append({"P": [ecu_b_pin, 2], "Q": 3000, "T": r0_b_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"R0-P2 {p2_product} on {planet_type_name} ({basics_per_type}+{basics_per_type} basic, {heads_per_ecu}+{heads_per_ecu} heads)",
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }


@app.get("/api/template/{setup}/{planet_type}/{product}", response_class=JSONResponse)
async def generate_template(setup: str, planet_type: str, product: str, request: Request):
    """Generate an importable template for a specific setup."""
    radius_km = float(request.query_params.get("radius_km", 5000))
    ccu_level = int(request.query_params.get("ccu_level", 5))

    # R0->P2: generate programmatically
    if setup == "r0_to_p2":
        template = _generate_r0_to_p2_template(planet_type, product, radius_km, ccu_level)
        if not template:
            return JSONResponse({"error": f"Cannot generate R0->P2 template for {product} on {planet_type} (CCU {ccu_level}, {radius_km:.0f}km)"}, status_code=404)
        return JSONResponse({"template": template})

    ref = _find_reference_template(product, setup)
    if not ref:
        return JSONResponse({"error": f"No reference template found for {product}"}, status_code=404)

    converted = convert_template(ref, to_planet_type=planet_type, game_data=game_data)

    # Ensure Diam is float (game requires it)
    if "Diam" in converted:
        converted["Diam"] = float(converted["Diam"])

    return JSONResponse({"template": converted})


def _sanitize(text: str, max_length: int = MAX_FEEDBACK_LENGTH) -> str:
    """Sanitize user input: escape HTML, strip control chars, enforce length."""
    text = text[:max_length]
    text = html.escape(text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.strip()


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request):
    return _render(request, "feedback.html")


@app.post("/feedback", response_class=HTMLResponse)
async def submit_feedback(request: Request):
    form = await request.form()
    name = _sanitize(form.get("name", "Anonymous"), 100)
    category = _sanitize(form.get("category", "general"), 50)
    message = _sanitize(form.get("message", ""))

    if not message:
        return _render(request, "feedback.html", error="Message is required.")

    # Store as JSON file with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name.replace(' ', '_'))[:30]
    filename = f"{timestamp}_{safe_name}.json"

    feedback = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "category": category,
        "message": message,
    }

    with open(FEEDBACK_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2)

    return _render(request, "feedback.html", success=True)


if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
