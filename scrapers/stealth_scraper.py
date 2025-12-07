"""Stealth scraper with human-like behavior for anti-bot evasion."""

import asyncio
import random
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from config import CountyConfig, config
from models import Address, Attorney, ForeclosureCase


class HumanBehavior:
    """Simulate human-like behavior patterns."""

    @staticmethod
    async def random_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        """Wait a random amount of time."""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Human delay: {delay:.2f}s")
        await asyncio.sleep(delay)

    @staticmethod
    async def long_delay() -> None:
        """Long delay between major actions (10-30 seconds as requested)."""
        delay = random.uniform(10.0, 30.0)
        logger.info(f"Long human delay: {delay:.1f}s")
        await asyncio.sleep(delay)

    @staticmethod
    async def type_like_human(page: Page, selector: str, text: str) -> None:
        """Type text character by character with random delays."""
        element = await page.query_selector(selector)
        if not element:
            logger.warning(f"Element not found: {selector}")
            return

        await element.click()
        await HumanBehavior.random_delay(0.3, 0.8)

        for char in text:
            await page.keyboard.type(char)
            # Random delay between keystrokes (50-200ms)
            await asyncio.sleep(random.uniform(0.05, 0.20))
            # Occasionally pause longer (like thinking)
            if random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.3, 0.8))

        await HumanBehavior.random_delay(0.2, 0.5)

    @staticmethod
    async def move_mouse_naturally(page: Page, x: int, y: int) -> None:
        """Move mouse in a natural curved path."""
        # Get current position (approximate)
        current_x = random.randint(100, 500)
        current_y = random.randint(100, 500)

        # Calculate steps
        steps = random.randint(10, 25)
        for i in range(steps):
            progress = (i + 1) / steps
            # Add some curve/noise
            noise_x = random.uniform(-5, 5)
            noise_y = random.uniform(-5, 5)

            new_x = current_x + (x - current_x) * progress + noise_x
            new_y = current_y + (y - current_y) * progress + noise_y

            await page.mouse.move(new_x, new_y)
            await asyncio.sleep(random.uniform(0.01, 0.03))

    @staticmethod
    async def click_like_human(page: Page, element) -> None:
        """Click an element with human-like behavior."""
        # Scroll element into view
        await element.scroll_into_view_if_needed()
        await HumanBehavior.random_delay(0.3, 0.8)

        # Get element bounding box
        box = await element.bounding_box()
        if box:
            # Click at a random point within the element
            x = box['x'] + random.uniform(box['width'] * 0.2, box['width'] * 0.8)
            y = box['y'] + random.uniform(box['height'] * 0.2, box['height'] * 0.8)

            # Move mouse naturally to the element
            await HumanBehavior.move_mouse_naturally(page, int(x), int(y))

            await HumanBehavior.random_delay(0.1, 0.3)
            await page.mouse.click(x, y)
        else:
            # Fallback to regular click
            await element.click()

        await HumanBehavior.random_delay(0.5, 1.5)

    @staticmethod
    async def scroll_naturally(page: Page) -> None:
        """Scroll the page in a natural way."""
        scroll_amount = random.randint(100, 400)
        steps = random.randint(5, 15)

        for _ in range(steps):
            await page.mouse.wheel(0, scroll_amount // steps)
            await asyncio.sleep(random.uniform(0.05, 0.15))

        await HumanBehavior.random_delay(0.5, 1.5)


class StealthCountyScraper:
    """Stealth scraper for York County court rosters with human-like behavior."""

    def __init__(self, county_config: Optional[CountyConfig] = None):
        self.county_config = county_config or config.county
        self._browser: Optional[Browser] = None
        self._playwright = None
        self.human = HumanBehavior()

    async def _get_browser(self) -> Browser:
        """Get browser with stealth configuration."""
        if self._browser is None:
            self._playwright = await async_playwright().start()

            # Launch with stealth args
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                ]
            )
        return self._browser

    async def _create_stealth_context(self) -> BrowserContext:
        """Create a browser context with stealth settings."""
        browser = await self._get_browser()

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            geolocation={'latitude': 34.9249, 'longitude': -81.0251},  # Rock Hill, SC
            permissions=['geolocation'],
            color_scheme='light',
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
        )

        # Add stealth scripts to every page
        await context.add_init_script("""
            // Overwrite navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Overwrite plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    },
                    {
                        0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                        description: "Portable Document Format",
                        filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                        length: 1,
                        name: "Chrome PDF Viewer"
                    }
                ]
            });

            // Overwrite languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Overwrite platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'MacIntel'
            });

            // Add Chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Prevent iframe detection
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    return window;
                }
            });
        """)

        return context

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _accept_disclaimer(self, page: Page) -> bool:
        """Accept the disclaimer with human-like behavior."""
        logger.info("Looking for disclaimer...")

        # Random initial delay like a human reading
        await self.human.random_delay(2.0, 4.0)

        # Scroll down a bit to "read" the disclaimer
        await self.human.scroll_naturally(page)
        await self.human.random_delay(1.5, 3.0)

        # Find and click checkbox
        checkbox = await page.query_selector('input[type="checkbox"]')
        if checkbox:
            logger.info("Found checkbox, clicking...")
            await self.human.click_like_human(page, checkbox)
            await self.human.random_delay(0.8, 1.5)

        # Find and click submit
        submit = await page.query_selector('input[type="submit"]')
        if submit:
            logger.info("Found submit button, clicking...")
            await self.human.click_like_human(page, submit)
            return True

        return False

    async def _navigate_to_roster(self, page: Page, roster_text: str) -> bool:
        """Navigate to a specific roster with human-like behavior."""
        # Find the roster link
        links = await page.query_selector_all('a')

        for link in links:
            text = await link.text_content()
            if text and roster_text.lower() in text.lower():
                logger.info(f"Found roster link: {text.strip()[:50]}")

                # Scroll to make it visible
                await link.scroll_into_view_if_needed()
                await self.human.random_delay(0.5, 1.0)

                # Click with human behavior
                await self.human.click_like_human(page, link)

                # Long wait after navigation
                await self.human.long_delay()

                return True

        return False

    def _extract_cases_from_html(self, html: str, source_url: str) -> list[ForeclosureCase]:
        """Extract foreclosure cases from HTML content."""
        cases = []
        soup = BeautifulSoup(html, 'lxml')

        # Look for table rows with case data
        rows = soup.select('table tr, .case-row, .roster-entry, div[class*="case"]')

        for row in rows:
            text = row.get_text(' ', strip=True)

            # Look for case number patterns
            case_match = re.search(r'(\d{4}[A-Z]{2}46\d{5}|\d{4}-[A-Z]+-\d+)', text)
            if not case_match:
                continue

            case = ForeclosureCase(
                case_number=case_match.group(1),
                source_url=source_url,
            )

            # Extract party names (plaintiff v. defendant pattern)
            vs_match = re.search(r'([A-Za-z\s,]+?)\s+(?:vs?\.?|V\.?)\s+([A-Za-z\s,]+)', text, re.IGNORECASE)
            if vs_match:
                case.plaintiff_name = vs_match.group(1).strip()
                defendant = vs_match.group(2).strip()
                parts = defendant.split()
                if len(parts) >= 2:
                    case.defendant_first_name = parts[0]
                    case.defendant_last_name = ' '.join(parts[1:])
                else:
                    case.defendant_last_name = defendant

            # Extract dates
            dates = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text)
            if dates:
                case.hearing_date = dates[0]

            # Extract address if present
            addr_match = re.search(
                r'(\d+\s+[A-Za-z0-9\s]+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Way|Blvd)[^,]*,\s*[A-Za-z\s]+,?\s*(?:SC)?\s*\d{5})',
                text, re.IGNORECASE
            )
            if addr_match:
                self._parse_address(addr_match.group(1), case.property_address)

            cases.append(case)

        return cases

    def _parse_address(self, addr_str: str, address: Address) -> None:
        """Parse address string into Address model."""
        # Extract zip
        zip_match = re.search(r'(\d{5})(?:-\d{4})?', addr_str)
        if zip_match:
            address.zip_code = zip_match.group(1)

        # Extract city
        city_match = re.search(r',\s*([A-Za-z\s]+?)(?:,?\s*(?:SC|South Carolina|\d{5}))', addr_str)
        if city_match:
            address.city = city_match.group(1).strip()

        # Street is everything before city
        if address.city:
            parts = addr_str.split(address.city)
            if parts:
                address.street = parts[0].strip().rstrip(',')

        address.state = 'SC'

    async def scrape(self) -> list[ForeclosureCase]:
        """Scrape foreclosure cases with full stealth and human-like behavior."""
        logger.info("Starting stealth scrape of York County court rosters...")
        all_cases = []

        context = await self._create_stealth_context()

        try:
            page = await context.new_page()

            # Initial navigation
            logger.info("Navigating to court rosters...")
            await page.goto(
                self.county_config.base_url,
                wait_until='networkidle',
                timeout=60000
            )

            # Human-like reading delay
            await self.human.random_delay(2.0, 4.0)

            # Accept disclaimer
            disclaimer_accepted = await self._accept_disclaimer(page)
            if disclaimer_accepted:
                logger.info("Disclaimer accepted, waiting for page load...")
                await page.wait_for_load_state('networkidle')
                await self.human.long_delay()

            # Check current URL
            logger.info(f"Current URL: {page.url}")

            # Take screenshot
            await page.screenshot(path='screenshots/stealth_roster_selection.png', full_page=True)

            # Look for Sales rosters (foreclosure sales)
            roster_names = ['Sales 11:00']
            for roster_name in roster_names:
                logger.info(f"Looking for roster: {roster_name}")

                if await self._navigate_to_roster(page, roster_name):
                    logger.info("Successfully navigated to roster")

                    # Wait for content to load
                    await page.wait_for_load_state('networkidle')
                    await self.human.random_delay(2.0, 4.0)

                    # Get page content
                    html = await page.content()
                    body_text = await page.evaluate('() => document.body.innerText')

                    logger.info(f"Page HTML length: {len(html)}")
                    logger.info(f"Page body text length: {len(body_text)}")

                    # Take screenshot
                    await page.screenshot(path='screenshots/stealth_roster_detail.png', full_page=True)

                    if len(html) > 500:
                        # Extract cases
                        cases = self._extract_cases_from_html(html, page.url)
                        all_cases.extend(cases)
                        logger.info(f"Extracted {len(cases)} cases from roster")

                        # Save content for debugging
                        with open('screenshots/stealth_content.html', 'w') as f:
                            f.write(html)
                        with open('screenshots/stealth_text.txt', 'w') as f:
                            f.write(body_text)
                    else:
                        logger.warning(f"Page content too short: {len(html)} bytes")
                        logger.info(f"Body preview: {body_text[:500] if body_text else 'empty'}")

                    # Long delay before next roster
                    await self.human.long_delay()

            logger.info(f"Total cases extracted: {len(all_cases)}")

        except Exception as e:
            logger.exception(f"Scrape failed: {e}")
        finally:
            await context.close()

        return all_cases

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


async def main():
    """Test the stealth scraper."""
    import os
    os.makedirs('screenshots', exist_ok=True)

    async with StealthCountyScraper() as scraper:
        cases = await scraper.scrape()
        print(f"\nFound {len(cases)} cases:")
        for case in cases[:5]:
            print(f"  {case.case_number}: {case.plaintiff_name} v. {case.defendant_full_name}")


if __name__ == "__main__":
    asyncio.run(main())
