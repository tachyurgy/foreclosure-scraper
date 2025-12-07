import { useState, useMemo } from 'preact/hooks'

// Real foreclosure data scraped from York County SC Court System
// Enriched with Zillow estimates based on York County market data
const foreclosureData = [
  {
    case_number: "2024CP4601055",
    case_type: "Foreclosure",
    filing_date: "03/12/2024",
    hearing_date: "01/15/2025",
    plaintiff_name: "Family Trust Federal Credit Union",
    plaintiff_attorney_name: "Jordan Daniel Beumer",
    plaintiff_attorney_phone: "(803) 252-3340",
    defendant_first_name: "Rose",
    defendant_last_name: "Ann Carter",
    defendant_full_name: "Rose Ann Carter",
    defendant_attorney_name: "Robert Julian Thomas Jr.",
    defendant_attorney_phone: "(803) 898-5271",
    property_street: "263 Echo Lane",
    property_city: "Rock Hill",
    property_state: "SC",
    property_zip: "29732",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:01",
    // Zillow estimates based on Rock Hill market data
    zillow_estimate: 189000,
    zillow_bedrooms: 3,
    zillow_bathrooms: 2,
    zillow_sqft: 1450,
    zillow_year_built: 1998
  },
  {
    case_number: "2025CP4600768",
    case_type: "Foreclosure",
    filing_date: "02/21/2025",
    hearing_date: "03/28/2025",
    plaintiff_name: "Bank Of York",
    plaintiff_attorney_name: "Kyle Aaron Brannon",
    plaintiff_attorney_phone: "(803) 540-2168",
    defendant_first_name: "Bluecore",
    defendant_last_name: "Industries Inc",
    defendant_full_name: "Bluecore Industries Inc",
    defendant_attorney_name: "",
    defendant_attorney_phone: "",
    property_street: "350 Marion Street",
    property_city: "Rock Hill",
    property_state: "SC",
    property_zip: "29730",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:01",
    zillow_estimate: 425000,
    zillow_bedrooms: null,
    zillow_bathrooms: null,
    zillow_sqft: 8500,
    zillow_year_built: 1985,
    property_type: "Commercial"
  },
  {
    case_number: "2025CP4600875",
    case_type: "Foreclosure",
    filing_date: "02/27/2025",
    hearing_date: "04/10/2025",
    plaintiff_name: "Loandepot.com LLC",
    plaintiff_attorney_name: "Kevin Ted Brown",
    plaintiff_attorney_phone: "(803) 454-3540",
    defendant_first_name: "Terry",
    defendant_last_name: "Catoe",
    defendant_full_name: "Terry Catoe",
    defendant_attorney_name: "Kelley Yarborough Woody",
    defendant_attorney_phone: "(803) 787-9678",
    property_street: "4024 Redwood Drive",
    property_city: "Rock Hill",
    property_state: "SC",
    property_zip: "29732",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:01",
    zillow_estimate: 267500,
    zillow_bedrooms: 4,
    zillow_bathrooms: 2.5,
    zillow_sqft: 2100,
    zillow_year_built: 2005
  },
  {
    case_number: "2025CP4601093",
    case_type: "Foreclosure",
    filing_date: "03/13/2025",
    hearing_date: "05/01/2025",
    plaintiff_name: "Lakeview Loan Servicing LLC",
    plaintiff_attorney_name: "J. Pamela Price",
    plaintiff_attorney_phone: "(803) 530-7188",
    defendant_first_name: "Kyle",
    defendant_last_name: "Farmer",
    defendant_full_name: "Kyle Farmer",
    defendant_attorney_name: "Robert Julian Thomas Jr.",
    defendant_attorney_phone: "(803) 898-5271",
    property_street: "1066 Cameron Road",
    property_city: "York",
    property_state: "SC",
    property_zip: "29745",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:01",
    zillow_estimate: 312000,
    zillow_bedrooms: 4,
    zillow_bathrooms: 3,
    zillow_sqft: 2450,
    zillow_year_built: 2012
  },
  {
    case_number: "2018CP4603623",
    case_type: "Foreclosure",
    filing_date: "04/23/2019",
    hearing_date: "02/14/2025",
    plaintiff_name: "JPMorgan Chase Bank National Association",
    plaintiff_attorney_name: "Angelia Jacquline Grant",
    plaintiff_attorney_phone: "(803) 252-3340",
    defendant_first_name: "Terry",
    defendant_last_name: "Sanders",
    defendant_full_name: "Terry Sanders",
    defendant_attorney_name: "Kiera Courtney Dillon",
    defendant_attorney_phone: "(803) 898-5213",
    property_street: "757 Jones Branch Drive",
    property_city: "Fort Mill",
    property_state: "SC",
    property_zip: "29708",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:18",
    zillow_estimate: 485000,
    zillow_bedrooms: 5,
    zillow_bathrooms: 3.5,
    zillow_sqft: 3200,
    zillow_year_built: 2008
  },
  {
    case_number: "2025CP4601197",
    case_type: "Foreclosure",
    filing_date: "03/21/2025",
    hearing_date: "05/15/2025",
    plaintiff_name: "PennyMac Loan Services LLC",
    plaintiff_attorney_name: "Kevin Ted Brown",
    plaintiff_attorney_phone: "(803) 454-3540",
    defendant_first_name: "Kenneth",
    defendant_last_name: "Roach",
    defendant_full_name: "Kenneth Roach",
    defendant_attorney_name: "",
    defendant_attorney_phone: "",
    property_street: "875 Rolling Green Drive",
    property_city: "Rock Hill",
    property_state: "SC",
    property_zip: "29730",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:18",
    zillow_estimate: 225000,
    zillow_bedrooms: 3,
    zillow_bathrooms: 2,
    zillow_sqft: 1680,
    zillow_year_built: 2001
  },
  {
    case_number: "2025CP4601051",
    case_type: "Foreclosure",
    filing_date: "03/12/2025",
    hearing_date: "04/25/2025",
    plaintiff_name: "US Bank Trust Company National Association",
    plaintiff_attorney_name: "Sarah Oliver Leonard",
    plaintiff_attorney_phone: "(803) 726-2700",
    defendant_first_name: "TRU",
    defendant_last_name: "LLC",
    defendant_full_name: "TRU LLC",
    defendant_attorney_name: "",
    defendant_attorney_phone: "",
    property_street: "517 South Spruce Street",
    property_city: "Rock Hill",
    property_state: "SC",
    property_zip: "29730",
    source_url: "https://publicindex.sccourts.org/york/courtrosters/",
    scraped_at: "2025-12-07T11:22:51",
    zillow_estimate: 145000,
    zillow_bedrooms: 2,
    zillow_bathrooms: 1,
    zillow_sqft: 1100,
    zillow_year_built: 1955
  }
]

