"""York County Court Roster scraper for foreclosure cases."""

import asyncio
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from config import CountyConfig, config
from models import Address, Attorney, ForeclosureCase

from .base import BaseScraper


class CountyCourtScraper(BaseScraper):
    """Scraper for York County SC court rosters to extract foreclosure cases."""

    def __init__(self, county_config: Optional[CountyConfig] = None):
        super().__init__()
        self.county_config = county_config or config.county
        self._browser: Optional[Browser] = None

    async def _get_browser(self) -> Browser:
        """Get or create the Playwright browser instance."""
        if self._browser is None:
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ]
            )
        return self._browser

    async def close(self) -> None:
        """Close browser and HTTP client."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        await super().close()

    async def _accept_disclaimer(self, page: Page) -> bool:
        """Accept the disclaimer page if present.

        Returns:
            True if disclaimer was accepted or not present, False on failure
        """
        # Check for disclaimer checkbox
        checkbox_selectors = [
            "input[type='checkbox']",
            "#disclaimer",
            "[name='accept']",
            "[name='disclaimer']",
        ]

        for selector in checkbox_selectors:
            checkbox = await page.query_selector(selector)
            if checkbox:
                try:
                    # Check if not already checked
                    is_checked = await checkbox.is_checked()
                    if not is_checked:
                        await checkbox.click()
                        logger.info("Accepted disclaimer checkbox")
                        await page.wait_for_timeout(500)
                    break
                except Exception as e:
                    logger.debug(f"Error clicking checkbox: {e}")

        # Look for submit/continue button
        submit_selectors = [
            "input[type='submit']",
            "button[type='submit']",
            "input[value*='Continue']",
            "input[value*='Accept']",
            "input[value*='Enter']",
            "button:has-text('Continue')",
            "button:has-text('Accept')",
            "a:has-text('Continue')",
        ]

        for selector in submit_selectors:
            button = await page.query_selector(selector)
            if button:
                try:
                    await button.click()
                    logger.info("Clicked submit/continue button")
                    await page.wait_for_timeout(2000)
                    return True
                except Exception as e:
                    logger.debug(f"Error clicking button: {e}")

        return False

    async def _navigate_to_rosters(self, page: Page) -> None:
        """Navigate to the court rosters page and wait for content."""
        url = self.county_config.base_url
        logger.info(f"Navigating to {url}")

        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)  # Allow dynamic content to load

        # Check for and accept disclaimer if present
        page_text = await page.content()
        if "disclaimer" in page_text.lower() or "accept" in page_text.lower():
            logger.info("Disclaimer page detected, attempting to accept...")
            accepted = await self._accept_disclaimer(page)
            if accepted:
                await page.wait_for_timeout(2000)
            else:
                logger.warning("Could not accept disclaimer automatically")

    async def _get_available_dates(self, page: Page) -> list[str]:
        """Get list of available court dates from the roster."""
        dates = []

        # Look for date selectors or links
        date_elements = await page.query_selector_all(
            "select option, a[href*='date'], .court-date, .roster-date"
        )

        for elem in date_elements:
            text = await elem.text_content()
            if text:
                dates.append(text.strip())

        return dates

    async def _select_foreclosure_cases(self, page: Page) -> None:
        """Filter or navigate to foreclosure-specific cases."""
        # Try to find and click on foreclosure filter/category
        selectors = [
            "text=Foreclosure",
            "text=FORECLOSURE",
            "option:has-text('Foreclosure')",
            "a:has-text('Foreclosure')",
            "[data-case-type='foreclosure']",
        ]

        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    await page.wait_for_timeout(1000)
                    logger.info("Selected foreclosure filter")
                    return
            except Exception:
                continue

        logger.warning("Could not find foreclosure filter, will scrape all cases")

    async def _extract_cases_from_page(self, page: Page) -> list[ForeclosureCase]:
        """Extract foreclosure case data from the current page."""
        cases = []

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # Find case entries - adjust selectors based on actual page structure
        case_rows = soup.select(
            "table tr, .case-row, .roster-entry, [data-case], .case-item"
        )

        for row in case_rows:
            try:
                case = self._parse_case_row(row)
                if case and self._is_foreclosure_case(case):
                    cases.append(case)
            except Exception as e:
                logger.debug(f"Error parsing case row: {e}")
                continue

        # Also look for detail pages/links
        detail_links = soup.select("a[href*='case'], a[href*='detail'], a[href*='view']")
        for link in detail_links[:20]:  # Limit to avoid too many requests
            href = link.get("href")
            if href and "foreclosure" in href.lower():
                try:
                    case = await self._scrape_case_detail(page, href)
                    if case:
                        cases.append(case)
                except Exception as e:
                    logger.debug(f"Error scraping case detail: {e}")

        return cases

    def _parse_case_row(self, row) -> Optional[ForeclosureCase]:
        """Parse a case row from the roster table."""
        cells = row.find_all(["td", "span", "div"])
        if len(cells) < 3:
            return None

        text_content = row.get_text(" ", strip=True)

        # Look for case number pattern (e.g., 2024CP4600123)
        case_num_match = re.search(r"\d{4}[A-Z]{2}\d{7,}", text_content)
        if not case_num_match:
            # Try alternative patterns
            case_num_match = re.search(r"\d{2,4}-[A-Z]{1,4}-\d{3,}", text_content)

        if not case_num_match:
            return None

        case_number = case_num_match.group()

        # Extract other fields
        case = ForeclosureCase(
            case_number=case_number,
            source_url=self.county_config.base_url,
        )

        # Try to extract names and other details
        self._extract_names(text_content, case)
        self._extract_dates(text_content, case)
        self._extract_address(text_content, case)

        return case

    def _extract_names(self, text: str, case: ForeclosureCase) -> None:
        """Extract plaintiff and defendant names from text."""
        # Common patterns for party names
        vs_match = re.search(r"(.+?)\s+(?:vs?\.?|versus)\s+(.+?)(?:\s*$|\s+\d)", text, re.IGNORECASE)
        if vs_match:
            case.plaintiff_name = vs_match.group(1).strip()

            defendant_text = vs_match.group(2).strip()
            # Try to split first/last name
            name_parts = defendant_text.split()
            if len(name_parts) >= 2:
                case.defendant_first_name = name_parts[0]
                case.defendant_last_name = " ".join(name_parts[1:])
            else:
                case.defendant_last_name = defendant_text

    def _extract_dates(self, text: str, case: ForeclosureCase) -> None:
        """Extract dates from text."""
        # Look for date patterns
        date_pattern = r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"
        dates = re.findall(date_pattern, text)

        if dates:
            case.hearing_date = dates[0]
            if len(dates) > 1:
                case.filing_date = dates[1]

    def _extract_address(self, text: str, case: ForeclosureCase) -> None:
        """Extract property address from text."""
        # Look for South Carolina address patterns
        address_pattern = r"(\d+\s+[A-Za-z0-9\s]+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Way|Blvd|Boulevard|Cir|Circle)[.\s,]+[A-Za-z\s]+,?\s*(?:SC|South Carolina)?\s*\d{5})"

        match = re.search(address_pattern, text, re.IGNORECASE)
        if match:
            full_addr = match.group(1)
            self._parse_address_string(full_addr, case.property_address)

    def _parse_address_string(self, address_str: str, address: Address) -> None:
        """Parse an address string into components."""
        # Try to extract zip code
        zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", address_str)
        if zip_match:
            address.zip_code = zip_match.group(1)

        # Extract city (before SC or zip)
        city_match = re.search(r",\s*([A-Za-z\s]+?)(?:,?\s*(?:SC|South Carolina|\d{5}))", address_str)
        if city_match:
            address.city = city_match.group(1).strip()

        # Street is everything before city
        if address.city:
            street_part = address_str.split(address.city)[0]
            address.street = street_part.strip().rstrip(",")

        address.state = "SC"

    def _is_foreclosure_case(self, case: ForeclosureCase) -> bool:
        """Check if a case is a foreclosure case."""
        indicators = ["foreclosure", "mortgage", "default", "lien"]

        text_to_check = " ".join([
            case.case_type,
            case.plaintiff_name,
            case.case_number,
        ]).lower()

        return any(ind in text_to_check for ind in indicators)

    async def _scrape_case_detail(self, page: Page, href: str) -> Optional[ForeclosureCase]:
        """Scrape detailed case information from a detail page."""
        # Construct full URL if relative
        if not href.startswith("http"):
            base = self.county_config.base_url.rstrip("/")
            href = f"{base}/{href.lstrip('/')}"

        await self._rate_limit()

        try:
            await page.goto(href, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Extract case details from the detail page
            case = ForeclosureCase(
                case_number="",
                source_url=href,
            )

            # Look for labeled fields
            self._extract_labeled_fields(soup, case)

            if case.case_number:
                return case

        except PlaywrightTimeout:
            logger.warning(f"Timeout loading case detail: {href}")
        except Exception as e:
            logger.debug(f"Error scraping case detail {href}: {e}")

        return None

    def _extract_labeled_fields(self, soup: BeautifulSoup, case: ForeclosureCase) -> None:
        """Extract fields from labeled elements on detail page."""
        # Common label patterns for court sites
        label_mappings = {
            "case number": "case_number",
            "case no": "case_number",
            "file number": "case_number",
            "plaintiff": "plaintiff_name",
            "petitioner": "plaintiff_name",
            "defendant": "defendant_last_name",
            "respondent": "defendant_last_name",
            "hearing date": "hearing_date",
            "court date": "hearing_date",
            "file date": "filing_date",
            "filing date": "filing_date",
            "property": "property_address.street",
            "address": "property_address.street",
            "attorney": "plaintiff_attorney.name",
        }

        for label, field in label_mappings.items():
            # Try different selector patterns
            selectors = [
                f"td:contains('{label}') + td",
                f"th:contains('{label}') + td",
                f".label:contains('{label}') + .value",
                f"dt:contains('{label}') + dd",
            ]

            for selector in selectors:
                try:
                    elements = soup.select(selector)
                    if elements:
                        value = elements[0].get_text(strip=True)
                        self._set_nested_field(case, field, value)
                        break
                except Exception:
                    continue

    def _set_nested_field(self, obj, field_path: str, value: str) -> None:
        """Set a potentially nested field value."""
        parts = field_path.split(".")
        target = obj

        for part in parts[:-1]:
            target = getattr(target, part)

        setattr(target, parts[-1], value)

    async def scrape(self) -> list[ForeclosureCase]:
        """Main method to scrape foreclosure cases from York County court roster."""
        logger.info("Starting York County court roster scrape")
        cases = []

        browser = await self._get_browser()
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.config.user_agents[0],
        )

        try:
            page = await context.new_page()

            await self._navigate_to_rosters(page)
            await self._select_foreclosure_cases(page)

            # Extract cases from main page
            page_cases = await self._extract_cases_from_page(page)
            cases.extend(page_cases)

            # Check for pagination
            while True:
                next_button = await page.query_selector(
                    "a:has-text('Next'), button:has-text('Next'), .pagination-next, [aria-label='Next']"
                )
                if not next_button:
                    break

                try:
                    await next_button.click()
                    await page.wait_for_timeout(2000)
                    page_cases = await self._extract_cases_from_page(page)
                    if not page_cases:
                        break
                    cases.extend(page_cases)
                except Exception as e:
                    logger.debug(f"Error navigating to next page: {e}")
                    break

            logger.info(f"Scraped {len(cases)} foreclosure cases from York County")

        finally:
            await context.close()

        return cases


async def main():
    """Test the county court scraper."""
    async with CountyCourtScraper() as scraper:
        cases = await scraper.scrape()
        for case in cases[:5]:
            print(f"\nCase: {case.case_number}")
            print(f"  Plaintiff: {case.plaintiff_name}")
            print(f"  Defendant: {case.defendant_full_name}")
            print(f"  Address: {case.property_address}")


if __name__ == "__main__":
    asyncio.run(main())
