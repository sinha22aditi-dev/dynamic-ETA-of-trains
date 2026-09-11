# DynamicRail Complete ML Package

## Included
- Cleaned master data and calibrated sequential simulation data.
- XGBoost future-delay baseline.
- GRU temporal model.
- GNN spatial encoder over railway station graph.
- Hybrid GNN-GRU delay model.
- Delay propagation classifier.
- Dynamic ETA calculation and ETA interval.
- Delay-reason explanation layer.
- Live weather endpoint (Open-Meteo).
- 23-language UI layer: English + 22 Scheduled Languages.
- Railway chatbot endpoint (rule-based fallback, ready for LLM replacement).
- Google Maps directions URL integration.
- Offline cache helper.
- Live data replay helper.
- FastAPI service for backend integration.

## Honest dataset note
The supplied master data contains 1,000 snapshot rows. The 30,000-row sequential file is a
synthetic prototype extension calibrated to those observations; it is not real railway telemetry.
The API is designed for live feeds, but an authorized live railway data source is still required for
real-world deployment. Google Maps is navigation only; it does not supply railway operational telemetry.

## Run

```bash
pip install -r requirements.txt
python train_all.py
uvicorn api:app --reload
```

Swagger: http://127.0.0.1:8000/docs

## Backend flow
POST `/predict` with current train features. POST `/predict/temporal` with the latest 6 observations
for hybrid GNN-GRU inference. Other endpoints provide weather, chatbot, language list, and Google Maps URL.

## Model-selection note
XGBoost is the strongest tabular baseline on this dataset. GRU and hybrid GNN-GRU are kept as advanced
models for temporal/spatial experimentation. Use group-by-sequence train/validation/test splits to avoid
mixing rows from the same simulated journey between splits.
