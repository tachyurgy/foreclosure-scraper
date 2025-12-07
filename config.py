"""Configuration settings for the foreclosure data scraper."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ScraperConfig:
    """Configuration for web scraping behavior."""

    # Rate limiting
    requests_per_second: float = 1.0
    max_concurrent_requests: int = 3

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0

    # Timeouts (seconds)
    request_timeout: float = 30.0
    page_load_timeout: float = 60.0

    # User agent rotation
    user_agents: list[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ])


@dataclass
class CountyConfig:
    """Configuration for York County court roster scraping."""

    base_url: str = "https://publicindex.sccourts.org/york/courtrosters/"
    # Target case types for foreclosure
    case_types: list[str] = field(default_factory=lambda: ["Foreclosure", "FORECLOSURE"])


@dataclass
class ZillowConfig:
    """Configuration for Zillow property lookups."""

    base_url: str = "https://www.zillow.com"
    target_zip_codes: list[str] = field(default_factory=lambda: [
        "29732", "29745", "29730", "29710", "29708",
        "29704", "29726", "29717", "29715", "29702",
        "29743", "29712"
    ])


@dataclass
class DealioConfig:
    """Configuration for Dealio lookups."""

    base_url: str = "https://www.dealio.com"


@dataclass
class StorageConfig:
    """Configuration for data storage."""

    data_dir: Path = field(default_factory=lambda: Path("./data"))
    database_path: Path = field(default_factory=lambda: Path("./data/foreclosures.db"))
    export_format: str = "csv"  # csv, xlsx, json

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class AppConfig:
    """Main application configuration."""

    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    county: CountyConfig = field(default_factory=CountyConfig)
    zillow: ZillowConfig = field(default_factory=ZillowConfig)
    dealio: DealioConfig = field(default_factory=DealioConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    # Scheduling
    schedule_interval_days: int = 14  # Run every two weeks

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create configuration from environment variables."""
        config = cls()

        # Override from environment if set
        if interval := os.getenv("SCHEDULE_INTERVAL_DAYS"):
            config.schedule_interval_days = int(interval)

        if rate := os.getenv("REQUESTS_PER_SECOND"):
            config.scraper.requests_per_second = float(rate)

        return config


# Global config instance
config = AppConfig.from_env()