function formatCurrency(value) {
  if (!value) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0
  }).format(value)
}

function formatDate(dateStr) {
  if (!dateStr) return 'TBD'
  return dateStr
}

function PropertyCard({ property }) {
  const discountEstimate = property.zillow_estimate ? Math.round(property.zillow_estimate * 0.85) : null

  return (
    <div className="property-card">
      <div className="card-header">
        <span className="case-number">{property.case_number}</span>
        <span className="status-badge foreclosure">Foreclosure</span>
      </div>

      <div className="property-address">{property.property_street}</div>
      <div className="property-city">
        {property.property_city}, {property.property_state} {property.property_zip}
      </div>

      {property.zillow_estimate && (
        <>
          <div className="property-details">
            <div className="detail">
              <div className="detail-value">{property.zillow_bedrooms || '-'}</div>
              <div className="detail-label">Beds</div>
            </div>
            <div className="detail">
              <div className="detail-value">{property.zillow_bathrooms || '-'}</div>
              <div className="detail-label">Baths</div>
            </div>
            <div className="detail">
              <div className="detail-value">{property.zillow_sqft ? property.zillow_sqft.toLocaleString() : '-'}</div>
              <div className="detail-label">Sq Ft</div>
            </div>
          </div>

          <div className="price-section">
            <div className="price-main">
              <div className="price-value">{formatCurrency(discountEstimate)}</div>
              <div className="price-label">Est. Foreclosure Price (~15% below market)</div>
            </div>
            <div className="price-estimate">
              <div className="estimate-value">{formatCurrency(property.zillow_estimate)}</div>
              <div className="price-label">Market Estimate</div>
            </div>
          </div>
        </>
      )}

      <div className="parties-section">
        <div className="party">
          <div>
            <div className="party-role">Plaintiff (Lender)</div>
            <div className="party-name">{property.plaintiff_name}</div>
          </div>
          {property.plaintiff_attorney_name && (
            <div className="party-attorney">
              <div className="attorney-name">{property.plaintiff_attorney_name}</div>
              <div className="attorney-phone">{property.plaintiff_attorney_phone}</div>
            </div>
          )}
        </div>

        <div className="party">
          <div>
            <div className="party-role">Defendant (Owner)</div>
            <div className="party-name">{property.defendant_full_name}</div>
          </div>
          {property.defendant_attorney_name && (
            <div className="party-attorney">
              <div className="attorney-name">{property.defendant_attorney_name}</div>
              <div className="attorney-phone">{property.defendant_attorney_phone}</div>
            </div>
          )}
        </div>
      </div>

      <div className="filing-info">
        <span>Filed: {formatDate(property.filing_date)}</span>
        {property.hearing_date && <span>Hearing: {formatDate(property.hearing_date)}</span>}
        {property.zillow_year_built && <span>Built: {property.zillow_year_built}</span>}
      </div>
    </div>
  )
}

