"""Base scraper class with common functionality."""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import ScraperConfig, config


class BaseScraper(ABC):
    """Base class for all scrapers with common HTTP and rate limiting functionality."""

    def __init__(self, scraper_config: Optional[ScraperConfig] = None):
        self.config = scraper_config or config.scraper
        self._client: Optional[httpx.AsyncClient] = None
        self._request_lock = asyncio.Lock()
        self._last_request_time = 0.0

    @property
    def headers(self) -> dict[str, str]:
        """Get default headers with randomized user agent."""
        return {
            "User-Agent": random.choice(self.config.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout),
                follow_redirects=True,
                headers=self.headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        async with self._request_lock:
            now = asyncio.get_event_loop().time()
            min_interval = 1.0 / self.config.requests_per_second

            if self._last_request_time > 0:
                elapsed = now - self._last_request_time
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    # Add jitter to avoid patterns
                    wait_time += random.uniform(0.1, 0.5)
                    await asyncio.sleep(wait_time)

            self._last_request_time = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def fetch(
        self,
        url: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> httpx.Response:
        """Fetch a URL with rate limiting and retries.

        Args:
            url: The URL to fetch
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments to pass to httpx

        Returns:
            The HTTP response

        Raises:
            httpx.HTTPError: If the request fails after retries
        """
        await self._rate_limit()

        client = await self.get_client()

        # Rotate user agent for each request
        headers = {**self.headers, **kwargs.pop("headers", {})}

        logger.debug(f"Fetching {method} {url}")

        response = await client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()

        logger.debug(f"Received {response.status_code} from {url}")

        return response

    async def fetch_html(self, url: str, **kwargs: Any) -> str:
        """Fetch a URL and return the HTML content."""
        response = await self.fetch(url, **kwargs)
        return response.text

    @abstractmethod
    async def scrape(self) -> list[Any]:
        """Main scraping method to be implemented by subclasses."""
        pass

    async def __aenter__(self) -> "BaseScraper":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
