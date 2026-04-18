"""
Automatic report generation in Markdown format.
"""

import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    ANALYSIS_END,
    ANALYSIS_START,
    FIRMS_SOURCE,
    MONTH_NAMES,
    OUTPUT_REPORT,
    PEAK_MONTHS,
)

logger = logging.getLogger(__name__)


def _format_district_table(summary_df: pd.DataFrame) -> str:
    """Return a Markdown table of district rankings."""
    if summary_df.empty:
        return "_No district data available._"

    col_map = {
        "priority_rank":           "Rank",
        "district":                "District",
        "total_hotspots":          "Total Hotspots (3yr)",
        "hotspots_per_year":       "Hotspots/Year",
        "hotspot_density_per_km2": "Density (per km²)",
        "peak_month":              "Peak Month",
        "avg_frp_all":             "Avg FRP (MW)",
        "high_confidence_pct":     "High Conf. (%)",
        "peak_month_pct":          "Peak-Month (%)",
    }
    cols = [c for c in col_map if c in summary_df.columns]
    df   = summary_df[cols].rename(columns=col_map).sort_values("Rank")

    header = "| " + " | ".join(df.columns) + " |"
    sep    = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    rows   = []
    for _, r in df.iterrows():
        cells = []
        for col in df.columns:
            val = r[col]
            if isinstance(val, float) and not np.isnan(val):
                cells.append(f"{val:,.2f}")
            elif isinstance(val, (int, np.integer)):
                cells.append(f"{val:,}")
            else:
                cells.append(str(val) if pd.notna(val) else "—")
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join([header, sep] + rows)


def _format_peak_period_analysis(monthly_df: pd.DataFrame) -> str:
    """Narrative paragraph about the top peak burning episodes."""
    if monthly_df.empty:
        return "_No monthly data available._"

    peak = monthly_df[monthly_df.get("is_peak_month", monthly_df["month"].isin(PEAK_MONTHS))].copy()
    if peak.empty:
        return "_No peak-period data found._"

    top3 = (
        peak.nlargest(3, "hotspot_count")[["period_label", "district", "hotspot_count", "avg_frp"]]
    )
    lines = ["Top 3 peak burning episodes:\n"]
    for i, (_, row) in enumerate(top3.iterrows(), 1):
        frp_str = f"{row['avg_frp']:.1f} MW" if pd.notna(row.get("avg_frp")) else "N/A"
        lines.append(
            f"{i}. **{row['period_label']}** — {row['district']} "
            f"({int(row['hotspot_count'])} hotspots, avg FRP: {frp_str})"
        )

    wet_total = peak[peak["month"].isin([9, 10])]["hotspot_count"].sum()
    dry_total = peak[peak["month"].isin([3, 4])]["hotspot_count"].sum()
    lines.append(
        f"\nAcross the 3-year period, the **Sep–Oct** post-harvest window "
        f"recorded **{int(wet_total):,} hotspots** vs **{int(dry_total):,} hotspots** "
        f"in the Mar–Apr window."
    )
    return "\n".join(lines)


