from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYTRADER_", env_file=".env", extra="ignore")

    # Scheduler
    interval_seconds: int = 600

    # Edge sources (weather)
    nws_user_agent: str = "polytrader/0.1 (contact: you@example.com)"
    locations_file: str | None = None  # path to JSON mapping of location->lat/lon

    # Edge sources (crypto)
    btc_vol_lookback_days: int = 30
    btc_drift_mu: float = 0.0

    btc_15m_lookback_minutes: int = 240

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

    # Optional focus filter (simple substring match against question)
    focus_query: str | None = None

    # Optional Gamma filters (recommended for recurring series like BTC up/down)
    gamma_series_id: int | None = None

    # LLM (optional)
    llm_provider: str | None = None  # e.g. "anthropic" / "openai"
    llm_api_key: str | None = None
    llm_model: str | None = None

    # Execution mode
    mode: str = "paper"  # paper | live

    # Exchange selection
    # - "paper": internal stub exchange
    # - "polymarket-public": read-only Gamma+CLOB adapter (dry-run decisions against real markets)
    exchange: str = "paper"

    # Live trading adapter (to be wired)
    api_base_url: str | None = None
    api_key: str | None = None


settings = Settings()
