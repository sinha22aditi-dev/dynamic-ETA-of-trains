# DynamicRail — Backend Product Requirements Document

**SIH 2026 · Problem Statement SIH26028 — Dynamic ETA Forecasting for Coaching Trains**
**Team:** Pascals · **Scope:** Backend/Application Development
**Source materials inspected:** `frontend.html` (UI mockup), `DynamicRail_Complete_ML.zip` (ML service code + trained models + data), `DynamicRail_Rebuilt_Dataset.zip` (canonical dataset + validation report)

---

## 1. Executive Summary

DynamicRail predicts train ETAs by combining a rule/history-driven current state with an XGBoost delay-prediction model and a propagation-risk classifier, both already implemented and served by a **separate FastAPI ML service** (`api.py`). The UI supplied is a **single static hero/landing page mockup** (no routing, no real network calls) that establishes the visual language and the feature set the product wants: train search, a live prediction card (ETA, delay, confidence, reason), a smart ETA alarm, an AI chat assistant, a recent/tracked-trains list, and an online/offline mode.

The backend's job is **not** to build ML — it already exists and works. The backend's job is to:
1. Own persistent state (users, trains, stations, routes, schedules, tracked trains, alarms, notifications, prediction history) in PostgreSQL.
2. Feed the ML service the exact 78-field snapshot it requires (see §12) by combining static reference data + a "current state" record (from the dataset/replay engine now, from real telemetry later).
3. Orchestrate calls to `/predict` (and optionally `/predict/temporal`, `/chat`, `/weather`, `/maps/directions`, `/languages`), validate responses, persist them, and expose a clean, frontend-shaped REST API.
4. Run the **replay/simulation engine** that turns the static 30,000-row sequential dataset into a live-feeling train feed, since no real railway API is available (dataset is synthetic, per the ML package's own README).

This document is the implementation-ready contract for that backend, built strictly from the three source artifacts — not from a generic assumption of what a "train ETA backend" should look like.

---

## 2. Current Codebase Audit

| Artifact | What it actually is |
|---|---|
| `frontend.html` | A single, static, hand-built HTML/Tailwind **landing page**. No router, no components, no state library, no `fetch`/`XMLHttpRequest`/`axios` calls anywhere in the file (verified by search — zero backend calls exist). All "live" behavior (ETA card values, chat replies, alarm countdown, online/offline banner) is **hardcoded or simulated with inline `<script>` functions and `setTimeout`**. There is no login/registration screen, no dedicated train-detail/tracking page, no map view, no notifications inbox, no settings page — only a home page that *implies* these features via UI copy and buttons that currently do nothing (`href="#"`) or `alert()`. |
| `DynamicRail_Complete_ML.zip` | A working, trainable, and already-trained ML package: FastAPI service (`api.py`), model definitions (`models.py`: `GRURegressor`, `GCNLayer`, `GNNEncoder`, `HybridGNNGRU`), preprocessing (`preprocess.py`), training script (`train_all.py`), delay-reason rules (`delay_reason.py`), weather proxy (`weather_service.py`), Google Maps URL helper (`maps_service.py`), 23-language chatbot (`language_service.py`), a CSV-replay generator helper (`live_replay.py`, not exposed as an API), an offline JSON cache helper (`offline_cache.py`), and trained artifacts (`xgb_delay.joblib`, `propagation_xgb.joblib`, `gru_delay.pt`, `hybrid_gnn_gru_delay.pt`, plus scaler/graph/metrics files). |
| `DynamicRail_Rebuilt_Dataset.zip` | The canonical dataset, matching what's bundled inside the ML zip: `railpulse_master_clean.csv` (1,000-row snapshot, 91 columns), `dynamicrail_sequential_simulation.csv` (30,000-row synthetic 10-minute-step simulation, 98 columns, 1,000 sequences of 30 steps over 995 trains), `railway_graph_nodes.csv` (30 stations), `railway_graph_edges.csv` (574 directed station-pair edges with distance + observed count), `DATASET_README.md`, and `data_validation_report.json`. |

**Key finding — frontend/ML/dataset are not yet wired together.** The frontend was designed independently of the ML/dataset (e.g., it shows fictional "ICE 4022 Amsterdam–Frankfurt" and "EuroRail 9412 Lyon–Paris" trains, while the actual dataset/graph only cover 30 Indian station codes across Indian railway zones). This PRD calls this out explicitly wherever it matters (see §36 Risks and §37 Open Questions) rather than silently reconciling it.

---

## 3. Frontend Audit (source of truth for UI requirements only — not for API contracts)

Because the frontend has no network code, it cannot be used as a source of truth for endpoint paths, payload shapes, or auth flows the way the prompt anticipates. It **is** a reliable source of truth for *what the product needs to display*, which drives the backend's response shapes. Extracted requirements:

### 3.1 Global / chrome
- Top nav: Home, "My Trains", Notifications (with unread badge count, e.g. "2").
- Language selector (stub `EN` dropdown) — the ML service already exposes `/languages` (23 codes: English + 22 Scheduled Languages) and multilingual label sets for `eta`/`delay`/`reason`/`risk`.
- An **Online/Offline network-status pill** the user can toggle, plus a banner: "Offline Mode • Last synchronized: HH:MM • Saved train information is still available • AI Assistant requires internet connection." This directly maps to the ML package's `offline_cache.py` (save/load last-known payload) and to a backend "last successful sync" concept per tracked train.

### 3.2 Home / search
- One large search input: "Enter Train Number or Train Name" + "Track Train" button → implies **GET train search by number or name**.

### 3.3 "Delay Update" transition banner
- Shows previous predicted ETA vs new predicted ETA with a delta ("+12 min"), plus a plain-language delay reason. Requires the backend to retain the **previous** prediction to compute/display a delta when a new one arrives (→ `prediction_history`).

### 3.4 Live Train Prediction card (the core screen)
Fields shown, each traceable to an ML response field (§12) or a derived backend calculation (§14):
- Train identity + route: "12951 Mumbai Rajdhani", "New Delhi → Mumbai Central", running status ("Running"), "Updated 2 min ago".
- **AI Predicted ETA** (large, hero number) ← ML `eta`.
- "+33 min vs Schedule" ← backend-computed: `final_eta − scheduled_arrival_time`.
- Scheduled/"Timetable" time ← `train_schedules.scheduled_arrival_time`.
- "Current Running Delay" ← ML `current_delay_mins` (echoed input) and "Predicted Additional Delay" ← ML `predicted_additional_delay_mins`.
- Warning callout with a plain-language reason ← ML `delay_reason`.
- **Prediction Confidence meter (%)** ← the UI wants a single 0–100 confidence percentage. The ML service does **not** return a generic "confidence" field for `/predict`; it returns `delay_reason_confidence` (0–1, confidence in the *reason* explanation) and a `propagation.probability`/`risk`. **Mismatch, flagged in §36**: the backend must decide which of these (most likely `delay_reason_confidence × 100`) backs the UI's "Prediction Confidence" bar, since the ML code does not expose a dedicated ETA-confidence score.
- "Calibrated Neural Telemetry" badge — cosmetic; no dedicated field required, but implies the frontend expects to know when a GNN/GRU-backed prediction (vs plain XGBoost) was used, another data point for the response's `model_version`/`model_used` metadata (§16).

### 3.5 "Set Smart Alarm" card
- Shows "Predicted Arrival" (base ETA), an offset dropdown (5/10/15/20/30 minutes before), a live-recalculated "Calculated Alarm" time, an "Automatically adjust alarm with ETA" toggle, and a "Set Smart Alarm" button with confirmation text. Maps directly to a `smart_alarms` entity: `train_id`, `target_station_id` (implied — "reach Borivali"), `offset_minutes`, `auto_adjust: bool`, plus server-side re-evaluation whenever a new prediction lands.

### 3.6 "Ask DynamicRail" AI assistant
- Suggested prompt chips ("Where is my train?", "When will it reach?", "Why is my train delayed?", "What is the latest ETA?") and a full modal chat UI with quick-prompt chips including **"Set smart alarm for this train"** and **"Weather & fog ahead"**. In the mock, replies are hardcoded per keyword match, but this exactly mirrors the ML service's real `/chat` endpoint keyword logic in `language_service.chatbot_reply` (why/reason, how late/delay, eta/arrival, another train/propagation). The backend's job is to wire this modal to a real `POST /predictions/chat` that forwards `{query, prediction, language}` to the ML `/chat` endpoint using the *last stored prediction* for that train — not to reimplement chat logic.
- Offline state shows a canned "cached telemetry" answer — maps to `offline_cache.py`/last-known-prediction fallback.

### 3.7 Recently tracked trains list
- Cards showing train id/name, delay badge, a status chip ("On time to next stop" / "In transit" / "Delay absorbed"), route, predicted ETA, and a "View Live Tracker" link. Requires `tracked_trains` (favourites) + the latest prediction per tracked train. **Note:** two of the three example cards are non-Indian trains not representable by the current dataset/graph — see §36.

### 3.8 Footer
- "Telemetry Latency: 1.2s" and a "High Contrast" accessibility toggle — cosmetic, no backend requirement beyond optionally reporting last-call latency in a health/metrics endpoint.

### 3.9 What the frontend does *not* show (must be assumed/left open)
No login form, no registration form, no train-detail/route-map page, no notification list page, no alarm-management (list/edit/delete) page, no settings/preferences page. These are required by the PRD's own "Backend Responsibility" list and by common sense for a working product, but their *exact* shape is an assumption, not observed UI — flagged individually in §37.

---

## 4. ML Audit

**Framework:** FastAPI + PyTorch (GRU, GNN) + XGBoost (via scikit-learn `Pipeline`) + joblib.
**Service entry point:** `uvicorn api:app` — default port **8000** (per the ML package's own README).
**Loaded artifacts at startup:** `xgb_delay.joblib` (delay regressor pipeline), `propagation_xgb.joblib` (propagation classifier pipeline), `neural_meta.json` (feature list, 30 station list, window/horizon config), `neural_scaler.npz` (mean/std for the 35 neural features), `graph_features.npz` (node features + adjacency for the 30-station graph), `gru_delay.pt`, `hybrid_gnn_gru_delay.pt`.

### 4.1 Exact exposed endpoints (do not deviate from these)

| Method & Path | Request body | Response |
|---|---|---|
| `GET /` | — | `{"service":"DynamicRail ML","status":"ok"}` |
| `GET /health` | — | `{"status":"ok","models":["xgboost","gru","gnn","hybrid_gnn_gru"]}` |
| `GET /metrics` | — | Contents of `metrics.json` (see §4.4) |
| `GET /languages` | — | `[{"code":"en","name":"English"}, ...]` (23 entries) |
| `POST /predict` | `{"data": {...78 fields...}, "history": []}` (`history` unused by this route but present in schema) | See §12.2 |
| `POST /predict/temporal` | `{"data": {}, "history": [ ...≥6 snapshot dicts... ]}` | `{"gru_predicted_additional_delay_mins": float, "hybrid_gnn_gru_predicted_additional_delay_mins": float}` |
| `GET /weather?lat=&lon=` | query params | Open-Meteo passthrough: `{"provider":"Open-Meteo","current":{...},"hourly":{...}}` |
| `GET /maps/directions?origin=&destination=&travelmode=` | query params | `{"url": "https://www.google.com/maps/dir/?api=1&origin=...&destination=...&travelmode=..."}` |
| `POST /chat` | `{"query": str, "prediction": {...a stored /predict response...}, "language": "en"}` | `{"language": "en", "response": str}` |

No other endpoints exist. **No authentication is implemented on the ML service** — it is a trusted internal service the backend calls server-to-server; it must never be exposed directly to the frontend/internet.

### 4.2 `/predict` — what it actually does
1. Builds a one-row DataFrame from `data`, adds `hour`/`minute`/`dayofweek_num`/`is_night` from `timestamp` if present (`add_time_features`), drops `future_delay_target` if present.
2. Runs the **already-fitted XGBoost pipeline** (`xgb`) to get `predicted_additional_delay_mins`. The pipeline's internal `ColumnTransformer` was fit against a specific 78-column feature set (exact list in §12.1) — **all 78 must be present in `data`** or the request throws a 400 (broad `except Exception` → `HTTPException(400, ...)`).
3. Runs the **propagation classifier** (`prop`) on the same 78-column frame to get a probability, bucketed into `LOW`/`MEDIUM`/`HIGH` at 0.4/0.7.
4. Computes `total = current_delay_mins + predicted_additional_delay_mins` (floored at 0).
5. Computes `remain` (estimated remaining travel minutes): if `current_speed_kmh > 5`, `remain = distance_remaining_km / current_speed_kmh * 60`; else it falls back to `estimated_remaining_travel_time_mins` (or `remaining_travel_time_mins`) from the input, defaulting to 0.
6. `eta = timestamp + (remain + total) minutes` (timestamp defaults to "now" if missing/unparseable).
7. Builds a **naive uncertainty interval**: `±metrics["xgboost_delay"]["mae"]` minutes around `eta` (currently ≈ ±0.61 min per `metrics.json` — extremely tight because the model is overfit-prone on synthetic data; see §36).
8. Computes a rule-based `delay_reason` + `delay_reason_confidence` via `delay_reason.explain_delay` (pure Python heuristics over `current_delay_mins`, `current_speed_kmh`, `section_congestion_index`, `number_of_trains_ahead`, `rainfall_mm`, `visibility_meters`, `speed_restriction_kmh` vs `current_speed_kmh`, `track_maintenance_active`) — **this is not a model output**, it is a rule engine bundled in the ML service; the backend must not reimplement it, just call `/predict` and use the field.

### 4.3 `/predict/temporal` — what it actually does
Requires ≥6 (`WINDOW`) historical snapshot dicts, each providing the 35 `NEURAL_NUMERIC_FEATURES` (§4.5). Normalizes with the saved scaler, builds a `(1, 6, 35)` tensor, runs it through the **GRU** and the **Hybrid GNN-GRU** (the latter also uses the 30-station graph and the last-known `current_station` to index into the graph). **It returns only two raw numbers — it does not compute ETA, interval, delay reason, or propagation.** If the backend wants to expose a GNN/GRU-based ETA, it must apply the *same* combination formula the `/predict` handler uses (steps 4–6 above) itself, because the ML code does not do this for the temporal route. This is explicitly flagged as an **open design decision** in §37, not invented here.

### 4.4 `/metrics` (live values from the shipped `metrics.json`)

| Model | MAE | RMSE | R² / Accuracy |
|---|---|---|---|
| XGBoost delay regressor | 0.61 min | 0.95 min | R² 0.985 |
| Propagation classifier | — | — | Accuracy 0.812, F1 0.843, positive rate 0.581 |
| GRU | 0.68 min | 1.21 min | R² 0.976 |
| Hybrid GNN-GRU | 0.74 min | 1.38 min | R² 0.969 |

These extremely low errors are a direct consequence of training/testing on the **synthetic, internally-consistent sequential simulation** — the ML package's own README states this plainly and warns these numbers cannot be read as real-world accuracy. The backend must **never present these numbers to end users as real-world accuracy claims**; they may only be surfaced internally (e.g., an admin/health screen) with the same caveat.

### 4.5 Neural (GRU/Hybrid) feature set — `NEURAL_NUMERIC_FEATURES` (35 fields, exact order matters for the scaler)
`current_speed_kmh, current_delay_mins, distance_remaining_km, previous_station_delay, delay_2_stations_ago, delay_3_stations_ago, historical_avg_train_delay, historical_avg_station_delay, historical_avg_section_delay, historical_on_time_pct, train_ahead_delay_mins, train_ahead_speed_kmh, train_ahead_distance_km, number_of_trains_ahead, distance_between_trains_km, headway_mins, section_congestion_index, temperature_celsius, rainfall_mm, humidity_pct, wind_speed_kmh, visibility_meters, track_vibration_hz, rail_wear_mm, speed_restriction_kmh, section_capacity_pct, bearing_temperature_c, axle_temperature_c, brake_pressure_bar, brake_pad_wear_pct, days_since_maintenance, hour, month, is_weekend_holiday, is_peak_hour`

Graph: 30 stations (exact same 30 codes as `railway_graph_nodes.csv`): `ADI, AGC, ALD, ASN, BCT, BPL, BRC, BZA, CNB, CSTM, DHN, GAYA, GWL, HWH, JHS, JP, KOTA, LKO, MAS, MGS, NDLS, NGP, PNBE, PUNE, RTM, SBC, SC, ST, TDL, VAPI`.

### 4.6 Auxiliary ML modules
- `weather_service.get_weather(lat, lon)` — live call to Open-Meteo (no API key needed); returns current + 6-hour hourly forecast. **This is real live data**, unlike the train dataset.
- `maps_service.directions_url(origin, destination, travelmode)` — pure string builder for a Google Maps deep link; **not** a routing/telemetry source.
- `language_service` — 23-language label dictionary + rule-based chatbot reply function (keyword matching in English/Hindi, transliteration-ish keywords like "kyun", "kab").
- `live_replay.replay_train(train_id, csv_path, seconds_per_step)` — a **generator function**, not an HTTP endpoint. It reads the sequential CSV, filters by `train_id`, sorts by `timestamp`, and yields rows with a `time.sleep` between them. **The backend must implement its own replay engine** (§10) — this file is a reference/pattern only, and per the "do not invent ML endpoints" rule, the backend must not assume this becomes a live ML API; it is dataset code, and the dataset lives with the backend's replay engine, not the ML service.
- `offline_cache.py` — trivial JSON file read/write. Reference pattern for the backend's own "last known good prediction" cache, not a shared component the backend calls into.

### 4.7 What the backend must NOT re-implement
Model training/inference math (XGBoost, GRU, GNN, Hybrid GNN-GRU), the delay-reason rule engine, the chatbot reply logic, feature scaling, or graph adjacency construction. The backend **may** need to replicate one small piece of arithmetic only if it chooses to expose `/predict/temporal` results as a full ETA (see §37 — flagged as open, not decided here).

---

## 5. Dataset Audit

### 5.1 Files and roles

| File | Rows × Cols | Role |
|---|---|---|
| `railpulse_master_clean.csv` | 1,000 × 91 | One (mostly) snapshot per train — static/reference seed source (trains, stations implied, routes, schedules) and the base the sequential file was calibrated from. |
| `dynamicrail_sequential_simulation.csv` | 30,000 × 98 | **Synthetic** — 1,000 sequences (`sequence_id`) × 30 ten-minute steps, covering 995 unique `train_id`s. This is the ML training data **and** the dataset the backend's replay engine drives itself from. |
| `railway_graph_nodes.csv` | 30 × 2 | `node_index, station` — the 30-station graph node set used by the GNN. |
| `railway_graph_edges.csv` | 574 × 4 | `current_station, next_station, distance_km, observed_count` — directed edges derived from observed transitions in the master snapshot, with median distance and how often that transition was observed. |
| `dataset_summary.json` | — | Aggregate stats (see §5.4). |
| `data_validation_report.json` | — | Automated QA: 0 duplicate rows, 0 missing critical fields, monotonic per-sequence timestamps, 10-minute intervals confirmed, 2,000 rows (last 2 steps × 1,000 sequences) intentionally missing the future target, propagation rate ≈ 0.59. |
| `DATASET_README.md` | — | **Authoritative honesty statement**, quoted in full effect here: repeated observations are simulated, not real railway measurements, and must not be presented as live/official data; splits must be by `sequence_id`, not by row. |

### 5.2 Column inventory (shared by master + sequential; sequential adds simulation bookkeeping columns)

**Identifiers / static train info:** `train_id, train_name, train_type, train_category, railway_zone, section_id, track_id`
**Position/route:** `latitude, longitude, current_station, previous_station, next_station, direction, current_location_km, distance_to_next_station_km, distance_from_previous_station_km, distance_remaining_km`
**Schedule:** `scheduled_arrival_time, scheduled_departure_time, scheduled_journey_time_hrs, scheduled_segment_travel_time_mins, scheduled_distance_km, station_halt_time_mins, historical_segment_travel_time_mins`
**Live state:** `timestamp, current_speed_kmh, current_delay_mins, movement_status, stoppage_duration_mins`
**Delay history/context:** `previous_station_delay, delay_2_stations_ago, delay_3_stations_ago, historical_avg_train_delay, historical_avg_station_delay, historical_avg_section_delay, historical_on_time_pct`
**Train-ahead / congestion:** `train_ahead_id, train_ahead_delay_mins, train_ahead_speed_kmh, train_ahead_distance_km, number_of_trains_ahead, distance_between_trains_km, headway_mins, same_track, same_section, section_congestion_index, section_capacity_pct`
**Delay reason bookkeeping (dataset-labelled, distinct from the ML rule engine):** `delay_reason_code, delay_reason, reason_severity, reason_start_time, reason_duration_mins, confirmed_unconfirmed_reason, reason_source, delay_reason_category`
**Weather:** `temperature_celsius, rainfall_mm, humidity_pct, wind_speed_kmh, visibility_meters, weather_condition, weather_severity`
**Track/rolling-stock health:** `track_condition, track_vibration_hz, rail_wear_mm, speed_restriction_kmh, track_maintenance_active, signal_status, bearing_temperature_c, axle_temperature_c, brake_condition, brake_pressure_bar, brake_pad_wear_pct, maintenance_status, days_since_maintenance, sensor_health, failure_type, failure_severity`
**Time context:** `hour, day_of_week, month, season, is_weekend_holiday, is_peak_hour`
**Outcome/journey state:** `journey_status, movement_status`
**Prediction targets / labels (never live inputs — see §5.6):** `predicted_eta, actual_arrival_time, remaining_travel_time_mins, future_additional_delay_mins, propagation_occurred, propagation_delay_mins`
**Sequential-only bookkeeping:** `sequence_step, sequence_id, data_source, future_delay_20m, propagation_probability, estimated_remaining_travel_time_mins, split`

### 5.3 Categorical value sets (from the sequential file, used for validation/enums)
`train_type`: DEMU, Duronto, Express, Freight, Garib Rath, MEMU, Mail, Passenger, Rajdhani, Shatabdi, Superfast, Vande Bharat
`train_category`: Freight, Long-Distance, Premium, Regional, Suburban
`railway_zone`: CR, ECR, ECoR, ER, NCR, NER, NFR, NR, NWR, SCR, SECR, SER, SR, SWR, WCR
`movement_status`: Departed_Late, Halted_Signal, Running, Slow_Running, Stopped_at_Station, Terminated
`journey_status`: Completed, In_Transit, Not_Started
`direction`: Up, Down
`signal_status`: Auto, Double_Yellow, Green, Red, Yellow
`weather_condition`: Clear, Cloudy, Fog, Haze, Heavy_Rain, Rain, Storm
`track_condition`: Excellent, Fair, Good, Poor, Under_Repair
`brake_condition`: Critical, Excellent, Fair, Good, Needs_Inspection
`maintenance_status`: Due_Soon, In_Progress, Overdue, Up_to_Date
`sensor_health`: Degraded, Faulty, Healthy, Offline
`failure_type`: Axle_Fault, Bearing_Overheat, Brake_Wear, Door_Malfunction, Electrical_Fault, HVAC_Failure, No_Failure
`failure_severity`: Critical, Minor, Moderate, No_Failure
`delay_reason_category`: Infrastructure, Mechanical, No_Delay, Operational, Traffic, Weather
`confirmed_unconfirmed_reason`: Auto-Detected, Confirmed, Not_Applicable, Unconfirmed
`reason_source`: Control_Office, IoT_Sensor, ML_Inference, Manual_Report, Not_Applicable, Station_Master
`split` (sequential only): train, test (val rows exist upstream but are not shipped as a labelled subset in this file — `sequence_splits.csv` inside the ML package records the actual train/val/test split by `sequence_id`)

### 5.4 Aggregate stats (`dataset_summary.json`)
1,000 master rows, 30,000 simulation rows, 995 unique trains, 30 steps/train, 30 graph nodes, 574 graph edges, 20-minute prediction horizon, propagation rate ≈ 58.7%, future-delay mean ≈ 6.6 min (std ≈ 8.0 min, observed range roughly −118 to +24 min in the summary; the validation report's own recomputation shows a tighter −5.0 to +24.0 min range — **both are shipped, numbers disagree slightly, flagged in §37**).

### 5.5 Graph structure
`railway_graph_nodes.csv` gives 30 `(node_index, station)` pairs. `railway_graph_edges.csv` gives 574 directed `(current_station, next_station, distance_km, observed_count)` rows built from observed transitions in the master snapshot — i.e., **this is not an official IR track topology**, it is inferred from the synthetic-but-plausible data. The ML service loads this graph once at startup via `graph_features.npz` (pre-baked node features + normalized adjacency); the backend does not need to reconstruct the GNN's adjacency matrix, only to (a) optionally mirror the node/edge list into PostgreSQL for the frontend's route-map feature, and (b) always send the model the plain `current_station` code — the ML service does the graph lookup internally.

### 5.6 Target / leakage fields — must never be sent as live prediction inputs
`predicted_eta`, `actual_arrival_time`, `future_additional_delay_mins`, `future_delay_20m`, `future_delay_target` (training-only, computed on the fly by `train_all.py`, not present in the shipped CSV), `propagation_delay_mins`, `propagation_occurred`, `propagation_probability` (this one is subtle: it's a **dataset-simulated** probability, not the model's own output — the model produces its own probability inside `/predict`; the dataset's `propagation_probability` column must be treated as historical/label data only, never fed back into a live request), `remaining_travel_time_mins` (this is itself a *result* field in the master/sequential schema — distinct from `estimated_remaining_travel_time_mins`, which **is** a required live input feature per the trained pipeline; see §12.1 note). These are correctly excluded from the ML training feature set already (`config.XGB_DROP` / `XGB_TIME_COLUMNS` / `XGB_DERIVED_OUTPUTS`), and the backend must mirror that exclusion at the API boundary: **never let a client-supplied or replay-supplied value for any of these fields reach `/predict`.**

### 5.7 Dataset → destination mapping (high level; full table in §9)
1. **PostgreSQL (seed/reference):** train identity, station list, route/segment graph, schedules — all sourced from `railpulse_master_clean.csv` + graph CSVs, loaded once at seed time.
2. **ML service input (per-prediction, not stored verbatim beyond the prediction snapshot):** the 78-field XGBoost feature set / 35-field neural feature set, sourced live from the current replay/live state, not re-derived from static tables at request time except where the field is genuinely static (e.g., `train_type`).
3. **ML service output:** stored in `predictions` / `prediction_history`.
4. **Live-data/replay ingestion:** the entire sequential CSV drives the replay engine; nothing here is "real" ingestion.
5. **Cache:** the latest prediction and latest position per train (short TTL), station/route/graph reference data (long TTL/startup load).
6. **Never stored by the backend:** the six leakage fields in §5.6, and bulk ML training artifacts (`sequence_splits.csv`, `metrics.json` is fine to store for an admin/health view only).

---

## 6. Backend Responsibilities

**Owns:** FastAPI app, REST APIs, auth (JWT), PostgreSQL + SQLAlchemy + Alembic, Pydantic schemas, all entities listed in §8, the ML client/orchestration layer, response transformation into frontend-friendly shapes, the replay/simulation engine, caching, background jobs, notifications, smart alarms, logging, error handling, security, tests, Docker.

**Explicitly does not own:** model training/inference, the delay-reason rule engine, the chatbot reply logic, feature scaling, graph adjacency construction, or a real railway ingestion API (none is provided or documented — the backend must not invent one; see §22).

---

## 7. System Architecture

```
Frontend (currently a static mockup; real SPA/app to be built against this API)
        │  REST/JSON, JWT bearer auth
        ▼
DynamicRail Backend — FastAPI modular monolith
 ├── auth, trains, stations, routes, tracking, predictions,
 │    notifications, alarms, replay, health  (API layer)
 ├── services/  (business logic: prediction orchestration, alarm
 │    evaluation, notification dispatch, replay engine)
 ├── repositories/ (SQLAlchemy data access)
 └── clients/
      ├── ml_client.py   → DynamicRail ML Service (FastAPI, port 8000)
      └── railway_client.py → RailwayDataProvider abstraction
                                 (today: Replay/Dataset provider only)
        │                                   │
        ▼                                   ▼
   PostgreSQL                    ML Service (external process)
   (all persistent state)        /predict, /predict/temporal, /chat,
                                  /weather, /maps/directions, /languages
```

A **modular monolith** is correct here: one deployable FastAPI app, clean internal module boundaries, no message broker, no separate microservices. The only externally separate process is the already-existing ML service — it is kept separate because it already exists as its own FastAPI app with its own heavy dependencies (PyTorch, XGBoost) and its own model lifecycle, not because the backend design calls for microservices.

---

## 8. Database Architecture (PostgreSQL)

All tables use `BIGSERIAL`/`UUID` primary keys per team convention — this PRD uses `BIGSERIAL` for simplicity; swap to `UUID` if the team prefers non-guessable public IDs (**OPEN QUESTION**, see §37).

### 8.1 `users` — user-specific, transactional
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| email | VARCHAR(255) UNIQUE NOT NULL | |
| password_hash | VARCHAR(255) NOT NULL | bcrypt/argon2 |
| full_name | VARCHAR(255) | nullable |
| preferred_language | VARCHAR(8) DEFAULT 'en' | must be one of the 23 codes from ML `/languages` |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at, updated_at | TIMESTAMPTZ | |

### 8.2 `stations` — static/reference
Sourced from `railway_graph_nodes.csv` (30 codes) — the *only* station codes with any operational meaning in this system today (they're the ones the GNN knows). Do not invent station full names/coordinates not present in source data.
| Column | Type | Notes |
|---|---|---|
| code | VARCHAR(10) PK | e.g. `NDLS`, `BCT` — from `railway_graph_nodes.station` |
| graph_node_index | INT UNIQUE NOT NULL | from `railway_graph_nodes.node_index`, required by the ML graph lookup contract |
| display_name | VARCHAR(255) | nullable — **OPEN QUESTION**: no station full-name mapping is provided anywhere in the three artifacts; do not fabricate "New Delhi" etc. beyond the code unless a mapping is supplied later |
| created_at | TIMESTAMPTZ | |

### 8.3 `trains` — static/reference
Sourced from distinct `(train_id, train_name, train_type, train_category, railway_zone)` in `railpulse_master_clean.csv`.
| Column | Type | Notes |
|---|---|---|
| train_id | BIGINT PK | matches dataset `train_id` exactly (not a surrogate key) |
| train_name | VARCHAR(255) NOT NULL | |
| train_type | VARCHAR(32) NOT NULL | enum, see §5.3 |
| train_category | VARCHAR(32) NOT NULL | enum, see §5.3 |
| railway_zone | VARCHAR(8) NOT NULL | enum, see §5.3 |
| created_at | TIMESTAMPTZ | |

### 8.4 `routes` — static/reference
A route is the (origin_station, destination_station) pair a train notionally runs — the master snapshot gives one origin/destination-ish pair per train only implicitly (via `current_station`/`previous_station`/`next_station` chains across the sequential file for that `train_id`). Build one `route` per distinct train journey found in the sequential simulation.
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| origin_station | VARCHAR(10) FK → stations.code | first `current_station` seen for this train's earliest sequence step |
| destination_station | VARCHAR(10) FK → stations.code | last `current_station`/`next_station` seen for this train's final sequence step |
| direction | VARCHAR(4) | Up/Down, from dataset |
| scheduled_distance_km | NUMERIC(10,2) | from dataset |
| scheduled_journey_time_hrs | NUMERIC(6,2) | from dataset |
| created_at | TIMESTAMPTZ | |

### 8.5 `route_stations` — static/reference (ordered stops for a route)
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| route_id | BIGINT FK → routes.id NOT NULL | |
| station_code | VARCHAR(10) FK → stations.code NOT NULL | |
| stop_order | INT NOT NULL | derived from ordering of distinct `current_station` per `sequence_id` by `sequence_step`/`timestamp` |
| scheduled_halt_time_mins | INT | from `station_halt_time_mins` |
| UNIQUE(route_id, stop_order) | | |

### 8.6 `route_segments` — static/reference (the graph, mirrored for the frontend's route map)
Directly from `railway_graph_edges.csv` — **do not** treat this as validated official topology; it is inferred from observed transitions.
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| from_station | VARCHAR(10) FK → stations.code | |
| to_station | VARCHAR(10) FK → stations.code | |
| distance_km | NUMERIC(10,3) | median observed distance, from dataset |
| observed_count | INT | from dataset, informational only |
| UNIQUE(from_station, to_station) | | |

### 8.7 `train_schedules` — static/reference, per route-station
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| train_id | BIGINT FK → trains.train_id | |
| route_station_id | BIGINT FK → route_stations.id | |
| scheduled_arrival_time | TIMESTAMPTZ | dataset `scheduled_arrival_time` (note: dataset year is fixed/synthetic, e.g. 2025-01-02 — treat as a template time-of-day pattern for the prototype, not a real calendar date; see §37) |
| scheduled_departure_time | TIMESTAMPTZ | |

### 8.8 `train_positions` — time-series, live/current movement
The record the replay engine (or, later, a real feed) writes on every tick; the "current state" row consumed to build ML requests.
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| sequence_id | VARCHAR(20) | dataset `sequence_id`, retained for replay traceability only |
| sequence_step | INT | |
| observed_at | TIMESTAMPTZ NOT NULL | from dataset `timestamp` (or wall-clock at replay time — see §10) |
| current_station | VARCHAR(10) FK → stations.code | |
| previous_station | VARCHAR(10) | |
| next_station | VARCHAR(10) | |
| latitude, longitude | DOUBLE PRECISION | |
| current_location_km | NUMERIC(10,2) | |
| current_speed_kmh | NUMERIC(6,2) | |
| current_delay_mins | NUMERIC(8,2) | |
| distance_remaining_km | NUMERIC(10,2) | |
| movement_status | VARCHAR(32) | enum, §5.3 |
| stoppage_duration_mins | INT | |
| raw_snapshot | JSONB NOT NULL | the **full** feature snapshot (all 78 XGBoost fields) as sent to `/predict` — stored so predictions are reproducible/debuggable without re-deriving from the replay stream |
| created_at | TIMESTAMPTZ | |
Index: `(train_id, observed_at DESC)`.

### 8.9 `train_running_status` — transactional, one row per train (current operational summary)
A denormalized "latest" view kept in sync from `train_positions` for fast reads.
| Column | Type | Notes |
|---|---|---|
| train_id | BIGINT PK FK → trains.train_id | |
| current_position_id | BIGINT FK → train_positions.id | |
| journey_status | VARCHAR(16) | enum, §5.3 |
| last_prediction_id | BIGINT FK → predictions.id NULL | |
| last_synced_at | TIMESTAMPTZ | backs the "Last synchronized: HH:MM" offline banner |
| updated_at | TIMESTAMPTZ | |

### 8.10 `predictions` — prediction-related, transactional
Only fields the ML implementation actually produces (§4.2), plus orchestration metadata. No invented fields.
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| position_id | BIGINT FK → train_positions.id NOT NULL | the input snapshot this prediction was computed from |
| model_used | VARCHAR(24) NOT NULL | `xgboost` (from `/predict`) or `hybrid_gnn_gru`/`gru` (from `/predict/temporal`, if enabled — see §37) |
| current_delay_mins | NUMERIC(8,2) | echoed from ML response |
| predicted_additional_delay_mins | NUMERIC(8,2) | ML response |
| predicted_total_delay_mins | NUMERIC(8,2) | ML response |
| estimated_remaining_travel_mins | NUMERIC(8,2) | ML response |
| eta | TIMESTAMPTZ NOT NULL | ML response |
| eta_lower | TIMESTAMPTZ | ML response `eta_interval.lower` |
| eta_upper | TIMESTAMPTZ | ML response `eta_interval.upper` |
| delay_reason | TEXT | ML response |
| delay_reason_confidence | NUMERIC(4,3) | ML response, 0–1 |
| propagation_probability | NUMERIC(5,4) | ML response |
| propagation_risk | VARCHAR(8) | ML response: LOW/MEDIUM/HIGH |
| ml_metrics_snapshot | JSONB | copy of `/metrics` at prediction time, for auditability of accuracy claims — **internal use only, never surfaced to end users as a real-world accuracy guarantee** |
| requested_at, responded_at | TIMESTAMPTZ | for latency/timeout observability |
| created_at | TIMESTAMPTZ | |
Index: `(train_id, created_at DESC)`.

### 8.11 `prediction_history`
Not a separate table — `predictions` **is** the history table (append-only, never updated in place); "latest" is just `train_running_status.last_prediction_id` or `MAX(created_at)`. This avoids duplicating storage per the PRD's "avoid overengineering" instruction.

### 8.12 `tracked_trains` — user-specific
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK → users.id NOT NULL | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| target_station_code | VARCHAR(10) FK → stations.code | the "destination I care about" — needed for smart alarms and the "will I make my connection" chat use case; nullable (defaults to route destination) |
| created_at | TIMESTAMPTZ | |
| UNIQUE(user_id, train_id) | | ON DELETE CASCADE from users and trains |

### 8.13 `notification_preferences` — user-specific
| Column | Type | Notes |
|---|---|---|
| user_id | BIGINT PK FK → users.id | |
| delay_alerts | BOOLEAN DEFAULT TRUE | |
| eta_change_alerts | BOOLEAN DEFAULT TRUE | |
| approaching_destination_alerts | BOOLEAN DEFAULT TRUE | |
| min_delay_change_threshold_mins | INT DEFAULT 5 | avoids notification spam on 1-minute ETA jitter |
| updated_at | TIMESTAMPTZ | |

### 8.14 `notifications` — user-specific, transactional
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK → users.id NOT NULL | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| type | VARCHAR(32) NOT NULL | `delay_increase`, `eta_change`, `approaching_destination`, `alarm_triggered` |
| title, body | TEXT NOT NULL | |
| is_read | BOOLEAN DEFAULT FALSE | |
| related_prediction_id | BIGINT FK → predictions.id NULL | |
| created_at | TIMESTAMPTZ | |
Index: `(user_id, is_read, created_at DESC)`.

### 8.15 `smart_alarms` — user-specific
| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK → users.id NOT NULL | |
| train_id | BIGINT FK → trains.train_id NOT NULL | |
| target_station_code | VARCHAR(10) FK → stations.code NOT NULL | "alert me before arrival at X" |
| offset_minutes | INT NOT NULL | one of 5/10/15/20/30 per the UI, but store as free INT |
| auto_adjust | BOOLEAN DEFAULT TRUE | maps to the UI's "Automatically adjust alarm with ETA" toggle |
| is_active | BOOLEAN DEFAULT TRUE | |
| last_evaluated_eta | TIMESTAMPTZ | so re-evaluation can detect a meaningful change |
| triggered_at | TIMESTAMPTZ NULL | |
| created_at, updated_at | TIMESTAMPTZ | |
Index: `(train_id, is_active)`.

### 8.16 Table classification summary
- **Static/reference:** `stations`, `trains`, `routes`, `route_stations`, `route_segments`, `train_schedules`
- **Time-series:** `train_positions`
- **Transactional:** `train_running_status`, `notifications`, `smart_alarms`
- **Prediction-related:** `predictions`
- **User-specific:** `users`, `tracked_trains`, `notification_preferences`, `notifications` (also transactional), `smart_alarms` (also transactional)

Cascade behavior: all `user_id` FKs → `ON DELETE CASCADE`. `train_id`/`station_code` FKs → `ON DELETE RESTRICT` (reference data shouldn't silently vanish under live data).

---

## 9. Dataset → Database Mapping

| Dataset Field | Meaning | Backend Table | Stored? | Used by ML? | Notes |
|---|---|---|---|---|---|
| `train_id, train_name, train_type, train_category, railway_zone` | train identity | `trains` | Yes | Yes (as features) | Static |
| `current_station, previous_station, next_station` | position | `train_positions` (+ `stations`, `route_stations`) | Yes | Yes | Station codes must exist in the 30-node graph |
| `latitude, longitude, current_location_km` | position | `train_positions` | Yes | Yes | |
| `distance_to_next_station_km, distance_from_previous_station_km, distance_remaining_km` | position | `train_positions` | Yes | Yes | |
| `scheduled_arrival_time, scheduled_departure_time, scheduled_journey_time_hrs, scheduled_segment_travel_time_mins, scheduled_distance_km, station_halt_time_mins` | schedule | `train_schedules`/`routes`/`route_stations` | Yes | Some (`scheduled_journey_time_hrs`, `scheduled_segment_travel_time_mins`, `scheduled_distance_km`, `station_halt_time_mins` are model features; `scheduled_arrival_time`/`scheduled_departure_time` are excluded time columns) | Split by concern |
| `timestamp` | observation time | `train_positions.observed_at` | Yes | Used only to derive `hour`/`month`/etc, then excluded as a raw feature | |
| `current_speed_kmh, current_delay_mins` | live state | `train_positions` | Yes | Yes | Core signal |
| `movement_status, stoppage_duration_mins` | live state | `train_positions` | Yes | Yes | |
| `previous_station_delay, delay_2/3_stations_ago` | delay history | `train_positions.raw_snapshot` (JSONB) | Yes (inside snapshot; not separately columned) | Yes | Cheaper as JSON than 3 more columns |
| `historical_avg_train_delay, historical_avg_station_delay, historical_avg_section_delay, historical_on_time_pct, historical_segment_travel_time_mins` | historical aggregates | Computed by backend from the seeded dataset (see §14), cached, embedded in `raw_snapshot` | Yes | Yes (all but the last) | These are precomputed in the source data; for MVP, seed them verbatim per train/station/section rather than recomputing |
| `train_ahead_id, train_ahead_delay_mins, train_ahead_speed_kmh, train_ahead_distance_km, number_of_trains_ahead, distance_between_trains_km, headway_mins, same_track, same_section, section_congestion_index, section_capacity_pct` | congestion | `raw_snapshot` (JSONB) | Yes | Yes | Needed only as ML inputs; not independently queried, so JSONB is sufficient (avoids 12 extra narrow columns) |
| `delay_reason_code, delay_reason, reason_severity, reason_start_time, reason_duration_mins, confirmed_unconfirmed_reason, reason_source, delay_reason_category` | dataset-labelled delay cause | Not stored as live input; **the dataset's own reason fields are historical/label data**, distinct from the ML's own `explain_delay` output which is what predictions.delay_reason stores | No (except inside `raw_snapshot` for replay fidelity) | `delay_reason_code`/`reason_severity`/etc are model features (not `delay_reason`/`delay_reason_category` text, which are explicitly dropped) | Do not confuse the dataset's ground-truth reason with the model's own predicted reason |
| `temperature_celsius, rainfall_mm, humidity_pct, wind_speed_kmh, visibility_meters, weather_condition, weather_severity` | weather | `raw_snapshot` | Yes | Yes | For MVP, sourced from dataset replay, not the live Open-Meteo call; the ML's own `/weather` endpoint is a *separate*, real, on-demand feature (§4.6), not a training input pipeline |
| `track_condition, track_vibration_hz, rail_wear_mm, speed_restriction_kmh, track_maintenance_active, signal_status, bearing_temperature_c, axle_temperature_c, brake_condition, brake_pressure_bar, brake_pad_wear_pct, maintenance_status, days_since_maintenance, sensor_health, failure_type, failure_severity` | rolling-stock/track health | `raw_snapshot` | Yes | Yes | |
| `hour, day_of_week, month, season, is_weekend_holiday, is_peak_hour` | time context | Derived at request time by backend from `observed_at`; also embedded in `raw_snapshot` for exact reproducibility | Yes | Yes | |
| `journey_status` | journey state | `train_running_status.journey_status` | Yes | Yes — it is one of the 78 XGBoost features (§12.1) | |
| `sequence_id, sequence_step, data_source, split` | simulation bookkeeping | `train_positions.sequence_id/sequence_step` | Yes (2 of 4; `data_source`/`split` are training-only, not stored) | No (explicitly excluded from ML features) | Replay traceability only |
| `estimated_remaining_travel_time_mins` | **live input feature** | `raw_snapshot` | Yes | **Yes** — required XGBoost feature | Confusingly named like a target; it is not one. Must be computed/replayed as a genuine live estimate |
| `remaining_travel_time_mins` | **derived output field**, excluded from features | Not stored as live input | No | No (explicitly dropped: `XGB_DERIVED_OUTPUTS`) | Do not confuse with the field above |
| `predicted_eta, actual_arrival_time` | **leakage/target** | Not stored as live input (only ever appear historically inside seed data for backtesting, never sent to `/predict`) | No | No (dropped) | |
| `future_additional_delay_mins, future_delay_20m, propagation_delay_mins, propagation_occurred, propagation_probability` | **leakage/targets** | Not stored as live input | No (may be retained in a separate `analytics`/offline schema for backtesting model quality — out of MVP scope) | No (all dropped) | See §5.6 |
| `railway_graph_nodes.*` | graph | `stations.graph_node_index` | Yes | Yes (loaded ML-side from its own bundled copy — backend's copy is for the frontend map only) | |
| `railway_graph_edges.*` | graph | `route_segments` | Yes | Yes (ML-side, same note) | |

---

## 10. Railway Graph Integration

- **Backend needs the graph in PostgreSQL?** Yes, but only to power the frontend's route-map/route-list feature (`route_segments`, seeded once from `railway_graph_edges.csv`). The backend does **not** need to run any graph algorithm over it.
- **Should the graph be passed to the ML service per request?** No — the ML service already loaded its own copy (`graph_features.npz`) at startup; the backend only ever needs to send the plain `current_station` code, and the ML service does its own node lookup (`node_idx.get(station, 0)`, defaulting to node 0 for unknown stations — a real risk if the backend ever sends a station code outside the 30-node set; validate before calling, see §21).
- **Loaded at startup or queried dynamically?** Backend: load `stations` + `route_segments` into an in-process cache at startup (30 nodes / 574 edges is trivial), refresh only on redeploy/reseed — this is static reference data with no live update path in the current dataset.
- The backend must **not** rebuild the GNN's normalized adjacency matrix, GCN layers, or any graph neural network logic — that is entirely ML-service-owned.

---

## 11. Replay/Simulation Architecture

The dataset ships no live railway feed and the ML package's `live_replay.py` is a demonstration generator, not a service. The backend must own a real replay engine.

### 11.1 Design
```
dynamicrail_sequential_simulation.csv (seeded once into train_positions
 at import time, OR streamed row-by-row at replay time — see below)
        ↓
Backend Replay Engine (background job, per active/tracked train)
        ↓
New train_positions row (current state) + train_running_status update
        ↓
Prediction orchestration (§13) → ML /predict
        ↓
predictions row + train_running_status.last_prediction_id
        ↓
Notification/alarm evaluation (§18, §19)
        ↓
Frontend polls or is pushed the update
```

### 11.2 Two supportable modes (pick one for MVP, both are cheap to support given the same table shape)
1. **Pre-seeded, timestamp-driven replay (recommended for MVP):** import all 30,000 rows into `train_positions` at seed time (or a dedicated `replay_source` table), then a background job advances a "virtual clock" per `sequence_id`, exposing whichever row's `sequence_step` matches the current virtual time as the train's "current" position, and copying it into `train_running_status` + firing a prediction. This makes replay pausable/resumable/resettable trivially (it's just moving a per-sequence pointer), matching the UI's implied need for a demo-friendly, controllable simulation.
2. **Streamed generator (mirrors `live_replay.py` literally):** a background task iterates each sequence's rows with a fixed delay between steps and writes directly into `train_positions`. Simpler to write, harder to pause/rewind cleanly. Not recommended beyond a first spike.

### 11.3 Replay/Simulation API (only if the frontend needs manual control — the UI mockup does not show simulation controls, so this is offered as a `SHOULD HAVE`, not `MUST HAVE`, see §33)
| Method | Path | Purpose |
|---|---|---|
| POST | `/replay/start` | begin advancing the virtual clock (global or per `sequence_id`) |
| POST | `/replay/pause` | freeze the virtual clock |
| POST | `/replay/resume` | resume |
| POST | `/replay/reset` | rewind all sequences to step 0 |
| GET | `/replay/status` | current virtual time / step per sequence, running/paused |

### 11.4 Clear separation from a future real feed
`RailwayDataProvider` (an interface with `get_current_state(train_id) -> dict`) has exactly one concrete implementation today: `ReplayProvider`, backed by the seeded sequential dataset. A future `LiveRailwayProvider` would implement the same interface against a real telemetry source, and nothing else in the backend (ML orchestration, persistence, notifications) needs to change. **No real railway API is invented here** — this is purely the seam for later.

---

## 12. ML Service Integration Contract

### 12.1 Backend → ML: `POST /predict`

- **Endpoint:** `POST {ML_SERVICE_URL}/predict`
- **Auth:** none (internal network call only; never proxy this route directly to the internet)
- **Headers:** `Content-Type: application/json`
- **Body:** `{"data": { ...78 named fields, see below... }, "history": []}` (`history` may be omitted/empty for this route)
- **All 78 fields are required** (the fitted `ColumnTransformer` will raise if any are missing, surfaced by the ML service as HTTP 400):

  `train_name, train_type, train_category, railway_zone, latitude, longitude, current_station, previous_station, next_station, section_id, track_id, distance_to_next_station_km, distance_from_previous_station_km, direction, scheduled_journey_time_hrs, scheduled_segment_travel_time_mins, scheduled_distance_km, station_halt_time_mins, current_location_km, current_speed_kmh, current_delay_mins, movement_status, stoppage_duration_mins, distance_remaining_km, previous_station_delay, delay_2_stations_ago, delay_3_stations_ago, historical_avg_train_delay, historical_avg_station_delay, historical_avg_section_delay, historical_on_time_pct, historical_segment_travel_time_mins, train_ahead_delay_mins, train_ahead_speed_kmh, train_ahead_distance_km, number_of_trains_ahead, distance_between_trains_km, headway_mins, same_track, same_section, section_congestion_index, delay_reason_code, reason_severity, reason_duration_mins, confirmed_unconfirmed_reason, reason_source, temperature_celsius, rainfall_mm, humidity_pct, wind_speed_kmh, visibility_meters, weather_condition, weather_severity, track_condition, track_vibration_hz, rail_wear_mm, speed_restriction_kmh, track_maintenance_active, signal_status, section_capacity_pct, bearing_temperature_c, axle_temperature_c, brake_condition, brake_pressure_bar, brake_pad_wear_pct, maintenance_status, days_since_maintenance, sensor_health, failure_type, failure_severity, hour, day_of_week, month, season, is_weekend_holiday, is_peak_hour, journey_status, estimated_remaining_travel_time_mins`

  Plus, **recommended but not model-required** (used by the handler's own arithmetic, not the pipeline): `timestamp` (ISO string; defaults to server "now" if omitted — but omitting it means the ETA is computed from the *wrong* clock, so the backend should always send it), and `train_ahead_id` is accepted but unused by the feature pipeline (it's in `XGB_DROP`) — safe to omit or include.

  **Never include:** `predicted_eta, actual_arrival_time, future_additional_delay_mins, future_delay_20m, propagation_delay_mins, propagation_occurred, propagation_probability, remaining_travel_time_mins, delay_reason, delay_reason_category, sequence_id, sequence_step, split, data_source` — either they're dropped server-side anyway or (worse) they're targets the backend should never know at prediction time in a real deployment.

- **Data types:** exactly as typed in §5.1/§8.10 — numeric fields as JSON numbers (not strings), booleans as JSON booleans (`is_weekend_holiday`, `is_peak_hour`), categorical fields as their exact enum strings from §5.3 (unrecognized categories are safely one-hot-ignored by the pipeline, not rejected, but will degrade prediction quality).

### 12.2 ML → Backend: `POST /predict` response
```json
{
  "current_delay_mins": 12.0,
  "predicted_additional_delay_mins": 8.42,
  "predicted_total_delay_mins": 20.42,
  "estimated_remaining_travel_mins": 34.11,
  "eta": "2026-09-11T21:47:00",
  "eta_interval": {"lower": "2026-09-11T21:46:24", "upper": "2026-09-11T21:47:36"},
  "delay_reason": "Likely contributors: high section congestion, multiple trains ahead.",
  "delay_reason_confidence": 0.66,
  "propagation": {"probability": 0.412, "risk": "MEDIUM"}
}
```
No `model_version`, no per-field confidence bounds beyond the single MAE-based ETA interval, no explicit "confidence %" field — **the backend must not invent one**; if the UI needs a single confidence percentage (§3.4), it should be explicitly derived and labelled as `delay_reason_confidence × 100`, or the product should change the UI copy. This is flagged, not silently resolved, in §36.

### 12.3 Backend → ML: `POST /predict/temporal`
`{"data": {}, "history": [ ...≥6 dicts, most-recent-last, each containing all 35 NEURAL_NUMERIC_FEATURES plus "current_station"... ]}`. Response: `{"gru_predicted_additional_delay_mins": float, "hybrid_gnn_gru_predicted_additional_delay_mins": float}` — no ETA, no interval, no reason. If the backend chooses to surface this (see §37), it must independently apply the same ETA-combination arithmetic as §4.2 steps 4–6, clearly labelled as a distinct `model_used` value so it's never confused with the XGBoost-backed `/predict` result.

### 12.4 Backend → ML: `POST /chat`
`{"query": "<user free text>", "prediction": <the full stored /predict response JSON for that train>, "language": "en"}` → `{"language": "en", "response": "<plain text>"}`. The backend must pass the **exact** last-stored prediction object (not a reshaped/renamed version) since `chatbot_reply` reads specific keys (`delay_reason`, `current_delay_mins`, `predicted_additional_delay_mins`, `eta`, `eta_interval.lower/upper`, `propagation.risk/probability`) verbatim.

### 12.5 `GET /weather`, `GET /maps/directions`, `GET /languages`
Simple passthroughs — the backend may proxy these directly (adding auth/rate-limiting) or let the frontend call... **no**, the ML service has no auth and should not be internet-facing, so the backend must proxy all three, unchanged in shape, behind its own authenticated routes.

### 12.6 Errors, from the ML service itself
- `400` from `/predict` on malformed/incomplete `data` (broad exception message, not machine-parseable — the backend should catch this and translate to its own structured error, §23).
- `400` from `/predict/temporal` if `len(history) < 6`.
- `502`-style failure possible from `/weather` if Open-Meteo is unreachable (ML service raises `HTTPException(502, str(e))`).
- No documented rate limits, no documented auth failures (there is no auth).

---

## 13. Prediction Flow

```
Replay engine writes new train_positions row (current state)
        ↓
Backend builds the 78-field ML request from:
   - static reference (trains, stations) — rarely changes
   - the new position row (speed, delay, station, weather, health, congestion...)
   - historical aggregates seeded from the dataset (avg delays, on-time %)
        ↓
Backend calls ML POST /predict  (timeout: 5s recommended; retry once on timeout only, not on 400)
        ↓
Backend validates the response shape (required keys present, eta parses, no NaN/None on required numerics)
        ↓
Backend inserts a new predictions row (always append — never overwrite)
        ↓
Backend updates train_running_status.last_prediction_id, last_synced_at
        ↓
Backend recomputes user-facing derived fields (§14: "vs schedule" delta, staleness flag)
        ↓
Response returned to whichever client call (or replay-triggered background call) initiated it
        ↓
Notification/alarm evaluation runs against the new prediction (§18/§19)
```

**Trigger types:**
- **Automatic:** every replay tick for actively-tracked trains (and, optionally, all trains within an active session's search results) — recommended interval: every simulated 10-minute step (i.e., whenever the replay engine advances that train's `sequence_step`), not faster, since the dataset itself has no finer granularity.
- **Manual:** `GET /trains/{id}/status` or `POST /trains/{id}/predict` can force a fresh prediction on demand (e.g., user pulls to refresh) using the *current* stored position, without waiting for the next replay tick, capped by a short min-interval (e.g., 30s) to avoid hammering the ML service.

**Duplicate/stale handling:** a prediction is considered **stale** if its `position_id` is no longer the train's latest position (i.e., a newer tick has occurred since); the API should mark stale predictions with a `stale: true` flag rather than deleting them (history must be preserved). A prediction request for a position that already has one is a no-op (return the existing row) unless `force=true`.

**Failure handling:** ML timeout/`502`/`400` → do not fail the whole train-status request; fall back to the last successfully stored prediction, mark the response `degraded: true`, and surface it to the frontend as the "offline cached telemetry" state the UI mockup already anticipates (§3.1, §3.6). Retry policy: one retry on network-level timeout only; no retry on a 400 (it will fail identically — log and alert instead, since a 400 means the backend built a malformed feature payload, which is a backend bug, not a transient failure).

**Prediction versioning:** `predictions.model_used` plus `ml_metrics_snapshot` (a copy of `/metrics` at call time) gives enough versioning for the MVP without a dedicated model-registry table.

---

## 14. ETA Calculation

**The ML model already returns the final ETA and its interval — the backend must not recompute it.** The only backend-side arithmetic is *display* math:
- `delta_vs_schedule = predictions.eta − train_schedules.scheduled_arrival_time` (the "+33 min vs Schedule" badge).
- `eta_delta_from_previous = predictions.eta − previous predictions.eta for same train` (the transition banner's "(+12 min delta)"), computed by comparing the two most recent rows in `predictions` for that train.
- **Staleness:** if `now() − predictions.created_at > N minutes` (recommend `N = 2× the replay tick interval`, i.e. 20 minutes for a 10-minute-tick simulation) and no newer replay tick has occurred, flag `eta_stale: true` in the API response rather than silently serving an old number.
- **Cancelled/terminated trains:** if `movement_status = 'Terminated'` or `journey_status = 'Completed'`, do not call `/predict` again for that train; return the last real prediction (or the dataset's own `actual_arrival_time` if seeded for backtesting) with `journey_status` surfaced plainly instead of a live ETA.

---

## 15. REST API Specification

Base path: `/api/v1`. All authenticated routes require `Authorization: Bearer <JWT>`.

### 15.1 Authentication
| Method | Path | Auth | Purpose | Request | Response | Errors |
|---|---|---|---|---|---|---|
| POST | `/auth/register` | none | create account | `{email, password, full_name?}` | `201 {id, email, full_name}` | 409 email exists, 422 validation |
| POST | `/auth/login` | none | issue JWT | `{email, password}` | `200 {access_token, token_type:"bearer", expires_in}` | 401 invalid credentials |
| GET | `/auth/me` | required | current user | — | `200 {id, email, full_name, preferred_language}` | 401 |

### 15.2 Trains
| Method | Path | Auth | Purpose | Request | Response | Errors |
|---|---|---|---|---|---|---|
| GET | `/trains?query=` | optional | search by number or name (UI: "Enter Train Number or Train Name") | query param `query` | `200 [{train_id, train_name, train_type, origin_station, destination_station}]` | 200 empty array if none |
| GET | `/trains/{train_id}` | optional | train details | — | `200 {train_id, train_name, train_type, train_category, railway_zone, route: {...}}` | 404 |
| GET | `/trains/{train_id}/status` | optional | current live status + latest prediction (drives the Live Train Prediction card, §3.4) | — | `200 {position: {...}, prediction: {...}, delta_vs_schedule_mins, eta_stale, degraded}` | 404 train, 200 with `degraded:true` on ML failure |
| POST | `/trains/{train_id}/predict` | required | force a fresh prediction (manual refresh) | `{}` | `200 <same shape as GET status prediction>` | 404, 429 if called faster than the min-interval, 502 if ML unreachable and no cached prediction exists |
| GET | `/trains/{train_id}/route` | optional | ordered stops for the route map | — | `200 {stations: [{code, stop_order, scheduled_arrival_time}], segments: [{from,to,distance_km}]}` | 404 |

### 15.3 Stations
| Method | Path | Auth | Purpose | Response |
|---|---|---|---|---|
| GET | `/stations?query=` | optional | search/list (30-station universe) | `200 [{code, display_name}]` |
| GET | `/stations/{code}` | optional | station detail | `200 {code, display_name, graph_node_index}` |

### 15.4 Routes
| Method | Path | Auth | Purpose | Response |
|---|---|---|---|---|
| GET | `/routes/{route_id}` | optional | full route detail | `200 {origin, destination, stations: [...], segments: [...]}` |

### 15.5 Tracking (favourites)
| Method | Path | Auth | Purpose | Request | Response |
|---|---|---|---|---|---|
| GET | `/tracking` | required | "Your Recent Trains" list (§3.7) | — | `200 [{train_id, train_name, origin, destination, latest_prediction: {...}}]` |
| POST | `/tracking` | required | track a train | `{train_id, target_station_code?}` | `201 {id, train_id}` |
| DELETE | `/tracking/{id}` | required | untrack | — | `204` |

### 15.6 Predictions
| Method | Path | Auth | Purpose | Response |
|---|---|---|---|---|
| GET | `/trains/{train_id}/predictions?limit=20` | optional | prediction history (for the delta/transition banner, §3.3) | `200 [{...prediction fields..., created_at}]` |
| POST | `/predictions/chat` | required | AI assistant modal (§3.6) — `{train_id, query, language?}` → backend loads the latest stored prediction and forwards to ML `/chat` | `200 {response}` |

### 15.7 Notifications
| Method | Path | Auth | Purpose | Response |
|---|---|---|---|---|
| GET | `/notifications?unread_only=` | required | list (badge count in nav, §3.1) | `200 [{id, type, title, body, is_read, created_at}]` |
| PATCH | `/notifications/{id}/read` | required | mark read | `200 {id, is_read:true}` |
| PATCH | `/notifications/preferences` | required | update prefs | request = `notification_preferences` fields |

### 15.8 Smart Alarms
| Method | Path | Auth | Purpose | Request | Response |
|---|---|---|---|---|---|
| GET | `/alarms` | required | list user's alarms | — | `200 [{...}]` |
| POST | `/alarms` | required | create (§3.5) | `{train_id, target_station_code, offset_minutes, auto_adjust}` | `201 {...}` |
| PATCH | `/alarms/{id}` | required | update offset/auto_adjust/active | partial body | `200 {...}` |
| DELETE | `/alarms/{id}` | required | delete | — | `204` |

### 15.9 Replay/Simulation (`SHOULD HAVE`, §11.3)
`POST /replay/start`, `POST /replay/pause`, `POST /replay/resume`, `POST /replay/reset`, `GET /replay/status` — admin/demo-only, should be gated behind a simple admin flag or disabled in a "production-like" deployment mode.

### 15.10 Health
| Method | Path | Auth | Purpose | Response |
|---|---|---|---|---|
| GET | `/health` | none | backend liveness | `200 {status:"ok", db:"ok"}` |
| GET | `/health/ml` | none or required | ML service connectivity (proxies ML `/health`) | `200 {ml_status:"ok", models:[...]}` or `503` |

### 15.11 Auxiliary passthroughs
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/weather?lat=&lon=` | optional | proxy ML `/weather` |
| GET | `/directions?origin=&destination=&travelmode=` | optional | proxy ML `/maps/directions` |
| GET | `/languages` | none | proxy ML `/languages` |

---

## 16. Pydantic Schemas (representative set — expand per endpoint as implemented)

**Request models** (`schemas/requests.py`): `UserRegisterRequest`, `UserLoginRequest`, `TrackTrainRequest{train_id, target_station_code: Optional[str]}`, `CreateAlarmRequest{train_id, target_station_code, offset_minutes: Literal[5,10,15,20,30], auto_adjust: bool=True}`, `UpdateAlarmRequest` (all fields optional), `ChatRequest{train_id, query: str, language: str="en"}`, `NotificationPreferencesRequest`.

**Response models** (`schemas/responses.py`): `UserResponse`, `TokenResponse`, `TrainSummaryResponse`, `TrainDetailResponse`, `TrainStatusResponse{position, prediction, delta_vs_schedule_mins, eta_stale: bool, degraded: bool}`, `PredictionResponse` (mirrors §12.2 field-for-field, plus `id, train_id, created_at, model_used, stale`), `StationResponse`, `RouteResponse`, `NotificationResponse`, `AlarmResponse`, `HealthResponse`.

**Database models** (`models/*.py`, SQLAlchemy ORM): one class per table in §8 — never returned directly from an endpoint; always mapped to a response schema.

**ML request models** (`clients/ml_schemas.py`): `MLPredictRequest{data: Dict[str, Any], history: List[Dict] = []}` mirroring the ML service's own `PredictRequest`, `MLTemporalRequest`, `MLChatRequest{query: str, prediction: Dict, language: str="en"}` — kept as thin passthrough models, not re-validated field-by-field beyond presence, since the ML service owns its own schema.

**ML response models:** `MLPredictResponse` (exact shape of §12.2, with a nested `EtaInterval{lower, upper}` and `Propagation{probability, risk}`), `MLTemporalResponse{gru_predicted_additional_delay_mins, hybrid_gnn_gru_predicted_additional_delay_mins}`, `MLChatResponse{language, response}`.

---

## 17. Authentication & Authorization

- **JWT** (e.g. `python-jose` or `pyjwt`), HS256 for MVP (RS256 if multi-service verification is ever needed — not required here).
- Password hashing: `bcrypt` via `passlib`.
- Access token expiry: 60 minutes (configurable); no refresh-token flow required for MVP (`SHOULD HAVE`: refresh tokens, §33).
- `get_current_user` FastAPI dependency decodes the bearer token, loads the user, 401 on invalid/expired.
- **Ownership checks:** every `tracking`, `alarms`, `notifications` endpoint filters by `current_user.id` at the query level — never trust a client-supplied `user_id`.
- Public/optional-auth endpoints (`/trains`, `/stations`, `/trains/{id}/status`) work unauthenticated for anonymous browsing (matches the frontend's home page being usable without a visible login step), but personalization (tracking, alarms) always requires auth.
- Secrets (`JWT_SECRET`, DB credentials, ML service URL if it ever needs a key) come only from environment variables, never hardcoded (§20).

---

## 18. Notifications

**Triggers** (evaluated right after a new `predictions` row is inserted, for every train with at least one active tracker or alarm):
- `delay_increase`: `predicted_total_delay_mins` increased by ≥ `notification_preferences.min_delay_change_threshold_mins` since the previous prediction for that train.
- `eta_change`: `eta` moved by ≥ the same threshold (in minutes) since the previous prediction.
- `approaching_destination`: current position's `distance_remaining_km` to the user's tracked/target station drops under a small fixed threshold (e.g., 15 km) — **no exact frontend-specified threshold exists; flagged as an assumption**, §37.
- `alarm_triggered`: see §19.

**Design:** `notifications` rows are created directly (no separate delivery/queue infra — "delivery abstraction" here means simply "in-app list," since no push/SMS/email provider is specified anywhere in the three artifacts; adding one is `FUTURE`, §33). Duplicate prevention: do not create a second `delay_increase`/`eta_change` notification for the same train within a cooldown window (e.g., 10 minutes) even if multiple predictions land in that window — keyed on `(user_id, train_id, type)` with a `created_at` cooldown check, not a DB unique constraint (since legitimate repeats are allowed after the cooldown).

---

## 19. Smart ETA Alarm

```
User selects train + target_station_code + offset_minutes + auto_adjust
        ↓
Backend stores a smart_alarms row (is_active=true)
        ↓
On every new prediction for that train:
   if target_station_code is on this train's remaining route AND is_active:
       compute eta_at_target (for MVP: same as predictions.eta if target
       is the final destination; if target is an intermediate stop, this
       requires a per-stop ETA the ML service does not provide today —
       see §37, flagged as an open design gap, not fabricated here)
       alarm_time = eta_at_target − offset_minutes
       if auto_adjust: update last_evaluated_eta; if NOT auto_adjust,
       the alarm_time was fixed at creation and is never recalculated
       if now() >= alarm_time and triggered_at is null:
           create a notifications row (type=alarm_triggered), set triggered_at
```
Evaluation rules: an alarm only fires once per activation (`triggered_at` gates re-firing); re-activating (`is_active` toggled back on, or `PATCH` updating `offset_minutes`) clears `triggered_at` to allow it to fire again.

---

## 20. Caching

No Redis for MVP — the data volumes (30 stations, 574 edges, ≤1,000 trains, one "latest prediction" per train) do not justify it; use in-process caching (e.g., `functools.lru_cache` or a simple in-memory dict refreshed at startup) for:
| Cached item | TTL | Invalidation |
|---|---|---|
| `stations`, `route_segments` (graph) | until process restart | reseed → restart |
| `route_stations`/`train_schedules` per train | until process restart | reseed → restart |
| ML `/health`, `/languages` | 5 minutes | time-based |
| Latest prediction per train | not cached separately — always read from `predictions` (already a fast indexed lookup); avoids a second source of truth for "latest" |

If load testing later shows DB read pressure on `train_running_status`/`predictions`, promote to Redis then — not before (`FUTURE`, §33).

---

## 21. Background Jobs

Simple `asyncio` background tasks or APScheduler jobs (no Celery/RabbitMQ — overkill for this scale):
1. **Replay tick job** — advances the virtual clock and writes new `train_positions` (§11).
2. **Prediction job** — for each train that just got a new position and has ≥1 active tracker/alarm, calls the ML client and persists a `predictions` row (§13).
3. **Alarm evaluation job** — runs immediately after each new prediction (in-process call, not a separate schedule) per §19.
4. **Notification evaluation job** — same, per §18.
5. **Cleanup job** (daily) — purge `notifications` older than e.g. 90 days marked read; **do not** purge `predictions` (history is a product feature, not log noise).

Before sending a station code to the ML service, the replay/prediction job **must validate** it is one of the 30 known graph stations (§10) — the ML service silently falls back to node index 0 for unknown stations, which would silently corrupt a GNN-based prediction rather than erroring.

---

## 22. Railway Data Provider Architecture

```
RailwayDataProvider (interface: get_current_state(train_id) -> dict)
       │
       ├── ReplayProvider   — implemented now, backed by the seeded
       │                      dynamicrail_sequential_simulation.csv
       └── LiveRailwayProvider — NOT implemented; no real railway API
                                  is documented anywhere in the supplied
                                  materials, so none is invented here.
                                  This is purely an interface seam.
```
Configuration selects the active provider via `RAILWAY_PROVIDER=replay` (env var, §24) so swapping to a real feed later is a config change plus one new class, not a rewrite.

---

## 23. Error Handling

Standard envelope for all 4xx/5xx responses:
```json
{"error": {"code": "TRAIN_NOT_FOUND", "message": "Train 12951 was not found.", "details": null}}
```
| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Pydantic validation failure |
| `UNAUTHORIZED` | 401 | missing/invalid/expired JWT |
| `FORBIDDEN` | 403 | authenticated but not the resource owner |
| `TRAIN_NOT_FOUND` / `STATION_NOT_FOUND` / `ROUTE_NOT_FOUND` / `ALARM_NOT_FOUND` | 404 | |
| `PREDICTION_UNAVAILABLE` | 200 (with `degraded:true`) or 502 if no cached fallback exists | ML call failed and no usable cached prediction exists |
| `ML_TIMEOUT` | 504 (internal) → surfaced as `PREDICTION_UNAVAILABLE` externally | ML service did not respond within timeout |
| `ML_UNAVAILABLE` | 503 (internal) → surfaced as `PREDICTION_UNAVAILABLE` externally | connection refused / ML service down |
| `STALE_STATUS` | 200 (flag, not an error) | replay hasn't ticked recently |
| `INVALID_DATASET_STATE` | 500 | e.g., a station code outside the 30-node graph reached the prediction path (should be prevented earlier, §21) |
| `INTERNAL_SERVER_ERROR` | 500 | catch-all |

---

## 24. Security

- Password hashing via `bcrypt`; never log raw passwords or tokens.
- JWT secret from `JWT_SECRET_KEY` env var, ≥32 random bytes, rotated via redeploy (no live rotation needed for MVP).
- CORS: allow only the deployed frontend origin(s) (`CORS_ALLOWED_ORIGINS` env var, comma-separated); no wildcard in anything beyond local dev.
- Input validation entirely via Pydantic; SQLAlchemy parameterized queries only (no raw string-interpolated SQL) — protects against SQL injection by construction.
- Rate limiting: not required for the hackathon MVP demo, but a simple per-IP limiter (e.g., `slowapi`) on `/auth/login` and `/trains/{id}/predict` is a cheap, worthwhile `SHOULD HAVE` (§33) to blunt brute-force/spam.
- The ML service itself has zero auth — it must be reachable only from the backend's private network (Docker network / internal URL), never exposed publicly.
- Safe logging: never log password hashes, JWT secrets, or full JWTs; log user IDs, not emails, where feasible in high-volume logs.

---

## 25. Logging & Observability

Structured logs (JSON via `structlog` or stdlib `logging` with a JSON formatter) for: auth failures (no credentials), all inbound API requests (method, path, status, latency), DB errors, every ML request/response (latency, status code, `model_used` — but never the full 78-field payload at INFO level, only at DEBUG, to avoid noisy logs), prediction failures (with the reason: timeout/400/503), replay ticks (DEBUG level only — high volume), notification/alarm dispatch failures. Never log passwords, JWT secrets, or the full feature payload at a default log level.

---

## 26. Testing Strategy

**Unit tests:** prediction-orchestration service (correct 78-field payload assembly, correct exclusion of leakage fields — assert none of the §5.6 fields ever appear in a built ML request), alarm evaluation logic (offset math, auto_adjust vs fixed, single-fire gating), notification threshold logic, ETA delta/staleness calculations (§14).

**API tests:** auth (register/login/me, wrong password, duplicate email), train search/detail/status (including the `degraded:true` path with ML mocked to fail), tracking CRUD + ownership isolation (user A cannot see/delete user B's tracked trains), notifications (mark-read, preference updates), alarms (create/update/delete/trigger simulation).

**Database tests:** FK cascade behavior (deleting a user removes their `tracked_trains`/`alarms`/`notifications`; deleting a train is restricted while positions/predictions reference it), uniqueness constraints (`tracked_trains(user_id,train_id)`, `route_segments(from,to)`), Alembic migration up/down round-trip on a throwaway DB.

**ML integration tests (ML service mocked):** successful `/predict` → correctly persisted `predictions` row; malformed ML response (missing key) → `PREDICTION_UNAVAILABLE`, not a raw 500; `/predict` timeout → one retry then graceful fallback to last cached prediction; ML service unreachable (connection refused) → same graceful path; `/predict/temporal` called with `<6` history entries → backend never sends this shape (validated before calling, so this should be untestable in practice — cover with a unit test on the client instead); stale-prediction flag correctly set when `position_id` no longer matches the train's latest position.

**Dataset/replay tests:** seeding the full dataset produces the expected row counts (1,000 trains/routes worth of reference data, 30 stations, 574 segments); replay engine advances `sequence_step` monotonically per `sequence_id` and never both restarts is a no-op double-counts a step; a full replay run of one `sequence_id` from step 0 to 29 produces exactly one `train_positions` row per step and never crosses into another train's data.

---

## 27. Backend Folder Structure

```
backend/
├── app/
│   ├── main.py
│   ├── config.py                 # env-driven Settings (pydantic-settings)
│   ├── database.py                # SQLAlchemy engine/session
│   ├── dependencies.py            # get_db, get_current_user, get_ml_client
│   │
│   ├── api/
│   │   ├── auth.py
│   │   ├── trains.py
│   │   ├── stations.py
│   │   ├── routes.py
│   │   ├── tracking.py
│   │   ├── predictions.py         # includes /predictions/chat
│   │   ├── notifications.py
│   │   ├── alarms.py
│   │   ├── replay.py              # SHOULD HAVE, gated by admin flag
│   │   ├── health.py
│   │   └── passthrough.py         # /weather, /directions, /languages
│   │
│   ├── models/                    # SQLAlchemy ORM, one file per §8 table group
│   │   ├── user.py
│   │   ├── train.py                # trains, routes, route_stations, route_segments, train_schedules
│   │   ├── position.py             # train_positions, train_running_status
│   │   ├── prediction.py
│   │   ├── tracking.py             # tracked_trains
│   │   ├── notification.py         # notifications, notification_preferences
│   │   └── alarm.py
│   │
│   ├── schemas/                    # Pydantic, split request/response (§16)
│   │   ├── requests.py
│   │   ├── responses.py
│   │   └── ml.py                   # MLPredictRequest/Response, MLChatRequest/Response, etc.
│   │
│   ├── services/
│   │   ├── prediction_service.py   # builds 78-field payload, calls ml_client, persists
│   │   ├── alarm_service.py
│   │   ├── notification_service.py
│   │   └── replay_service.py
│   │
│   ├── repositories/               # thin SQLAlchemy query wrappers per entity
│   │
│   ├── clients/
│   │   ├── ml_client.py            # POST /predict, /predict/temporal, /chat; GET /weather, /maps/directions, /languages, /health
│   │   └── railway_client.py       # RailwayDataProvider + ReplayProvider (§22)
│   │
│   ├── workers/                    # background jobs (§21)
│   │   ├── replay_tick.py
│   │   ├── prediction_job.py
│   │   └── cleanup_job.py
│   │
│   └── utils/
│       ├── security.py             # JWT, password hashing
│       └── errors.py                # error envelope (§23)
│
├── migrations/                     # Alembic
├── seed/
│   ├── seed_reference_data.py      # loads railpulse_master_clean.csv + graph CSVs
│   └── seed_replay_source.py       # loads dynamicrail_sequential_simulation.csv
├── tests/
│   ├── unit/
│   ├── api/
│   ├── db/
│   └── ml_integration/
├── scripts/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 28. Environment Configuration

`.env.example`:
```
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://dynamicrail:dynamicrail@postgres:5432/dynamicrail

# JWT
JWT_SECRET_KEY=change-me-to-a-random-32-byte-value
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# ML Service (see api.py / README — default port 8000)
ML_SERVICE_URL=http://ml-service:8000
ML_SERVICE_TIMEOUT_SECONDS=5

# Railway data provider
RAILWAY_PROVIDER=replay
REPLAY_TICK_SECONDS=10
REPLAY_SOURCE_CSV=/data/dynamicrail_sequential_simulation.csv

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:5173

# Notifications thresholds
DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS=5
APPROACHING_DESTINATION_KM=15
```
No secrets are ever hardcoded; the ML service itself needs no secrets today (no auth), so nothing further to configure there beyond its URL.

---

## 29. Docker & Local Development

```
services: frontend (future SPA, not built yet) | backend (FastAPI, :8080) |
          postgres (:5432) | ml-service (FastAPI, :8000, from the supplied
          DynamicRail_Complete_ML package, run via `uvicorn api:app`)
```
**Startup order:** `postgres` → `backend` (waits for DB healthy, then runs Alembic migrations, then seeds reference data + replay source on first boot only) → `ml-service` (independent; backend tolerates it being briefly unavailable at boot, per §13's fallback behavior) → replay/prediction background workers (start inside the backend process or as a second `backend-worker` container running the same image with a different entrypoint command).
**Ports:** backend `8080:8080`, ml-service `8000:8000` (internal-only in a real deployment — do not publish externally), postgres `5432:5432` (dev only).
**Networking:** a single Docker Compose network; backend reaches ML via `http://ml-service:8000` (service name resolution), never via a published host port in production.
**Migrations:** run automatically on backend container start (`alembic upgrade head`) — acceptable for a hackathon MVP; a `SHOULD HAVE` is moving this to an explicit init-container/job.
**Dataset seeding:** a one-time init step (idempotent — checks row counts before reseeding) loads `railpulse_master_clean.csv` + graph CSVs into reference tables and `dynamicrail_sequential_simulation.csv` into the replay source table.

---

## 30. Dataset Seeding

**Import order:** (1) `railway_graph_nodes.csv` → `stations`, (2) `railway_graph_edges.csv` → `route_segments`, (3) `railpulse_master_clean.csv` distinct trains → `trains`, (4) derive one `routes` + ordered `route_stations` + `train_schedules` per train from the **sequential** dataset (since the master file has only one snapshot per train and can't establish a full stop sequence on its own — the sequential file's `sequence_step` ordering per `sequence_id` is the actual source of stop order), (5) `dynamicrail_sequential_simulation.csv` in full → a `replay_source` staging table (not `train_positions` directly — `train_positions` should only ever contain rows the replay engine has actually "played," so the UI's implied "live" feel is preserved even though the underlying data is static).

**Duplicate handling:** `data_validation_report.json` confirms 0 duplicate rows in the shipped sequential file, so straightforward bulk insert with a unique constraint on `(sequence_id, sequence_step)` as a safety net is sufficient.

**ID mapping:** dataset `train_id` values are used verbatim as the `trains.train_id` primary key (no surrogate remapping) — this keeps replay/prediction traceability simple and matches the "do not invent identifiers" instruction.

**Prototype seed data vs production/live data:** everything in §30 is explicitly prototype seed data, sourced from a documented-synthetic dataset (`DATASET_README.md`). Do not import `sequence_splits.csv` or `metrics.json` into any user-facing table — they are ML-training artifacts, useful only for an internal `/health`-style admin view (§4.4), never for product data.

---

## 31. Frontend ↔ Backend Contract

| Frontend Feature | API | Request | Response | Database | ML |
|---|---|---|---|---|---|
| Train Search | `GET /trains?query=` | query string | list of train summaries | `trains` | — |
| Train Details / route | `GET /trains/{id}`, `GET /trains/{id}/route` | — | train + route/segments | `trains, routes, route_stations, route_segments` | — |
| Live Tracking / status card | `GET /trains/{id}/status` | — | position + latest prediction + delta/staleness | `train_positions, train_running_status, predictions` | `/predict` (indirectly, via the background prediction job) |
| Dynamic ETA | (part of the same status response) | — | `prediction.eta`, `eta_interval` | `predictions` | `/predict` |
| Future Delay | (part of status response) | — | `predicted_additional_delay_mins` | `predictions` | `/predict` |
| Confidence | (part of status response) | — | `delay_reason_confidence` (see §36 mismatch note — no dedicated confidence field exists) | `predictions` | `/predict` |
| Delay Reason | (part of status response) | — | `delay_reason` | `predictions` | `/predict` (rule engine inside the ML service) |
| Route Map | `GET /trains/{id}/route` | — | stations + segments | `route_stations, route_segments` | — (graph is ML-internal for prediction; backend's copy is display-only) |
| Notifications | `GET/PATCH /notifications*` | — | list, mark-read, preferences | `notifications, notification_preferences` | — |
| Smart Alarm | `GET/POST/PATCH/DELETE /alarms*` | offset/target/auto_adjust | alarm state | `smart_alarms` | (evaluated against `predictions`) |
| Chatbot | `POST /predictions/chat` | `{train_id, query, language}` | plain-text response | reads `predictions` for context, does not write | `/chat` |
| Weather | `GET /weather?lat=&lon=` | query | Open-Meteo passthrough | — | `/weather` |
| Authentication | `/auth/*` | credentials | JWT | `users` | — |
| Favourite/Tracked Trains | `/tracking*` | `train_id` | list/create/delete | `tracked_trains` | — |
| Replay/Simulation | `/replay/*` (SHOULD HAVE) | — | virtual-clock control | `replay_source`, drives `train_positions` | — |

---

## 32. End-to-End Feature Flows

**1. Registration/login:** `POST /auth/register` → `POST /auth/login` → store JWT client-side → `GET /auth/me` to hydrate the session.
**2. Train search:** user types in the search bar → `GET /trains?query=` → user selects a result → `GET /trains/{id}`.
**3. Train tracking:** from a train detail/status view, `POST /tracking {train_id}` → appears in `GET /tracking` ("Your Recent Trains").
**4. Live train status:** `GET /trains/{id}/status` returns the latest replay-derived position and the latest stored prediction; if none exists yet (never replayed/predicted), the backend triggers a synchronous first prediction rather than returning an empty state.
**5. Dynamic ETA prediction:** replay tick → prediction job builds the 78-field payload → `/predict` → `predictions` row persisted → available on the next `GET /trains/{id}/status` or pushed if a websocket/poll layer is added later (`FUTURE`).
**6. Prediction refresh:** manual `POST /trains/{id}/predict` (rate-limited) or automatic via the next replay tick.
**7. Prediction history:** `GET /trains/{id}/predictions?limit=` powers the "previous vs new ETA" transition banner (§3.3) by comparing the two most recent rows.
**8. Notification:** background job detects a qualifying delta after a new prediction → `notifications` row created → `GET /notifications` / nav badge count.
**9. Smart ETA alarm:** `POST /alarms` → evaluated on every subsequent prediction for that train (§19) → fires a `notifications` row of type `alarm_triggered`.
**10. Replay/simulation:** (if exposed) `POST /replay/start` begins advancing virtual time; `GET /replay/status` shows progress; this is what makes flows 4–9 actually produce changing data in a demo without a real feed.
**11. Route visualization:** `GET /trains/{id}/route` → frontend renders stations/segments (no coordinates guaranteed beyond `stations.graph_node_index` unless `latitude`/`longitude` are also surfaced from the most recent `train_positions` row for a live dot on a map).
**12. Chatbot:** modal opens (with an optional suggested prompt) → `POST /predictions/chat {train_id, query}` → backend loads latest `predictions` row for that train → forwards to ML `/chat` → returns `response` text.

---

## 33. Implementation Roadmap

**Phase 1 — Foundation:** FastAPI skeleton, PostgreSQL, SQLAlchemy, Alembic, `config.py`/env loading, Docker Compose skeleton (backend + postgres only).
**Phase 2 — Reference data:** `stations`, `trains`, `routes`, `route_stations`, `route_segments`, `train_schedules` models + seeding scripts from the master CSV + graph CSVs.
**Phase 3 — Auth:** `users`, register/login/me, JWT dependency, ownership-check pattern established.
**Phase 4 — Replay + live status:** `replay_source` staging, `train_positions`, `train_running_status`, the replay tick worker, `GET /trains/{id}/status` returning position-only data (no prediction yet).
**Phase 5 — ML integration:** `ml_client.py`, `prediction_service.py` (78-field payload assembly + leakage-field exclusion tests), `predictions` table, wire into `/trains/{id}/status`.
**Phase 6 — Frontend integration checkpoint:** confirm response shapes against whatever real frontend app is built next (the current `frontend.html` is a mockup only — this phase is where a real SPA would first consume the live API).
**Phase 7 — Tracking, notifications, alarms:** `tracked_trains`, `notification_preferences`/`notifications`, `smart_alarms`, their background evaluation jobs.
**Phase 8 — Replay control API + chatbot passthrough:** `/replay/*`, `/predictions/chat`, `/weather`, `/directions`, `/languages` passthroughs.
**Phase 9 — Testing, Docker (full stack incl. ML service), deployment, monitoring:** full test suite (§26), `docker-compose.yml` including the ML service container, logging/health endpoints finalized.

---

## 34. MVP Scope

```
User → Search Train → View Current Status → View Dynamic ETA →
View Future Delay/Prediction → View Route → Track Train → Receive ETA/Delay Alert
```

**MUST HAVE:** auth (register/login), train search/detail, replay-driven live status, `/predict` integration with full 78-field payload assembly and leakage-field exclusion, `predictions` persistence + prediction history, route/segment display, tracking (favourites), delay-increase/eta-change notifications, smart alarms (fixed + auto-adjust), graceful degradation on ML failure.

**SHOULD HAVE:** manual replay controls (`/replay/*`), chatbot passthrough (`/predictions/chat`), weather/directions passthroughs, rate limiting on auth/predict, refresh tokens, admin `/metrics` view.

**FUTURE:** `/predict/temporal` (GNN/GRU) as a user-facing alternative model, a real `LiveRailwayProvider`, push/SMS/email notification delivery, Redis caching, per-intermediate-stop ETA (§37), multi-language full UI (beyond the label set already in the ML service).

---

## 35. Definition of Done

- Backend starts via Docker Compose (backend + postgres + ml-service) with one command.
- Alembic migrations apply cleanly from empty DB.
- Seed scripts populate 30 stations, 574 segments, ~995 trains/routes, and the full 30,000-row replay source, idempotently.
- A user can register, log in, and call `GET /auth/me`.
- `GET /trains?query=` returns real seeded trains.
- `GET /trains/{id}/status` returns a real position and, after the prediction job has run at least once, a real `/predict`-backed prediction with the exact fields in §12.2.
- The 78-field ML request payload never contains any of the six leakage fields in §5.6 (covered by an automated unit test, not just manual inspection).
- Killing the ML service container causes `GET /trains/{id}/status` to return `degraded:true` with the last cached prediction, not a 500.
- Tracking a train, then untracking it, correctly updates `GET /tracking`.
- Creating a smart alarm and advancing the replay clock past the target ETA produces exactly one `alarm_triggered` notification.
- `POST /predictions/chat` returns a real reply sourced from the ML `/chat` endpoint, using the actual last stored prediction as context.
- All test suites in §26 pass in CI.
- Docker Compose brings up the full stack (including the supplied ML service package) with correct startup ordering.

---

## 36. Risks & Technical Decisions

1. **Frontend is a non-functional mockup, not a real API contract.** Every API shape in §15 is derived from what the UI *implies* it needs, not from observed request/response code, since none exists. Treat §15 as a strong first draft to validate against the real frontend once it's built, not as an immutable spec.
2. **"Prediction Confidence %" has no matching ML field.** The UI wants one number; the ML service gives `delay_reason_confidence` (confidence in the *explanation text*, not the ETA itself) and a separate propagation probability. Recommendation: relabel the UI element to "Delay Reason Confidence" and use `delay_reason_confidence × 100` verbatim, rather than inventing a synthetic ETA-confidence score the ML service doesn't produce. This is a case where, per the PRD's own rule #18, **the frontend's assumption should change**, not the backend inventing data.
3. **The mockup's example trains include two non-Indian, non-dataset routes** ("ICE 4022 Amsterdam→Frankfurt", "EuroRail 9412 Lyon→Paris"). The dataset/graph/ML model only cover 30 Indian stations. Recommendation: MVP restricts all real functionality to dataset-covered trains; the mockup's European examples should be treated as **placeholder visual design only**, not a requirement to support international rail data (no such data exists anywhere in the supplied materials).
4. **The MAE-based ETA interval is extremely tight (≈ ±0.6–0.7 minutes)** because it's derived from a model trained and evaluated on internally-consistent synthetic data (`metrics.json`, `xgboost_delay.mae ≈ 0.61`). Displaying "±1 minute" confidence to end users would overstate real-world reliability. Recommendation: the backend should pass the interval through unmodified (per the "don't invent ML output" rule) but the product/UI copy should carry a visible "prototype model, not production-grade accuracy" disclaimer, consistent with the ML package's own README caveat.
5. **`dataset_summary.json` and `data_validation_report.json` disagree slightly on the observed range of `future_additional_delay_mins`** (−118.3 to +24.0 vs −5.0 to +24.0). Neither file explains the discrepancy. Not resolved here — flagged in §37.
6. **`/predict/temporal` (GNN/GRU) has no ETA-combination logic in the ML service.** Exposing it as a user-facing "alternative model" prediction requires the backend to replicate a small piece of arithmetic that today only exists inside the `/predict` handler — a genuine duplication risk the PRD's own rules warn against. Recommendation: keep `/predict/temporal` out of the MVP's user-facing surface (internal/admin-only comparison tool at most) unless/until the ML team adds ETA synthesis to that route themselves.
7. **No official station full names/coordinates are provided** beyond the 30 short codes and the per-position `latitude`/`longitude` sampled inside the dataset (which are synthetic, not authoritative geocodes for those stations). Do not fabricate a station gazetteer.

---

## 37. Open Questions / Items Requiring Confirmation

1. Should primary keys be `BIGSERIAL` or `UUID` for public-facing IDs (§8)? No preference is evident in any supplied artifact.
2. Is there an intended mapping from the 30 short station codes to full display names/geo-coordinates for the map UI? None is present in `railway_graph_nodes.csv` or elsewhere.
3. How should a smart alarm's ETA be computed when `target_station_code` is an **intermediate** stop rather than the train's final destination? The ML service only ever returns a single end-to-end `eta`; no per-stop ETA endpoint or field exists (§19).
4. Should `/predict/temporal` (GRU / Hybrid GNN-GRU) ever be exposed to end users, and if so, who owns writing the ETA-combination formula for it — the ML team (extending `/predict/temporal`'s response) or the backend (duplicating the `/predict` arithmetic)? Per the "do not duplicate ML logic" rule, the cleaner fix is asking the ML team to extend the endpoint; not decided here.
5. What exact distance/time threshold should trigger an "approaching destination" notification? No frontend or ML artifact specifies one; §18 proposes 15 km as a placeholder default, configurable via env var.
6. Should the MVP support real push/SMS/email notification delivery, or is an in-app notification list sufficient for the SIH demo? No delivery provider is referenced anywhere in the supplied materials.
7. The dataset's schedule timestamps carry a fixed synthetic date (e.g. `2025-01-02`) rather than "today" — should seeding remap these onto rolling relative dates (e.g., relative to each demo session's start) so the replay always feels "live," or is a fixed historical date acceptable for the hackathon demo? Not specified.
8. Reconcile the `dataset_summary.json` vs `data_validation_report.json` discrepancy in `future_additional_delay_mins` range (§36 point 5) — needs the dataset author, not something the backend can resolve unilaterally.
9. Should anonymous (unauthenticated) users be able to view `GET /trains/{id}/status` at all (the mockup's home page has no visible login gate), or does the real product intend to gate all functionality behind auth? Assumed "optional auth, public read" in §15/§17 — confirm before implementation.
10. Confirm whether the "Recently Tracked Trains" section (§3.7) is meant to show only the current user's `tracked_trains`, or a broader "recently viewed" history distinct from explicit favouriting — the mockup's copy ("Your Recent Trains") suggests the latter, but no separate "recently viewed" entity was requested elsewhere in the PRD brief, and none is modeled in §8 to avoid inventing an untold requirement.

---

*End of document.*
