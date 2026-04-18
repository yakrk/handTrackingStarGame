"""
Run spatial analysis and aggregation on raw FIRMS CSV data.

Loads all CSV files from data/raw/, assigns district labels via
point-in-polygon, filters for agricultural fires, aggregates by
district × month, and saves processed Parquet files.

Usage:
    python scripts/analyze.py
    python scripts/analyze.py --confidence high
    python scripts/analyze.py --no-landcover        # skip cropland spatial filter
    python scripts/analyze.py --archive path/to/file.csv  # add a manual archive CSV
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis import (
    aggregate_by_district_month,
    compute_district_summary,
    filter_by_confidence,
)
from src.config import (
    LANDCOVER_FILE,
    PROCESSED_HOTSPOTS,
    PROCESSED_MONTHLY,
    PROCESSED_SUMMARY,
)
from src.data_loader import load_all_raw_data, load_archive_csv, save_processed
from src.spatial import (
    assign_districts,
    filter_agricultural,
    hotspots_to_geodataframe,
    load_district_boundaries,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Analyze FIRMS fire data: spatial join + aggregation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--confidence", default="nominal",
        choices=["low", "nominal", "high"],
        help="Minimum confidence level to include (default: nominal)",
    )
    p.add_argument(
        "--no-landcover", dest="use_landcover", action="store_false",
        help="Skip ESA WorldCover cropland spatial filter",
    )
    p.add_argument(
        "--archive", metavar="CSV_PATH", action="append", default=[],
        help="Path to a manually-downloaded FIRMS archive CSV (can be repeated)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    logger.info("=" * 60)
    logger.info("Battambang FIRMS Analysis")
    logger.info("  Confidence filter : >= %s", args.confidence)
    logger.info("  Landcover filter  : %s", args.use_landcover)
    logger.info("=" * 60)

    # ── Load raw data ─────────────────────────────────────────────────────────
    df = load_all_raw_data()

    # Append any manually-specified archive CSVs
    for arc_path in args.archive:
        try:
            arc_df = load_archive_csv(arc_path)
            import pandas as pd
            df = pd.concat([df, arc_df], ignore_index=True).drop_duplicates(
                subset=[c for c in ["latitude", "longitude", "acq_date", "acq_time", "satellite"]
                        if c in df.columns]
            )
            logger.info("Added archive CSV: %s", arc_path)
        except Exception as exc:
            logger.warning("Could not load archive CSV %s: %s", arc_path, exc)

    if df.empty:
        logger.error(
            "No data loaded. Run 'python scripts/fetch_firms.py' first, "
            "or place FIRMS archive CSVs in data/raw/."
        )
        sys.exit(1)

    logger.info("Loaded %d raw records.", len(df))

    # ── Confidence filter ─────────────────────────────────────────────────────
    from src.analysis import filter_by_confidence
    df_filtered = filter_by_confidence(
        hotspots_to_geodataframe(df), min_confidence=args.confidence
    )

    # ── Agricultural fire filter ──────────────────────────────────────────────
    landcover_path = LANDCOVER_FILE if args.use_landcover else None
    ag_gdf, using_type_filter_only = filter_agricultural(df_filtered, landcover_path=landcover_path)

    if ag_gdf.empty:
        logger.warning("No agricultural fire records after filtering.")

    # ── Load district boundaries ──────────────────────────────────────────────
    boundaries_gdf = load_district_boundaries()
    using_fallback = not (Path(__file__).resolve().parent.parent / "data/boundaries/battambang_districts.geojson").exists()

    # ── Assign districts ──────────────────────────────────────────────────────
    hotspots_assigned = assign_districts(ag_gdf, boundaries_gdf)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    monthly_df  = aggregate_by_district_month(hotspots_assigned)
    summary_df  = compute_district_summary(hotspots_assigned, boundaries_gdf)

    # ── Save processed data ───────────────────────────────────────────────────
    save_processed(hotspots_assigned.drop(columns=["geometry"]), PROCESSED_HOTSPOTS)
    save_processed(monthly_df,  PROCESSED_MONTHLY)
    save_processed(summary_df,  PROCESSED_SUMMARY)

    # Persist flags for downstream scripts
    flags_path = PROCESSED_HOTSPOTS.parent / "analysis_flags.json"
    import json
    with open(flags_path, "w") as f:
        json.dump({
            "using_fallback_boundaries": using_fallback,
            "using_type_filter_only":    using_type_filter_only,
        }, f, indent=2)
    logger.info("Analysis flags saved: %s", flags_path)

    logger.info("")
    logger.info("Analysis complete:")
    logger.info("  Hotspots (agricultural): %d", len(hotspots_assigned))
    logger.info("  Districts with data    : %d", hotspots_assigned["district"].nunique())
    if not summary_df.empty:
        top = summary_df.head(3)["district"].tolist()
        logger.info("  Top districts by density: %s", ", ".join(top))
    logger.info("")
    logger.info("Processed files saved to: data/processed/")
    logger.info("Next step: python scripts/generate_output.py")


if __name__ == "__main__":
    main()
