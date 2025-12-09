"""Data models for foreclosure scraping."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Address(BaseModel):
    """Property address model."""

    street: str = ""
    city: str = ""
    state: str = "SC"
    zip_code: str = ""

    @property
    def full_address(self) -> str:
        """Return formatted full address."""
        parts = [self.street, self.city, self.state, self.zip_code]
        return ", ".join(p for p in parts if p)

    def __str__(self) -> str:
        return self.full_address


class Attorney(BaseModel):
    """Attorney information model."""

    name: str = ""
    phone: str = ""
    email: str = ""
    firm: str = ""


class ForeclosureCase(BaseModel):
    """Foreclosure case data from county court roster."""

    case_number: str
    case_type: str = "Foreclosure"
    filing_date: Optional[str] = None
    hearing_date: Optional[str] = None
    court_room: Optional[str] = None

    # Plaintiff (typically the lender)
    plaintiff_name: str = ""
    plaintiff_attorney: Attorney = Field(default_factory=Attorney)

    # Defendant (property owner)
    defendant_first_name: str = ""
    defendant_last_name: str = ""
    defendant_attorney: Attorney = Field(default_factory=Attorney)

    # Property information
    property_address: Address = Field(default_factory=Address)

    # Metadata
    scraped_at: datetime = Field(default_factory=datetime.now)
    source_url: str = ""

    @property
    def defendant_full_name(self) -> str:
        """Return defendant's full name."""
        return f"{self.defendant_first_name} {self.defendant_last_name}".strip()


class ZillowProperty(BaseModel):
    """Zillow property data."""

    address: str = ""
    zpid: str = ""  # Zillow Property ID

    # Pricing
    price: Optional[float] = None
    zestimate: Optional[float] = None
    rent_zestimate: Optional[float] = None

    # Property details
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None
    lot_size: Optional[str] = None
    year_built: Optional[int] = None
    property_type: str = ""

    # Status
    status: str = ""  # For sale, sold, etc.
    days_on_zillow: Optional[int] = None

    # URLs
    listing_url: str = ""
    image_url: str = ""

    # Metadata
    scraped_at: datetime = Field(default_factory=datetime.now)


class ForeclosureRecord(BaseModel):
    """Complete foreclosure record combining all data sources."""

    # Core case data
    case: ForeclosureCase

    # Enriched data from other sources
    zillow_data: Optional[ZillowProperty] = None

    # Processing metadata
    processed_at: datetime = Field(default_factory=datetime.now)
    errors: list[str] = Field(default_factory=list)

    def to_flat_dict(self) -> dict:
        """Flatten the record for CSV/database export."""
        data = {
            # Case info
            "case_number": self.case.case_number,
            "case_type": self.case.case_type,
            "filing_date": self.case.filing_date,
            "hearing_date": self.case.hearing_date,
            "court_room": self.case.court_room,

            # Plaintiff
            "plaintiff_name": self.case.plaintiff_name,
            "plaintiff_attorney_name": self.case.plaintiff_attorney.name,
            "plaintiff_attorney_phone": self.case.plaintiff_attorney.phone,

            # Defendant
            "defendant_first_name": self.case.defendant_first_name,
            "defendant_last_name": self.case.defendant_last_name,
            "defendant_full_name": self.case.defendant_full_name,
            "defendant_attorney_name": self.case.defendant_attorney.name,
            "defendant_attorney_phone": self.case.defendant_attorney.phone,

            # Property address
            "property_street": self.case.property_address.street,
            "property_city": self.case.property_address.city,
            "property_state": self.case.property_address.state,
            "property_zip": self.case.property_address.zip_code,
            "property_full_address": self.case.property_address.full_address,

            # Source
            "source_url": self.case.source_url,
            "scraped_at": self.case.scraped_at.isoformat(),
        }

        # Add Zillow data if available
        if self.zillow_data:
            data.update({
                "zillow_price": self.zillow_data.price,
                "zillow_zestimate": self.zillow_data.zestimate,
                "zillow_bedrooms": self.zillow_data.bedrooms,
                "zillow_bathrooms": self.zillow_data.bathrooms,
                "zillow_sqft": self.zillow_data.sqft,
                "zillow_year_built": self.zillow_data.year_built,
                "zillow_status": self.zillow_data.status,
                "zillow_url": self.zillow_data.listing_url,
            })

        return data
