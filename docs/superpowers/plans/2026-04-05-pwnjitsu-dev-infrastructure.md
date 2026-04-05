# pwnjitsu.dev Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the eve-pi project into a public library repo and a private web repo, deploy to Railway at pwnjitsu.dev with auto-deploy from GitHub.

**Architecture:** Two repos — `eve-pi` (public, library + CLI) and `pwnjitsu-web` (private, FastAPI web layer). The web repo imports eve-pi as a pip dependency. Railway deploys the private repo with a Dockerfile. Routes are prefixed under `/eve/pi`.

**Tech Stack:** Python, FastAPI, Jinja2, Docker, Railway, GitHub

---

## File Structure

### eve-pi repo (public) — `C:\Development\eve-pi`
Remove the web layer. Keep everything else.
- Remove: `eve_pi/web/` (entire directory)
- Remove: `Caddyfile`
- Modify: `pyproject.toml` (remove web dependencies if any)
- Keep: everything else (eve_pi/, tests/, docs/, reference_templates/, etc.)

### pwnjitsu-web repo (private) — `C:\Development\pwnjitsu-web`
New repo with the web layer and deployment config.
- Create: `web/__init__.py`
- Create: `web/app.py` — main FastAPI app, landing page, mounts eve-pi routes
- Create: `web/templates/base.html` — shared layout
- Create: `web/templates/landing.html` — tool listing homepage
- Create: `web/templates/eve_pi/` — moved from eve_pi/web/templates/ (index.html, results.html, template_converter.html, feedback.html)
- Create: `web/static/favicon.svg` — moved from eve_pi/web/static/
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `railway.json`
- Create: `CLAUDE.md`

---

### Task 1: Prepare eve-pi repo for public release

**Repo:** `C:\Development\eve-pi`

- [ ] **Step 1: Remove the web directory**

```bash
rm -rf eve_pi/web
```

- [ ] **Step 2: Remove the Caddyfile**

```bash
rm Caddyfile
```

- [ ] **Step 3: Remove web-specific files**

```bash
rm -rf feedback
rm -f j125227.json
rm -f r0_p2_coolant_gas.json
```

- [ ] **Step 4: Update pyproject.toml**

The current pyproject.toml has no web dependencies (FastAPI etc. were installed manually). Add them as an optional `web` extra for anyone who wants to run the old web UI, but the base package stays dependency-light:

Replace the full `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "eve-pi"
version = "0.1.0"
description = "EVE Online Planetary Interaction optimizer — library and CLI"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "requests>=2.28",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
eve-pi = "eve_pi.cli.main:main"
```

- [ ] **Step 5: Verify tests still pass**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. Tests should not depend on the web layer. If any imports fail, they reference `eve_pi.web` and need to be removed.

- [ ] **Step 6: Add .gitignore**

Create `.gitignore`:

```
__pycache__/
*.pyc
*.egg-info/
.pi_cache/
dist/
build/
.pytest_cache/
*.egg
```

- [ ] **Step 7: Update CLAUDE.md**

Remove references to the web UI, Caddy, reload, and server commands. Keep the library/CLI documentation, verified values, data sources, and design decisions. Remove the "Start server" and "Caddy SSL" lines. Update the project overview to say "Python library + CLI".

- [ ] **Step 8: Commit and push**

```bash
git add -A
git commit -m "Remove web layer for public release — library and CLI only"
git remote add origin https://github.com/jwebbdev/eve-pi.git
git branch -M main
git push -u origin main
```

---

### Task 2: Scaffold the pwnjitsu-web repo

**Repo:** `C:\Development\pwnjitsu-web`

- [ ] **Step 1: Clone the repo and set up structure**

```bash
cd /c/Development
git clone https://github.com/jwebbdev/pwnjitsu-web.git
cd pwnjitsu-web
mkdir -p web/templates/eve_pi web/static
```

