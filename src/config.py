from pathlib import Path

# ---------------------------------------------------------------------------
# Spatial extent
# ---------------------------------------------------------------------------

BBOX = {"west": 102.80, "south": 12.70, "east": 103.70, "north": 13.40}
BBOX_TUPLE = (102.80, 12.70, 103.70, 13.40)  # (west, south, east, north)

# Target districts in Battambang province (Sampov Loun / Pailin excluded)
TARGET_DISTRICTS = [
    {"name": "Sangkae",                 "lat": 13.10, "lon": 103.20},
    {"name": "Banan",                   "lat": 12.95, "lon": 103.15},
    {"name": "Moung Ruessei",           "lat": 12.95, "lon": 103.50},
    {"name": "Thma Koul",               "lat": 13.25, "lon": 103.15},
    {"name": "Koas Krala",              "lat": 13.05, "lon": 103.40},
    {"name": "Bavel",                   "lat": 12.85, "lon": 103.10},
    {"name": "Battambang Municipality", "lat": 13.10, "lon": 103.20},
]

# Fallback polygon radius when GADM boundaries are not available
FALLBACK_BUFFER_DEGREES = 0.15

# ---------------------------------------------------------------------------
# NASA FIRMS API
# ---------------------------------------------------------------------------

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_SOURCE = "VIIRS_SNPP_SP"
FIRMS_DAY_RANGE_MAX = 10  # API hard limit per single request

# Available sources for reference
FIRMS_SOURCES = {
    "VIIRS_SNPP_SP":   "VIIRS S-NPP Standard (2012-01-20–present) [recommended]",
    "VIIRS_NOAA20_NRT": "VIIRS NOAA-20 NRT (2018-04-01–present)",
    "VIIRS_NOAA21_NRT": "VIIRS NOAA-21 NRT (2024-01-17–present)",
    "MODIS_SP":         "MODIS Standard (2000-11-01–present)",
}

# ---------------------------------------------------------------------------
# Analysis periods
# ---------------------------------------------------------------------------

ANALYSIS_START = "2023-01-01"
ANALYSIS_END   = "2025-12-31"

# Harvest burning peak months (1-indexed)
WET_SEASON_MONTHS  = [9, 10]    # post wet-season harvest → burning peak
DRY_SEASON_MONTHS  = [3, 4]     # post dry-season harvest + general burning
DRY_PEAK_MONTHS    = [1, 2]     # dry season peak (mostly forest fires)
PEAK_MONTHS        = WET_SEASON_MONTHS + DRY_SEASON_MONTHS

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

# ---------------------------------------------------------------------------
# File paths (all anchored to project root)
# ---------------------------------------------------------------------------

PROJECT_ROOT    = Path(__file__).resolve().parent.parent

DATA_RAW        = PROJECT_ROOT / "data" / "raw"
DATA_BOUNDARIES = PROJECT_ROOT / "data" / "boundaries"
DATA_LANDCOVER  = PROJECT_ROOT / "data" / "landcover"
DATA_PROCESSED  = PROJECT_ROOT / "data" / "processed"

OUTPUT_MAPS     = PROJECT_ROOT / "output" / "maps"
OUTPUT_CHARTS   = PROJECT_ROOT / "output" / "charts"
OUTPUT_TABLES   = PROJECT_ROOT / "output" / "tables"
OUTPUT_REPORT   = PROJECT_ROOT / "output" / "report.md"

# Expected filenames for external data
BOUNDARIES_FILE    = DATA_BOUNDARIES / "battambang_districts.geojson"
LANDCOVER_FILE     = DATA_LANDCOVER  / "battambang_cropland.geojson"

# Processed data files
PROCESSED_HOTSPOTS = DATA_PROCESSED / "hotspots_assigned.parquet"
PROCESSED_MONTHLY  = DATA_PROCESSED / "monthly_aggregation.parquet"
PROCESSED_SUMMARY  = DATA_PROCESSED / "district_summary.csv"
