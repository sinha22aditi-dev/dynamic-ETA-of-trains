import os, json, math, joblib
from pathlib import Path
from datetime import datetime
import numpy as np, pandas as pd, torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import *
from models import GRURegressor, HybridGNNGRU
from preprocess import add_time_features
from delay_reason import explain_delay
from weather_service import get_weather
from maps_service import directions_url
from language_service import available_languages, chatbot_reply

app=FastAPI(title="DynamicRail ML API",version="2.0")
xgb=joblib.load(MODEL_DIR/"xgb_delay.joblib")
prop=joblib.load(MODEL_DIR/"propagation_xgb.joblib")
meta=json.loads((MODEL_DIR/"neural_meta.json").read_text())
sc=np.load(MODEL_DIR/"neural_scaler.npz"); mean=sc["mean"]; std=np.where(sc["std"]<1e-6,1,sc["std"])
g=np.load(MODEL_DIR/"graph_features.npz",allow_pickle=True); node_x=torch.tensor(g["node_x"],dtype=torch.float32); adj=torch.tensor(g["adj"],dtype=torch.float32); stations=[str(x) for x in g["stations"]]; node_idx={s:i for i,s in enumerate(stations)}

gru=GRURegressor(len(NEURAL_NUMERIC_FEATURES), hidden=32, layers=1, dropout=0.15); gru.load_state_dict(torch.load(MODEL_DIR/"gru_delay.pt",map_location="cpu")); gru.eval()
hybrid=HybridGNNGRU(len(NEURAL_NUMERIC_FEATURES),len(NEURAL_NUMERIC_FEATURES), gru_hidden=32, gnn_hidden=16, dropout=0.15); hybrid.load_state_dict(torch.load(MODEL_DIR/"hybrid_gnn_gru_delay.pt",map_location="cpu")); hybrid.eval()
metrics=json.loads((MODEL_DIR/"metrics.json").read_text())

class PredictRequest(BaseModel):
    data: dict
    history: list[dict]=[]

class ChatRequest(BaseModel):
    query: str
    prediction: dict
    language: str="en"

@app.get("/")
def root(): return {"service":"DynamicRail ML","status":"ok"}
@app.get("/health")
def health(): return {"status":"ok","models":["xgboost","gru","gnn","hybrid_gnn_gru"]}
@app.get("/metrics")
def get_metrics(): return metrics
@app.get("/languages")
def languages(): return available_languages()

@app.post("/predict")
def predict(req: PredictRequest):
    data=dict(req.data)
    try:
        X=add_time_features(pd.DataFrame([data]))
        X=X.drop(columns=["future_delay_target"],errors="ignore")
        add=float(xgb.predict(X)[0])
        prob=float(prop.predict_proba(X)[0,1])
    except Exception as e:
        raise HTTPException(400,f"Input data could not be processed: {e}")
    current=float(data.get("current_delay_mins",0) or 0)
    total=max(0,current+add)
    dist=max(0,float(data.get("distance_remaining_km",0) or 0))
    speed=max(0,float(data.get("current_speed_kmh",0) or 0))
    remain=(dist/speed*60) if speed>5 else float(data.get("estimated_remaining_travel_time_mins",data.get("remaining_travel_time_mins",0)) or 0)
    ts=pd.to_datetime(data.get("timestamp",pd.Timestamp.now()),errors="coerce")
    if pd.isna(ts): ts=pd.Timestamp.now()
    eta=ts+pd.Timedelta(minutes=remain+total)
    # Historical residual interval is kept intentionally simple and labeled an uncertainty interval.
    interval=metrics.get("xgboost_delay",{}).get("mae",5.0)
    low=eta-pd.Timedelta(minutes=interval); high=eta+pd.Timedelta(minutes=interval)
    reason=explain_delay(data)
    return {"current_delay_mins":round(current,2),"predicted_additional_delay_mins":round(add,2),
            "predicted_total_delay_mins":round(total,2),"estimated_remaining_travel_mins":round(remain,2),
            "eta":eta.isoformat(),"eta_interval":{"lower":low.isoformat(),"upper":high.isoformat()},
            "delay_reason":reason["reason"],"delay_reason_confidence":reason["confidence"],
            "propagation":{"probability":round(prob,3),"risk":"HIGH" if prob>=.7 else ("MEDIUM" if prob>=.4 else "LOW")}}

@app.post("/predict/temporal")
def predict_temporal(req: PredictRequest):
    if len(req.history)<WINDOW: raise HTTPException(400,f"history must contain at least {WINDOW} observations")
    arr=[]
    for h in req.history[-WINDOW:]:
        arr.append([float(h.get(c,0) or 0) for c in NEURAL_NUMERIC_FEATURES])
    arr=(np.array(arr,float)-mean)/std
    x=torch.tensor(arr,dtype=torch.float32).unsqueeze(0)
    station=str(req.history[-1].get("current_station",stations[0])); ni=torch.tensor([node_idx.get(station,0)])
    with torch.no_grad():
        p=float(hybrid(x,node_x,adj,ni).item()); pg=float(gru(x).item())
    return {"gru_predicted_additional_delay_mins":pg,"hybrid_gnn_gru_predicted_additional_delay_mins":p}

@app.get("/weather")
def weather(lat:float,lon:float):
    try:return get_weather(lat,lon)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/maps/directions")
def maps(origin:str,destination:str,travelmode:str="transit"):
    return {"url":directions_url(origin,destination,travelmode)}

@app.post("/chat")
def chat(req:ChatRequest): return {"language":req.language,"response":chatbot_reply(req.query,req.prediction,req.language)}
