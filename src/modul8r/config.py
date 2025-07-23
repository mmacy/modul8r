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
    openai_default_model: str = "gpt-4.1-nano"  # Default model for image processing
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.1
    openai_timeout: float = 60.0

    # Concurrency Configuration
    max_concurrent_requests: int = Field(default=3, ge=1, le=100)
    pdf_processing_timeout: float = 300.0

    # Rate Limiting
    requests_per_minute: int = 60
    retry_max_attempts: int = 1  # Reduce retries to prevent loops
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0

    # PDF Processing
    pdf_dpi: int = Field(default=300, ge=150, le=600)
    pdf_format: str = "PNG"

    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "json"
    log_correlation_id_header: str = "X-Correlation-ID"
    enable_log_capture: bool = True  # Enable WebSocket log streaming

    # Server Configuration
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    server_reload: bool = False

    # WebSocket Configuration
    websocket_timeout: float = 60.0
    websocket_ping_interval: float = 20.0

    # Phase 1 Foundation Safeguards Configuration

    # Message Throttling Settings
    throttle_batch_interval: float = Field(default=0.5, ge=0.1, le=5.0)  # seconds
    throttle_max_batch_size: int = Field(default=100, ge=10, le=500)
    throttle_circuit_breaker_threshold: float = Field(default=50.0, ge=10.0, le=200.0)  # msgs/sec
    throttle_circuit_breaker_window: float = Field(default=10.0, ge=5.0, le=60.0)  # seconds
    throttle_circuit_breaker_recovery_time: float = Field(default=30.0, ge=10.0, le=300.0)  # seconds

    # Memory Management Settings
    enhanced_log_capture_max_entries: int = Field(default=1000, ge=100, le=5000)
    enhanced_log_capture_max_age_seconds: int = Field(default=3600, ge=300, le=86400)  # 5 mins to 24 hours
    enhanced_log_capture_cleanup_interval: int = Field(default=300, ge=60, le=1800)  # cleanup every 5 minutes

    # Performance Monitoring Settings
    performance_monitor_max_lag_ms: float = Field(default=40.0, ge=10.0, le=200.0)  # event loop lag threshold
    performance_monitor_check_interval: float = Field(default=1.0, ge=0.5, le=10.0)  # check every second
    performance_monitor_severe_lag_threshold_multiplier: float = Field(
        default=3.0, ge=2.0, le=10.0
    )  # 3x normal threshold
    performance_monitor_max_severe_lag_count: int = Field(default=5, ge=1, le=20)

    # Phase 1 Feature Flags
    enable_message_throttling: bool = True
    enable_enhanced_memory_management: bool = True
    enable_performance_monitoring: bool = True
    enable_phase1_status_endpoint: bool = True


settings = Settings()
