from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GCP — ADC handles auth automatically on VM, no JSON file needed
    google_application_credentials: str = ""
    gcp_project_id: str = "project-6bf0badc-9510-4a48-9e6"
    gcp_region: str = "us-central1"

    # Gemini API key (Google AI Studio) — alternative to Vertex AI for Gemini chat
    # Get free key at: aistudio.google.com/app/apikey
    gemini_api_key: Optional[str] = None

    # Vertex AI chain-scorer endpoints (predict protected attr) — deploy_vertex.py
    vertex_ai_endpoint_compas:      Optional[str] = None
    vertex_ai_endpoint_adult_train: Optional[str] = None
    vertex_ai_endpoint_adult_test:  Optional[str] = None
    vertex_ai_endpoint_german:      Optional[str] = None
    vertex_ai_endpoint_id:          Optional[str] = None  # generic fallback

    # Vertex AI outcome-scorer endpoints (predict outcome) — deploy_outcome_models.py
    vertex_ai_outcome_compas:       Optional[str] = None
    vertex_ai_outcome_adult_train:  Optional[str] = None
    vertex_ai_outcome_adult_test:   Optional[str] = None
    vertex_ai_outcome_german:       Optional[str] = None

    # Graph thresholds
    correlation_threshold: float = 0.15
    chain_depth_max: int = 6
    chain_risk_threshold: float = 0.50


settings = Settings()
