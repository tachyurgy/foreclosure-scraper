"""Zillow scraper using undetected-chromedriver for anti-bot evasion.

undetected-chromedriver patches Chrome to avoid detection by:
- Removing webdriver flag
- Patching navigator.webdriver
- Using real Chrome user agent
- Avoiding automation detection signatures
"""

import json
import random
import re
import time
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    logger.warning("undetected-chromedriver not available")

from config import ZillowConfig, config
from models import Address, ZillowProperty


class ZillowStealthScraper:
    """Zillow scraper using undetected-chromedriver for anti-bot evasion."""

    def __init__(self, zillow_config: Optional[ZillowConfig] = None, headless: bool = True):
        self.zillow_config = zillow_config or config.zillow
        self._driver = None
        self._headless = headless

    def _get_driver(self):
        """Get or create the undetected Chrome driver."""
        if self._driver is None:
            logger.info("Launching undetected Chrome browser...")

            options = uc.ChromeOptions()

            if self._headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-first-run')
            options.add_argument('--no-service-autorun')
            options.add_argument('--password-store=basic')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-extensions')

            # Create driver with version_main to avoid chromedriver version issues
            self._driver = uc.Chrome(
                options=options,
                use_subprocess=True,
            )

            # Set page load timeout
            self._driver.set_page_load_timeout(30)

        return self._driver

    def close(self):
        """Close the browser."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def _build_search_url(self, address: str) -> str:
        """Build Zillow search URL for an address."""
        encoded = quote_plus(address)
        return f"https://www.zillow.com/homes/{encoded}_rb/"

    def _random_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """Human-like random delay."""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.1f}s...")
        time.sleep(delay)

    def _scroll_page(self, driver):
        """Scroll page to simulate human behavior."""
        try:
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(0.5)
            driver.execute_script("window.scrollBy(0, 200);")
        except Exception:
            pass

    def _extract_property_data(self, driver, url: str) -> Optional[ZillowProperty]:
        """Extract property data from a Zillow page."""
        property_data = ZillowProperty(listing_url=url)

        try:
            html = driver.page_source

            # Extract from JSON-LD schema
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

            # Extract from __NEXT_DATA__
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

            # Fallback: regex extraction
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
            if addr := item.get("address"):
                if isinstance(addr, dict):
                    parts = [
                        addr.get("streetAddress", ""),
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("postalCode", ""),
                    ]
                    prop.address = ", ".join(p for p in parts if p)

            if floor_size := item.get("floorSize"):
                if isinstance(floor_size, dict):
                    val = floor_size.get("value")
                    if val:
                        prop.sqft = int(float(val))
                elif isinstance(floor_size, (int, float)):
                    prop.sqft = int(floor_size)

            if beds := item.get("numberOfRooms"):
                prop.bedrooms = int(beds)
            if beds := item.get("numberOfBedrooms"):
                prop.bedrooms = int(beds)
            if baths := item.get("numberOfBathroomsTotal"):
                prop.bathrooms = float(baths)
            if year := item.get("yearBuilt"):
                prop.year_built = int(year)

        if "offers" in item:
            offers = item["offers"]
            if isinstance(offers, dict):
                if price := offers.get("price"):
                    prop.price = float(price)
        elif item_type == "Offer":
            if price := item.get("price"):
                prop.price = float(price)

    def _parse_next_data(self, data: dict, prop: ZillowProperty):
        """Parse Next.js hydration data."""
        try:
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            property_data = (
                page_props.get("property") or
                page_props.get("initialData", {}).get("property") or
                page_props.get("componentProps", {}).get("property") or
                {}
            )

            if not property_data:
                redux = page_props.get("initialReduxState", {})
                gdp = redux.get("gdp", {})
                property_data = gdp.get("building") or {}

            if property_data:
                if price := property_data.get("price"):
                    prop.price = float(price)
                if price := property_data.get("listPrice"):
                    prop.price = float(price)
                if zest := property_data.get("zestimate"):
                    prop.zestimate = float(zest)
                if beds := property_data.get("bedrooms"):
                    prop.bedrooms = int(beds)
                if baths := property_data.get("bathrooms"):
                    prop.bathrooms = float(baths)
                if sqft := property_data.get("livingArea"):
                    prop.sqft = int(sqft)
                if year := property_data.get("yearBuilt"):
                    prop.year_built = int(year)
                if status := property_data.get("homeStatus"):
                    prop.status = status
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
        """Fallback regex extraction."""
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
                        if 10000 < price < 100000000:
                            prop.price = price
                            break
                    except ValueError:
                        continue

        if not prop.zestimate:
            zest_match = re.search(r'"zestimate"\s*:\s*(\d+)', html)
            if zest_match:
                prop.zestimate = float(zest_match.group(1))

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

        if not prop.year_built:
            year_match = re.search(r'"yearBuilt"\s*:\s*(\d{4})', html)
            if year_match:
                prop.year_built = int(year_match.group(1))

    def lookup_property(self, address: Address | str) -> Optional[ZillowProperty]:
        """Look up a property on Zillow by address.

        Args:
            address: Property address to search

        Returns:
            ZillowProperty if found, None otherwise
        """
        if not UC_AVAILABLE:
            logger.error("undetected-chromedriver not available")
            return None

        if isinstance(address, Address):
            address_str = address.full_address
        else:
            address_str = address

        if not address_str:
            return None

        logger.info(f"Zillow lookup (stealth): {address_str}")

        driver = self._get_driver()

        try:
            search_url = self._build_search_url(address_str)
            logger.debug(f"Navigating to: {search_url}")

            driver.get(search_url)
            self._random_delay(3, 5)
            self._scroll_page(driver)

            current_url = driver.current_url
            logger.debug(f"Current URL: {current_url}")

            # Check if we're on a property detail page
            if "/homedetails/" in current_url:
                logger.info("Landed on property detail page")
                return self._extract_property_data(driver, current_url)

            # Try to find and click first result
            try:
                wait = WebDriverWait(driver, 10)

                # Look for property cards
                selectors = [
                    'article[data-test="property-card"]',
                    '.property-card',
                    '[data-test="property-card-link"]',
                    '.list-card',
                    'a[data-test="property-card-link"]',
                ]

                for selector in selectors:
                    try:
                        cards = driver.find_elements(By.CSS_SELECTOR, selector)
                        if cards:
                            logger.info(f"Found {len(cards)} property cards")

                            # Click first card
                            first_card = cards[0]
                            driver.execute_script("arguments[0].click();", first_card)
                            self._random_delay(3, 5)

                            current_url = driver.current_url
                            if "/homedetails/" in current_url:
                                return self._extract_property_data(driver, current_url)
                            break
                    except NoSuchElementException:
                        continue

            except TimeoutException:
                logger.debug("Timeout waiting for property cards")

            # Try extracting from current page
            return self._extract_property_data(driver, current_url)

        except Exception as e:
            logger.warning(f"Zillow lookup failed for {address_str}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_zillow_stealth():
    """Test the stealth Zillow scraper."""
    if not UC_AVAILABLE:
        print("undetected-chromedriver not available")
        return

    test_addresses = [
        "263 Echo Lane, Rock Hill, SC 29732",
        "4024 Redwood Drive, Rock Hill, SC 29732",
        "757 Jones Branch Drive, Fort Mill, SC 29708",
    ]

    # Use headed mode for testing
    scraper = ZillowStealthScraper(headless=False)

    try:
        for addr in test_addresses:
            print(f"\n{'='*60}")
            print(f"Looking up: {addr}")
            print('='*60)

            result = scraper.lookup_property(addr)

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

            time.sleep(5)

    finally:
        scraper.close()


if __name__ == "__main__":
    test_zillow_stealth()
