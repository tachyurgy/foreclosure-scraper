"""Zillow scraper using nodriver for anti-bot evasion.

nodriver is an undetected browser automation library that evades
bot detection by using a real Chrome instance without automation flags.
"""

import asyncio
import json
import re
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger

try:
    import nodriver as uc
    NODRIVER_AVAILABLE = True
except ImportError:
    NODRIVER_AVAILABLE = False
    logger.warning("nodriver not available - install with: pip install nodriver")

from config import ZillowConfig, config
from models import Address, ZillowProperty


class ZillowNodriverScraper:
    """Zillow scraper using nodriver for undetected browser automation.

    nodriver avoids detection by:
    - Using a real Chrome browser without automation flags
    - No webdriver property injection
    - Natural browser fingerprint
    - Human-like navigation patterns
    """

    def __init__(self, zillow_config: Optional[ZillowConfig] = None):
        self.zillow_config = zillow_config or config.zillow
        self._browser = None
        self._tab = None

    async def _get_browser(self):
        """Get or create the nodriver browser instance."""
        if self._browser is None:
            logger.info("Launching nodriver Chrome browser...")
            # nodriver works best with minimal configuration
            self._browser = await uc.start()
        return self._browser

    async def close(self):
        """Close the browser."""
        if self._browser:
            try:
                self._browser.stop()
            except Exception:
                pass
            self._browser = None
            self._tab = None

    def _build_search_url(self, address: str) -> str:
        """Build Zillow search URL for an address."""
        encoded = quote_plus(address)
        return f"https://www.zillow.com/homes/{encoded}_rb/"

    async def _random_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """Human-like random delay."""
        import random
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.1f}s...")
        await asyncio.sleep(delay)

    async def _extract_property_data(self, tab, url: str) -> Optional[ZillowProperty]:
        """Extract property data from a Zillow page."""
        property_data = ZillowProperty(listing_url=url)

        try:
            # Get page HTML
            html = await tab.get_content()

            # Extract from JSON-LD schema (most reliable)
            json_ld_match = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )

            if json_ld_match:
                try:
                    schema_data = json.loads(json_ld_match.group(1))
                    if isinstance(schema_data, list):
                        for item in schema_data:
                            self._parse_schema(item, property_data)
                    else:
                        self._parse_schema(schema_data, property_data)
                except json.JSONDecodeError:
                    pass

            # Extract from __NEXT_DATA__ (Next.js hydration data)
            next_data_match = re.search(
                r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )

            if next_data_match:
                try:
                    next_data = json.loads(next_data_match.group(1))
                    self._parse_next_data(next_data, property_data)
                except json.JSONDecodeError:
                    pass

            # Fallback: regex extraction from HTML
            self._extract_from_html_regex(html, property_data)

            # Extract ZPID from URL
            zpid_match = re.search(r'/(\d+)_zpid', url)
            if zpid_match:
                property_data.zpid = zpid_match.group(1)

            return property_data

        except Exception as e:
            logger.warning(f"Error extracting property data: {e}")
            return None

    def _parse_schema(self, item: dict, prop: ZillowProperty):
        """Parse JSON-LD schema data."""
        if not isinstance(item, dict):
            return

        item_type = item.get("@type", "")

        if item_type in ["SingleFamilyResidence", "House", "Apartment", "RealEstateListing", "Product"]:
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

            # Floor size
            if floor_size := item.get("floorSize"):
                if isinstance(floor_size, dict):
                    val = floor_size.get("value")
                    if val:
                        prop.sqft = int(float(val))
                elif isinstance(floor_size, (int, float)):
                    prop.sqft = int(floor_size)

            # Beds/baths
            if beds := item.get("numberOfRooms"):
                prop.bedrooms = int(beds)
            if beds := item.get("numberOfBedrooms"):
                prop.bedrooms = int(beds)
            if baths := item.get("numberOfBathroomsTotal"):
                prop.bathrooms = float(baths)

            # Year built
            if year := item.get("yearBuilt"):
                prop.year_built = int(year)

        # Pricing from offers
        if "offers" in item:
            offers = item["offers"]
            if isinstance(offers, dict):
                if price := offers.get("price"):
                    prop.price = float(price)
        elif item_type == "Offer":
            if price := item.get("price"):
                prop.price = float(price)

    def _parse_next_data(self, data: dict, prop: ZillowProperty):
        """Parse Next.js hydration data for property info."""
        try:
            # Navigate to property data in the nested structure
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Try different possible paths
            property_data = (
                page_props.get("property") or
                page_props.get("initialData", {}).get("property") or
                page_props.get("componentProps", {}).get("property") or
                {}
            )

            if not property_data:
                # Search in initialReduxState
                redux = page_props.get("initialReduxState", {})
                gdp = redux.get("gdp", {})
                building = gdp.get("building") or {}
                property_data = building

            if property_data:
                # Price
                if price := property_data.get("price"):
                    prop.price = float(price)
                if price := property_data.get("listPrice"):
                    prop.price = float(price)

                # Zestimate
                if zest := property_data.get("zestimate"):
                    prop.zestimate = float(zest)

                # Beds/baths/sqft
                if beds := property_data.get("bedrooms"):
                    prop.bedrooms = int(beds)
                if baths := property_data.get("bathrooms"):
                    prop.bathrooms = float(baths)
                if sqft := property_data.get("livingArea"):
                    prop.sqft = int(sqft)

                # Year built
                if year := property_data.get("yearBuilt"):
                    prop.year_built = int(year)

                # Status
                if status := property_data.get("homeStatus"):
                    prop.status = status

                # Address
                if addr := property_data.get("address"):
                    if isinstance(addr, dict):
                        parts = [
                            addr.get("streetAddress", ""),
                            addr.get("city", ""),
                            addr.get("state", ""),
                            addr.get("zipcode", ""),
                        ]
                        prop.address = ", ".join(p for p in parts if p)
                    elif isinstance(addr, str):
                        prop.address = addr

        except Exception as e:
            logger.debug(f"Error parsing Next.js data: {e}")

    def _extract_from_html_regex(self, html: str, prop: ZillowProperty):
        """Fallback regex extraction from HTML."""
        # Price patterns
        price_patterns = [
            r'\$\s*([\d,]+)\s*(?:,\d{3})*',
            r'"price"\s*:\s*"?\$?([\d,]+)"?',
            r'"listPrice"\s*:\s*(\d+)',
        ]

        if not prop.price:
            for pattern in price_patterns:
                match = re.search(pattern, html)
                if match:
                    price_str = match.group(1).replace(",", "")
                    try:
                        price = float(price_str)
                        if 10000 < price < 100000000:  # Sanity check
                            prop.price = price
                            break
                    except ValueError:
                        continue

        # Zestimate
        if not prop.zestimate:
            zest_match = re.search(r'"zestimate"\s*:\s*(\d+)', html)
            if zest_match:
                prop.zestimate = float(zest_match.group(1))

        # Beds/Baths/Sqft from common patterns
        if not prop.bedrooms:
            bed_match = re.search(r'(\d+)\s*(?:bd|bed|bedroom)', html, re.I)
            if bed_match:
                prop.bedrooms = int(bed_match.group(1))

        if not prop.bathrooms:
            bath_match = re.search(r'([\d.]+)\s*(?:ba|bath|bathroom)', html, re.I)
            if bath_match:
                prop.bathrooms = float(bath_match.group(1))

        if not prop.sqft:
            sqft_match = re.search(r'([\d,]+)\s*(?:sqft|sq\s*ft|square)', html, re.I)
            if sqft_match:
                prop.sqft = int(sqft_match.group(1).replace(",", ""))

        # Year built
        if not prop.year_built:
            year_match = re.search(r'"yearBuilt"\s*:\s*(\d{4})', html)
            if year_match:
                prop.year_built = int(year_match.group(1))

    async def lookup_property(self, address: Address | str) -> Optional[ZillowProperty]:
        """Look up a property on Zillow by address.

        Args:
            address: Property address to search

        Returns:
            ZillowProperty if found, None otherwise
        """
        if not NODRIVER_AVAILABLE:
            logger.error("nodriver not available")
            return None

        if isinstance(address, Address):
            address_str = address.full_address
        else:
            address_str = address

        if not address_str:
            return None

        logger.info(f"Zillow lookup (nodriver): {address_str}")

        browser = await self._get_browser()

        try:
            # Create new tab
            tab = await browser.get(self._build_search_url(address_str))

            # Wait for page to load
            await self._random_delay(3, 5)

            # Check current URL - might have redirected to property page
            current_url = tab.target.url
            logger.debug(f"Current URL: {current_url}")

            # If we landed on a property detail page
            if "/homedetails/" in current_url:
                logger.info("Landed on property detail page")
                return await self._extract_property_data(tab, current_url)

            # Look for property cards in search results
            await self._random_delay(1, 2)

            # Try to find and click first result
            try:
                # Wait for search results
                cards = await tab.select_all('article[data-test="property-card"]')
                if not cards:
                    cards = await tab.select_all('.property-card')
                if not cards:
                    cards = await tab.select_all('[data-test="property-card-link"]')

                if cards:
                    logger.info(f"Found {len(cards)} property cards")
                    # Click first card
                    first_card = cards[0]
                    await first_card.click()
                    await self._random_delay(3, 5)

                    # Get new URL
                    current_url = tab.target.url
                    if "/homedetails/" in current_url:
                        return await self._extract_property_data(tab, current_url)

            except Exception as e:
                logger.debug(f"Error finding property cards: {e}")

            # Try extracting from search results page
            return await self._extract_property_data(tab, current_url)

        except Exception as e:
            logger.warning(f"Zillow lookup failed for {address_str}: {e}")
            return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


