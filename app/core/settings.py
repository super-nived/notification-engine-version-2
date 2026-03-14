from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PB_URL: str = "http://127.0.0.1:8090"
    PB_ADMIN_EMAIL: str = "abhi-s@industryapps.net"
    PB_ADMIN_PASSWORD: str = "Linux@1994"

    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "uatsignup@industryapps.net"
    SMTP_PASSWORD: str = "uatiapps@123"
    SMTP_TLS: bool = True
    EMAIL_FROM: str = "uatsignup@industryapps.net"

    APP_PORT: int = 8000
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
