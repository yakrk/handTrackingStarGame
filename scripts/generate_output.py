"""
Generate all output artifacts: interactive map, charts, summary tables, report.

Reads processed Parquet/CSV files produced by analyze.py.

Usage:
    python scripts/generate_output.py
    python scripts/generate_output.py --no-heatmap   # skip FRP heatmap
    python scripts/generate_output.py --no-map       # skip interactive HTML map
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import (
    BOUNDARIES_FILE,
    PROCESSED_HOTSPOTS,
    PROCESSED_MONTHLY,
    PROCESSED_SUMMARY,
)
from src.data_loader import load_processed
from src.report import generate_report, save_report
from src.spatial import hotspots_to_geodataframe, load_district_boundaries
from src.visualize import (
    create_annual_comparison_chart,
    create_district_summary_table,
    create_frp_heatmap,
    create_hotspot_map,
    create_monthly_trend_chart,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate maps, charts, tables, and report from processed data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--no-map",     dest="make_map",     action="store_false", help="Skip interactive HTML map")
    p.add_argument("--no-heatmap", dest="make_heatmap", action="store_false", help="Skip FRP heatmap chart")
    return p


def _load_flags() -> dict:
    flags_path = PROCESSED_HOTSPOTS.parent / "analysis_flags.json"
    if flags_path.exists():
        with open(flags_path) as f:
            return json.load(f)
    return {"using_fallback_boundaries": True, "using_type_filter_only": True}


def main() -> None:
    args = build_parser().parse_args()

    logger.info("=" * 60)
    logger.info("Battambang FIRMS Output Generation")
    logger.info("=" * 60)

    # ── Load processed data ───────────────────────────────────────────────────
    try:
        hotspots_df = load_processed(PROCESSED_HOTSPOTS)
        monthly_df  = load_processed(PROCESSED_MONTHLY)
        summary_df  = load_processed(PROCESSED_SUMMARY)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    flags = _load_flags()
    logger.info(
        "Flags — fallback_boundaries: %s, type_filter_only: %s",
        flags["using_fallback_boundaries"],
        flags["using_type_filter_only"],
    )

    # Convert hotspots back to GeoDataFrame
    hotspots_gdf = hotspots_to_geodataframe(hotspots_df)
    boundaries_gdf = load_district_boundaries()

    logger.info("Loaded: %d hotspots, %d district-months, %d districts in summary.",
                len(hotspots_gdf), len(monthly_df), len(summary_df))

    # ── Interactive map ───────────────────────────────────────────────────────
    if args.make_map:
        logger.info("Generating interactive map …")
        create_hotspot_map(hotspots_gdf, boundaries_gdf)

    # ── Monthly trend chart ───────────────────────────────────────────────────
    logger.info("Generating monthly trend chart …")
    create_monthly_trend_chart(monthly_df)

    # ── FRP heatmap ───────────────────────────────────────────────────────────
    if args.make_heatmap:
        logger.info("Generating FRP heatmap …")
        create_frp_heatmap(monthly_df)

    # ── Annual comparison chart ───────────────────────────────────────────────
    logger.info("Generating annual comparison chart …")
    create_annual_comparison_chart(monthly_df)

    # ── Summary tables ────────────────────────────────────────────────────────
    logger.info("Generating district summary table (CSV + Excel) …")
    create_district_summary_table(summary_df)

    # ── Markdown report ───────────────────────────────────────────────────────
    logger.info("Generating analysis report …")
    report_text = generate_report(
        summary_df=summary_df,
        monthly_df=monthly_df,
        using_fallback_boundaries=flags["using_fallback_boundaries"],
        using_type_filter_only=flags["using_type_filter_only"],
    )
    save_report(report_text)

    logger.info("")
    logger.info("All outputs generated:")
    logger.info("  output/maps/hotspot_map.html         — Interactive map")
    logger.info("  output/charts/monthly_trend.png      — Monthly stacked bar chart")
    if args.make_heatmap:
        logger.info("  output/charts/frp_heatmap.png        — FRP heatmap")
    logger.info("  output/charts/annual_comparison.png  — Year-over-year seasonal chart")
    logger.info("  output/tables/district_summary.csv   — District ranking table")
    logger.info("  output/tables/district_summary.xlsx  — District ranking (Excel)")
    logger.info("  output/report.md                     — Analysis report")


if __name__ == "__main__":
    main()
