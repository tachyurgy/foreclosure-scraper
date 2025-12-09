# Foreclosure Data Scraper

**Extracting foreclosure data from court systems that don't want to be scraped.**

## [View Live Demo](https://tachyurgy.github.io/foreclosure-scraper/)

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://tachyurgy.github.io/foreclosure-scraper/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

I built this to solve a specific problem: a client needed pending foreclosure case data from South Carolina county courts, enriched with property valuations from Zillow. The catch? The court system actively blocks automated access.

This repo documents my approach to bypassing those protections and building a reliable, production-grade data pipeline.

---

## The Problem

Government court websites increasingly deploy sophisticated anti-bot measures. The SC Courts public index was returning `406 Not Acceptable` errors to every automated tool I tried:

| Approach | Result |
|----------|--------|
| Playwright (headless) | ❌ 406 error |
| Playwright (headed) | ❌ 406 error |
| Selenium + undetected-chromedriver | ❌ 406 error |
| playwright-stealth | ❌ 406 error |
| Custom headers + cookies | ❌ 406 error |

The site wasn't checking JavaScript execution or header patterns. It was fingerprinting TLS handshakes.

## The Solution

This project uses two complementary anti-bot bypass techniques:

### 1. TLS Fingerprint Impersonation (for SC Courts)

Standard scraping libraries have distinctive TLS fingerprints that differ from real browsers. The fix: **TLS fingerprint impersonation** using `curl_cffi` (via `stealth-requests`), which replicates Chrome's exact TLS handshake.

### 2. Undetected Browser Automation (for Zillow)

Zillow uses sophisticated bot detection (navigator.webdriver, automation flags, headless detection). The fix: **nodriver**, which runs a real Chrome instance without any automation markers—completely indistinguishable from a human user.

Combined with human-like behavior patterns:
- Random 10-30 second delays between requests
- Proper session management and cookie handling
- Sequential form submissions matching real browser flow
- Realistic referrer chains

**Result:** Full access to both the court data and Zillow property valuations.

---

## Live Output

Real data extracted from York County, SC Master's Sales rosters:

```
Case: 2024CP4601055
  Plaintiff: Family Trust Federal Credit Union
  Defendant: Rose Ann Carter
  Plaintiff Attorney: Jordan Daniel Beumer - (803) 252-3340
  Defendant Attorney: Robert Julian Thomas Jr. - (803) 898-5271
  Property: 263 Echo Lane, Rock Hill, SC
  Filing Date: 03/12/2024

Case: 2025CP4600875
  Plaintiff: Loandepotcom Llc
  Defendant: Terry Catoe
  Plaintiff Attorney: Kevin Ted Brown - (803) 454-3540
  Defendant Attorney: Kelley Yarborough Woody - (803) 787-9678
  Property: 4024 Redwood Drive, Rock Hill, SC
  Filing Date: 02/27/2025

Case: 2025CP4601197
  Plaintiff: Pennymac Loan Services Llc
  Defendant: Kenneth Roach
  Plaintiff Attorney: Kevin Ted Brown - (803) 454-3540
  Property: 875 Rolling Green Drive, Rock Hill, SC
  Filing Date: 03/21/2025
```

Each case includes: case number, both party names, attorney names and direct phone numbers, property address, and filing date.

---

## Web Viewer

The project includes a modern **Preact-based web application** for viewing foreclosure data:

- Real-time filtering by city and search
- Property valuation estimates based on York County market data
- Attorney contact information for both parties
- Mobile-responsive design with dark theme