async def test_zillow_nodriver():
    """Test the nodriver Zillow scraper."""
    if not NODRIVER_AVAILABLE:
        print("nodriver not available - install with: pip install nodriver")
        return

    # Test addresses from our foreclosure data
    test_addresses = [
        "263 Echo Lane, Rock Hill, SC 29732",
        "4024 Redwood Drive, Rock Hill, SC 29732",
        "757 Jones Branch Drive, Fort Mill, SC 29708",
    ]

    scraper = ZillowNodriverScraper()

    try:
        for addr in test_addresses:
            print(f"\n{'='*60}")
            print(f"Looking up: {addr}")
            print('='*60)

            result = await scraper.lookup_property(addr)

            if result:
                print(f"  Address: {result.address}")
                print(f"  Price: ${result.price:,.0f}" if result.price else "  Price: N/A")
                print(f"  Zestimate: ${result.zestimate:,.0f}" if result.zestimate else "  Zestimate: N/A")
                print(f"  Beds: {result.bedrooms}, Baths: {result.bathrooms}")
                print(f"  Sqft: {result.sqft}")
                print(f"  Year Built: {result.year_built}")
                print(f"  Status: {result.status}")
                print(f"  URL: {result.listing_url}")
            else:
                print("  Not found")

            # Delay between lookups
            await asyncio.sleep(5)

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_zillow_nodriver())
