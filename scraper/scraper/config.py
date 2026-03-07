import os
from dataclasses import dataclass

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

    @property
    def db_url(self) -> str:
        return (
            f"mysql+mysqldb://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?charset=utf8mb4"
        )


settings = Settings()
