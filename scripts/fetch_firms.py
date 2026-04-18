"""
Fetch NASA FIRMS fire hotspot data for the Battambang analysis period.

Usage:
    python scripts/fetch_firms.py
    python scripts/fetch_firms.py --start 2025-12-22 --end 2025-12-31
    python scripts/fetch_firms.py --start 2023-01-01 --end 2023-12-31 --source MODIS_SP
    python scripts/fetch_firms.py --no-skip-existing  # re-download all chunks
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ANALYSIS_END, ANALYSIS_START, FIRMS_SOURCE
from src.firms_client import FIRMSAuthError, FIRMSRateLimitError, fetch_firms_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch NASA FIRMS fire data for Battambang province.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--start", default=ANALYSIS_START,
        help=f"Start date YYYY-MM-DD (default: {ANALYSIS_START})",
    )
    p.add_argument(
        "--end", default=ANALYSIS_END,
        help=f"End date YYYY-MM-DD (default: {ANALYSIS_END})",
    )
    p.add_argument(
        "--source", default=FIRMS_SOURCE,
        help=f"FIRMS data source (default: {FIRMS_SOURCE})",
    )
    p.add_argument(
        "--no-skip-existing", dest="skip_existing", action="store_false",
        help="Re-download chunks even if cached CSV already exists",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    logger.info("=" * 60)
    logger.info("Battambang FIRMS Data Fetch")
    logger.info("  Period: %s – %s", args.start, args.end)
    logger.info("  Source: %s", args.source)
    logger.info("  Skip existing: %s", args.skip_existing)
    logger.info("=" * 60)

    try:
        df = fetch_firms_data(
            start_date=args.start,
            end_date=args.end,
            source=args.source,
            skip_existing=args.skip_existing,
        )
    except FIRMSAuthError as exc:
        logger.error("Authentication error: %s", exc)
        logger.error("Check your FIRMS_MAP_KEY in the .env file.")
        sys.exit(1)
    except FIRMSRateLimitError as exc:
        logger.error("Rate limit: %s", exc)
        sys.exit(1)
    except EnvironmentError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        sys.exit(1)

    if df.empty:
        logger.warning("No records fetched. Check date range and API key.")
        return

    logger.info("")
    logger.info("Fetch complete:")
    logger.info("  Total records : %d", len(df))
    if "acq_date" in df.columns and df["acq_date"].notna().any():
        logger.info("  Date range    : %s – %s",
                    df["acq_date"].min().date(), df["acq_date"].max().date())
    if "year" in df.columns:
        for yr, grp in df.groupby("year"):
            logger.info("  %s: %d records", int(yr), len(grp))
    logger.info("")
    logger.info("Raw CSV chunks saved to: data/raw/")
    logger.info("Next step: python scripts/analyze.py")


if __name__ == "__main__":
    main()
