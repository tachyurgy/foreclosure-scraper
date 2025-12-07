# Foreclosure Data Scraper

A production-ready web scraping system that extracts foreclosure case data from South Carolina county court rosters, enriches it with property data from Zillow, and finds related deals on Dealio.

## What It Does

This scraper tackles a real-world data extraction challenge: pulling pending foreclosure case information from government court systems that actively block automated access. The extracted data includes:

- **Case Details**: Case numbers, filing dates, case status
- **Party Information**: Plaintiff names, defendant names
- **Attorney Contacts**: Names and phone numbers for both plaintiff and defendant attorneys
- **Property Addresses**: Full street addresses parsed and normalized
- **Property Values**: Zillow estimates, pricing data (when available)
- **Deal Information**: Related offers from Dealio

### Sample Output

Here's actual data extracted from York County, SC court rosters:

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
```

## The Technical Challenge

Government court websites often employ aggressive anti-bot measures. The SC Courts public index, for example, returns `406 Not Acceptable` responses to standard scraping tools—including headless browsers with stealth plugins.

After testing multiple approaches:
- Standard Playwright/Puppeteer ❌
- Selenium with undetected-chromedriver ❌
- Various stealth plugins ❌
- Custom header manipulation ❌

The solution that worked: **TLS fingerprint impersonation** using `stealth-requests` (built on `curl_cffi`). This library mimics the exact TLS handshake of real browsers, bypassing fingerprint-based detection.

Combined with:
- Human-like request timing (10-30 second random delays)
- Proper session/cookie handling
- Realistic HTTP header patterns
- Sequential form submissions matching browser behavior

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   County Court  │────▶│  Stealth Scraper │────▶│   Data Models   │
│   (Step A)      │     │  (TLS Bypass)    │     │   (Pydantic)    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│     Zillow      │◀────│ Property Lookup  │◀─────────────┤
│   (Step B)      │     │  (Playwright)    │              │
└─────────────────┘     └──────────────────┘              │
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│     Dealio      │◀────│  Deal Lookup     │◀─────────────┘
│   (Step C)      │     │  (Playwright)    │
└─────────────────┘     └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  SQLite + Export │
                        │  (CSV/Excel/JSON)│
                        └──────────────────┘
```

## Quick Start

### Using Docker

```bash
# Build the image
docker build -t foreclosure-scraper .

# Run a single extraction
docker run -v $(pwd)/data:/app/data foreclosure-scraper

# Or use docker-compose for scheduled runs
docker-compose up scheduler
```

### Local Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the scraper
python main.py --format csv
```

## Configuration

Environment variables or edit `config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SCHEDULE_INTERVAL_DAYS` | 14 | Days between scheduled runs |
| `REQUESTS_PER_SECOND` | 1.0 | Rate limiting for requests |

### Target Configuration

The scraper currently targets York County, SC. Modify `config.py` to change:

```python
@dataclass
class CountyConfig:
    base_url: str = "https://publicindex.sccourts.org/york/courtrosters/"
    case_types: list[str] = field(default_factory=lambda: ["Foreclosure"])
```

### Zillow ZIP Codes

```python
target_zip_codes: list[str] = field(default_factory=lambda: [
    "29732", "29745", "29730", "29710", "29708",
    "29704", "29726", "29717", "29715", "29702",
    "29743", "29712"
])
```

## Project Structure

```
foreclosure-scraper/
├── main.py                 # Main orchestrator
├── scheduler.py            # Periodic execution
├── config.py               # Configuration settings
├── models.py               # Pydantic data models
├── storage.py              # Database and export
├── scrapers/
│   ├── base.py             # Base scraper class
│   ├── county_scraper.py   # Playwright-based county scraper
│   ├── stealth_scraper.py  # Stealth Playwright variant
│   ├── stealth_requests_scraper.py  # TLS fingerprint bypass
│   ├── zillow_scraper.py   # Property data lookup
│   └── dealio_scraper.py   # Deal/offer lookup
├── data/                   # Output directory
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Data Export

Extracted data is automatically saved to SQLite and can be exported to:

- **CSV**: `python main.py --format csv`
- **Excel**: `python main.py --format xlsx`
- **JSON**: `python main.py --format json`

Output files are timestamped and saved to the `data/` directory.

## Scheduling

For periodic extraction (default: every 2 weeks):

```bash
# Run the scheduler
python scheduler.py

# Or run once without scheduling
python scheduler.py --once

# Custom interval
python scheduler.py --interval 7  # Weekly
```

## Key Dependencies

- **stealth-requests**: TLS fingerprint impersonation via curl_cffi
- **playwright**: Browser automation for JavaScript-heavy sites
- **beautifulsoup4/lxml**: HTML parsing
- **pydantic**: Data validation and serialization
- **sqlalchemy**: Database ORM
- **pandas**: Data manipulation and export
- **rich**: Terminal output formatting
- **loguru**: Logging

## Extending to Other Counties

The modular architecture makes it straightforward to add new court systems:

1. Create a new scraper in `scrapers/` inheriting from `BaseScraper`
2. Implement the `scrape()` method for the target site's structure
3. Update `config.py` with the new court's URL and settings
4. The data models and export pipeline work automatically

## Notes on Anti-Bot Measures

Different sites require different approaches:

| Site | Challenge | Solution |
|------|-----------|----------|
| SC Courts | TLS fingerprinting | stealth-requests with curl_cffi |
| Zillow | Rate limiting, JS rendering | Playwright with delays |
| Dealio | Standard protection | Standard requests with headers |

The key insight: modern anti-bot systems often rely more on TLS fingerprints than on JavaScript execution or header analysis. When standard tools fail, TLS-level impersonation is worth trying.

## License

MIT

---

*Built to solve a real data extraction problem. If you have a similar challenge, feel free to reach out.*
