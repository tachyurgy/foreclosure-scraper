#!/usr/bin/env python3
"""Main orchestrator for the foreclosure data pipeline.

This script coordinates the multi-step data extraction process:
1. Step A: Scrape York County court rosters for foreclosure cases
2. Step B: Look up property data on Zillow using addresses from Step A
3. Step C: Look up deals on Dealio using addresses from Step A
4. Export combined data to CSV/Excel/JSON
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from config import config
from models import ForeclosureCase, ForeclosureRecord
from scrapers import CountyCourtScraper, ZillowScraper, DealioScraper
from storage import DataStorage

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO",
)
logger.add(
    "data/logs/scraper_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)

console = Console()


class ForeclosurePipeline:
    """Main pipeline orchestrating the foreclosure data extraction."""

    def __init__(self):
        self.storage = DataStorage()
        self.county_scraper = CountyCourtScraper()
        self.zillow_scraper = ZillowScraper()
        self.dealio_scraper = DealioScraper()

    async def close(self):
        """Close all scrapers."""
        await self.county_scraper.close()
        await self.zillow_scraper.close()
        await self.dealio_scraper.close()

    async def run_step_a(self) -> list[ForeclosureCase]:
        """Step A: Scrape York County court rosters for foreclosure cases."""
        console.print("\n[bold blue]Step A: Scraping York County Court Rosters[/bold blue]")

        try:
            cases = await self.county_scraper.scrape()
            console.print(f"[green]✓ Found {len(cases)} foreclosure cases[/green]")
            return cases
        except Exception as e:
            logger.error(f"Step A failed: {e}")
            console.print(f"[red]✗ Error in Step A: {e}[/red]")
            return []

    async def run_step_b(self, cases: list[ForeclosureCase]) -> dict[str, any]:
        """Step B: Look up properties on Zillow."""
        console.print("\n[bold blue]Step B: Looking up properties on Zillow[/bold blue]")

        results = {}

        if not cases:
            console.print("[yellow]⚠ No cases to look up[/yellow]")
            return results

        addresses = [case.property_address for case in cases if case.property_address.street]

        if not addresses:
            console.print("[yellow]⚠ No valid addresses found in cases[/yellow]")
            return results

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Looking up on Zillow...", total=len(addresses))

            for case in cases:
                if not case.property_address.street:
                    progress.advance(task)
                    continue

                try:
                    zillow_data = await self.zillow_scraper.lookup_property(
                        case.property_address
                    )
                    results[case.case_number] = zillow_data
                except Exception as e:
                    logger.debug(f"Zillow lookup failed for {case.case_number}: {e}")
                    results[case.case_number] = None

                progress.advance(task)

        found_count = sum(1 for v in results.values() if v)
        console.print(f"[green]✓ Found Zillow data for {found_count}/{len(cases)} properties[/green]")

        return results

    async def run_step_c(self, cases: list[ForeclosureCase]) -> dict[str, any]:
        """Step C: Look up properties on Dealio."""
        console.print("\n[bold blue]Step C: Looking up properties on Dealio[/bold blue]")

        results = {}

        if not cases:
            console.print("[yellow]⚠ No cases to look up[/yellow]")
            return results

        addresses = [case.property_address for case in cases if case.property_address.street]

        if not addresses:
            console.print("[yellow]⚠ No valid addresses found in cases[/yellow]")
            return results

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Looking up on Dealio...", total=len(addresses))

            for case in cases:
                if not case.property_address.street:
                    progress.advance(task)
                    continue

                try:
                    dealio_data = await self.dealio_scraper.lookup_property(
                        case.property_address
                    )
                    results[case.case_number] = dealio_data
                except Exception as e:
                    logger.debug(f"Dealio lookup failed for {case.case_number}: {e}")
                    results[case.case_number] = None

                progress.advance(task)

        found_count = sum(1 for v in results.values() if v)
        console.print(f"[green]✓ Found Dealio data for {found_count}/{len(cases)} properties[/green]")

        return results

    def combine_results(
        self,
        cases: list[ForeclosureCase],
        zillow_data: dict,
        dealio_data: dict,
    ) -> list[ForeclosureRecord]:
        """Combine all data sources into complete records."""
        records = []

        for case in cases:
            record = ForeclosureRecord(
                case=case,
                zillow_data=zillow_data.get(case.case_number),
                dealio_data=dealio_data.get(case.case_number),
            )
            records.append(record)

        return records

    async def run(self, export_format: str = "csv") -> list[ForeclosureRecord]:
        """Run the complete foreclosure data pipeline.

        Args:
            export_format: Output format (csv, xlsx, json)

        Returns:
            List of complete foreclosure records
        """
        console.print("\n[bold]═══ Foreclosure Data Pipeline ═══[/bold]")
        console.print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # Step A: Get foreclosure cases from county
            cases = await self.run_step_a()

            if not cases:
                console.print("\n[yellow]No foreclosure cases found. Exiting.[/yellow]")
                return []

            # Step B: Enrich with Zillow data
            zillow_data = await self.run_step_b(cases)

            # Step C: Enrich with Dealio data
            dealio_data = await self.run_step_c(cases)

            # Combine all results
            console.print("\n[bold blue]Combining results...[/bold blue]")
            records = self.combine_results(cases, zillow_data, dealio_data)

            # Save to database
            console.print("\n[bold blue]Saving to database...[/bold blue]")
            self.storage.save_records(records)

            # Export data
            console.print(f"\n[bold blue]Exporting to {export_format.upper()}...[/bold blue]")
            export_path = self.storage.export(export_format)
            console.print(f"[green]✓ Exported to: {export_path}[/green]")

            # Print summary
            self._print_summary(records)

            return records

        finally:
            await self.close()

    def _print_summary(self, records: list[ForeclosureRecord]) -> None:
        """Print a summary of the scraped data."""
        console.print("\n[bold]═══ Summary ═══[/bold]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Cases", str(len(records)))
        table.add_row(
            "With Zillow Data",
            str(sum(1 for r in records if r.zillow_data))
        )
        table.add_row(
            "With Dealio Data",
            str(sum(1 for r in records if r.dealio_data))
        )
        table.add_row(
            "With Property Address",
            str(sum(1 for r in records if r.case.property_address.street))
        )

        console.print(table)

        # Show sample of records
        if records:
            console.print("\n[bold]Sample Records:[/bold]")
            for record in records[:3]:
                console.print(f"  • {record.case.case_number}: {record.case.defendant_full_name}")
                if record.case.property_address.street:
                    console.print(f"    Address: {record.case.property_address}")
                if record.zillow_data and record.zillow_data.price:
                    console.print(f"    Zillow Price: ${record.zillow_data.price:,.0f}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Foreclosure Data Scraper")
    parser.add_argument(
        "--format",
        choices=["csv", "xlsx", "json"],
        default="csv",
        help="Export format (default: csv)",
    )
    parser.add_argument(
        "--step",
        choices=["a", "b", "c", "all"],
        default="all",
        help="Run specific step or all (default: all)",
    )

    args = parser.parse_args()

    # Ensure data directories exist
    Path("data/logs").mkdir(parents=True, exist_ok=True)

    pipeline = ForeclosurePipeline()

    try:
        await pipeline.run(export_format=args.format)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        logger.exception("Pipeline failed")
        console.print(f"\n[red]Pipeline failed: {e}[/red]")
        raise


if __name__ == "__main__":
    asyncio.run(main())
