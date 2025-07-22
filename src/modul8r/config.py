from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="MODUL8R_"
    )

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_default_model: str = "gpt-4o"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.1
    openai_timeout: float = 60.0

    # Concurrency Configuration  
    max_concurrent_requests: int = Field(default=3, ge=1, le=100)
    pdf_processing_timeout: float = 300.0
    
    # Rate Limiting
    requests_per_minute: int = 60
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0

    # PDF Processing
    pdf_dpi: int = Field(default=300, ge=150, le=600)
    pdf_format: str = "PNG"

    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "json"
    log_correlation_id_header: str = "X-Correlation-ID"

    # Server Configuration
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    server_reload: bool = False

    # WebSocket Configuration
    websocket_timeout: float = 60.0
    websocket_ping_interval: float = 20.0


settings = Settings()