"""
seed_reference_data.py

Seeds the following tables from the real dataset CSVs:
- stations (30 nodes from railway_graph_nodes.csv)
- route_segments (from railway_graph_edges.csv)  
- trains (~995 unique trains from railpulse_master_clean.csv)
- routes (one per train, with origin/destination)
- route_stations (ordered stops per route)

Run from backend/ directory:
  python seed/seed_reference_data.py

Requires:
  - data/railway_graph_nodes.csv
  - data/railway_graph_edges.csv
  - data/railpulse_master_clean.csv
  - A running PostgreSQL instance and alembic migrations applied
"""

import sys
import os
import asyncio
import logging
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.config import settings
from app.database import AsyncSessionLocal, engine, Base
from app.models import *  # noqa

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


NODES_CSV = os.environ.get("GRAPH_NODES_CSV", settings.GRAPH_NODES_CSV)
EDGES_CSV = os.environ.get("GRAPH_EDGES_CSV", settings.GRAPH_EDGES_CSV)
MASTER_CSV = os.environ.get("MASTER_CSV", settings.MASTER_CSV)


async def seed_stations(db, nodes_df: pd.DataFrame):
    """Seed stations from railway_graph_nodes.csv"""
    logger.info(f"Seeding {len(nodes_df)} stations...")
    from app.models.train import Station
    from sqlalchemy import select

    for _, row in nodes_df.iterrows():
        code = str(row["station"]).strip().upper()
        idx = int(row["node_index"]) if "node_index" in row else _

        existing = await db.get(Station, code)
        if existing:
            continue

        s = Station(
            code=code,
            graph_node_index=int(nodes_df.index.get_loc(nodes_df.index[nodes_df["station"] == row["station"]][0])) if "station" in nodes_df.columns else idx,
            display_name=code,
        )
        db.add(s)

    await db.commit()
    logger.info("Stations seeded.")


async def seed_segments(db, edges_df: pd.DataFrame):
    """Seed route segments from railway_graph_edges.csv"""
    from app.models.train import RouteSegment
    logger.info(f"Seeding {len(edges_df)} route segments...")

    for _, row in edges_df.iterrows():
        from_s = str(row.get("from_station", row.get("source", ""))).strip().upper()
        to_s = str(row.get("to_station", row.get("target", ""))).strip().upper()
        dist = float(row.get("distance_km", row.get("weight", 0)) or 0)

        if not from_s or not to_s:
            continue

        # Check existing
        from sqlalchemy import select
        result = await db.execute(
            select(RouteSegment)
            .where(RouteSegment.from_station == from_s)
            .where(RouteSegment.to_station == to_s)
        )
        if result.scalar_one_or_none():
            continue

        seg = RouteSegment(from_station=from_s, to_station=to_s, distance_km=dist if dist > 0 else None)
        db.add(seg)

    await db.commit()
    logger.info("Route segments seeded.")


async def seed_trains(db, master_df: pd.DataFrame):
    """Seed trains, routes, and route_stations from railpulse_master_clean.csv"""
    from app.models.train import Train, Route, RouteStation
    from sqlalchemy import select

    # Get unique trains
    if "train_id" not in master_df.columns:
        logger.error("master_df has no train_id column!")
        return

    train_cols = [c for c in ["train_id", "train_name", "train_type", "train_category", "railway_zone"] if c in master_df.columns]
    trains_df = master_df[train_cols].drop_duplicates(subset=["train_id"]).reset_index(drop=True)
    logger.info(f"Seeding {len(trains_df)} unique trains...")

    seeded_trains = 0
    for _, row in trains_df.iterrows():
        train_id = int(row["train_id"])

        existing = await db.get(Train, train_id)
        if existing:
            continue

        train = Train(
            train_id=train_id,
            train_name=str(row.get("train_name", f"Train {train_id}")).strip(),
            train_type=str(row.get("train_type", "Express")).strip(),
            train_category=str(row.get("train_category", "Mail")).strip(),
            railway_zone=str(row.get("railway_zone", "CR")).strip(),
        )
        db.add(train)
        seeded_trains += 1

    await db.flush()

    # Seed routes and route_stations per train
    logger.info("Seeding routes and route stations...")
    train_routes = {}  # train_id -> list of stations in order

    # Build route from master: unique (train_id, current_station, direction) sequences
    if all(c in master_df.columns for c in ["train_id", "current_station", "direction"]):
        for train_id, group in master_df.groupby("train_id"):
            origin = str(group["origin_station"].iloc[0]).strip().upper() if "origin_station" in group.columns else None
            dest = str(group["destination_station"].iloc[0]).strip().upper() if "destination_station" in group.columns else None
            direction = str(group["direction"].iloc[0]).strip() if "direction" in group.columns else None
            sched_dist = float(group["scheduled_distance_km"].iloc[0]) if "scheduled_distance_km" in group.columns and not pd.isna(group["scheduled_distance_km"].iloc[0]) else None
            sched_hrs = float(group["scheduled_journey_time_hrs"].iloc[0]) if "scheduled_journey_time_hrs" in group.columns and not pd.isna(group["scheduled_journey_time_hrs"].iloc[0]) else None

            # Check if route already seeded
            existing_route = await db.execute(
                select(Route).where(Route.train_id == int(train_id)).limit(1)
            )
            if existing_route.scalar_one_or_none():
                continue

            route = Route(
                train_id=int(train_id),
                origin_station=origin,
                destination_station=dest,
                direction=direction,
                scheduled_distance_km=sched_dist,
                scheduled_journey_time_hrs=sched_hrs,
            )
            db.add(route)
            await db.flush()

            # Get unique ordered stations for this train
            if "current_station" in group.columns:
                unique_stations = group["current_station"].dropna().unique()
                for order, station in enumerate(unique_stations[:50]):  # cap at 50 stops
                    sc = str(station).strip().upper()
                    if not sc or sc == "NAN":
                        continue
                    rs = RouteStation(
                        route_id=route.id,
                        station_code=sc,
                        stop_order=order,
                    )
                    db.add(rs)

    await db.commit()
    logger.info(f"Seeded {seeded_trains} new trains with routes and route stations.")


async def main():
    logger.info("=== DynamicRail Reference Data Seeder ===")

    # Load CSVs
    try:
        nodes_df = pd.read_csv(NODES_CSV)
        logger.info(f"Loaded nodes CSV: {len(nodes_df)} rows, columns: {list(nodes_df.columns)}")
    except FileNotFoundError:
        logger.error(f"Nodes CSV not found: {NODES_CSV}")
        sys.exit(1)

    try:
        edges_df = pd.read_csv(EDGES_CSV)
        logger.info(f"Loaded edges CSV: {len(edges_df)} rows, columns: {list(edges_df.columns)}")
    except FileNotFoundError:
        logger.error(f"Edges CSV not found: {EDGES_CSV}")
        sys.exit(1)

    try:
        master_df = pd.read_csv(MASTER_CSV, low_memory=False)
        logger.info(f"Loaded master CSV: {len(master_df)} rows, {len(master_df.columns)} columns")
    except FileNotFoundError:
        logger.error(f"Master CSV not found: {MASTER_CSV}")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        await seed_stations(db, nodes_df)
        await seed_segments(db, edges_df)
        await seed_trains(db, master_df)

    logger.info("=== Seeding complete ===")


if __name__ == "__main__":
    asyncio.run(main())
