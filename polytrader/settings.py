from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYTRADER_", env_file=".env", extra="ignore")

    # Scheduler
    interval_seconds: int = 600

    # Strategy thresholds
    min_edge: float = 0.08  # 8% by default
    max_position_fraction: float = 0.06  # 6% cap (you can lower)
    kelly_fraction: float = 0.25  # fractional Kelly (safer than 1.0)

    # Risk limits
    max_daily_loss_fraction: float = 0.10
    max_open_positions: int = 20
    min_liquidity_usd: float = 200.0

    # Data universe
    max_markets: int = 1000

    # LLM (optional)
    llm_provider: str | None = None  # e.g. "anthropic" / "openai"
    llm_api_key: str | None = None
    llm_model: str | None = None

    # Execution mode
    mode: str = "paper"  # paper | live

    # Live trading adapter (to be wired)
    exchange: str = "polymarket"  # placeholder
    api_base_url: str | None = None
    api_key: str | None = None


settings = Settings()
