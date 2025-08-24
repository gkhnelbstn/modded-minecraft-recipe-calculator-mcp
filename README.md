# modded-minecraft-recipe-calculator-mcp
 CLI-based tool to analyze Minecraft modpack recipes and compute total raw material costs. It reads datapack-like JSON recipes/tags, resolves crafting chains recursively, and outputs deterministic JSON and optional Mermaid diagrams.

> Last updated: 2025-08-24

## Features
 - Deterministic, data-driven analysis from JSON
 - Recursive recipe resolution with cycle detection and memoization
 - Tag resolution (first match for now; preferences configurable in future)
 - Outputs:
   - Pretty JSON with total raw materials and step list
   - Mermaid flowchart (LR) for crafting graph

## Requirements
 - Python 3.11+
 - No extra deps for CLI (FastAPI/Celery are for API path; optional)

## Quick Start (CLI)
 Run as a module. Ensure project `src` is on `PYTHONPATH`.

 Windows PowerShell:
 ```powershell
 $env:PYTHONPATH="src"; python -m mcbom.cli.main minecraft:stone_pickaxe -n 1 --datapack-path instance --diagram
 ```

 Arguments:
 - `item` – target item id, e.g. `minecraft:stick`, `ae2:controller`
 - `-n, --quantity` – target quantity (default 1)
 - `--cube N` – use N^3 as quantity (e.g., 3 -> 27)
 - `--datapack-path` – base folder containing `data/*/recipes` and `data/*/tags/items`
 - `-o, --output` – write JSON to file
 - `--diagram` – also print Mermaid diagram

 Example (write JSON to file):
 ```powershell
 $env:PYTHONPATH="src"; python -m mcbom.cli.main minecraft:stick -n 8 --datapack-path instance -o stick.json --diagram
 ```

## Where do recipes come from?
 This tool expects a filesystem layout like datapacks:

 ```
 <BASE>/data/<namespace>/recipes/**/*.json
 <BASE>/data/<namespace>/tags/items/**/*.json
 ```

 Many modpacks ship most recipes inside JARs (mods). We now scan mod JARs under `<BASE>/mods/*.jar` for datapack-like paths (`data/*/recipes/**/*.json` and `data/*/tags/items/**/*.json`) and merge them, while preferring on-disk datapacks over JAR contents.

### Instance layout (generic)
 Common on-disk datapack locations under an instance's `minecraft` folder include:
 - `minecraft/kubejs/data/...`
 - `minecraft/config/openloader/data/...`
 - world datapacks (if any): `minecraft/saves/<world>/datapacks/...`

 You can point `--datapack-path` directly to `minecraft/kubejs` (or `minecraft/config/openloader/data`) so that `<BASE>/data/...` exists. For example (generic Windows):

 ```powershell
$base = "C:/path/to/your/instance/minecraft/kubejs"
$env:PYTHONPATH="src"; python -m mcbom.cli.main minecraft:stick -n 4 --datapack-path $base --diagram
```

 If you are unsure where `data/*/recipes` exists, search:

 ```powershell
# Define your instance root (generic example)
$instance = "C:/path/to/your/instance"

# Show first 20 recipe JSON files found under instance
Get-ChildItem -Path $instance -Recurse -Filter *.json -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*\\data\\*\\recipes\\*" } |
  Select-Object -First 20 -ExpandProperty FullName

# Show first 10 tag item JSON files
Get-ChildItem -Path $instance -Recurse -Filter *.json -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*\\data\\*\\tags\\items\\*" } |
  Select-Object -First 10 -ExpandProperty FullName
```

 If nothing turns up, rely on JAR scanning (now supported) or place a custom datapack folder and point `--datapack-path` there.

## Docker + UI Quickstart

Run the API and open the minimal UI served at `/ui`.

1. Set your instance's `minecraft` folder path as an environment variable (Windows example):

```powershell
$env:MCBOM_INSTANCE_HOST="C:/path/to/your/instance/minecraft"
```

2. Start containers:

```powershell
docker compose up -d --build
```

3. Use the UI and API:
- UI: http://localhost:8000/ui
- API: http://localhost:8000

## API: synchronous calculate endpoint

POST `/calculate` performs an on-demand analysis using the parser + engine and can also return a Mermaid diagram.

Example:

```bash
curl -X POST http://localhost:8000/calculate \
  -H "Content-Type: application/json" \
  -d '{
        "item_id": "minecraft:stick",
        "quantity": 4,
        "instance_path": "/data/instance",
        "diagram": true
      }'
```

Response shape:

```json
{
  "analysis": {
    "target": "minecraft:stick",
    "quantity": 4,
    "total_raw_materials": [ {"item":"minecraft:stick","count":4} ],
    "steps": []
  },
  "mermaid": "flowchart LR..."
}
```

Notes:
- `instance_path` defaults to `/data/instance` in containers and can be overridden.
- Parser walks on-disk datapacks first, then merges datapack-like entries from mod JARs.

## Frontend (minimal)

Static React UI under `frontend/` is mounted at `/ui`. It lets you:
- Enter `item_id`, `quantity`, and `instance_path`.
- Toggle Mermaid diagram rendering.
- It calls `/calculate` and renders JSON + diagram.

## Windows volume mapping notes

`docker-compose.yml` uses the env var `MCBOM_INSTANCE_HOST` to map your local instance folder into the container as `/data/instance` (read-only). Example value:

```
MCBOM_INSTANCE_HOST=C:/path/to/your/instance/minecraft
```

If the path contains spaces, keep forward slashes as shown.

## Roadmap / TODOs

- Parser
  - Support more recipe types (smelting/blasting/stonecutting/etc.).
  - Normalize outputs (counts) and ingredients across types.
  - Resolve tags with configurable preference strategies.
  - Optional importer for JEI/RecipeManager dumps (see below).
- Analyzer/Engine
  - Multiple recipe options per item with deterministic preference order.
  - Better cycle detection diagnostics and caching.
- API
  - Upload endpoint to ingest JEI dumps and merge with on-disk/JAR data.
  - Config endpoint (preferences, tag strategies).
- Frontend
  - Item search/autocomplete from loaded namespaces.
  - Rich diagram interactions (expand/collapse, tooltips).
- Testing
  - Pytest unit tests for parser/engine/exporter with a tiny sample datapack.
  - Coverage and CI gates.
- Packaging
  - Pre-commit with black/isort/ruff/mypy.
  - Docker image hardening, non-root user.

### JEI/Recipe dump (planned)

We plan an optional importer that reads JEI or server-side dumps of the RecipeManager and converts them into our internal normalized schema. This closes gaps for recipes that are not represented as datapack JSONs directly. Once available, drop the dump files into a mounted folder and call an ingest endpoint or CLI to merge them for analysis.

## API & Worker (optional)
 There is a FastAPI app and a Celery worker under `src/mcbom/api` and `src/mcbom/worker`. For CLI-only use, these are not required.

