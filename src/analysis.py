"""
Time-series aggregation and district-level summarization.

Pure pandas/numpy — no geospatial operations here.
"""

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import MONTH_NAMES, PEAK_MONTHS
from src.spatial import compute_district_areas_km2

logger = logging.getLogger(__name__)

CONFIDENCE_ORDER = {"low": 0, "nominal": 1, "high": 2}


def filter_by_confidence(
    hotspots_gdf: gpd.GeoDataFrame,
    min_confidence: str = "nominal",
) -> gpd.GeoDataFrame:
    """Keep only hotspots at or above the specified confidence level."""
    min_level = CONFIDENCE_ORDER.get(min_confidence, 1)
    mask = hotspots_gdf["confidence"].map(
        lambda v: CONFIDENCE_ORDER.get(str(v).lower(), 0) >= min_level
    )
    filtered = hotspots_gdf[mask].reset_index(drop=True)
    logger.info(
        "Confidence filter (>=%s): %d → %d records.",
        min_confidence, len(hotspots_gdf), len(filtered),
    )
    return filtered


def aggregate_by_district_month(hotspots_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """
    Aggregate hotspot counts and FRP statistics by (district, year, month).

    Returns a plain DataFrame (no geometry).
    """
    if hotspots_gdf.empty:
        return pd.DataFrame()

    df = pd.DataFrame(hotspots_gdf.drop(columns=["geometry"], errors="ignore"))

    # Ensure required columns
    for col in ("district", "year", "month", "frp", "confidence"):
        if col not in df.columns:
            logger.warning("Column '%s' missing — aggregation may be incomplete.", col)

    grp = df.groupby(["district", "year", "month"], dropna=False)

    monthly = grp.agg(
        hotspot_count          = ("latitude",   "count"),
        avg_frp                = ("frp",        "mean"),
        max_frp                = ("frp",        "max"),
        total_frp              = ("frp",        "sum"),
    ).reset_index()

    # Confidence breakdown
    def _conf_count(sub_df: pd.DataFrame, level: str) -> int:
        return (sub_df["confidence"].str.lower() == level).sum()

    conf_agg = (
        df.groupby(["district", "year", "month"])
        .apply(lambda g: pd.Series({
            "high_confidence_count":         _conf_count(g, "high"),
            "nominal_confidence_count":      _conf_count(g, "nominal"),
            "low_confidence_count":          _conf_count(g, "low"),
            "nominal_plus_high_count":       (_conf_count(g, "nominal") + _conf_count(g, "high")),
        }))
        .reset_index()
    )

    monthly = monthly.merge(conf_agg, on=["district", "year", "month"], how="left")

    monthly["period_label"] = monthly.apply(
        lambda r: f"{int(r['year'])}-{int(r['month']):02d}", axis=1
    )
    monthly["is_peak_month"] = monthly["month"].isin(PEAK_MONTHS)
    monthly["month_name"]    = monthly["month"].map(MONTH_NAMES)

    monthly = monthly.sort_values(["district", "year", "month"]).reset_index(drop=True)
    logger.info(
        "Monthly aggregation: %d district×month combinations across %d districts.",
        len(monthly), monthly["district"].nunique(),
    )
    return monthly


def compute_district_summary(
    hotspots_gdf: gpd.GeoDataFrame,
    boundaries_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """
    Compute per-district summary statistics for the full analysis period.

    Includes hotspot density (per km²), peak month, and priority rank.
    """
    if hotspots_gdf.empty:
        logger.warning("No hotspot data to summarize.")
        return pd.DataFrame()

    df = pd.DataFrame(hotspots_gdf.drop(columns=["geometry"], errors="ignore"))
    years_in_data = df["year"].nunique() if "year" in df.columns else 3
    years_in_data = max(years_in_data, 1)

    # Basic stats per district
    grp = df.groupby("district", dropna=False)
    summary = grp.agg(
        total_hotspots = ("latitude",    "count"),
        avg_frp_all    = ("frp",         "mean"),
        max_frp_all    = ("frp",         "max"),
    ).reset_index()

    summary["hotspots_per_year"] = (summary["total_hotspots"] / years_in_data).round(1)

    # High-confidence percentage
    high_conf = (
        df[df["confidence"].str.lower() == "high"]
        .groupby("district")
        .size()
        .rename("high_conf_count")
        .reset_index()
    )
    summary = summary.merge(high_conf, on="district", how="left")
    summary["high_conf_count"] = summary["high_conf_count"].fillna(0)
    summary["high_confidence_pct"] = (
        100.0 * summary["high_conf_count"] / summary["total_hotspots"]
    ).round(1)

    # Peak month hotspot counts
    peak_df = df[df["month"].isin(PEAK_MONTHS)] if "month" in df.columns else pd.DataFrame()
    if not peak_df.empty:
        peak_grp = (
            peak_df.groupby("district")
            .size()
            .rename("peak_month_hotspots")
            .reset_index()
        )
        summary = summary.merge(peak_grp, on="district", how="left")
    else:
        summary["peak_month_hotspots"] = 0
    summary["peak_month_hotspots"] = summary["peak_month_hotspots"].fillna(0).astype(int)
    summary["peak_month_pct"] = (
        100.0 * summary["peak_month_hotspots"] / summary["total_hotspots"].replace(0, np.nan)
    ).fillna(0).round(1)

    # Identify the single month with most hotspots per district
    if "month" in df.columns:
        peak_month_per_district = (
            df.groupby(["district", "month"])
            .size()
            .reset_index(name="cnt")
            .sort_values("cnt", ascending=False)
            .drop_duplicates("district")
            [["district", "month"]]
        )
        peak_month_per_district["peak_month"] = peak_month_per_district["month"].map(MONTH_NAMES)
        summary = summary.merge(
            peak_month_per_district[["district", "peak_month"]], on="district", how="left"
        )
    else:
        summary["peak_month"] = "Unknown"

    # Year with most hotspots
    if "year" in df.columns:
        peak_year_per_district = (
            df.groupby(["district", "year"])
            .size()
            .reset_index(name="cnt")
            .sort_values("cnt", ascending=False)
            .drop_duplicates("district")
            [["district", "year"]]
            .rename(columns={"year": "peak_year"})
        )
        summary = summary.merge(peak_year_per_district, on="district", how="left")
    else:
        summary["peak_year"] = "Unknown"

    # District area and hotspot density
    area_map = compute_district_areas_km2(boundaries_gdf)
    summary["district_area_km2"] = summary["district"].map(area_map).fillna(np.nan)
    summary["hotspot_density_per_km2"] = (
        summary["total_hotspots"] / summary["district_area_km2"].replace(0, np.nan)
    ).round(4)

    # Priority rank (descending density; ties broken by peak_month_hotspots)
    summary = summary.sort_values(
        ["hotspot_density_per_km2", "peak_month_hotspots"],
        ascending=[False, False],
    ).reset_index(drop=True)
    summary["priority_rank"] = range(1, len(summary) + 1)

    # Round for readability
    summary["avg_frp_all"]  = summary["avg_frp_all"].round(2)
    summary["max_frp_all"]  = summary["max_frp_all"].round(2)

    logger.info("District summary computed for %d districts.", len(summary))
    return summary


def identify_peak_periods(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize burning activity during peak harvest months per district.
    """
    if monthly_df.empty:
        return pd.DataFrame()

    peak = monthly_df[monthly_df["is_peak_month"]].copy()
    if peak.empty:
        logger.warning("No peak-month data in monthly_df.")
        return pd.DataFrame()

    summary = (
        peak.groupby("district")
        .agg(
            peak_hotspot_total = ("hotspot_count", "sum"),
            peak_avg_frp       = ("avg_frp",       "mean"),
            peak_month_records = ("period_label",  "count"),
        )
        .reset_index()
    )
    summary["peak_avg_frp"] = summary["peak_avg_frp"].round(2)
    return summary


def compute_year_over_year(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute year-over-year percentage change in monthly hotspot counts per district.
    """
    if monthly_df.empty:
        return pd.DataFrame()

    pivot = monthly_df.pivot_table(
        index=["district", "month"], columns="year", values="hotspot_count", aggfunc="sum"
    )
    years = sorted(pivot.columns.tolist())
    rows = []
    for (district, month), row in pivot.iterrows():
        for i in range(1, len(years)):
            prev_yr, curr_yr = years[i - 1], years[i]
            prev_val = row.get(prev_yr, np.nan)
            curr_val = row.get(curr_yr, np.nan)
            if pd.notna(prev_val) and prev_val > 0 and pd.notna(curr_val):
                pct_change = 100.0 * (curr_val - prev_val) / prev_val
            else:
                pct_change = np.nan
            rows.append({
                "district":   district,
                "month":      month,
                "year":       curr_yr,
                "prev_year":  prev_yr,
                "hotspots":   curr_val,
                "pct_change": round(pct_change, 1) if pd.notna(pct_change) else np.nan,
            })
    return pd.DataFrame(rows)
