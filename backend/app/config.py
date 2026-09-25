from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str = "sandbox"
    # Needed for bank OAuth flows on Android (e.g. Chase): Plaid redirects back to the app by
    # package name. It must ALSO be registered in the Plaid dashboard (Developers > API >
    # Allowed Android package names) or Plaid rejects the link token with INVALID_FIELD.
    plaid_android_package_name: str = ""
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    airflow_sync_secret: str = "airflowsecret"

    # AI insights are optional: without a key the rule-based fallback is used.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Comma-separated list of allowed CORS origins ("*" allows any).
    cors_origins: str = "*"

    # Key material for encrypting Plaid access tokens at rest.
    # Falls back to a key derived from JWT_SECRET when unset.
    token_encryption_key: str = ""

    # Max login/register attempts per client address per minute; 0 disables the limit.
    auth_rate_limit_per_minute: int = 20

    @model_validator(mode="after")
    def _refuse_weak_config_outside_sandbox(self):
        """Fail at startup rather than run real bank data behind placeholder secrets."""
        if self.plaid_env == "sandbox":
            return self
        problems = []
        if len(self.jwt_secret) < 32 or "change_this" in self.jwt_secret:
            problems.append("JWT_SECRET must be a random value of at least 32 characters")
        if self.airflow_sync_secret == "airflowsecret" or "change_this" in self.airflow_sync_secret:
            problems.append("AIRFLOW_SYNC_SECRET must not be the default placeholder")
        if self.cors_origin_list == ["*"]:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'")
        if problems:
            raise ValueError(f"Unsafe configuration for PLAID_ENV={self.plaid_env}: " + "; ".join(problems))
        return self

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
