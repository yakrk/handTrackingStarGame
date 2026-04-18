"""
Data loading and normalization for NASA FIRMS CSV files.

Handles both API-cached chunks and manually-downloaded archive CSVs.
"""

import logging
from pathlib import Path

import pandas as pd

from src.config import DATA_RAW

logger = logging.getLogger(__name__)

# Canonical column order after normalization
REQUIRED_COLUMNS = [
    "latitude", "longitude", "bright_ti4", "bright_ti5",
    "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version",
    "frp", "daynight", "type",
]

DERIVED_COLUMNS = ["year", "month", "day_of_year"]


def normalize_firms_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize a raw FIRMS DataFrame into a consistent schema.

    - Strips whitespace from column names
    - Casts numeric columns, parses dates
    - Adds year / month / day_of_year derived columns
    - Deduplicates on the natural key
    - Drops records with missing coordinates
    """
    if df.empty:
        return df

    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    # Numeric casts
    for col in ("latitude", "longitude", "frp", "bright_ti4", "bright_ti5", "scan", "track"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Type field (0=vegetation, 1=volcano, 2=other static, 3=offshore)
    if "type" in df.columns:
        df["type"] = pd.to_numeric(df["type"], errors="coerce").fillna(0).astype(int)

    # Date parsing
    if "acq_date" in df.columns:
        df["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")

    # Derived temporal columns
    if "acq_date" in df.columns and df["acq_date"].notna().any():
        df["year"]       = df["acq_date"].dt.year
        df["month"]      = df["acq_date"].dt.month
        df["day_of_year"] = df["acq_date"].dt.day_of_year
    else:
        df["year"] = df["month"] = df["day_of_year"] = pd.NA

    # Confidence: VIIRS uses 'l'/'n'/'h' — expand to full words
    if "confidence" in df.columns:
        conf_map = {"l": "low", "n": "nominal", "h": "high"}
        df["confidence"] = (
            df["confidence"].astype(str).str.strip().str.lower()
            .map(lambda v: conf_map.get(v, v))
        )

    # Drop records without coordinates
    df = df.dropna(subset=["latitude", "longitude"])

    # Deduplicate on natural key (overlap between API chunks)
    key_cols = [c for c in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if c in df.columns]
    before = len(df)
    df = df.drop_duplicates(subset=key_cols)
    dropped = before - len(df)
    if dropped:
        logger.debug("Removed %d duplicate rows.", dropped)

    df = df.reset_index(drop=True)
    return df


def load_archive_csv(filepath: str | Path) -> pd.DataFrame:
    """
    Load a single manually-downloaded FIRMS archive CSV and normalize it.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Archive CSV not found: {filepath}")

    df = pd.read_csv(filepath)
    df = normalize_firms_df(df)
    logger.info("Loaded archive CSV: %s — %d records (%s to %s)",
                filepath.name,
                len(df),
                df["acq_date"].min().date() if "acq_date" in df.columns and not df.empty else "?",
                df["acq_date"].max().date() if "acq_date" in df.columns and not df.empty else "?")
    return df


def load_all_raw_data(raw_dir: Path = DATA_RAW) -> pd.DataFrame:
    """
    Load and combine all *.csv files from the raw data directory.

    Returns an empty DataFrame (not raises) if no files are found.
    """
    raw_dir = Path(raw_dir)
    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        logger.warning("No CSV files found in %s. Run fetch_firms.py first, or place archive CSVs there.", raw_dir)
        return pd.DataFrame()

    logger.info("Loading %d CSV file(s) from %s …", len(csv_files), raw_dir)
    frames = []
    for fp in csv_files:
        try:
            df = pd.read_csv(fp)
            df = normalize_firms_df(df)
            frames.append(df)
        except Exception as exc:
            logger.warning("Skipping %s: %s", fp.name, exc)

    if not frames:
        logger.warning("All CSV files failed to load.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Global deduplication across files
    key_cols = [c for c in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if c in combined.columns]
    before = len(combined)
    combined = combined.drop_duplicates(subset=key_cols)
    combined = combined.reset_index(drop=True)
    logger.info(
        "Combined: %d records total (%d deduped) | %s – %s",
        len(combined),
        before - len(combined),
        combined["acq_date"].min().date() if "acq_date" in combined.columns and not combined.empty else "?",
        combined["acq_date"].max().date() if "acq_date" in combined.columns and not combined.empty else "?",
    )
    for yr, grp in combined.groupby("year"):
        logger.info("  %s: %d records", yr, len(grp))

    return combined


def save_processed(df: pd.DataFrame, path: Path) -> None:
    """Save DataFrame as Parquet or CSV depending on file extension."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
    logger.info("Saved %d records → %s", len(df), path)


def load_processed(path: Path) -> pd.DataFrame:
    """Load a processed Parquet or CSV file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Processed file not found: {path}\n"
            "Run 'python scripts/analyze.py' first to generate processed data."
        )
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)
