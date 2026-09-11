import pytest
from app.clients.ml_client import (
    LEAKAGE_FIELDS,
    _strip_leakage,
    MLUnavailableError,
    MLBadRequestError,
)


def test_leakage_columns_definition():
    # Verify strict data leakage prevention rules (§12.1)
    forbidden = [
        "predicted_eta", "actual_arrival_time", "future_additional_delay_mins",
        "future_delay_20m", "future_delay_target", "propagation_delay_mins",
        "propagation_occurred", "propagation_probability", "sequence_step",
        "sequence_id", "split", "data_source", "train_id", "train_ahead_id"
    ]
    for col in forbidden:
        assert col in LEAKAGE_FIELDS


def test_strip_leakage_excludes_forbidden_fields():
    sample_snapshot = {
        "train_id": 12345,
        "sequence_id": "seq_1",
        "future_delay_target": 15.0,
        "predicted_eta": "2026-09-11T12:00:00",
        "current_speed_kmh": 65.5,
        "current_delay_mins": 10.0,
        "distance_remaining_km": 120.0,
        "timestamp": "2026-09-11T10:00:00",
    }
    payload = _strip_leakage(sample_snapshot)
    
    # Assert leakage fields were stripped
    assert "future_delay_target" not in payload
    assert "predicted_eta" not in payload
    assert "train_id" not in payload
    assert "sequence_id" not in payload
    
    # Assert valid fields remain
    assert payload["current_speed_kmh"] == 65.5
    assert payload["current_delay_mins"] == 10.0
    assert payload["distance_remaining_km"] == 120.0
