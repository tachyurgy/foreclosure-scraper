"""Data storage and export utilities."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import StorageConfig, config
from models import ForeclosureRecord

Base = declarative_base()


class ForeclosureTable(Base):
    """SQLAlchemy model for foreclosure records."""

    __tablename__ = "foreclosures"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Case info
    case_number = Column(String(50), unique=True, index=True)
    case_type = Column(String(50))
    filing_date = Column(String(20))
    hearing_date = Column(String(20))
    court_room = Column(String(50))

    # Plaintiff
    plaintiff_name = Column(String(200))
    plaintiff_attorney_name = Column(String(200))
    plaintiff_attorney_phone = Column(String(50))

    # Defendant
    defendant_first_name = Column(String(100))
    defendant_last_name = Column(String(100))
    defendant_attorney_name = Column(String(200))
    defendant_attorney_phone = Column(String(50))

    # Property address
    property_street = Column(String(300))
    property_city = Column(String(100))
    property_state = Column(String(10))
    property_zip = Column(String(20))

    # Zillow data
    zillow_price = Column(Float, nullable=True)
    zillow_zestimate = Column(Float, nullable=True)
    zillow_bedrooms = Column(Integer, nullable=True)
    zillow_bathrooms = Column(Float, nullable=True)
    zillow_sqft = Column(Integer, nullable=True)
    zillow_year_built = Column(Integer, nullable=True)
    zillow_status = Column(String(50))
    zillow_url = Column(Text)

    # Dealio data
    dealio_price = Column(Float, nullable=True)
    dealio_offer = Column(Text)
    dealio_contact_phone = Column(String(50))
    dealio_contact_email = Column(String(100))
    dealio_url = Column(Text)

    # Metadata
    source_url = Column(Text)
    scraped_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DataStorage:
    """Handle data persistence and export."""

    def __init__(self, storage_config: Optional[StorageConfig] = None):
        self.config = storage_config or config.storage
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        db_path = self.config.database_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_records(self, records: list[ForeclosureRecord]) -> int:
        """Save foreclosure records to database.

        Args:
            records: List of ForeclosureRecord objects

        Returns:
            Number of records saved/updated
        """
        session = self.Session()
        saved_count = 0

        try:
            for record in records:
                flat_data = record.to_flat_dict()

                # Check if record exists
                existing = session.query(ForeclosureTable).filter_by(
                    case_number=flat_data["case_number"]
                ).first()

                if existing:
                    # Update existing record
                    for key, value in flat_data.items():
                        if hasattr(existing, key) and key != "case_number":
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now()
                else:
                    # Create new record
                    new_record = ForeclosureTable(**{
                        k: v for k, v in flat_data.items()
                        if hasattr(ForeclosureTable, k)
                    })
                    session.add(new_record)

                saved_count += 1

            session.commit()
            logger.info(f"Saved {saved_count} records to database")

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving records: {e}")
            raise
        finally:
            session.close()

        return saved_count

    def get_all_records(self) -> list[dict]:
        """Get all records from database as dictionaries."""
        session = self.Session()
        try:
            records = session.query(ForeclosureTable).all()
            return [
                {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for r in records
            ]
        finally:
            session.close()

    def export_to_csv(self, filename: Optional[str] = None) -> Path:
        """Export all records to CSV.

        Args:
            filename: Optional filename (defaults to timestamped name)

        Returns:
            Path to the exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"foreclosures_{timestamp}.csv"

        filepath = self.config.data_dir / filename
        records = self.get_all_records()

        if not records:
            logger.warning("No records to export")
            return filepath

        df = pd.DataFrame(records)
        df.to_csv(filepath, index=False, quoting=csv.QUOTE_ALL)

        logger.info(f"Exported {len(records)} records to {filepath}")
        return filepath

    def export_to_excel(self, filename: Optional[str] = None) -> Path:
        """Export all records to Excel.

        Args:
            filename: Optional filename (defaults to timestamped name)

        Returns:
            Path to the exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"foreclosures_{timestamp}.xlsx"

        filepath = self.config.data_dir / filename
        records = self.get_all_records()

        if not records:
            logger.warning("No records to export")
            return filepath

        df = pd.DataFrame(records)
        df.to_excel(filepath, index=False, engine="openpyxl")

        logger.info(f"Exported {len(records)} records to {filepath}")
        return filepath

    def export_to_json(self, filename: Optional[str] = None) -> Path:
        """Export all records to JSON.

        Args:
            filename: Optional filename (defaults to timestamped name)

        Returns:
            Path to the exported file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"foreclosures_{timestamp}.json"

        filepath = self.config.data_dir / filename
        records = self.get_all_records()

        # Convert datetime objects to strings
        for record in records:
            for key, value in record.items():
                if isinstance(value, datetime):
                    record[key] = value.isoformat()

        with open(filepath, "w") as f:
            json.dump(records, f, indent=2, default=str)

        logger.info(f"Exported {len(records)} records to {filepath}")
        return filepath

    def export(self, format: Optional[str] = None) -> Path:
        """Export records in the configured format.

        Args:
            format: Export format (csv, xlsx, json). Defaults to config setting.

        Returns:
            Path to the exported file
        """
        format = format or self.config.export_format

        if format == "xlsx":
            return self.export_to_excel()
        elif format == "json":
            return self.export_to_json()
        else:
            return self.export_to_csv()
