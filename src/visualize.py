"""
Visualization: interactive Folium map, Matplotlib charts, Excel summary table.
"""

import logging
from pathlib import Path
from typing import Optional

import folium
import folium.plugins
import geopandas as gpd
import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # non-interactive backend for server/script use

from src.config import (
    DRY_PEAK_MONTHS,
    DRY_SEASON_MONTHS,
    MONTH_NAMES,
    OUTPUT_CHARTS,
    OUTPUT_MAPS,
    OUTPUT_TABLES,
    PEAK_MONTHS,
    WET_SEASON_MONTHS,
)

logger = logging.getLogger(__name__)

# Map center for Battambang province
MAP_CENTER = (13.05, 103.25)
MAP_ZOOM   = 10

# Color scheme for month classification
COLOR_WET_SEASON  = "#d62728"   # dark red  — Sep/Oct peak
COLOR_DRY_SEASON  = "#ff7f0e"   # orange    — Mar/Apr peak
COLOR_DRY_PEAK    = "#8c564b"   # brown     — Jan/Feb dry
COLOR_OTHER       = "#aec7e8"   # light blue — off-peak


def _month_color(month: int) -> str:
    if month in WET_SEASON_MONTHS:
        return COLOR_WET_SEASON
    if month in DRY_SEASON_MONTHS:
        return COLOR_DRY_SEASON
    if month in DRY_PEAK_MONTHS:
        return COLOR_DRY_PEAK
    return COLOR_OTHER


