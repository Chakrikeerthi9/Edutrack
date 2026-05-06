from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    anthropic_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    sentry_dsn: str = ""
    environment: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"  # ignores any extra fields in .env

settings = Settings()