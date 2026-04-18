"""
Geospatial operations: boundary loading/generation, point-in-polygon,
and cropland filtering.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

from src.config import (
    BBOX_TUPLE,
    BOUNDARIES_FILE,
    FALLBACK_BUFFER_DEGREES,
    LANDCOVER_FILE,
    TARGET_DISTRICTS,
)

logger = logging.getLogger(__name__)

WGS84 = "EPSG:4326"
UTM48N = "EPSG:32648"  # UTM Zone 48N covers Cambodia — used for area calculations


def load_district_boundaries(boundaries_file: Path = BOUNDARIES_FILE) -> gpd.GeoDataFrame:
    """
    Load district boundary polygons.

    Tries to load the GADM GeoJSON from data/boundaries/. If the file is
    missing, falls back to approximate circular buffers around the known
    district centers defined in config.py.
    """
    boundaries_file = Path(boundaries_file)

    if not boundaries_file.exists():
        logger.warning(
            "District boundary file not found: %s\n"
            "Falling back to approximate circular buffers (accuracy ±15 km).\n"
            "Download Cambodia GADM Level-3 GeoJSON from https://gadm.org/download_country.html\n"
            "and save as %s for accurate results.",
            boundaries_file,
            boundaries_file,
        )
        return create_fallback_boundaries()

    gdf = gpd.read_file(boundaries_file)
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(WGS84)

    # Attempt to find the district name column
    name_col = None
    for candidate in ("name", "NAME", "NAME_3", "NAME_2", "district", "District", "DISTRICT"):
        if candidate in gdf.columns:
            name_col = candidate
            break

    if name_col is None:
        logger.warning(
            "No recognized name column found in %s. Columns: %s",
            boundaries_file.name, list(gdf.columns),
        )
        gdf["name"] = [f"District_{i}" for i in range(len(gdf))]
    elif name_col != "name":
        gdf = gdf.rename(columns={name_col: "name"})

    # Filter to Battambang bounding box
    west, south, east, north = BBOX_TUPLE
    bbox_poly = box(west, south, east, north)
    gdf = gdf[gdf.geometry.intersects(bbox_poly)].reset_index(drop=True)

    logger.info("Loaded %d district boundaries from %s.", len(gdf), boundaries_file.name)
    return gdf[["name", "geometry"]]


def create_fallback_boundaries(
    districts: list[dict] = TARGET_DISTRICTS,
    buffer_deg: float = FALLBACK_BUFFER_DEGREES,
) -> gpd.GeoDataFrame:
    """
    Create approximate district polygons by buffering known center coordinates.

    NOTE: Buffers are in degrees (not meters). At Cambodia's latitude,
    0.15° ≈ 16 km radius. Use GADM boundaries for accurate results.
    """
    geometries = []
    names = []
    for d in districts:
        pt = Point(d["lon"], d["lat"])
        # Buffer in geographic CRS — acceptable approximation for ~15 km radius
        geometries.append(pt.buffer(buffer_deg))
        names.append(d["name"])

    gdf = gpd.GeoDataFrame({"name": names, "geometry": geometries}, crs=WGS84)
    logger.warning(
        "Using approximate fallback district boundaries (circular buffers, r=%.2f°). "
        "District assignments near boundaries may be inaccurate.",
        buffer_deg,
    )
    return gdf


def hotspots_to_geodataframe(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Convert a normalized FIRMS DataFrame to a GeoDataFrame (EPSG:4326)."""
    if df.empty:
        return gpd.GeoDataFrame(df, geometry=[], crs=WGS84)

    geometry = gpd.points_from_xy(df["longitude"], df["latitude"])
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=WGS84)
    return gdf


