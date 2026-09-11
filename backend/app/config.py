from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dynamicrail:dynamicrail@localhost:5432/dynamicrail"

    # JWT
    JWT_SECRET_KEY: str = "change-me-to-a-random-32-byte-value-for-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ML Service
    ML_SERVICE_URL: str = "http://localhost:8000"
    ML_SERVICE_TIMEOUT_SECONDS: float = 5.0

    # Railway provider
    RAILWAY_PROVIDER: str = "replay"
    REPLAY_TICK_SECONDS: int = 10

    # Dataset CSV paths (relative to backend/ working directory or absolute)
    REPLAY_SOURCE_CSV: str = "data/dynamicrail_sequential_simulation.csv"
    MASTER_CSV: str = "data/railpulse_master_clean.csv"
    GRAPH_NODES_CSV: str = "data/railway_graph_nodes.csv"
    GRAPH_EDGES_CSV: str = "data/railway_graph_edges.csv"

    # CORS
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    # Notification thresholds
    DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS: int = 5
    APPROACHING_DESTINATION_KM: float = 15.0

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
