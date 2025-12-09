"""Zillow scraper using stealth-requests for TLS fingerprint impersonation.

Uses the same TLS fingerprint bypass approach that works for the county court site.
curl_cffi impersonates a real browser's TLS handshake to evade detection.
"""

import json
import random
import re
import time
from typing import Optional
from urllib.parse import quote_plus

from loguru import logger

try:
    from stealth_requests import StealthSession
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    logger.warning("stealth-requests not available")

from config import ZillowConfig, config
from models import Address, ZillowProperty


class ZillowTLSScraper:
    """Zillow scraper using stealth-requests for TLS fingerprint impersonation."""

    def __init__(self, zillow_config: Optional[ZillowConfig] = None):
        self.zillow_config = zillow_config or config.zillow
        self._session = None
        self._cookies = {}

    def _create_session(self):
        """Create a stealth session with browser impersonation."""
        if not STEALTH_AVAILABLE:
            raise RuntimeError("stealth-requests library not installed")

        session = StealthSession(
            timeout=60,
            verify=True,
        )
        return session

    def _random_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        """Human-like random delay."""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.1f}s...")
        time.sleep(delay)

    def _get(self, url: str, **kwargs):
        """Make a GET request with stealth session."""
        if self._session is None:
            self._session = self._create_session()

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        if self._cookies:
            kwargs['cookies'] = self._cookies

        response = self._session.get(url, headers=headers, **kwargs)

        if hasattr(response, 'cookies'):
            self._cookies.update(dict(response.cookies))

        return response

    def _build_search_url(self, address: str) -> str:
        """Build Zillow search URL for an address."""
        encoded = quote_plus(address)
        return f"https://www.zillow.com/homes/{encoded}_rb/"

    def _build_homedetails_url(self, zpid: str) -> str:
        """Build Zillow homedetails URL."""
        return f"https://www.zillow.com/homedetails/{zpid}_zpid/"

    def _extract_zpid_from_search(self, html: str) -> Optional[str]:
        """Extract ZPID from search results."""
        # Look for ZPID in various places
        patterns = [
            r'"zpid"\s*:\s*"?(\d+)"?',
            r'/homedetails/[^/]+-(\d+)_zpid',
            r'data-zpid="(\d+)"',
            r'"propertyId"\s*:\s*"?(\d+)"?',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)

        return None

    def _extract_property_from_json(self, html: str) -> Optional[ZillowProperty]:
        """Extract property data from embedded JSON."""
        prop = ZillowProperty()

        # Try to find JSON data in script tags
        # Zillow embeds property data in __NEXT_DATA__ and other places
        patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            r'"propertyDetails"\s*:\s*({[^}]+})',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    self._parse_json_data(data, prop)
                    if prop.price or prop.zestimate:
                        return prop
                except json.JSONDecodeError:
                    continue

        # Fallback: regex extraction
        self._extract_from_html_regex(html, prop)

        if prop.price or prop.zestimate or prop.sqft:
            return prop

        return None

    def _parse_json_data(self, data: dict, prop: ZillowProperty, path: str = ""):
        """Recursively parse JSON data looking for property info."""
        if not isinstance(data, dict):
            return

        # Look for property-related keys
        if 'price' in data and isinstance(data['price'], (int, float)):
            prop.price = float(data['price'])
        if 'listPrice' in data and isinstance(data['listPrice'], (int, float)):
            prop.price = float(data['listPrice'])
        if 'zestimate' in data and isinstance(data['zestimate'], (int, float)):
            prop.zestimate = float(data['zestimate'])
        if 'bedrooms' in data and data['bedrooms'] is not None:
            prop.bedrooms = int(data['bedrooms'])
        if 'bathrooms' in data and data['bathrooms'] is not None:
            prop.bathrooms = float(data['bathrooms'])
        if 'livingArea' in data and data['livingArea'] is not None:
            prop.sqft = int(data['livingArea'])
        if 'yearBuilt' in data and data['yearBuilt'] is not None:
            prop.year_built = int(data['yearBuilt'])
        if 'homeStatus' in data:
            prop.status = data['homeStatus']
        if 'zpid' in data:
            prop.zpid = str(data['zpid'])

        # Handle address
        if 'address' in data:
            addr = data['address']
            if isinstance(addr, dict):
                parts = [
                    addr.get('streetAddress', ''),
                    addr.get('city', ''),
                    addr.get('state', ''),
                    addr.get('zipcode', ''),
                ]
                prop.address = ', '.join(p for p in parts if p)

        # Recurse into nested objects
        for key, value in data.items():
            if isinstance(value, dict):
                self._parse_json_data(value, prop, f"{path}.{key}")
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._parse_json_data(item, prop, f"{path}.{key}[{i}]")

    def _extract_from_html_regex(self, html: str, prop: ZillowProperty):
        """Fallback regex extraction from HTML."""
        # Price
        if not prop.price:
            price_patterns = [
                r'"price"\s*:\s*(\d+)',
                r'"listPrice"\s*:\s*(\d+)',
                r'\$\s*([\d,]+)(?:,\d{3})*\s*(?:\/mo|per month)?',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, html)
                if match:
                    price_str = match.group(1).replace(',', '')
                    try:
                        price = float(price_str)
                        if 10000 < price < 100000000:
                            prop.price = price
                            break
                    except ValueError:
                        continue

        # Zestimate
        if not prop.zestimate:
            match = re.search(r'"zestimate"\s*:\s*(\d+)', html)
            if match:
                prop.zestimate = float(match.group(1))

        # Beds/Baths/Sqft
        if not prop.bedrooms:
            match = re.search(r'"bedrooms"\s*:\s*(\d+)', html)
            if match:
                prop.bedrooms = int(match.group(1))

        if not prop.bathrooms:
            match = re.search(r'"bathrooms"\s*:\s*([\d.]+)', html)
            if match:
                prop.bathrooms = float(match.group(1))

        if not prop.sqft:
            match = re.search(r'"livingArea"\s*:\s*(\d+)', html)
            if match:
                prop.sqft = int(match.group(1))

        # Year built
        if not prop.year_built:
            match = re.search(r'"yearBuilt"\s*:\s*(\d{4})', html)
            if match:
                prop.year_built = int(match.group(1))

    def lookup_property(self, address: Address | str) -> Optional[ZillowProperty]:
        """Look up a property on Zillow by address."""
        if not STEALTH_AVAILABLE:
            logger.error("stealth-requests not available")
            return None

        if isinstance(address, Address):
            address_str = address.full_address
        else:
            address_str = address

        if not address_str:
            return None

        logger.info(f"Zillow lookup (TLS stealth): {address_str}")

        try:
            # First, try the search page
            search_url = self._build_search_url(address_str)
            logger.debug(f"Fetching: {search_url}")

            response = self._get(search_url)
            logger.info(f"Search response: {response.status_code}")

            if response.status_code != 200:
                logger.warning(f"Got status {response.status_code}")
                return None

            html = response.text
            logger.debug(f"Response length: {len(html)}")

            # Check for blocking
            if 'Access to this page has been denied' in html:
                logger.warning("Access denied - bot detection triggered")
                return None

            if 'captcha' in html.lower():
                logger.warning("Captcha detected")
                return None

            # Try to extract property data directly
            prop = self._extract_property_from_json(html)

            if prop and (prop.price or prop.zestimate):
                prop.listing_url = response.url
                logger.info(f"Found property: ${prop.price:,.0f}" if prop.price else "Found property (no price)")
                return prop

            # Try to find ZPID and fetch property page
            zpid = self._extract_zpid_from_search(html)
            if zpid:
                logger.info(f"Found ZPID: {zpid}")
                self._random_delay(2, 4)

                # Fetch homedetails page
                details_url = self._build_homedetails_url(zpid)
                response = self._get(details_url, headers={'Referer': search_url})

                if response.status_code == 200:
                    html = response.text
                    prop = self._extract_property_from_json(html)
                    if prop:
                        prop.zpid = zpid
                        prop.listing_url = response.url
                        return prop

            logger.info("No property data found")
            return None

        except Exception as e:
            logger.warning(f"Zillow lookup failed: {e}")
            return None

    def close(self):
        """Close the session."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_zillow_tls():
    """Test the TLS Zillow scraper."""
    if not STEALTH_AVAILABLE:
        print("stealth-requests not available")
        return

    test_addresses = [
        "263 Echo Lane, Rock Hill, SC 29732",
        "4024 Redwood Drive, Rock Hill, SC 29732",
    ]

    scraper = ZillowTLSScraper()

    try:
        for addr in test_addresses:
            print(f"\n{'='*60}")
            print(f"Looking up: {addr}")
            print('='*60)

            result = scraper.lookup_property(addr)

            if result:
                print(f"  Price: ${result.price:,.0f}" if result.price else "  Price: N/A")
                print(f"  Zestimate: ${result.zestimate:,.0f}" if result.zestimate else "  Zestimate: N/A")
                print(f"  Beds: {result.bedrooms}, Baths: {result.bathrooms}")
                print(f"  Sqft: {result.sqft}")
                print(f"  Year Built: {result.year_built}")
            else:
                print("  Not found")

            time.sleep(5)

    finally:
        scraper.close()


if __name__ == "__main__":
    test_zillow_tls()