- [ ] **Step 2: Create requirements.txt**

```
fastapi>=0.104
uvicorn[standard]>=0.24
jinja2>=3.1
python-multipart>=0.0.6
git+https://github.com/jwebbdev/eve-pi.git@main
```

- [ ] **Step 3: Create web/__init__.py**

Empty file:

```python
```

- [ ] **Step 4: Create the main app — web/app.py**

This is the main FastAPI application. It serves the landing page at `/` and mounts all eve-pi routes under `/eve/pi`.

```python
"""pwnjitsu.dev — gaming tools platform."""
import json
import traceback
import html
import logging
import re
from pathlib import Path
from datetime import datetime
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
from eve_pi.capacity.planet_capacity import can_fit
from eve_pi.templates.converter import convert_template
from eve_pi.templates.generator import generate_template as gen_template

logger = logging.getLogger("pwnjitsu.web")

app = FastAPI(title="pwnjitsu.dev")

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Load game data once at startup
game_data = GameData.load()

# Feedback storage
FEEDBACK_DIR = Path(__file__).parent.parent / "feedback"
FEEDBACK_DIR.mkdir(exist_ok=True)
MAX_FEEDBACK_LENGTH = 5000


def _render(request, template_name, **context):
    """Helper to render a template with Starlette 1.0 compatible args."""
    return templates.TemplateResponse(request, template_name, context)


# ---- Landing page ----

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return _render(request, "landing.html")


# ---- EVE PI routes (mounted at /eve/pi) ----
# These are the routes from the original eve_pi/web/app.py,
# with all paths prefixed under /eve/pi.
# The full route handlers are copied below with updated paths.
```

Then copy ALL route handlers from the current `eve_pi/web/app.py` (lines 48-484), changing:
- `@app.get("/")` → `@app.get("/eve/pi")`
- `@app.post("/optimize")` → `@app.post("/eve/pi/optimize")`
- `@app.get("/template-converter")` → `@app.get("/eve/pi/template-converter")`
- `@app.post("/template/convert")` → `@app.post("/eve/pi/template/convert")`
- `@app.get("/api/template/...")` → `@app.get("/eve/pi/api/template/...")`
- `@app.get("/api/system-products/...")` → `@app.get("/eve/pi/api/system-products/...")`
- `@app.get("/feedback")` → `@app.get("/eve/pi/feedback")`
- `@app.post("/feedback")` → `@app.post("/eve/pi/feedback")`

Also update any `redirect` or internal URL references in the route handlers.

- [ ] **Step 5: Copy templates from eve-pi**

```bash
cp /c/Development/eve-pi/eve_pi/web/templates/base.html web/templates/eve_pi/base.html
cp /c/Development/eve-pi/eve_pi/web/templates/index.html web/templates/eve_pi/index.html
cp /c/Development/eve-pi/eve_pi/web/templates/results.html web/templates/eve_pi/results.html
cp /c/Development/eve-pi/eve_pi/web/templates/template_converter.html web/templates/eve_pi/template_converter.html
cp /c/Development/eve-pi/eve_pi/web/templates/feedback.html web/templates/eve_pi/feedback.html
cp /c/Development/eve-pi/eve_pi/web/static/favicon.svg web/static/favicon.svg
```

**Important:** Update template references in app.py to use `eve_pi/` prefix:
- `_render(request, "index.html", ...)` → `_render(request, "eve_pi/index.html", ...)`
- `_render(request, "results.html", ...)` → `_render(request, "eve_pi/results.html", ...)`
- etc.

**Important:** Update form actions and links in the HTML templates:
- In `index.html`: `action="/optimize"` → `action="/eve/pi/optimize"`
- In `base.html`: any nav links pointing to `/` should point to `/eve/pi` for the PI tool, `/` for the landing page
- In `results.html`: any fetch URLs like `/api/template/` → `/eve/pi/api/template/`
- In `template_converter.html`: form action `/template/convert` → `/eve/pi/template/convert`
- In `feedback.html`: form action `/feedback` → `/eve/pi/feedback`

