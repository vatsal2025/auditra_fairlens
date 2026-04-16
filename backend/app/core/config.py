from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str = ""
    google_application_credentials: str = ""
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    vertex_ai_endpoint_id: Optional[str] = None

    # Graph thresholds
    correlation_threshold: float = 0.15
    chain_depth_max: int = 6
    chain_risk_threshold: float = 0.50


settings = Settings()