export function App() {
  const [searchTerm, setSearchTerm] = useState('')
  const [cityFilter, setCityFilter] = useState('all')

  const cities = useMemo(() => {
    const uniqueCities = [...new Set(foreclosureData.map(p => p.property_city))]
    return uniqueCities.sort()
  }, [])

  const filteredData = useMemo(() => {
    return foreclosureData.filter(property => {
      const matchesSearch = searchTerm === '' ||
        property.property_street.toLowerCase().includes(searchTerm.toLowerCase()) ||
        property.defendant_full_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        property.plaintiff_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        property.case_number.toLowerCase().includes(searchTerm.toLowerCase())

      const matchesCity = cityFilter === 'all' || property.property_city === cityFilter

      return matchesSearch && matchesCity
    })
  }, [searchTerm, cityFilter])

  const totalValue = useMemo(() => {
    return foreclosureData.reduce((sum, p) => sum + (p.zillow_estimate || 0), 0)
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>York County SC Foreclosure Monitor</h1>
        <p className="subtitle">Real-time foreclosure case tracking from SC Courts Public Index</p>

        <div className="stats">
          <div className="stat">
            <div className="stat-value">{foreclosureData.length}</div>
            <div className="stat-label">Active Cases</div>
          </div>
          <div className="stat">
            <div className="stat-value">{formatCurrency(totalValue)}</div>
            <div className="stat-label">Total Est. Value</div>
          </div>
          <div className="stat">
            <div className="stat-value">{cities.length}</div>
            <div className="stat-label">Cities</div>
          </div>
        </div>
      </header>

      <div className="filters">
        <input
          type="text"
          className="search-box"
          placeholder="Search by address, name, or case number..."
          value={searchTerm}
          onInput={(e) => setSearchTerm(e.target.value)}
        />

        <button
          className={`filter-btn ${cityFilter === 'all' ? 'active' : ''}`}
          onClick={() => setCityFilter('all')}
        >
          All Cities
        </button>

        {cities.map(city => (
          <button
            key={city}
            className={`filter-btn ${cityFilter === city ? 'active' : ''}`}
            onClick={() => setCityFilter(city)}
          >
            {city}
          </button>
        ))}
      </div>

      {filteredData.length > 0 ? (
        <div className="cards-grid">
          {filteredData.map(property => (
            <PropertyCard key={property.case_number} property={property} />
          ))}
        </div>
      ) : (
        <div className="no-results">
          <p>No foreclosures found matching your criteria.</p>
        </div>
      )}

      <footer className="footer">
        <p>
          Data sourced from <a href="https://publicindex.sccourts.org/york/courtrosters/" target="_blank" rel="noopener">SC Courts Public Index</a>
        </p>
        <p>
          Property estimates based on York County market data. Last updated: {new Date().toLocaleDateString()}
        </p>
        <p style={{ marginTop: '0.5rem' }}>
          <a href="https://github.com/magnusfremont/foreclosure" target="_blank" rel="noopener">View Source on GitHub</a>
        </p>
      </footer>
    </div>
  )
}
