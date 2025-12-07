"""Dealio property deals scraper."""

import asyncio
import json
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page

from config import DealioConfig, config
from models import Address, DealioListing

from .base import BaseScraper


class DealioScraper(BaseScraper):
    """Scraper for Dealio property deals and offers.

    Searches for property deals using address-based lookups.
    """

    def __init__(self, dealio_config: Optional[DealioConfig] = None):
        super().__init__()
        self.dealio_config = dealio_config or config.dealio
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _get_browser(self) -> Browser:
        """Get or create the Playwright browser instance."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ]
            )
        return self._browser

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        await super().close()

    def _build_search_url(self, address: str) -> str:
        """Build Dealio search URL for an address."""
        encoded_address = quote_plus(address)
        return f"{self.dealio_config.base_url}/search?q={encoded_address}"

    async def _search_listings(self, page: Page, address: str) -> list[str]:
        """Search for listings and return detail page URLs."""
        search_url = self._build_search_url(address)
        logger.info(f"Searching Dealio for: {address}")

        listing_urls = []

        try:
            await self._rate_limit()
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Look for search results
            result_cards = await page.query_selector_all(
                ".listing-card, .deal-card, .property-card, article[data-listing]"
            )

            for card in result_cards[:5]:  # Limit to top 5 results
                link = await card.query_selector("a[href]")
                if link:
                    href = await link.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"{self.dealio_config.base_url}{href}"
                        listing_urls.append(href)

            # If no cards found, try general links
            if not listing_urls:
                links = await page.query_selector_all(
                    "a[href*='listing'], a[href*='deal'], a[href*='property']"
                )
                for link in links[:5]:
                    href = await link.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"{self.dealio_config.base_url}{href}"
                        listing_urls.append(href)

        except Exception as e:
            logger.warning(f"Error searching Dealio for {address}: {e}")

        return listing_urls

    async def _extract_listing_data(self, page: Page, url: str) -> Optional[DealioListing]:
        """Extract listing data from a Dealio detail page."""
        logger.debug(f"Extracting Dealio data from: {url}")

        try:
            await self._rate_limit()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            listing = DealioListing(listing_url=url)

            # Try JSON-LD first
            self._extract_from_schema(soup, listing)

            # Extract from HTML
            self._extract_from_html(soup, listing)

            return listing

        except Exception as e:
            logger.warning(f"Error extracting Dealio data from {url}: {e}")
            return None

    def _extract_from_schema(self, soup: BeautifulSoup, listing: DealioListing) -> None:
        """Extract data from JSON-LD schema."""
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)

                if isinstance(data, list):
                    for item in data:
                        self._parse_schema_item(item, listing)
                else:
                    self._parse_schema_item(data, listing)

            except (json.JSONDecodeError, TypeError):
                continue

    def _parse_schema_item(self, item: dict, listing: DealioListing) -> None:
        """Parse a schema.org item for listing data."""
        if not isinstance(item, dict):
            return

        item_type = item.get("@type", "")

        if item_type in ["Product", "Offer", "RealEstateListing", "Service"]:
            # Title/Name
            if name := item.get("name"):
                listing.title = name

            # Description
            if desc := item.get("description"):
                listing.description = desc

            # Price
            if offers := item.get("offers"):
                if isinstance(offers, dict):
                    if price := offers.get("price"):
                        listing.price = float(price)
                    if orig_price := offers.get("highPrice"):
                        listing.original_price = float(orig_price)

            elif price := item.get("price"):
                listing.price = float(price)

            # Address
            if addr := item.get("address"):
                if isinstance(addr, dict):
                    parts = [
                        addr.get("streetAddress", ""),
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                    ]
                    listing.address = ", ".join(p for p in parts if p)

    def _extract_from_html(self, soup: BeautifulSoup, listing: DealioListing) -> None:
        """Extract listing data from HTML elements."""
        # Title
        title_selectors = [
            "h1.listing-title",
            ".deal-title",
            "h1",
            "[data-testid='title']",
        ]
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem and not listing.title:
                listing.title = elem.get_text(strip=True)
                break

        # Description
        desc_selectors = [
            ".listing-description",
            ".deal-description",
            "[data-testid='description']",
            ".description",
        ]
        for selector in desc_selectors:
            elem = soup.select_one(selector)
            if elem:
                listing.description = elem.get_text(strip=True)[:1000]  # Limit length
                break

        # Price
        price_selectors = [
            ".price",
            ".deal-price",
            "[data-testid='price']",
            ".listing-price",
        ]
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                price = self._parse_price(elem.get_text(strip=True))
                if price:
                    listing.price = price
                    break

        # Original price / discount
        orig_price_elem = soup.select_one(
            ".original-price, .was-price, .strikethrough, del"
        )
        if orig_price_elem:
            listing.original_price = self._parse_price(orig_price_elem.get_text(strip=True))

        # Calculate discount if we have both prices
        if listing.price and listing.original_price and listing.original_price > listing.price:
            listing.discount_percent = (
                (listing.original_price - listing.price) / listing.original_price * 100
            )

        # Offer description
        offer_selectors = [
            ".offer-details",
            ".deal-details",
            ".promotion",
            ".special-offer",
        ]
        for selector in offer_selectors:
            elem = soup.select_one(selector)
            if elem:
                listing.offer_description = elem.get_text(strip=True)
                break

        # Contact information
        self._extract_contact_info(soup, listing)

        # Address (if not already set)
        if not listing.address:
            addr_selectors = [
                ".address",
                ".property-address",
                "[data-testid='address']",
            ]
            for selector in addr_selectors:
                elem = soup.select_one(selector)
                if elem:
                    listing.address = elem.get_text(strip=True)
                    break

    def _extract_contact_info(self, soup: BeautifulSoup, listing: DealioListing) -> None:
        """Extract contact information from the page."""
        # Phone number
        phone_patterns = [
            r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",  # (123) 456-7890
            r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",  # 123-456-7890
        ]

        phone_selectors = [
            "a[href^='tel:']",
            ".phone",
            ".contact-phone",
            "[data-testid='phone']",
        ]

        for selector in phone_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                for pattern in phone_patterns:
                    match = re.search(pattern, text)
                    if match:
                        listing.contact_phone = match.group()
                        break
                if listing.contact_phone:
                    break

        # If no phone found in specific elements, search whole page
        if not listing.contact_phone:
            page_text = soup.get_text()
            for pattern in phone_patterns:
                match = re.search(pattern, page_text)
                if match:
                    listing.contact_phone = match.group()
                    break

        # Email
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

        email_selectors = [
            "a[href^='mailto:']",
            ".email",
            ".contact-email",
            "[data-testid='email']",
        ]

        for selector in email_selectors:
            elem = soup.select_one(selector)
            if elem:
                href = elem.get("href", "")
                if href.startswith("mailto:"):
                    listing.contact_email = href.replace("mailto:", "").split("?")[0]
                    break
                text = elem.get_text(strip=True)
                match = re.search(email_pattern, text)
                if match:
                    listing.contact_email = match.group()
                    break

        # Contact name
        name_selectors = [
            ".agent-name",
            ".contact-name",
            ".seller-name",
            "[data-testid='contact-name']",
        ]

        for selector in name_selectors:
            elem = soup.select_one(selector)
            if elem:
                listing.contact_name = elem.get_text(strip=True)
                break

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse a price string to float."""
        if not price_text:
            return None

        cleaned = re.sub(r"[^\d.]", "", price_text)

        try:
            return float(cleaned)
        except ValueError:
            return None

    async def lookup_property(self, address: Address | str) -> Optional[DealioListing]:
        """Look up a property on Dealio by address.

        Args:
            address: The property address to look up

        Returns:
            DealioListing data if found, None otherwise
        """
        if isinstance(address, Address):
            address_str = address.full_address
        else:
            address_str = address

        if not address_str:
            return None

        browser = await self._get_browser()
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.config.user_agents[0],
        )

        try:
            page = await context.new_page()

            # Search for listings
            listing_urls = await self._search_listings(page, address_str)

            if listing_urls:
                # Get data from first matching listing
                return await self._extract_listing_data(page, listing_urls[0])

        finally:
            await context.close()

        return None

    async def lookup_properties(
        self,
        addresses: list[Address | str],
        max_concurrent: int = 2,
    ) -> list[Optional[DealioListing]]:
        """Look up multiple properties with controlled concurrency.

        Args:
            addresses: List of addresses to look up
            max_concurrent: Maximum concurrent lookups

        Returns:
            List of DealioListing data (None for failures)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def lookup_with_semaphore(addr):
            async with semaphore:
                return await self.lookup_property(addr)

        tasks = [lookup_with_semaphore(addr) for addr in addresses]
        return await asyncio.gather(*tasks)

    async def scrape(self) -> list[DealioListing]:
        """Not used directly - use lookup_property instead."""
        logger.warning("DealioScraper.scrape() not implemented - use lookup_property()")
        return []


async def main():
    """Test the Dealio scraper."""
    test_address = "123 Main St, Rock Hill, SC 29732"

    async with DealioScraper() as scraper:
        result = await scraper.lookup_property(test_address)

        if result:
            print(f"Found listing: {result.title}")
            print(f"  Price: ${result.price:,.0f}" if result.price else "  Price: N/A")
            print(f"  Offer: {result.offer_description}")
            print(f"  Contact: {result.contact_phone} / {result.contact_email}")
            print(f"  URL: {result.listing_url}")
        else:
            print("No listings found")


if __name__ == "__main__":
    asyncio.run(main())
