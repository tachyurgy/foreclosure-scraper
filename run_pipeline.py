#!/usr/bin/env python3
"""
Full pipeline test runner - scrapes real data from county courts and Zillow.

This script:
1. Step A: Scrapes York County court rosters for foreclosure cases (using stealth-requests)
2. Step B: Enriches each property with Zillow data (using Playwright)
3. Combines, deduplicates, and exports to JSON/CSV

Run with: python run_pipeline.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table

# Configure rich console
console = Console()

# Configure detailed logging
logger.remove()

# Console logging with colors
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# File logging with full details
log_file = Path("data/logs") / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_file.parent.mkdir(parents=True, exist_ok=True)
logger.add(
    str(log_file),
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB",
)


def print_banner():
    """Print startup banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║     FORECLOSURE DATA PIPELINE - YORK COUNTY, SC               ║
║                                                               ║
║     Step A: County Court Rosters (stealth-requests)           ║
║     Step B: Zillow Property Lookup (Playwright)               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner, style="bold blue"))
    console.print(f"[dim]Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print(f"[dim]Log file: {log_file}[/dim]\n")


async def run_step_a() -> list:
    """Step A: Scrape county court rosters for foreclosure cases."""
    console.print("\n[bold yellow]═══ STEP A: County Court Roster Scraping ═══[/bold yellow]")
    console.print("[dim]Using stealth-requests with TLS fingerprint impersonation[/dim]\n")

    try:
        from scrapers.stealth_requests_scraper import StealthRequestsScraper, STEALTH_AVAILABLE

        if not STEALTH_AVAILABLE:
            console.print("[red]ERROR: stealth-requests not available. Install with: pip install stealth-requests[/red]")
            logger.error("stealth-requests library not available")
            return []

        logger.info("Initializing StealthRequestsScraper...")
        scraper = StealthRequestsScraper()

        with console.status("[bold green]Scraping court rosters...[/bold green]") as status:
            cases = await scraper.scrape()

        scraper.close()

        if cases:
            console.print(f"[green]✓ Found {len(cases)} foreclosure cases[/green]\n")

            # Display sample cases
            table = Table(title="Sample Cases from County Court", show_lines=True)
            table.add_column("Case #", style="cyan")
            table.add_column("Defendant", style="white")
            table.add_column("Plaintiff", style="dim")
            table.add_column("Property Address", style="green")
            table.add_column("Filed", style="yellow")

            for case in cases[:5]:
                table.add_row(
                    case.case_number,
                    case.defendant_full_name,
                    case.plaintiff_name[:30] + "..." if len(case.plaintiff_name) > 30 else case.plaintiff_name,
                    f"{case.property_address.street}, {case.property_address.city}",
                    case.filing_date or "N/A"
                )

            console.print(table)
            return cases
        else:
            console.print("[yellow]⚠ No cases found[/yellow]")
            return []

    except ImportError as e:
        console.print(f"[red]Import error: {e}[/red]")
        logger.exception("Import error in Step A")
        return []
    except Exception as e:
        console.print(f"[red]Error in Step A: {e}[/red]")
        logger.exception("Step A failed")
        return []


async def run_step_b(cases: list) -> dict:
    """Step B: Look up properties on Zillow using nodriver."""
    console.print("\n[bold yellow]═══ STEP B: Zillow Property Lookup ═══[/bold yellow]")
    console.print("[dim]Using nodriver for undetected browser automation[/dim]\n")

    if not cases:
        console.print("[yellow]⚠ No cases to look up[/yellow]")
        return {}

    results = {}

    try:
        from scrapers.zillow_nodriver import ZillowNodriverScraper, NODRIVER_AVAILABLE

        if not NODRIVER_AVAILABLE:
            console.print("[red]ERROR: nodriver not available. Install with: pip install nodriver[/red]")
            return {}

        scraper = ZillowNodriverScraper()

        # Filter cases with valid addresses
        valid_cases = [c for c in cases if c.property_address.street]
        console.print(f"[dim]Looking up {len(valid_cases)} properties with valid addresses[/dim]\n")

        for i, case in enumerate(valid_cases):
            address = case.property_address.full_address
            console.print(f"[{i+1}/{len(valid_cases)}] Looking up: {case.property_address.street}...")
            logger.info(f"Zillow lookup: {address}")

            try:
                zillow_data = await scraper.lookup_property(case.property_address)

                if zillow_data and (zillow_data.price or zillow_data.sqft):
                    results[case.case_number] = zillow_data
                    price_str = f"${zillow_data.price:,.0f}" if zillow_data.price else "N/A"
                    console.print(f"  [green]✓ Found: {price_str}, {zillow_data.bedrooms}bd/{zillow_data.bathrooms}ba, {zillow_data.sqft} sqft[/green]")
                    logger.info(f"  ✓ Found: {price_str}")
                else:
                    results[case.case_number] = None
                    console.print(f"  [yellow]✗ Not found[/yellow]")
                    logger.info("  ✗ Not found")

            except Exception as e:
                logger.warning(f"Zillow lookup failed for {address}: {e}")
                console.print(f"  [red]✗ Error: {e}[/red]")
                results[case.case_number] = None

            # Brief delay between lookups
            await asyncio.sleep(2)

        await scraper.close()

        found_count = sum(1 for v in results.values() if v)
        console.print(f"\n[green]✓ Zillow data found for {found_count}/{len(valid_cases)} properties[/green]")

        return results

    except ImportError as e:
        console.print(f"[red]Import error: {e}[/red]")
        logger.exception("Import error in Step B")
        return {}
    except Exception as e:
        console.print(f"[red]Error in Step B: {e}[/red]")
        logger.exception("Step B failed")
        return {}


def combine_and_export(cases: list, zillow_data: dict) -> Path:
    """Combine all data and export to JSON."""
    console.print("\n[bold yellow]═══ COMBINING & EXPORTING DATA ═══[/bold yellow]\n")

    combined_records = []

    for case in cases:
        record = {
            # Case info
            "case_number": case.case_number,
            "case_type": case.case_type,
            "filing_date": case.filing_date,
            "hearing_date": case.hearing_date,
            "court_room": case.court_room,

            # Plaintiff
            "plaintiff_name": case.plaintiff_name,
            "plaintiff_attorney_name": case.plaintiff_attorney.name,
            "plaintiff_attorney_phone": case.plaintiff_attorney.phone,

            # Defendant
            "defendant_first_name": case.defendant_first_name,
            "defendant_last_name": case.defendant_last_name,
            "defendant_full_name": case.defendant_full_name,
            "defendant_attorney_name": case.defendant_attorney.name,
            "defendant_attorney_phone": case.defendant_attorney.phone,

            # Property
            "property_street": case.property_address.street,
            "property_city": case.property_address.city,
            "property_state": case.property_address.state,
            "property_zip": case.property_address.zip_code,
            "property_full_address": case.property_address.full_address,

            # Source
            "source_url": case.source_url,
            "scraped_at": case.scraped_at.isoformat(),
        }

        # Add Zillow data
        zdata = zillow_data.get(case.case_number)
        if zdata:
            record.update({
                "zillow_price": zdata.price,
                "zillow_zestimate": zdata.zestimate,
                "zillow_bedrooms": zdata.bedrooms,
                "zillow_bathrooms": zdata.bathrooms,
                "zillow_sqft": zdata.sqft,
                "zillow_year_built": zdata.year_built,
                "zillow_lot_size": zdata.lot_size,
                "zillow_property_type": zdata.property_type,
                "zillow_status": zdata.status,
                "zillow_days_on_market": zdata.days_on_zillow,
                "zillow_url": zdata.listing_url,
                "zillow_image_url": zdata.image_url,
            })

        combined_records.append(record)

    # Deduplicate by case number
    seen = set()
    unique_records = []
    for r in combined_records:
        if r["case_number"] not in seen:
            seen.add(r["case_number"])
            unique_records.append(r)

    logger.info(f"Deduplicated: {len(combined_records)} -> {len(unique_records)} records")

    # Export to JSON
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"foreclosures_enriched_{timestamp}.json"

    with open(json_path, "w") as f:
        json.dump(unique_records, f, indent=2, default=str)

    # Also update the main enriched file
    main_json_path = output_dir / "foreclosures_enriched.json"
    with open(main_json_path, "w") as f:
        json.dump(unique_records, f, indent=2, default=str)

    console.print(f"[green]✓ Exported {len(unique_records)} records to:[/green]")
    console.print(f"  [cyan]{json_path}[/cyan]")
    console.print(f"  [cyan]{main_json_path}[/cyan]")

    return json_path


def print_summary(cases: list, zillow_data: dict):
    """Print final summary."""
    console.print("\n[bold yellow]═══ PIPELINE SUMMARY ═══[/bold yellow]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")

    table.add_row("Total Cases Scraped", str(len(cases)))
    table.add_row("With Property Address", str(sum(1 for c in cases if c.property_address.street)))
    table.add_row("With Zillow Data", str(sum(1 for v in zillow_data.values() if v)))

    console.print(table)

    # Price statistics if we have Zillow data
    prices = [z.price for z in zillow_data.values() if z and z.price]
    if prices:
        console.print(f"\n[bold]Zillow Price Statistics:[/bold]")
        console.print(f"  Min: ${min(prices):,.0f}")
        console.print(f"  Max: ${max(prices):,.0f}")
        console.print(f"  Avg: ${sum(prices)/len(prices):,.0f}")


async def main():
    """Run the full pipeline."""
    print_banner()

    # Ensure directories exist
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    Path("screenshots").mkdir(exist_ok=True)

    # Step A: County data
    cases = await run_step_a()

    if not cases:
        console.print("\n[red]Pipeline stopped: No cases found in Step A[/red]")
        console.print("[dim]Check if stealth-requests is installed: pip install stealth-requests[/dim]")
        return

    # Step B: Zillow enrichment
    zillow_data = await run_step_b(cases)

    # Combine and export
    output_path = combine_and_export(cases, zillow_data)

    # Print summary
    print_summary(cases, zillow_data)

    console.print(f"\n[bold green]Pipeline complete![/bold green]")
    console.print(f"[dim]Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
    console.print(f"[dim]Output: {output_path}[/dim]")
    console.print(f"[dim]Log: {log_file}[/dim]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Pipeline failed: {e}[/red]")
        logger.exception("Pipeline failed")
        raise