- [ ] **Step 6: Create the landing page template — web/templates/landing.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>pwnjitsu.dev — Gaming Tools</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0a0a1a;
            color: #c8d6e5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        header {
            padding: 60px 20px 40px;
            text-align: center;
        }
        header h1 {
            font-size: 2.5rem;
            color: #00d4ff;
            margin-bottom: 8px;
        }
        header p {
            color: #8888aa;
            font-size: 1.1rem;
        }
        .tools {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            padding: 20px;
            max-width: 900px;
            width: 100%;
        }
        .tool-card {
            background: #12122a;
            border: 1px solid #2a2a4a;
            border-radius: 8px;
            padding: 24px;
            flex: 1 1 300px;
            transition: border-color 0.2s;
        }
        .tool-card:hover {
            border-color: #00d4ff;
        }
        .tool-card h2 {
            color: #00d4ff;
            font-size: 1.3rem;
            margin-bottom: 4px;
        }
        .tool-card .game {
            color: #ff6b6b;
            font-size: 0.85rem;
            margin-bottom: 12px;
        }
        .tool-card p {
            color: #8888aa;
            font-size: 0.95rem;
            line-height: 1.5;
            margin-bottom: 16px;
        }
        .tool-card a {
            display: inline-block;
            color: #00d4ff;
            text-decoration: none;
            border: 1px solid #00d4ff;
            padding: 8px 20px;
            border-radius: 4px;
            font-size: 0.9rem;
            transition: background 0.2s;
        }
        .tool-card a:hover {
            background: rgba(0, 212, 255, 0.1);
        }
        footer {
            margin-top: auto;
            padding: 30px;
            color: #555;
            font-size: 0.8rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>pwnjitsu.dev</h1>
        <p>Gaming tools and optimizers</p>
    </header>
    <div class="tools">
        <div class="tool-card">
            <h2>PI Optimizer</h2>
            <div class="game">EVE Online</div>
            <p>Optimize your Planetary Interaction colonies. Calculates the most profitable setups for your system, characters, and hauling capacity. Generates importable templates.</p>
            <a href="/eve/pi">Open Tool</a>
        </div>
    </div>
    <footer>pwnjitsu.dev</footer>
</body>
</html>
```

- [ ] **Step 7: Install dependencies and test locally**

```bash
cd /c/Development/pwnjitsu-web
pip install -e /c/Development/eve-pi
pip install -r requirements.txt
python -m uvicorn web.app:app --reload --port 8000
```

Verify:
- `http://localhost:8000/` shows the landing page
- `http://localhost:8000/eve/pi` shows the PI optimizer
- Form submission works at `/eve/pi/optimize`
- Template generation works
- All links/forms use `/eve/pi/` prefixed URLs

- [ ] **Step 8: Commit and push**

```bash
git add -A
git commit -m "Initial pwnjitsu.dev web app with eve-pi routes at /eve/pi"
git push -u origin main
```

---

### Task 3: Create Dockerfile and Railway config

**Repo:** `C:\Development\pwnjitsu-web`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install git for pip install from github
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create railway.json**

```json
{
    "$schema": "https://railway.com/railway.schema.json",
    "build": {
        "builder": "DOCKERFILE",
        "dockerfilePath": "Dockerfile"
    },
    "deploy": {
        "restartPolicyType": "ON_FAILURE",
        "restartPolicyMaxRetries": 10
    }
}
```

- [ ] **Step 3: Create .dockerignore**

```
__pycache__/
*.pyc
.git/
.pytest_cache/
*.egg-info/
feedback/
```

- [ ] **Step 4: Test Docker build locally**

```bash
docker build -t pwnjitsu-web .
docker run -p 8000:8000 pwnjitsu-web
```

Verify `http://localhost:8000/` and `http://localhost:8000/eve/pi` work.

- [ ] **Step 5: Commit and push**

```bash
git add Dockerfile railway.json .dockerignore
git commit -m "Add Dockerfile and Railway deployment config"
git push
```

---

### Task 4: Deploy to Railway and configure domain

This task involves manual steps in the Railway and registrar web UIs.

- [ ] **Step 1: Create Railway project**

1. Go to https://railway.app and sign in with GitHub
2. Click "New Project" → "Deploy from GitHub repo"
3. Select `jwebbdev/pwnjitsu-web`
4. Railway will detect the Dockerfile and start building

- [ ] **Step 2: Set spending cap**

1. In Railway project settings → Billing
2. Set usage limit to $10/month
3. Confirm the cap

- [ ] **Step 3: Configure custom domain**

1. In Railway service settings → Networking → Custom Domain
2. Add `pwnjitsu.dev`
3. Railway will show you the CNAME target (e.g., `something.up.railway.app`)

- [ ] **Step 4: Configure DNS at registrar**

1. Go to your domain registrar (where you bought pwnjitsu.dev)
2. Add a CNAME record: `pwnjitsu.dev` → Railway's CNAME target
3. If the registrar requires an A record for apex domain, use Railway's provided IP or set up their DNS proxy

- [ ] **Step 5: Verify deployment**

Wait for DNS propagation (can take up to 48h, usually minutes).
- `https://pwnjitsu.dev/` — landing page
- `https://pwnjitsu.dev/eve/pi` — PI optimizer

- [ ] **Step 6: Set up auto-deploy webhook for eve-pi updates**

1. In GitHub, go to `jwebbdev/eve-pi` → Settings → Webhooks
2. Add webhook pointing to a Railway deploy hook URL (found in Railway service settings → Deploy → Deploy Hooks)
3. Set it to trigger on push events to main branch
4. Test by pushing a trivial change to eve-pi

---

### Task 5: Create CLAUDE.md for pwnjitsu-web

**Repo:** `C:\Development\pwnjitsu-web`

- [ ] **Step 1: Create CLAUDE.md**

```markdown
# pwnjitsu.dev — Developer Guide

## Project Overview

Gaming tools platform. Private web layer that imports open-source tool libraries.
Hosted on Railway at https://pwnjitsu.dev with auto-deploy from GitHub.
Start server: `uvicorn web.app:app --reload --port 8000`

## Architecture

- Private repo: web UI, landing page, deployment config
- Public repos: tool libraries (eve-pi, etc.) imported as pip dependencies
- Single FastAPI app serves landing page at `/` and tools at `/game/tool` paths

## Tools

### EVE PI Optimizer (`/eve/pi`)
- Source: https://github.com/jwebbdev/eve-pi (public)
- Routes defined in `web/app.py`
- Templates in `web/templates/eve_pi/`
- Library installed via `requirements.txt` from GitHub

## Local Development

```bash
# Install eve-pi as editable for local dev
pip install -e ../eve-pi
pip install -r requirements.txt

# Run
uvicorn web.app:app --reload --port 8000
```

## Deployment

- Railway auto-deploys on push to main
- eve-pi updates trigger redeploy via GitHub webhook → Railway deploy hook
- Spending cap set at $10/mo — app sleeps if exceeded
- Domain: pwnjitsu.dev (CNAME to Railway)

## Common Gotchas

- Template paths use `eve_pi/` prefix (e.g., `_render(request, "eve_pi/index.html", ...)`)
- All eve-pi routes are prefixed with `/eve/pi`
- Form actions and fetch URLs in templates must use the full `/eve/pi/` prefix
- Local dev uses editable install (`pip install -e ../eve-pi`), production uses git+https
```

- [ ] **Step 2: Commit and push**

```bash
git add CLAUDE.md
git commit -m "Add CLAUDE.md developer guide"
git push
```