def assign_districts(
    hotspots_gdf: gpd.GeoDataFrame,
    boundaries_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Assign each hotspot to a district via point-in-polygon spatial join.

    Points that fall outside all district polygons are labeled
    "Outside_Battambang". A secondary nearest-neighbour pass assigns
    any remaining unmatched points to the closest district, which handles
    points that fall in small gaps between non-contiguous polygons.
    """
    if hotspots_gdf.empty:
        hotspots_gdf["district"] = pd.NA
        return hotspots_gdf

    # Ensure same CRS
    if boundaries_gdf.crs != hotspots_gdf.crs:
        boundaries_gdf = boundaries_gdf.to_crs(hotspots_gdf.crs)

    joined = gpd.sjoin(
        hotspots_gdf,
        boundaries_gdf[["name", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.rename(columns={"name": "district"})
    joined = joined.drop(columns=["index_right"], errors="ignore")

    # Secondary pass: nearest for unassigned points
    unassigned_mask = joined["district"].isna()
    if unassigned_mask.any():
        unassigned = hotspots_gdf[unassigned_mask.values]
        nearest = gpd.sjoin_nearest(
            unassigned,
            boundaries_gdf[["name", "geometry"]],
            how="left",
        )
        nearest = nearest.rename(columns={"name": "district"})
        nearest = nearest.drop(columns=["index_right"], errors="ignore")
        joined.loc[unassigned_mask, "district"] = nearest["district"].values
        logger.debug(
            "Nearest-neighbour assigned %d point(s) that fell outside all polygons.",
            unassigned_mask.sum(),
        )

    # Fill any still-unassigned (shouldn't happen, but defensive)
    joined["district"] = joined["district"].fillna("Outside_Battambang")

    logger.info(
        "District assignment complete: %d hotspots, %d districts represented.",
        len(joined),
        joined["district"].nunique(),
    )
    return joined.reset_index(drop=True)


def filter_agricultural(
    hotspots_gdf: gpd.GeoDataFrame,
    landcover_path: Path = None,
) -> tuple[gpd.GeoDataFrame, bool]:
    """
    Filter hotspots to agricultural fires.

    Always applies type==0 (presumed vegetation fire) filter.
    Optionally applies spatial cropland mask from ESA WorldCover (class 40).

    Returns:
        (filtered GeoDataFrame, using_type_filter_only: bool)
    """
    landcover_path = landcover_path or LANDCOVER_FILE
    landcover_path = Path(landcover_path)

    before = len(hotspots_gdf)
    gdf = hotspots_gdf[hotspots_gdf["type"] == 0].copy()
    logger.info(
        "type==0 filter: %d → %d records (removed %d non-vegetation).",
        before, len(gdf), before - len(gdf),
    )

    if not landcover_path.exists():
        logger.info(
            "Cropland mask not found at %s. Using type==0 filter only.\n"
            "Download ESA WorldCover tiles from https://esa-worldcover.org/en\n"
            "and extract cropland (class 40) polygons to %s for stricter filtering.",
            landcover_path,
            landcover_path,
        )
        return gdf, True  # using_type_filter_only = True

    try:
        cropland = gpd.read_file(landcover_path)
        if cropland.crs is None:
            cropland = cropland.set_crs(WGS84)
        elif cropland.crs.to_epsg() != 4326:
            cropland = cropland.to_crs(WGS84)

        before_crop = len(gdf)
        gdf_crop = gpd.sjoin(gdf, cropland[["geometry"]], how="inner", predicate="within")
        gdf_crop = gdf_crop.drop(columns=["index_right"], errors="ignore")
        gdf_crop = gdf_crop.reset_index(drop=True)
        logger.info(
            "Cropland spatial filter: %d → %d records (removed %d non-cropland).",
            before_crop, len(gdf_crop), before_crop - len(gdf_crop),
        )
        return gdf_crop, False  # using_type_filter_only = False

    except Exception as exc:
        logger.warning("Failed to apply cropland filter (%s). Falling back to type==0 only.", exc)
        return gdf, True


def compute_district_areas_km2(boundaries_gdf: gpd.GeoDataFrame) -> dict[str, float]:
    """
    Compute district areas in km² using UTM Zone 48N projection.

    Returns a dict mapping district name → area (km²).
    """
    projected = boundaries_gdf.to_crs(UTM48N)
    return {
        row["name"]: row.geometry.area / 1e6
        for _, row in projected.iterrows()
    }
