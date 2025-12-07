"""Zillow property data scraper."""

import asyncio
import json
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page

from config import ZillowConfig, config
from models import Address, ZillowProperty

from .base import BaseScraper


class ZillowScraper(BaseScraper):
    """Scraper for Zillow property data.

    Uses address-based lookups to find property information.
    Handles Zillow's anti-bot protections with Playwright.
    """

    def __init__(self, zillow_config: Optional[ZillowConfig] = None):
        super().__init__()
        self.zillow_config = zillow_config or config.zillow
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
                    "--disable-dev-shm-usage",
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
        """Build Zillow search URL for an address."""
        encoded_address = quote_plus(address)
        return f"{self.zillow_config.base_url}/homes/{encoded_address}_rb/"

    async def _search_property(self, page: Page, address: str) -> Optional[str]:
        """Search for a property and return its detail page URL."""
        search_url = self._build_search_url(address)
        logger.info(f"Searching Zillow for: {address}")

        try:
            await self._rate_limit()
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Check if we landed on a property detail page directly
            current_url = page.url
            if "/homedetails/" in current_url:
                return current_url

            # Look for search results
            result_cards = await page.query_selector_all(
                "article[data-test='property-card'], .property-card, .list-card"
            )

            if result_cards:
                first_card = result_cards[0]
                link = await first_card.query_selector("a[href*='homedetails']")
                if link:
                    href = await link.get_attribute("href")
                    if href and not href.startswith("http"):
                        href = f"{self.zillow_config.base_url}{href}"
                    return href

            # Try clicking on first result
            first_result = await page.query_selector(
                "a[href*='homedetails'], .property-card a, .list-card a"
            )
            if first_result:
                href = await first_result.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        href = f"{self.zillow_config.base_url}{href}"
                    return href

        except Exception as e:
            logger.warning(f"Error searching Zillow for {address}: {e}")

        return None

    async def _extract_property_data(self, page: Page, url: str) -> Optional[ZillowProperty]:
        """Extract property data from a Zillow detail page."""
        logger.debug(f"Extracting data from: {url}")

        try:
            await self._rate_limit()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            property_data = ZillowProperty(listing_url=url)

            # Try to extract from JSON-LD schema
            self._extract_from_schema(soup, property_data)

            # Extract from page elements
            self._extract_from_html(soup, property_data)

            # Try to get ZPID from URL or page
            zpid_match = re.search(r"/(\d+)_zpid", url)
            if zpid_match:
                property_data.zpid = zpid_match.group(1)

            return property_data

        except Exception as e:
            logger.warning(f"Error extracting Zillow data from {url}: {e}")
            return None

    def _extract_from_schema(self, soup: BeautifulSoup, prop: ZillowProperty) -> None:
        """Extract property data from JSON-LD schema."""
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)

                if isinstance(data, list):
                    for item in data:
                        self._parse_schema_item(item, prop)
                else:
                    self._parse_schema_item(data, prop)

            except (json.JSONDecodeError, TypeError):
                continue

    def _parse_schema_item(self, item: dict, prop: ZillowProperty) -> None:
        """Parse a schema.org item for property data."""
        if not isinstance(item, dict):
            return

        item_type = item.get("@type", "")

        if item_type in ["SingleFamilyResidence", "House", "Apartment", "RealEstateListing"]:
            # Address
            if addr := item.get("address"):
                if isinstance(addr, dict):
                    parts = [
                        addr.get("streetAddress", ""),
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("postalCode", ""),
                    ]
                    prop.address = ", ".join(p for p in parts if p)
                elif isinstance(addr, str):
                    prop.address = addr

            # Floor area
            if floor_size := item.get("floorSize"):
                if isinstance(floor_size, dict):
                    prop.sqft = int(floor_size.get("value", 0))
                elif isinstance(floor_size, (int, float)):
                    prop.sqft = int(floor_size)

            # Beds/baths
            if beds := item.get("numberOfRooms"):
                prop.bedrooms = int(beds)

            if baths := item.get("numberOfBathroomsTotal"):
                prop.bathrooms = float(baths)

            # Year built
            if year := item.get("yearBuilt"):
                prop.year_built = int(year)

        # Check for offers/pricing
        if item_type == "Offer" or "offers" in item:
            offers = item.get("offers", item)
            if isinstance(offers, dict):
                if price := offers.get("price"):
                    prop.price = float(price)

    def _extract_from_html(self, soup: BeautifulSoup, prop: ZillowProperty) -> None:
        """Extract property data from HTML elements."""
        # Price
        price_selectors = [
            "[data-test='property-value']",
            ".ds-value",
            ".price",
            "span[data-testid='price']",
            ".home-price",
        ]

        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                price_text = elem.get_text(strip=True)
                price = self._parse_price(price_text)
                if price:
                    prop.price = price
                    break

        # Zestimate
        zestimate_elem = soup.select_one(
            "[data-testid='zestimate-value'], .zestimate"
        )
        if zestimate_elem:
            prop.zestimate = self._parse_price(zestimate_elem.get_text(strip=True))

        # Address
        address_elem = soup.select_one(
            "[data-testid='bdp-header-address'], h1.ds-address-container, .property-address"
        )
        if address_elem and not prop.address:
            prop.address = address_elem.get_text(strip=True)

        # Beds/Baths/Sqft - often in a summary row
        summary = soup.select_one(".ds-bed-bath-living-area, .bdp-summary")
        if summary:
            text = summary.get_text(" ", strip=True)

            bed_match = re.search(r"(\d+)\s*(?:bd|bed|bedroom)", text, re.I)
            if bed_match:
                prop.bedrooms = int(bed_match.group(1))

            bath_match = re.search(r"([\d.]+)\s*(?:ba|bath|bathroom)", text, re.I)
            if bath_match:
                prop.bathrooms = float(bath_match.group(1))

            sqft_match = re.search(r"([\d,]+)\s*(?:sqft|sq\s*ft|square)", text, re.I)
            if sqft_match:
                prop.sqft = int(sqft_match.group(1).replace(",", ""))

        # Property type
        type_elem = soup.select_one("[data-testid='home-type'], .property-type")
        if type_elem:
            prop.property_type = type_elem.get_text(strip=True)

        # Status
        status_elem = soup.select_one("[data-testid='listing-status'], .listing-status")
        if status_elem:
            prop.status = status_elem.get_text(strip=True)

        # Year built - often in facts section
        facts = soup.select(".ds-home-fact-list-item, .fact-item, dt + dd")
        for fact in facts:
            text = fact.get_text(strip=True)
            if "built" in text.lower():
                year_match = re.search(r"\b(19|20)\d{2}\b", text)
                if year_match:
                    prop.year_built = int(year_match.group())
                    break

        # Image
        img = soup.select_one("picture img, .media-stream-tile img, [data-testid='hero-image']")
        if img:
            prop.image_url = img.get("src", "")

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse a price string to float."""
        if not price_text:
            return None

        # Remove currency symbols and commas
        cleaned = re.sub(r"[^\d.]", "", price_text)

        try:
            return float(cleaned)
        except ValueError:
            return None

    async def lookup_property(self, address: Address | str) -> Optional[ZillowProperty]:
        """Look up a property on Zillow by address.

        Args:
            address: The property address to look up

        Returns:
            ZillowProperty data if found, None otherwise
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

            # Search for the property
            detail_url = await self._search_property(page, address_str)

            if detail_url:
                # Extract property data
                return await self._extract_property_data(page, detail_url)

        finally:
            await context.close()

        return None

    async def lookup_properties(
        self,
        addresses: list[Address | str],
        max_concurrent: int = 2,
    ) -> list[Optional[ZillowProperty]]:
        """Look up multiple properties with controlled concurrency.

        Args:
            addresses: List of addresses to look up
            max_concurrent: Maximum concurrent lookups

        Returns:
            List of ZillowProperty data (None for failures)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def lookup_with_semaphore(addr):
            async with semaphore:
                return await self.lookup_property(addr)

        tasks = [lookup_with_semaphore(addr) for addr in addresses]
        return await asyncio.gather(*tasks)

    async def scrape(self) -> list[ZillowProperty]:
        """Not used directly - use lookup_property instead."""
        logger.warning("ZillowScraper.scrape() not implemented - use lookup_property()")
        return []


async def main():
    """Test the Zillow scraper."""
    # Test address
    test_address = "123 Main St, Rock Hill, SC 29732"

    async with ZillowScraper() as scraper:
        result = await scraper.lookup_property(test_address)

        if result:
            print(f"Found property: {result.address}")
            print(f"  Price: ${result.price:,.0f}" if result.price else "  Price: N/A")
            print(f"  Zestimate: ${result.zestimate:,.0f}" if result.zestimate else "  Zestimate: N/A")
            print(f"  Beds: {result.bedrooms}, Baths: {result.bathrooms}")
            print(f"  Sqft: {result.sqft}")
            print(f"  URL: {result.listing_url}")
        else:
            print("Property not found")


if __name__ == "__main__":
    asyncio.run(main())
