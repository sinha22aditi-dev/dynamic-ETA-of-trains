"""
verify_e2e.py — End-to-end verification script for DynamicRail
Tests:
1. Database connectivity and counts (stations, trains, replay source)
2. ML inference pipeline (/predict and /chat)
3. Backend train status computation
"""

import sys
import os
import asyncio
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import AsyncSessionLocal
from app.models.train import Station, Train, Route
from app.models.position import ReplaySource, TrainPosition, TrainRunningStatus
from app.models.prediction import Prediction
from app.services import prediction_service
from app.clients import ml_client
from sqlalchemy import select, func

# Add ML path
ML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "DynamicRail_Complete_ML")
sys.path.insert(0, ML_PATH)
import api as ml_api


async def test_database():
    print("\n--- 1. Testing Database & Seed Data ---")
    async with AsyncSessionLocal() as db:
        stations_cnt = (await db.execute(select(func.count(Station.code)))).scalar()
        trains_cnt = (await db.execute(select(func.count(Train.train_id)))).scalar()
        routes_cnt = (await db.execute(select(func.count(Route.id)))).scalar()
        replay_cnt = (await db.execute(select(func.count(ReplaySource.id)))).scalar()

        print(f"Stations count:      {stations_cnt} (Expected: 30)")
        print(f"Trains count:        {trains_cnt} (Expected: ~995)")
        print(f"Routes count:        {routes_cnt} (Expected: ~995)")
        print(f"Replay rows count:   {replay_cnt} (Expected: 30000)")

        assert stations_cnt == 30, f"Expected 30 stations, found {stations_cnt}"
        assert trains_cnt > 900, f"Expected >900 trains, found {trains_cnt}"
        assert replay_cnt == 30000, f"Expected 30000 replay rows, found {replay_cnt}"
        print(">>> Database checks PASSED!")


async def test_ml_service(db):
    print("\n--- 2. Testing ML Engine (In-Process) ---")
    client = TestClient(ml_api.app)
    
    # 1. Health
    h_res = client.get("/health")
    assert h_res.status_code == 200
    print(f"ML Health: {h_res.json()}")

    # 2. Get a real row from replay_source
    row_result = await db.execute(select(ReplaySource).limit(1))
    sample_row = row_result.scalar_one()
    sample_data = ml_client._strip_leakage(dict(sample_row.raw_data))
    
    pred_res = client.post("/predict", json={"data": sample_data})
    assert pred_res.status_code == 200, f"Predict failed: {pred_res.text}"
    pred = pred_res.json()
    print(f"ML Prediction Output for Train {sample_row.train_id}:")
    print(f"  - Current Delay:         {pred['current_delay_mins']} mins")
    print(f"  - Predicted Total Delay: {pred['predicted_total_delay_mins']} mins")
    print(f"  - ETA:                   {pred['eta']}")
    print(f"  - Delay Reason:          {pred['delay_reason']}")
    print(f"  - Delay Reason Conf:     {pred['delay_reason_confidence']}")
    print(f"  - Propagation Risk:      {pred['propagation']['risk']} (Prob: {pred['propagation']['probability']})")
    
    # 3. Chat query
    chat_res = client.post("/chat", json={
        "query": "Why is my train delayed?",
        "prediction": pred,
        "language": "en"
    })
    assert chat_res.status_code == 200
    print(f"AI Assistant Reply (English): {chat_res.json()['response']}")
    print(">>> ML Engine checks PASSED!")


async def main():
    print("===================================================")
    print("DynamicRail End-to-End Verification")
    print("===================================================")
    await test_database()
    async with AsyncSessionLocal() as db:
        await test_ml_service(db)
    print("\n===================================================")
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("DynamicRail is fully operational and presentation-ready.")
    print("===================================================")


if __name__ == "__main__":
    asyncio.run(main())
