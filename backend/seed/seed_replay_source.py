"""
seed_replay_source.py

Loads the full dynamicrail_sequential_simulation.csv (~30k rows) into the
replay_source table as JSONB rows for the replay engine.

Run from backend/ directory:
  python seed/seed_replay_source.py

The replay engine reads from this table during each tick.
"""

import sys
import os
import asyncio
import logging
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.position import ReplaySource

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SEQ_CSV = os.environ.get("REPLAY_SOURCE_CSV", settings.REPLAY_SOURCE_CSV)
BATCH_SIZE = 500  # rows per DB commit


def _safe_value(v):
    """Convert numpy types and NaN to JSON-compatible Python types."""
    if v is None:
        return None
    if isinstance(v, float) and v != v:  # NaN check
        return None
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return None if v != v else float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except ImportError:
        pass
    return v


async def main():
    logger.info("=== DynamicRail Replay Source Seeder ===")
    logger.info(f"Loading sequential simulation CSV: {SEQ_CSV}")

    try:
        df = pd.read_csv(SEQ_CSV, low_memory=False)
    except FileNotFoundError:
        logger.error(f"Replay source CSV not found: {SEQ_CSV}")
        sys.exit(1)

    logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    logger.info(f"Columns: {list(df.columns[:20])}...")

    # Check for required columns
    required = {"train_id"}
    missing = required - set(df.columns)
    if missing:
        logger.error(f"Missing required columns: {missing}")
        sys.exit(1)

    # Build sequence_id from sequence_id column if available, else from train_id
    if "sequence_id" in df.columns:
        df["_seq_id"] = df["sequence_id"].astype(str)
    else:
        df["_seq_id"] = "seq_" + df["train_id"].astype(str)

    # Build sequence_step (order within each sequence_id)
    if "sequence_step" in df.columns:
        df["_seq_step"] = df["sequence_step"].astype(int)
    else:
        df["_seq_step"] = df.groupby("_seq_id").cumcount()

    # Check how many rows already exist
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, func
        count_result = await db.execute(select(func.count(ReplaySource.id)))
        existing_count = count_result.scalar()
        logger.info(f"Existing replay_source rows: {existing_count}")

        if existing_count >= len(df):
            logger.info("Replay source already fully seeded. Skipping.")
            return

    logger.info(f"Seeding {len(df)} rows in batches of {BATCH_SIZE}...")
    total_seeded = 0

    for batch_start in range(0, len(df), BATCH_SIZE):
        batch = df.iloc[batch_start:batch_start + BATCH_SIZE]

        async with AsyncSessionLocal() as db:
            for _, row in batch.iterrows():
                train_id = int(row["train_id"])
                seq_id = str(row["_seq_id"])
                seq_step = int(row["_seq_step"])

                # Serialize the full row as a clean dict
                raw_data = {
                    k: _safe_value(v)
                    for k, v in row.items()
                    if not k.startswith("_") and k not in {"_seq_id", "_seq_step"}
                }

                source_row = ReplaySource(
                    train_id=train_id,
                    sequence_id=seq_id,
                    sequence_step=seq_step,
                    raw_data=raw_data,
                )
                db.add(source_row)

            await db.commit()

        total_seeded += len(batch)
        pct = (total_seeded / len(df)) * 100
        logger.info(f"Progress: {total_seeded}/{len(df)} ({pct:.1f}%)")

    logger.info(f"=== Replay source seeded: {total_seeded} rows ===")


if __name__ == "__main__":
    asyncio.run(main())