def create_hotspot_map(
    hotspots_gdf: gpd.GeoDataFrame,
    boundaries_gdf: gpd.GeoDataFrame,
    output_path: Optional[Path] = None,
) -> folium.Map:
    """
    Create an interactive Folium map of fire hotspots over Battambang.

    Layers:
    - CartoDB Positron base map
    - District boundary polygons with tooltips
    - Full-dataset HeatMap layer
    - Top-N individual CircleMarkers colored by month (for detail)
    - LayerControl
    """
    output_path = output_path or (OUTPUT_MAPS / "hotspot_map.html")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=MAP_ZOOM,
        tiles="CartoDB positron",
        attr="&copy; CartoDB &copy; OpenStreetMap contributors",
    )

    # ── District boundaries ──────────────────────────────────────────────────
    if boundaries_gdf is not None and not boundaries_gdf.empty:
        boundary_layer = folium.FeatureGroup(name="District Boundaries", show=True)
        folium.GeoJson(
            boundaries_gdf.__geo_interface__,
            style_function=lambda _: {
                "fillColor":   "#444444",
                "color":       "#333333",
                "weight":       1.5,
                "fillOpacity":  0.05,
            },
            highlight_function=lambda _: {
                "weight":       3,
                "fillOpacity":  0.15,
            },
            tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["District:"]),
        ).add_to(boundary_layer)
        boundary_layer.add_to(m)

    if hotspots_gdf.empty:
        folium.LayerControl().add_to(m)
        if output_path:
            m.save(str(output_path))
            logger.info("Map saved (no hotspot data): %s", output_path)
        return m

    # ── HeatMap layer (full dataset) ─────────────────────────────────────────
    heat_data = hotspots_gdf[["latitude", "longitude"]].dropna().values.tolist()
    heat_layer = folium.FeatureGroup(name="Hotspot Heatmap", show=True)
    folium.plugins.HeatMap(
        heat_data,
        radius=12,
        blur=15,
        min_opacity=0.3,
        gradient={0.2: "blue", 0.4: "lime", 0.6: "orange", 1.0: "red"},
    ).add_to(heat_layer)
    heat_layer.add_to(m)

    # ── CircleMarker layer (top 5000 by FRP for detail) ──────────────────────
    n_markers = 5000
    if "frp" in hotspots_gdf.columns:
        top_gdf = hotspots_gdf.nlargest(n_markers, "frp")
    else:
        top_gdf = hotspots_gdf.head(n_markers)

    marker_layer = folium.FeatureGroup(
        name=f"Individual Hotspots (top {n_markers} by FRP)", show=False
    )
    for _, row in top_gdf.iterrows():
        month = int(row["month"]) if pd.notna(row.get("month")) else 0
        color = _month_color(month)
        acq   = str(row.get("acq_date", ""))[:10]
        dist  = row.get("district", "Unknown")
        frp   = f"{row['frp']:.1f} MW" if pd.notna(row.get("frp")) else "N/A"
        conf  = row.get("confidence", "N/A")

        popup_html = (
            f"<b>Date:</b> {acq}<br>"
            f"<b>District:</b> {dist}<br>"
            f"<b>FRP:</b> {frp}<br>"
            f"<b>Confidence:</b> {conf}"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=4,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=0.5,
            popup=folium.Popup(popup_html, max_width=200),
        ).add_to(marker_layer)
    marker_layer.add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px; z-index: 9999;
        background: white; padding: 12px 16px; border-radius: 6px;
        border: 1px solid #ccc; font-size: 13px; line-height: 1.6;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
    ">
    <b>Fire Hotspot — Month</b><br>
    <span style="color:{wet}">&#9679;</span> Sep/Oct (wet-season harvest)<br>
    <span style="color:{dry}">&#9679;</span> Mar/Apr (dry-season harvest)<br>
    <span style="color:{peak}">&#9679;</span> Jan/Feb (dry-season peak)<br>
    <span style="color:{other}">&#9679;</span> Other months
    </div>
    """.format(
        wet=COLOR_WET_SEASON,
        dry=COLOR_DRY_SEASON,
        peak=COLOR_DRY_PEAK,
        other=COLOR_OTHER,
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl(collapsed=False).add_to(m)

    if output_path:
        m.save(str(output_path))
        logger.info("Interactive map saved: %s", output_path)

    return m


def create_monthly_trend_chart(
    monthly_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """
    Stacked bar chart: monthly hotspot counts per district over 36 months.
    Harvest peak periods are highlighted with background shading.
    """
    output_path = output_path or (OUTPUT_CHARTS / "monthly_trend.png")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if monthly_df.empty:
        logger.warning("No monthly data for trend chart.")
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        return fig

    # Build pivot: rows=period_label, cols=district
    pivot = monthly_df.pivot_table(
        index="period_label", columns="district", values="hotspot_count",
        aggfunc="sum", fill_value=0,
    )
    pivot = pivot.sort_index()

    districts = list(pivot.columns)
    colors    = plt.cm.get_cmap("tab10")(np.linspace(0, 1, len(districts)))

    fig, ax = plt.subplots(figsize=(18, 7))

    bottom = np.zeros(len(pivot))
    for i, dist in enumerate(districts):
        ax.bar(
            range(len(pivot)), pivot[dist].values,
            bottom=bottom, label=dist,
            color=colors[i], alpha=0.85, width=0.85,
        )
        bottom += pivot[dist].values

    # Shade peak months
    labels = list(pivot.index)
    for idx, label in enumerate(labels):
        try:
            month = int(label.split("-")[1])
        except (IndexError, ValueError):
            continue
        if month in PEAK_MONTHS:
            ax.axvspan(idx - 0.5, idx + 0.5, color="#ffe0e0", alpha=0.4, zorder=0)

    # X-axis: quarterly labels
    tick_positions = []
    tick_labels    = []
    for idx, label in enumerate(labels):
        parts = label.split("-")
        if len(parts) == 2 and parts[1] in ("01", "04", "07", "10"):
            tick_positions.append(idx)
            tick_labels.append(label)

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=9)
    ax.set_xlabel("Month", fontsize=11)
    ax.set_ylabel("Hotspot Count", fontsize=11)
    ax.set_title(
        "Monthly Agricultural Fire Hotspots — Battambang Province (2023–2025)\n"
        "(Pink shading = post-harvest burning peak: Sep–Oct & Mar–Apr)",
        fontsize=12,
    )
    ax.legend(
        loc="upper left", bbox_to_anchor=(1.01, 1),
        title="District", fontsize=9, title_fontsize=9,
    )
    ax.set_xlim(-0.5, len(pivot) - 0.5)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Monthly trend chart saved: %s", output_path)
    return fig


def create_frp_heatmap(
    monthly_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """
    Heatmap of average FRP (Fire Radiative Power) by district × month.
    Rows = districts, columns = year-month periods.
    """
    output_path = output_path or (OUTPUT_CHARTS / "frp_heatmap.png")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if monthly_df.empty:
        logger.warning("No monthly data for FRP heatmap.")
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        return fig

    pivot = monthly_df.pivot_table(
        index="district", columns="period_label", values="avg_frp", aggfunc="mean"
    )
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    fig, ax = plt.subplots(figsize=(20, 5))
    im = ax.imshow(
        pivot.values, aspect="auto", cmap="YlOrRd",
        vmin=0, vmax=np.nanpercentile(pivot.values, 95),
    )
    plt.colorbar(im, ax=ax, label="Avg FRP (MW)", fraction=0.03, pad=0.02)

    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=10)

    # Show only Jan of each year on X-axis
    col_labels = list(pivot.columns)
    x_ticks = [i for i, lbl in enumerate(col_labels) if lbl.endswith("-01")]
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([col_labels[i] for i in x_ticks], rotation=45, ha="right", fontsize=9)

    # Outline peak-month columns
    for i, lbl in enumerate(col_labels):
        try:
            month = int(lbl.split("-")[1])
        except (IndexError, ValueError):
            continue
        if month in PEAK_MONTHS:
            for y in range(len(pivot.index)):
                ax.add_patch(
                    mpatches.Rectangle(
                        (i - 0.5, y - 0.5), 1, 1,
                        linewidth=0.8, edgecolor="#d62728", fill=False,
                    )
                )

    ax.set_title(
        "Average Fire Radiative Power (FRP) by District × Month — Battambang Province\n"
        "(Red outlines = post-harvest peak months)",
        fontsize=12,
    )
    ax.set_xlabel("Month", fontsize=10)
    ax.set_ylabel("District", fontsize=10)
    plt.tight_layout()

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("FRP heatmap saved: %s", output_path)
    return fig


def create_annual_comparison_chart(
    monthly_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """
    Line chart comparing seasonal hotspot patterns across years (all districts combined).
    X-axis = month (1-12), one line per year.
    """
    output_path = output_path or (OUTPUT_CHARTS / "annual_comparison.png")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if monthly_df.empty:
        logger.warning("No monthly data for annual comparison chart.")
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        return fig

    by_year_month = (
        monthly_df.groupby(["year", "month"])["hotspot_count"].sum().reset_index()
    )

    fig, ax = plt.subplots(figsize=(12, 6))
    years  = sorted(by_year_month["year"].dropna().unique())
    colors = plt.cm.get_cmap("Set1")(np.linspace(0, 0.8, len(years)))

    for yr, color in zip(years, colors):
        sub = by_year_month[by_year_month["year"] == yr].sort_values("month")
        ax.plot(
            sub["month"], sub["hotspot_count"],
            marker="o", linewidth=2, color=color,
            label=str(int(yr)), markersize=5,
        )

    # Shade peak months
    for month in PEAK_MONTHS:
        ax.axvspan(month - 0.5, month + 0.5, color="#ffe0e0", alpha=0.5, zorder=0)

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels([MONTH_NAMES[m][:3] for m in range(1, 13)])
    ax.set_xlabel("Month", fontsize=11)
    ax.set_ylabel("Total Hotspot Count (all districts)", fontsize=11)
    ax.set_title(
        "Year-over-Year Seasonal Fire Pattern — Battambang Province\n"
        "(Pink shading = post-harvest burning peak months)",
        fontsize=12,
    )
    ax.legend(title="Year", fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Annual comparison chart saved: %s", output_path)
    return fig


def create_district_summary_table(
    summary_df: pd.DataFrame,
    output_dir: Optional[Path] = None,
) -> None:
    """
    Save district summary as CSV and Excel (with conditional formatting on rank column).
    """
    output_dir = Path(output_dir or OUTPUT_TABLES)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path   = output_dir / "district_summary.csv"
    excel_path = output_dir / "district_summary.xlsx"

    if summary_df.empty:
        logger.warning("Empty summary_df — no table saved.")
        return

    # Friendly column rename for output
    display_cols = {
        "district":               "District",
        "total_hotspots":         "Total Hotspots (3yr)",
        "hotspots_per_year":      "Hotspots/Year",
        "hotspot_density_per_km2": "Density (per km²)",
        "avg_frp_all":            "Avg FRP (MW)",
        "max_frp_all":            "Max FRP (MW)",
        "high_confidence_pct":    "High Conf. (%)",
        "peak_month_hotspots":    "Peak-Month Hotspots",
        "peak_month_pct":         "Peak-Month (%)",
        "peak_month":             "Peak Month",
        "peak_year":              "Peak Year",
        "district_area_km2":      "Area (km²)",
        "priority_rank":          "Priority Rank",
    }
    out_df = summary_df[[c for c in display_cols if c in summary_df.columns]].copy()
    out_df = out_df.rename(columns=display_cols)

    # CSV
    out_df.to_csv(csv_path, index=False, float_format="%.2f")
    logger.info("Summary CSV saved: %s", csv_path)

    # Excel with conditional formatting
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        out_df.to_excel(excel_path, index=False, sheet_name="District Summary", engine="openpyxl")
        wb = load_workbook(excel_path)
        ws = wb.active

        # Bold header row
        for cell in ws[1]:
            cell.font      = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        # Conditional fill for Priority Rank column
        rank_col_idx = None
        for i, cell in enumerate(ws[1], 1):
            if cell.value == "Priority Rank":
                rank_col_idx = i
                break

        if rank_col_idx:
            n_rows = ws.max_row - 1  # excluding header
            green  = "C6EFCE"
            yellow = "FFEB9C"
            red    = "FFC7CE"
            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=rank_col_idx)
                rank_val = cell.value
                if rank_val is None:
                    continue
                if rank_val == 1:
                    fill_color = green
                elif rank_val <= max(2, n_rows // 2):
                    fill_color = yellow
                else:
                    fill_color = red
                cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

        # Auto-width columns
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max(
                (len(str(cell.value)) if cell.value else 0 for cell in col),
                default=10,
            )
            ws.column_dimensions[col_letter].width = min(max_len + 3, 30)

        wb.save(excel_path)
        logger.info("Summary Excel saved: %s", excel_path)

    except Exception as exc:
        logger.warning("Excel formatting failed (%s) — plain Excel saved without formatting.", exc)
