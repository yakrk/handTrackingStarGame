"""
NASA FIRMS API client.

Fetches fire hotspot data in 10-day chunks, caches raw CSV to disk,
and returns a unified normalized DataFrame.
"""

import io
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from src.config import (
    BBOX,
    DATA_RAW,
    FIRMS_BASE_URL,
    FIRMS_DAY_RANGE_MAX,
    FIRMS_SOURCE,
)

logger = logging.getLogger(__name__)


class FIRMSAuthError(Exception):
    pass


class FIRMSRateLimitError(Exception):
    pass


def load_api_key() -> str:
    load_dotenv()
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "FIRMS_MAP_KEY is not set.\n"
            "Copy .env.example to .env and add your NASA FIRMS MAP key.\n"
            "Get a free key at: https://firms.modaps.eosdis.nasa.gov/api/area/"
        )
    return key


def _date_chunks(
    start_date: str, end_date: str, chunk_days: int = FIRMS_DAY_RANGE_MAX
) -> list[tuple[date, date]]:
    """Split a date range into non-overlapping chunks of at most chunk_days days."""
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _fetch_chunk_with_retry(
    url: str, filename: Path, max_retries: int = 3
) -> pd.DataFrame:
    """GET the URL with exponential backoff; raises on persistent failure."""
    delays = [2, 4, 8]
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, timeout=60)
        except requests.RequestException as exc:
            if attempt < max_retries:
                wait = delays[min(attempt, len(delays) - 1)]
                logger.warning("Request error (attempt %d): %s — retrying in %ds", attempt + 1, exc, wait)
                time.sleep(wait)
                continue
            raise

        if resp.status_code == 200:
            DATA_RAW.mkdir(parents=True, exist_ok=True)
            filename.write_text(resp.text, encoding="utf-8")
            try:
                df = pd.read_csv(io.StringIO(resp.text))
                return df
            except Exception:
                return pd.DataFrame()

        if resp.status_code == 401:
            raise FIRMSAuthError(
                "FIRMS API returned 401 Unauthorized. Check your FIRMS_MAP_KEY."
            )
        if resp.status_code == 429:
            wait = 65
            logger.warning("Rate limit hit (429). Sleeping %ds before retry.", wait)
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            if attempt < max_retries:
                wait = delays[min(attempt, len(delays) - 1)]
                logger.warning("Server error %d (attempt %d) — retrying in %ds", resp.status_code, attempt + 1, wait)
                time.sleep(wait)
                continue
        resp.raise_for_status()

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} retries.")


def fetch_firms_data(
    start_date: str = None,
    end_date: str = None,
    source: str = FIRMS_SOURCE,
    bbox: dict = None,
    skip_existing: bool = True,
) -> pd.DataFrame:
    """
    Fetch FIRMS fire data for a date range, splitting into 10-day chunks.

    Args:
        start_date: ISO date string, e.g. "2023-01-01". Defaults to ANALYSIS_START.
        end_date:   ISO date string, e.g. "2023-12-31". Defaults to ANALYSIS_END.
        source:     FIRMS data source identifier.
        bbox:       Bounding box dict with keys west/south/east/north.
        skip_existing: If True, use cached CSV files instead of re-fetching.

    Returns:
        Normalized combined DataFrame of all hotspot records.
    """
    from src.config import ANALYSIS_END, ANALYSIS_START
    from src.data_loader import normalize_firms_df

    start_date = start_date or ANALYSIS_START
    end_date   = end_date   or ANALYSIS_END
    bbox       = bbox       or BBOX

    api_key = load_api_key()
    area    = f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"
    chunks  = _date_chunks(start_date, end_date)

    logger.info("Fetching %s data from %s to %s (%d chunks).",
                source, start_date, end_date, len(chunks))

    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in chunks:
        day_range = (chunk_end - chunk_start).days + 1
        filename  = DATA_RAW / f"{source}_{chunk_start}_{chunk_end}.csv"

        if skip_existing and filename.exists():
            logger.debug("Using cached: %s", filename.name)
            try:
                df = pd.read_csv(filename)
                frames.append(df)
                continue
            except Exception as exc:
                logger.warning("Failed to read cache %s: %s — re-fetching.", filename.name, exc)

        url = f"{FIRMS_BASE_URL}/{api_key}/{source}/{area}/{day_range}/{chunk_start}"
        logger.info("Fetching: %s … %s (%d days)", chunk_start, chunk_end, day_range)
        df = _fetch_chunk_with_retry(url, filename)

        if df.empty:
            logger.debug("No data for chunk %s – %s.", chunk_start, chunk_end)
        else:
            logger.info("  → %d records.", len(df))
        frames.append(df)

    if not frames:
        logger.warning("No data returned for the requested period.")
        return pd.DataFrame()

    combined = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if combined.empty:
        logger.warning("All chunks returned empty data.")
        return pd.DataFrame()

    return normalize_firms_df(combined)
