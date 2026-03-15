from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PB_URL: str = ""
    PB_ADMIN_EMAIL: str = ""
    PB_ADMIN_PASSWORD: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    EMAIL_FROM: str = ""

    APP_PORT: int = 8000
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
