import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "shipinfo")
    db_user: str = os.getenv("DB_USER", "")
    db_password: str = os.getenv("DB_PASSWORD", "")
    interval_minutes: int = int(os.getenv("SCRAPER_INTERVAL_MINUTES", "30"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    marue_search_days_ahead: int = int(os.getenv("MARUE_SEARCH_DAYS_AHEAD", "3"))
    marue_far_search_interval_hours: int = int(
        os.getenv("MARUE_FAR_SEARCH_INTERVAL_HOURS", "6")
    )
    marue_search_delay_seconds: float = float(
        os.getenv("MARUE_SEARCH_DELAY_SECONDS", "0.5")
    )

    @property
    def db_url(self) -> str:
        return (
            f"mysql+mysqldb://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )


settings = Settings()
