from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str = "sandbox"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    airflow_sync_secret: str = "airflowsecret"

    # AI insights are optional: without a key the rule-based fallback is used.
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Comma-separated list of allowed CORS origins ("*" allows any).
    cors_origins: str = "*"

    # Key material for encrypting Plaid access tokens at rest.
    # Falls back to a key derived from JWT_SECRET when unset.
    token_encryption_key: str = ""

    @field_validator("plaid_env")
    @classmethod
    def _valid_plaid_env(cls, v: str) -> str:
        v = v.lower()
        if v not in {"sandbox", "development", "production"}:
            raise ValueError("PLAID_ENV must be sandbox, development or production")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
