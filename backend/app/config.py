from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    plaid_client_id: str
    plaid_secret: str
    plaid_env: str = "sandbox"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    openai_api_key: str
    airflow_sync_secret: str = "airflowsecret"

    class Config:
        env_file = ".env"


settings = Settings()