def generate_report(
    summary_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    using_fallback_boundaries: bool = True,
    using_type_filter_only: bool = True,
) -> str:
    """
    Generate a complete Markdown analysis report.

    Args:
        summary_df:                Per-district summary table.
        monthly_df:                Monthly aggregation table.
        using_fallback_boundaries: True if approximate boundary buffers were used.
        using_type_filter_only:    True if ESA WorldCover cropland mask was not applied.
    """
    today = date.today().isoformat()
    total_hotspots = int(summary_df["total_hotspots"].sum()) if not summary_df.empty else 0
    top_districts  = (
        summary_df.head(3)["district"].tolist()
        if not summary_df.empty else ["(no data)"]
    )

    # Boundary / cropland warning flags
    boundary_warning = ""
    if using_fallback_boundaries:
        boundary_warning = (
            "\n> ⚠️ **Note:** District boundaries are approximate circular buffers "
            "(radius ≈ 15 km). Download GADM Cambodia Level-3 boundaries for accurate "
            "district assignments. See README for instructions.\n"
        )

    cropland_warning = ""
    if using_type_filter_only:
        cropland_warning = (
            "\n> ⚠️ **Note:** ESA WorldCover cropland mask was not applied. "
            "Agricultural fires are inferred from `type==0` (vegetation fire) only. "
            "Some detections may include grassland or forest fires. "
            "See README for WorldCover download instructions.\n"
        )

    # ── Section 1: Executive Summary ─────────────────────────────────────────
    top_list = "\n".join(f"  {i+1}. **{d}**" for i, d in enumerate(top_districts))
    exec_summary = f"""# Battambang Province — Agricultural Fire Hotspot Analysis Report

**Generated:** {today}
**Analysis Period:** {ANALYSIS_START} – {ANALYSIS_END}
**Data Source:** NASA FIRMS {FIRMS_SOURCE}
**Total Hotspots Identified:** {total_hotspots:,}

## Executive Summary

This report analyzes agricultural fire hotspots in Battambang province, Cambodia,
using NASA FIRMS VIIRS satellite data over a 3-year period (2023–2025).
The analysis supports sourcing target selection for a corn-cob biochar carbon credit
project by identifying districts with high open-field burning activity.

**Recommended procurement target districts (by hotspot density):**

{top_list}

These districts exhibit the highest fire density during post-harvest burning seasons
(Sep–Oct wet-season harvest, Mar–Apr dry-season harvest), indicating strong potential
demand for alternative corn-cob residue utilization (i.e., biochar production).
"""

    # ── Section 2: Methodology ───────────────────────────────────────────────
    boundary_src = (
        "Approximate circular buffers (r ≈ 15 km) around known district centers — **fallback mode**"
        if using_fallback_boundaries
        else "GADM Cambodia Administrative Level-3 boundaries"
    )
    cropland_src = (
        "fire `type == 0` (presumed vegetation fire) — **WorldCover mask not applied**"
        if using_type_filter_only
        else "fire `type == 0` + ESA WorldCover 10m cropland mask (class 40)"
    )

    methodology = f"""
## Methodology

| Parameter | Value |
|-----------|-------|
| Satellite data source | NASA FIRMS {FIRMS_SOURCE} |
| Analysis period | {ANALYSIS_START} – {ANALYSIS_END} |
| Bounding box | 102.80°E–103.70°E, 12.70°N–13.40°N |
| Confidence filter | `nominal` and `high` only (low confidence excluded) |
| Fire type filter | {cropland_src} |
| District boundaries | {boundary_src} |
| Area calculation CRS | UTM Zone 48N (EPSG:32648) |

{boundary_warning}{cropland_warning}
### Data Pipeline

1. **Fetch** — NASA FIRMS API (`fetch_firms.py`): 10-day chunk requests, cached to `data/raw/`
2. **Analyze** — Spatial assignment (`analyze.py`): point-in-polygon district join, agricultural filter
3. **Output** — Visualization (`generate_output.py`): interactive map, charts, this report
"""

    # ── Section 3: District Ranking ──────────────────────────────────────────
    district_section = f"""
## District Ranking

Districts ranked by **hotspot density** (hotspots per km²) — higher density = greater
burning activity relative to district size = higher priority for biochar feedstock sourcing.

{_format_district_table(summary_df)}

### Interpretation Guide

- **Total Hotspots (3yr)**: raw count of satellite fire detections 2023–2025
- **Density (per km²)**: normalizes by district area — the primary ranking criterion
- **Avg FRP (MW)**: Fire Radiative Power — proxy for fire intensity; larger fires produce more residue
- **Peak Month**: month with the most detections — use to plan field visits and off-take agreements
- **Peak-Month (%)**: share of annual detections concentrated in post-harvest windows
"""

    # ── Section 4: Seasonal Pattern ──────────────────────────────────────────
    seasonal_section = f"""
## Seasonal Pattern Analysis

{_format_peak_period_analysis(monthly_df)}

### Harvest Calendar Context

| Season | Harvest | Expected Burning |
|--------|---------|-----------------|
| Wet-season corn | Aug–Sep | Sep–Oct (peak) |
| Dry-season corn | Feb–Mar | Mar–Apr (peak) |
| Dry season (other) | — | Jan–Feb (mostly forest/scrub) |

Fire detections in Sep–Oct and Mar–Apr are most likely attributable to agricultural
residue burning following corn harvest. Jan–Feb detections at high FRP may include
forest fires — these can be partially filtered using `type==0` + cropland masking.
"""

    # ── Section 5: Limitations ───────────────────────────────────────────────
    limitations = """
## Limitations and Caveats

1. **Cloud cover / wet-season underestimation**: VIIRS uses infrared detection, which
   is blocked by cloud cover. Sep–Oct falls during Cambodia's wet season
   (peak cloud cover). Actual burning during this period may be **20–50% higher**
   than satellite counts suggest. Treat Sep–Oct figures as **lower bounds**.

2. **VIIRS detection threshold**: Small fires (<~0.1 ha or low intensity) may not
   be detected. The technology captures moderate-to-large burning events.

3. **FRP variability**: Fire Radiative Power depends on fire size, fuel load, scan
   angle, and atmospheric conditions. It is a relative indicator, not an absolute
   measure of biomass consumed.

4. **Agricultural vs. forest/scrub fire distinction**: `type==0` (vegetation fire)
   includes all non-volcanic terrestrial fires. Without the ESA WorldCover cropland
   mask, some detections in forested or grassland areas may be included. The error is
   partially mitigated by focusing on Sep–Oct and Mar–Apr (harvest burning seasons).

5. **District boundary accuracy**: If fallback circular buffers were used instead of
   GADM boundaries, hotspot assignments within ±15 km of district borders are
   approximate. Download official boundaries for production use.

6. **2026 Thai Burn-Free regulation baseline**: This dataset covers 2023–2025 and
   establishes the pre-regulation baseline. Post-January 2026 data can be compared
   against this baseline to measure additionality.
"""

    # ── Section 6: Recommended Next Steps ────────────────────────────────────
    top_d1 = top_districts[0] if len(top_districts) > 0 else "top district"
    top_d2 = top_districts[1] if len(top_districts) > 1 else "second district"

    next_steps = f"""
## Recommended Next Steps

1. **Field verification in {top_d1} and {top_d2}**: Visit during Mar–Apr or Sep–Oct
   to directly observe burning activity and engage farmer cooperatives about residue
   off-take alternatives.

2. **Feedstock availability assessment**: Estimate corn-cob yield from planted area
   in top-ranked districts using Agricultural Department data. Cross-reference with
   hotspot density to estimate collectible residue volume.

3. **Stakeholder engagement**: Prioritize outreach to BUAC agricultural cooperative
   members in Sangkae and Banan districts (existing cooperative relationships).

4. **Improve boundary data**: Download GADM Cambodia Level-3 GeoJSON and place in
   `data/boundaries/battambang_districts.geojson` to replace approximate buffers.

5. **Apply ESA WorldCover cropland mask**: Download Battambang tiles from
   https://esa-worldcover.org/en, extract class 40 (cropland), and save to
   `data/landcover/battambang_cropland.geojson` for stricter agricultural filtering.

6. **Expand to 2026 data**: Re-run with 2026 data after Thai Burn-Free regulation
   (January 2026 implementation) to measure cross-border burning displacement effects.

---

_Report generated by battambang-fire-analysis v0.1.0_
_Data: NASA FIRMS — https://firms.modaps.eosdis.nasa.gov_
"""

    return exec_summary + methodology + district_section + seasonal_section + limitations + next_steps


def save_report(report_text: str, output_path: Path = OUTPUT_REPORT) -> None:
    """Write the report Markdown to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")
    logger.info("Report saved: %s", output_path)