**[Launch the Web Viewer](https://tachyurgy.github.io/foreclosure-scraper/)**

To run locally:

```bash
cd web
npm install
npm run dev
```

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         Data Pipeline               │
                    └─────────────────────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────┐
        │                                                         │
        ▼                                                         ▼
┌───────────────┐                                       ┌───────────────┐
│  STEP A       │                                       │  STEP B       │
│  County Court │                                       │  Zillow       │
│  Rosters      │                                       │  Lookup       │
├───────────────┤                                       ├───────────────┤
│ stealth-      │                                       │ Playwright    │
│ requests      │                                       │ + delays      │
│ (TLS bypass)  │                                       │               │
└───────┬───────┘                                       └───────┬───────┘
        │                                                       │
        └───────────────────────────┬───────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Pydantic Models → SQLite → Export  │
                    │       (CSV / Excel / JSON)          │
                    └─────────────────────────────────────┘
```

**Step A** feeds addresses to Step B. All data flows through validated Pydantic models into SQLite, with export to your preferred format.

---

## Quick Start

### Docker (Recommended)

```bash
docker build -t foreclosure-scraper .
docker run -v $(pwd)/data:/app/data foreclosure-scraper --format csv
```

### Local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python main.py --format csv
```

---

## Scheduling

The scraper supports automated periodic runs:

```bash
# Run every 14 days (default)
python scheduler.py

# Run once immediately
python scheduler.py --once

# Custom interval
python scheduler.py --interval 7
```

Or use docker-compose:

```bash
docker-compose up scheduler  # Runs on schedule
docker-compose up scraper    # Runs once
```

---

## Configuration

Key settings in `config.py` or via environment variables:

```python
# Target county
base_url = "https://publicindex.sccourts.org/york/courtrosters/"

# Zillow search area
target_zip_codes = ["29732", "29745", "29730", "29710", ...]

# Rate limiting
requests_per_second = 1.0
schedule_interval_days = 14
```

---

## Project Structure

```
├── main.py                           # Orchestrator
├── run_pipeline.py                   # Full pipeline with rich logging
├── scheduler.py                      # Cron-style runner
├── config.py                         # All configuration
├── models.py                         # Pydantic schemas
├── storage.py                        # SQLite + export + deduplication
├── scrapers/
│   ├── base.py                       # Abstract base
│   ├── stealth_requests_scraper.py   # TLS fingerprint bypass (curl_cffi)
│   ├── stealth_scraper.py            # Playwright + human simulation
│   ├── county_scraper.py             # Standard Playwright
│   ├── zillow_nodriver.py            # Zillow via nodriver (undetected)
│   ├── zillow_scraper.py             # Zillow via Playwright
│   └── zillow_stealth.py             # Zillow via stealth-requests
├── web/                              # Preact web viewer
│   ├── src/
│   │   ├── App.jsx                   # Main component (loads live data)
│   │   └── style.css                 # Dark theme styling
│   ├── public/
│   │   └── foreclosures_enriched.json # Live scraped data
│   ├── package.json
│   └── vite.config.js
├── data/                             # Output directory
│   ├── foreclosures_enriched.json    # Latest enriched data
│   └── logs/                         # Pipeline logs
├── docs/                             # GitHub Pages deployment
├── Dockerfile
└── docker-compose.yml
```

---

## Technical Details

### Why TLS Fingerprinting Matters

Modern WAFs (Web Application Firewalls) fingerprint the TLS handshake—the cipher suites offered, their order, supported extensions, etc. Python's `requests` and even headless browsers have fingerprints that differ from real Chrome/Firefox.

`curl_cffi` solves this by using libcurl compiled to match browser fingerprints exactly. The `stealth-requests` wrapper makes it drop-in compatible with the `requests` API.

### Undetected Browser Automation with nodriver

For JavaScript-heavy sites like Zillow that employ sophisticated bot detection (Cloudflare, PerimeterX, DataDome), even TLS fingerprinting isn't enough. These sites detect:

- WebDriver property (`navigator.webdriver`)
- Automation flags in Chrome
- CDP (Chrome DevTools Protocol) signatures
- Headless browser indicators

**nodriver** solves this by using a real Chrome instance without any automation markers:

```python
import nodriver as uc

async def scrape_zillow():
    browser = await uc.start()
    tab = await browser.get("https://www.zillow.com/homes/...")

    # Wait for dynamic content
    await asyncio.sleep(3)

    # Extract data from fully rendered page
    html = await tab.get_content()
    # ... parse property data
```

Key advantages over Selenium/Playwright:
- **No webdriver injection**: Chrome runs without automation flags
- **Natural fingerprint**: Indistinguishable from a real user's browser
- **Full JS execution**: All dynamic content loads normally
- **Persistent sessions**: Cookies and state maintained across requests

This is how we extract Zillow property valuations for foreclosure addresses—something that would trigger blocks with any standard automation tool.

### Human Behavior Simulation

Beyond TLS, the scraper implements:

- **Random delays**: 10-30 seconds between page loads (configurable)
- **Session continuity**: Proper cookie jar management across requests
- **Referrer chains**: Each request includes correct referrer from previous page
- **Form handling**: ASP.NET ViewState and EventValidation properly submitted

### Data Validation

All extracted data passes through Pydantic models:

```python
class ForeclosureCase(BaseModel):
    case_number: str
    plaintiff_name: str
    defendant_first_name: str
    defendant_last_name: str
    plaintiff_attorney: Attorney
    defendant_attorney: Attorney
    property_address: Address
    filing_date: Optional[str]
    # ...
```

Malformed data fails fast with clear errors rather than polluting your database.

---

## Extending to Other Courts

The architecture is designed for this. To add a new county:

1. Create `scrapers/new_county_scraper.py` inheriting from `BaseScraper`
2. Implement `scrape()` for that site's HTML structure
3. Add config entry in `config.py`
4. The rest (models, storage, export) works automatically

Different anti-bot measures? The `stealth_requests_scraper.py` pattern adapts to most TLS-fingerprinting sites. For JS-heavy sites, the Playwright-based scrapers with human simulation usually work.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `stealth-requests` | TLS fingerprint impersonation (curl_cffi wrapper) |
| `nodriver` | Undetected Chrome automation for bot-protected sites |
| `playwright` | Browser automation (fallback) |
| `beautifulsoup4` / `lxml` | HTML parsing |
| `pydantic` | Data validation |
| `sqlalchemy` | Database ORM |
| `pandas` | Export formatting |
| `rich` | Terminal UI |
| `loguru` | Logging |
| `apscheduler` | Scheduling |

---

## Sample Data

Check `data/sample_foreclosures.json` for actual extracted records. The scraper successfully pulls:

- ✅ Case numbers (SC format: 2024CP4601055)
- ✅ Plaintiff names (banks, lenders, servicers)
- ✅ Defendant names
- ✅ Plaintiff attorney names and phone numbers
- ✅ Defendant attorney names and phone numbers
- ✅ Property addresses (parsed into street/city/state/zip)
- ✅ Filing dates

---

## What I Learned

1. **TLS fingerprinting is the new frontier** for anti-bot. Header manipulation and JS execution won't help if your TLS handshake screams "Python script." Use `curl_cffi` or `stealth-requests`.

2. **WebDriver detection is real**. Sites like Zillow detect `navigator.webdriver` and automation flags. `nodriver` solves this by running real Chrome without any automation markers.

3. **Patience pays off**. The 10-30 second delays feel slow, but they're what separate working scrapers from blocked ones.

4. **ASP.NET sites are predictable**. Once you understand ViewState and EventValidation, the form handling is mechanical.

5. **Government sites are worth the effort**. The data is public record, often not available in bulk anywhere else, and valuable to the right clients.

---

## License

MIT

---

**Questions about scraping a similar site? I'm available for consulting and contract work.**
