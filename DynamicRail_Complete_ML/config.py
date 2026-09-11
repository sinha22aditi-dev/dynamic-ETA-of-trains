from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
SEQ_PATH = DATA_DIR / "dynamicrail_sequential_simulation.csv"
GRAPH_NODES_PATH = DATA_DIR / "railway_graph_nodes.csv"
GRAPH_EDGES_PATH = DATA_DIR / "railway_graph_edges.csv"

RANDOM_STATE = 42
WINDOW = 6              # 6 x 10 min = 60 minutes of history
HORIZON_STEPS = 2       # predict 20 minutes ahead

# Numerics that are known at prediction time.
NEURAL_NUMERIC_FEATURES = [
    "current_speed_kmh", "current_delay_mins", "distance_remaining_km",
    "previous_station_delay", "delay_2_stations_ago", "delay_3_stations_ago",
    "historical_avg_train_delay", "historical_avg_station_delay",
    "historical_avg_section_delay", "historical_on_time_pct",
    "train_ahead_delay_mins", "train_ahead_speed_kmh", "train_ahead_distance_km",
    "number_of_trains_ahead", "distance_between_trains_km", "headway_mins",
    "section_congestion_index", "temperature_celsius", "rainfall_mm",
    "humidity_pct", "wind_speed_kmh", "visibility_meters",
    "track_vibration_hz", "rail_wear_mm", "speed_restriction_kmh",
    "section_capacity_pct", "bearing_temperature_c", "axle_temperature_c",
    "brake_pressure_bar", "brake_pad_wear_pct", "days_since_maintenance",
    "hour", "month", "is_weekend_holiday", "is_peak_hour"
]

XGB_DROP = {
    "predicted_eta", "actual_arrival_time", "future_additional_delay_mins",
    "future_delay_20m", "future_delay_target", "propagation_delay_mins", "propagation_occurred",
    "propagation_probability",
    "sequence_step", "sequence_id", "split", "data_source",
    "train_id", "train_ahead_id"
}
# These are outputs/future values and are never allowed into predictive features.
XGB_TIME_COLUMNS = {"timestamp", "scheduled_arrival_time", "scheduled_departure_time", "reason_start_time"}
XGB_DERIVED_OUTPUTS = {"remaining_travel_time_mins"}
