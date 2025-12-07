#!/usr/bin/env python3
"""Scheduler for periodic foreclosure data extraction.

Runs the foreclosure pipeline on a configurable schedule (default: every 2 weeks).
"""

import asyncio
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from rich.console import Console

from config import config
from main import ForeclosurePipeline

console = Console()


class ForeclosureScheduler:
    """Scheduler for running the foreclosure pipeline periodically."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = False

    async def run_pipeline(self):
        """Run the foreclosure pipeline."""
        console.print(f"\n[bold cyan]Scheduled run started at {datetime.now()}[/bold cyan]")

        try:
            pipeline = ForeclosurePipeline()
            await pipeline.run()
        except Exception as e:
            logger.exception("Scheduled pipeline run failed")
            console.print(f"[red]Pipeline failed: {e}[/red]")

    def schedule_job(self):
        """Schedule the pipeline to run periodically."""
        interval_days = config.schedule_interval_days

        self.scheduler.add_job(
            lambda: asyncio.create_task(self.run_pipeline()),
            trigger=IntervalTrigger(days=interval_days),
            id="foreclosure_pipeline",
            name="Foreclosure Data Pipeline",
            replace_existing=True,
        )

        console.print(f"[green]✓ Scheduled to run every {interval_days} days[/green]")

    def start(self, run_immediately: bool = True):
        """Start the scheduler.

        Args:
            run_immediately: If True, run the pipeline once before starting schedule
        """
        self.running = True

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        console.print("\n[bold]═══ Foreclosure Scheduler Started ═══[/bold]")
        console.print(f"Interval: Every {config.schedule_interval_days} days")

        self.schedule_job()
        self.scheduler.start()

        if run_immediately:
            console.print("\n[yellow]Running initial extraction...[/yellow]")
            asyncio.get_event_loop().run_until_complete(self.run_pipeline())

        console.print("\n[green]Scheduler running. Press Ctrl+C to stop.[/green]")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        console.print("\n[yellow]Shutting down scheduler...[/yellow]")
        self.scheduler.shutdown(wait=False)
        self.running = False
        sys.exit(0)


async def run_once():
    """Run the pipeline once without scheduling."""
    pipeline = ForeclosurePipeline()
    await pipeline.run()


def main():
    """Main entry point for the scheduler."""
    import argparse

    parser = argparse.ArgumentParser(description="Foreclosure Data Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (no scheduling)",
    )
    parser.add_argument(
        "--no-immediate",
        action="store_true",
        help="Don't run immediately when starting scheduler",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Override schedule interval in days",
    )

    args = parser.parse_args()

    if args.interval:
        config.schedule_interval_days = args.interval

    if args.once:
        asyncio.run(run_once())
    else:
        scheduler = ForeclosureScheduler()
        scheduler.start(run_immediately=not args.no_immediate)

        # Keep the script running
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped by user[/yellow]")


if __name__ == "__main__":
    main()
