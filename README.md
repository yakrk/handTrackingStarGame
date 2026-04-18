# Battambang Fire Hotspot Analysis Tool

NASA FIRMS衛星データを使用したバッタンバン州農業野焼きホットスポット分析ツール。
バイオ炭カーボンクレジット事業（Puro.earth CORC）の穂軸調達ターゲット選定と
Additionality（追加性）エビデンス構築を目的として開発。

---

## Overview

This tool fetches and analyzes NASA FIRMS (Fire Information for Resource Management System)
satellite fire hotspot data for Cambodia's Battambang province to:

1. **Identify procurement target districts** — where agricultural residue burning is most
   concentrated (corn cob residue post-harvest)
2. **Build additionality baseline** — quantitative evidence of "fire avoidance" for
   carbon credit applications (2023–2025 baseline period)

**Analysis area:** 7 districts in Battambang province (Sampov Loun / Pailin excluded):
Sangkae, Banan, Moung Ruessei, Thma Koul, Koas Krala, Bavel, Battambang Municipality

---

## Prerequisites

- Python 3.10+
- [NASA Earthdata account](https://urs.earthdata.nasa.gov/users/new) (free)
- FIRMS MAP KEY (see Step 1 below)

---

## Installation

```bash
# Clone / enter the project
cd battambang-fire-analysis

# Install with pip (editable mode)
pip install -e .

# Or with uv
uv sync

# Or with Poetry
poetry install
```

---

## Step-by-Step Setup

### Step 1 — Get Your FIRMS MAP KEY

1. Register for a free NASA Earthdata account: https://urs.earthdata.nasa.gov/users/new
2. Go to https://firms.modaps.eosdis.nasa.gov/api/area/
3. Click **"Get MAP KEY"** and follow instructions
4. Copy your key

```bash
cp .env.example .env
# Edit .env and replace "your_map_key_here" with your actual key:
# FIRMS_MAP_KEY=abcdef1234567890abcdef1234567890
```

Rate limit: 5,000 API transactions per 10-minute interval (free tier).

---

### Step 2 — Fetch Data (API, up to 10 days per request)

The API supports up to 10 days per request. For the full 3-year analysis (2023–2025),
the script automatically splits the date range into 10-day chunks:

```bash
# Full 3-year fetch (2023–2025) — ~110 API requests, takes ~5 min
python scripts/fetch_firms.py --start 2023-01-01 --end 2025-12-31

# Quick test with a 10-day window
python scripts/fetch_firms.py --start 2025-12-22 --end 2025-12-31

# Use a different source (MODIS has data back to 2000)
python scripts/fetch_firms.py --source MODIS_SP --start 2020-01-01 --end 2020-12-31
```

Downloaded chunks are cached in `data/raw/`. Re-runs skip already-cached files automatically
(use `--no-skip-existing` to force re-download).

---

### Step 2b — Archive Download for Historical Data (alternative)

For data older than what the API easily provides, or if you prefer batch downloads:

1. Go to https://firms.modaps.eosdis.nasa.gov/download/
2. Select:
   - **Source:** VIIRS_SNPP_SP
   - **Region:** Custom area: `102.80, 12.70, 103.70, 13.40` (W, S, E, N)
   - **Date range:** e.g., 2023-01-01 to 2025-12-31
3. Download the CSV file(s) and place them in `data/raw/`

The `analyze.py` script loads all `*.csv` files in `data/raw/` regardless of origin.

---

### Step 3 — District Boundaries (recommended)

For accurate district assignment, download the official GADM boundary data:

1. Go to https://gadm.org/download_country.html
2. Select **Cambodia** and download **Level 3 (District)** as GeoJSON
3. Open in QGIS or use the following Python snippet to filter Battambang:

```python
import geopandas as gpd
gdf = gpd.read_file("gadm41_KHM_3.json")
btb = gdf[gdf["NAME_2"] == "Battambang"]  # adjust column name if needed
btb.to_file("data/boundaries/battambang_districts.geojson", driver="GeoJSON")
```

4. Save as `data/boundaries/battambang_districts.geojson`

**Without this file:** The tool falls back to approximate circular buffers
(radius ≈ 15 km) around known district centers. Results will be approximate.

---

### Step 4 — ESA WorldCover Cropland Mask (optional but recommended)

To distinguish agricultural fires from forest/grassland fires:

1. Go to https://esa-worldcover.org/en
2. Download tiles covering Battambang (approximately tile `N12E102`)
3. Extract cropland class 40 polygons (using QGIS or rasterio + geopandas):

```python
import rasterio
import numpy as np
import geopandas as gpd
from rasterio.features import shapes
from shapely.geometry import shape

with rasterio.open("ESA_WorldCover_10m_2021_N12E102.tif") as src:
    data = src.read(1)
    transform = src.transform
    crs = src.crs

cropland_mask = (data == 40)
geoms = [
    {"geometry": shape(geom), "properties": {"class": 40}}
    for geom, val in shapes(cropland_mask.astype(np.uint8), transform=transform)
    if val == 1
]
cropland_gdf = gpd.GeoDataFrame.from_features(geoms, crs=crs)
cropland_gdf = cropland_gdf.to_crs("EPSG:4326")
cropland_gdf.to_file("data/landcover/battambang_cropland.geojson", driver="GeoJSON")
```

**Without this file:** Only `type==0` (vegetation fire) filter is applied.

---

### Step 5 — Run Analysis

```bash
python scripts/analyze.py

# Options:
python scripts/analyze.py --confidence high       # strict: high confidence only
python scripts/analyze.py --no-landcover          # skip cropland filter
python scripts/analyze.py --archive data/raw/archive_2022.csv  # add archive CSV
```

Outputs saved to `data/processed/`:
- `hotspots_assigned.parquet` — all hotspots with district labels
- `monthly_aggregation.parquet` — monthly counts per district
- `district_summary.csv` — district ranking table

---

### Step 6 — Generate Output

```bash
python scripts/generate_output.py

# Options:
python scripts/generate_output.py --no-heatmap   # skip FRP heatmap (faster)
python scripts/generate_output.py --no-map       # skip interactive HTML map
```

---

## Output Files

| File | Description |
|------|-------------|
| `output/maps/hotspot_map.html` | Interactive Leaflet map — open in any browser |
| `output/charts/monthly_trend.png` | Stacked bar chart: 36-month hotspot trend |
| `output/charts/frp_heatmap.png` | FRP heatmap: district × month |
| `output/charts/annual_comparison.png` | Year-over-year seasonal pattern (2023–2025) |
| `output/tables/district_summary.csv` | District ranking table (CSV) |
| `output/tables/district_summary.xlsx` | District ranking table (Excel, color-coded) |
| `output/report.md` | Auto-generated analysis report (Markdown) |

---

## Data Sources

| Source | Description | URL |
|--------|-------------|-----|
| NASA FIRMS VIIRS_SNPP_SP | Fire hotspot data (primary) | https://firms.modaps.eosdis.nasa.gov |
| GADM Level 3 | Cambodia district boundaries | https://gadm.org |
| ESA WorldCover 10m | Land cover / cropland mask | https://esa-worldcover.org |

---

## Important Limitations

### Cloud Cover (Wet Season Underestimation)
VIIRS uses infrared thermal detection, which is blocked by cloud cover.
Sep–Oct (wet season) data may **underestimate actual burning by 20–50%**.
Treat Sep–Oct hotspot counts as **lower bounds**.

### VIIRS Detection Threshold
Small fires (<~0.1 ha) or low-intensity smoldering may not be detected.
The satellite captures moderate-to-large burning events.

### Agricultural vs. Forest Fire Distinction
`type==0` (vegetation fire) includes all terrestrial fires.
The ESA WorldCover cropland mask provides stricter filtering but is not
available without manual download. Without it, results include some
grassland/forest fires, particularly in Jan–Feb.

### Boundary Accuracy (Fallback Mode)
Without GADM boundaries, circular buffer approximations are used.
District assignments within ±15 km of borders may be inaccurate.

---

## Project Structure

```
battambang-fire-analysis/
├── pyproject.toml
├── .env.example          # Template: FIRMS_MAP_KEY=your_key_here
├── README.md
├── src/
│   ├── config.py         # All settings (area, periods, paths)
│   ├── firms_client.py   # NASA FIRMS API client
│   ├── data_loader.py    # CSV loading + normalization
│   ├── spatial.py        # Boundary loading, point-in-polygon, cropland filter
│   ├── analysis.py       # Temporal aggregation + district summary
│   ├── visualize.py      # Folium map, Matplotlib charts, Excel output
│   └── report.py         # Auto-generate Markdown report
├── data/
│   ├── raw/              # FIRMS CSV files (API chunks + archive)
│   ├── boundaries/       # District boundary GeoJSON (GADM)
│   ├── landcover/        # ESA WorldCover cropland polygons
│   └── processed/        # Analysis outputs (Parquet/CSV)
├── output/
│   ├── maps/             # HTML interactive maps
│   ├── charts/           # PNG charts
│   └── tables/           # CSV/Excel summary tables
└── scripts/
    ├── fetch_firms.py    # Step 1: fetch data
    ├── analyze.py        # Step 2: spatial analysis
    └── generate_output.py # Step 3: generate all outputs
```

---

## Carbon Credit Context

The analysis outputs are designed to support:

- **Sourcing target selection**: Districts with highest hotspot density → highest
  potential for corn-cob biochar feedstock procurement (alternative to burning)
- **Additionality baseline**: 3-year fire frequency data establishes the "without
  project" scenario for Puro.earth CORC biochar methodology
- **Thai Burn-Free regulation tracking**: January 2026 Thai regulation baseline
  allows monitoring cross-border burning displacement post-implementation

---

*Built for the Battambang province corn-cob biochar carbon credit project.*
*Satellite data: NASA FIRMS — https://firms.modaps.eosdis.nasa.gov*
