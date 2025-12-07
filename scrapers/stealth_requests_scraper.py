"""Scraper using stealth-requests library for anti-bot evasion."""

import asyncio
import random
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger

try:
    from stealth_requests import StealthSession
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    logger.warning("stealth-requests not available, falling back to regular requests")

from config import CountyConfig, config
from models import Address, ForeclosureCase


class StealthRequestsScraper:
    """Scraper using stealth-requests for bypassing anti-bot protection.

    stealth-requests uses curl_cffi which impersonates real browser TLS fingerprints,
    making it much harder to detect as a bot.
    """

    def __init__(self, county_config: Optional[CountyConfig] = None):
        self.county_config = county_config or config.county
        self.session: Optional[StealthSession] = None
        self._cookies = {}

    def _create_session(self) -> StealthSession:
        """Create a stealth session with browser impersonation."""
        if not STEALTH_AVAILABLE:
            raise RuntimeError("stealth-requests library not installed")

        # Create session that impersonates Chrome
        # StealthSession already defaults to Chrome impersonation
        session = StealthSession(
            timeout=60,
            verify=True,
        )
        return session

    async def _random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        """Random delay to simulate human behavior."""
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Waiting {delay:.2f}s")
        await asyncio.sleep(delay)

    async def _long_delay(self) -> None:
        """Long delay between major requests (10-30 seconds)."""
        delay = random.uniform(10.0, 30.0)
        logger.info(f"Long delay: {delay:.1f}s")
        await asyncio.sleep(delay)

    def _get(self, url: str, **kwargs) -> 'Response':
        """Make a GET request with stealth session."""
        if self.session is None:
            self.session = self._create_session()

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

        # Merge with any additional headers
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        # Add cookies
        if self._cookies:
            kwargs['cookies'] = self._cookies

        response = self.session.get(url, headers=headers, **kwargs)

        # Store cookies from response
        if hasattr(response, 'cookies'):
            self._cookies.update(dict(response.cookies))

        return response

    def _post(self, url: str, data: dict = None, **kwargs) -> 'Response':
        """Make a POST request with stealth session."""
        if self.session is None:
            self.session = self._create_session()

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://publicindex.sccourts.org',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        if self._cookies:
            kwargs['cookies'] = self._cookies

        response = self.session.post(url, data=data, headers=headers, **kwargs)

        if hasattr(response, 'cookies'):
            self._cookies.update(dict(response.cookies))

        return response

    def _extract_form_fields(self, html: str) -> dict:
        """Extract ASP.NET form fields from HTML."""
        soup = BeautifulSoup(html, 'lxml')
        fields = {}

        # Extract hidden fields
        for field_name in ['__VIEWSTATE', '__VIEWSTATEGENERATOR', '__EVENTVALIDATION', '__EVENTTARGET', '__EVENTARGUMENT']:
            field = soup.find('input', {'name': field_name})
            if field:
                fields[field_name] = field.get('value', '')

        return fields

    def _extract_cases(self, html: str, source_url: str) -> list[ForeclosureCase]:
        """Extract foreclosure cases from HTML.

        The roster detail page has a table with class 'searchResultsGrid' containing rows.
        Columns: # | Case / Case Caption | Plaintiff Attorney | Defendant Attorney | Filed Date | Sub Type | Status | Tax Map | Notes
        """
        cases = []
        soup = BeautifulSoup(html, 'lxml')

        # Find the main data table
        table = soup.find('table', {'class': 'searchResultsGrid'})
        if not table:
            logger.warning("Could not find searchResultsGrid table")
            return cases

        # Get all data rows (skip header row)
        rows = table.find_all('tr', {'class': ['standardRow', 'altRow']})
        logger.info(f"Found {len(rows)} case rows in table")

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 9:
                continue

            try:
                # Column 0: Priority/Number
                # Column 1: Case Number and Caption
                case_cell = cells[1]
                case_link = case_cell.find('a')
                case_number = case_link.get_text(strip=True) if case_link else ""

                if not case_number:
                    continue

                case = ForeclosureCase(
                    case_number=case_number,
                    source_url=source_url,
                    case_type='Foreclosure'
                )

                # Extract caption (Plaintiff VS Defendant)
                caption_text = case_cell.get_text(' ', strip=True)
                vs_match = re.search(
                    r'([A-Za-z\s,\.\-]+?(?:Llc|Inc|Bank|Credit Union|Trust|Federal)?)\s+VS\s+([A-Za-z\s]+?)\s*,?\s*(?:defendant|et al)',
                    caption_text, re.IGNORECASE
                )
                if vs_match:
                    case.plaintiff_name = vs_match.group(1).strip()
                    defendant = vs_match.group(2).strip()
                    parts = defendant.split()
                    if len(parts) >= 2:
                        case.defendant_first_name = parts[0]
                        case.defendant_last_name = ' '.join(parts[1:])
                    else:
                        case.defendant_last_name = defendant

                # Column 2: Plaintiff Attorney
                plaintiff_atty_cell = cells[2]
                plaintiff_atty_text = plaintiff_atty_cell.get_text(' ', strip=True)
                atty_match = re.search(r'([A-Za-z\.\s]+?)\s*\((\d{3})\)\s*(\d{3})-?(\d{4})', plaintiff_atty_text)
                if atty_match:
                    case.plaintiff_attorney.name = atty_match.group(1).strip()
                    case.plaintiff_attorney.phone = f"({atty_match.group(2)}) {atty_match.group(3)}-{atty_match.group(4)}"

                # Column 3: Defendant Attorney
                defendant_atty_cell = cells[3]
                defendant_atty_text = defendant_atty_cell.get_text(' ', strip=True)
                atty_match = re.search(r'([A-Za-z\.\s]+?)\s*\((\d{3})\)\s*(\d{3})-?(\d{4})', defendant_atty_text)
                if atty_match:
                    case.defendant_attorney.name = atty_match.group(1).strip()
                    case.defendant_attorney.phone = f"({atty_match.group(2)}) {atty_match.group(3)}-{atty_match.group(4)}"

                # Column 4: Filed Date
                filed_date_cell = cells[4]
                case.filing_date = filed_date_cell.get_text(strip=True)

                # Column 5: Sub Type (already set to Foreclosure)
                # Column 6: Status
                # Column 7: Tax Map

                # Column 8: Notes (contains property address)
                notes_cell = cells[8]
                notes_text = notes_cell.get_text(' ', strip=True)

                # Extract Property Address from notes
                addr_match = re.search(
                    r'Property Address:\s*([^J\n]+?)(?:Judgment|$)',
                    notes_text, re.IGNORECASE
                )
                if addr_match:
                    self._parse_address(addr_match.group(1).strip(), case.property_address)
                else:
                    # Try to find address without label
                    addr_match = re.search(
                        r'(\d+\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Boulevard|Blvd)[^,]*,\s*[A-Za-z\s]+,?\s*SC)',
                        notes_text, re.IGNORECASE
                    )
                    if addr_match:
                        self._parse_address(addr_match.group(1), case.property_address)

                cases.append(case)
                logger.debug(f"Extracted case: {case.case_number} - {case.defendant_full_name}")

            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue

        return cases

    def _parse_address(self, addr_str: str, address: Address) -> None:
        """Parse address string into Address model."""
        addr_str = addr_str.strip()

        # Extract zip code
        zip_match = re.search(r'(\d{5})(?:-\d{4})?', addr_str)
        if zip_match:
            address.zip_code = zip_match.group(1)

        # Extract city (typically before SC or zip)
        # Common SC cities in York County
        city_pattern = r',\s*([A-Za-z\s]+?)(?:,?\s*(?:SC|South Carolina|\d{5}))'
        city_match = re.search(city_pattern, addr_str, re.IGNORECASE)
        if city_match:
            address.city = city_match.group(1).strip()

        # Street is everything before city
        if address.city:
            parts = addr_str.split(address.city)
            if parts:
                address.street = parts[0].strip().rstrip(',')
        else:
            # No city found, use everything up to SC or end
            street_match = re.match(r'([^,]+)', addr_str)
            if street_match:
                address.street = street_match.group(1).strip()

        address.state = 'SC'

    async def scrape(self) -> list[ForeclosureCase]:
        """Scrape foreclosure cases using stealth requests."""
        logger.info("Starting stealth-requests scrape...")

        if not STEALTH_AVAILABLE:
            logger.error("stealth-requests library not available")
            return []

        all_cases = []

        try:
            # Step 1: Load disclaimer page
            logger.info("Loading disclaimer page...")
            response = self._get(self.county_config.base_url)
            logger.info(f"Disclaimer page status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Failed to load disclaimer: {response.status_code}")
                return []

            html = response.text
            logger.info(f"Disclaimer page length: {len(html)}")

            # Extract form fields
            form_fields = self._extract_form_fields(html)
            logger.info(f"Found form fields: {list(form_fields.keys())}")

            # Human-like delay
            await self._random_delay(2.0, 4.0)

            # Step 2: Submit disclaimer form
            logger.info("Submitting disclaimer...")

            soup = BeautifulSoup(html, 'lxml')
            submit = soup.find('input', {'type': 'submit', 'value': 'Accept'})

            if submit:
                form_data = form_fields.copy()
                form_data[submit.get('name', '')] = submit.get('value', 'Accept')

                await self._random_delay(1.0, 2.0)

                response = self._post(
                    self.county_config.base_url,
                    data=form_data,
                    headers={'Referer': self.county_config.base_url}
                )

                logger.info(f"Disclaimer submit status: {response.status_code}")
                logger.info(f"Redirected to: {response.url}")

                if response.status_code == 200:
                    html = response.text
                    roster_selection_url = str(response.url)
                    logger.info(f"Roster selection page length: {len(html)}")

                    # Save for debugging
                    with open('screenshots/stealth_req_roster_selection.html', 'w') as f:
                        f.write(html)

                    # Long delay
                    await self._long_delay()

                    # Step 3: Find all Sales rosters
                    soup = BeautifulSoup(html, 'lxml')
                    roster_links = soup.find_all('a', href=re.compile(r'RosterDetails'))

                    # Collect all sales roster URLs
                    sales_rosters = []
                    for link in roster_links:
                        link_text = link.get_text(strip=True)
                        # Look for Sales or Master's Sales rosters
                        if 'Sales' in link_text:
                            href = link.get('href')
                            if not href.startswith('http'):
                                base = self.county_config.base_url.rsplit('/', 1)[0]
                                roster_url = f"{base}/{href}"
                            else:
                                roster_url = href
                            sales_rosters.append((link_text, roster_url))

                    logger.info(f"Found {len(sales_rosters)} sales rosters")

                    # Scrape each sales roster
                    for roster_name, roster_url in sales_rosters[:3]:  # Limit to first 3 for testing
                        logger.info(f"Loading roster: {roster_name}")

                        # Random delay before each request
                        await self._random_delay(2.0, 5.0)

                        response = self._get(
                            roster_url,
                            headers={'Referer': roster_selection_url}
                        )

                        logger.info(f"Roster status: {response.status_code}, length: {len(response.text)}")

                        if response.status_code == 200 and len(response.text) > 1000:
                            # Save roster HTML
                            safe_name = re.sub(r'[^\w\-]', '_', roster_name)[:50]
                            with open(f'screenshots/roster_{safe_name}.html', 'w') as f:
                                f.write(response.text)

                            # Extract cases
                            cases = self._extract_cases(response.text, roster_url)
                            all_cases.extend(cases)
                            logger.info(f"Extracted {len(cases)} cases from {roster_name}")

                            for case in cases:
                                logger.info(f"  Case {case.case_number}: {case.defendant_full_name} at {case.property_address.street}")

                        # Long delay before next roster
                        await self._long_delay()

        except Exception as e:
            logger.exception(f"Scrape failed: {e}")

        logger.info(f"Total cases extracted: {len(all_cases)}")
        return all_cases

    def close(self):
        """Close the session."""
        if self.session:
            self.session.close()
            self.session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()


async def main():
    """Test the stealth requests scraper."""
    import os
    os.makedirs('screenshots', exist_ok=True)

    scraper = StealthRequestsScraper()
    try:
        cases = await scraper.scrape()
        print(f"\nFound {len(cases)} cases:")
        for case in cases[:5]:
            print(f"  {case.case_number}: {case.plaintiff_name} v. {case.defendant_full_name}")
    finally:
        scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
