"""
Bootstrap geo database with initial seed data.
Creates SQLite database with postal patterns, cities, and terms.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple

def bootstrap_geo_db():
    """Create and populate geo.sqlite database with seed data."""
    db_path = Path(__file__).parent.parent / "data" / "geo.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing database if present
    if db_path.exists():
        db_path.unlink()
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE postal_patterns (
            country_code TEXT PRIMARY KEY,
            pattern TEXT NOT NULL,
            weight REAL NOT NULL,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT NOT NULL,
            name_norm TEXT NOT NULL,
            display_name TEXT NOT NULL,
            admin1 TEXT,
            alt_names TEXT,
            pop_rank INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_cities_country ON cities(country_code)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_cities_name ON cities(name_norm)
    """)
    
    cursor.execute("""
        CREATE TABLE terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT NOT NULL,
            kind TEXT NOT NULL,
            token_norm TEXT NOT NULL,
            weight REAL NOT NULL,
            examples TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_terms_country ON terms(country_code)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_terms_kind ON terms(kind)
    """)
    
    # Seed postal patterns
    postal_patterns = [
        ("IN", r"\b\d{6}\b", 0.50, "India 6-digit PIN code"),
        ("US", r"\b\d{5}(?:-\d{4})?\b", 0.25, "US ZIP code (5 or 9 digit)"),
        ("DE", r"\b\d{5}\b", 0.25, "Germany 5-digit postal code"),
        ("UK", r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", 0.50, "UK postcode"),
        ("CA", r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", 0.50, "Canada postal code"),
        ("SG", r"\b\d{6}\b", 0.30, "Singapore 6-digit postal code"),
        ("AU", r"\b\d{4}\b", 0.30, "Australia 4-digit postcode"),
        ("AE", r"\b\d{5}\b", 0.20, "UAE postal code (weak signal)"),
    ]
    
    cursor.executemany("""
        INSERT INTO postal_patterns (country_code, pattern, weight, description)
        VALUES (?, ?, ?, ?)
    """, postal_patterns)
    
    # Seed cities (top cities per country)
    cities = _get_seed_cities()
    cursor.executemany("""
        INSERT INTO cities (country_code, name_norm, display_name, admin1, alt_names, pop_rank)
        VALUES (?, ?, ?, ?, ?, ?)
    """, cities)
    
    # Seed terms
    terms = _get_seed_terms()
    cursor.executemany("""
        INSERT INTO terms (country_code, kind, token_norm, weight, examples)
        VALUES (?, ?, ?, ?, ?)
    """, terms)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Geo database bootstrapped: {db_path}")
    print(f"   - {len(postal_patterns)} postal patterns")
    print(f"   - {len(cities)} cities")
    print(f"   - {len(terms)} terms")

def _get_seed_cities() -> List[Tuple]:
    """Get seed city data (country, name_norm, display_name, admin1, alt_names, pop_rank)."""
    return [
        # India (top 50 cities)
        ("IN", "mumbai", "Mumbai", "Maharashtra", "bombay", 100),
        ("IN", "delhi", "Delhi", "Delhi", "new delhi", 99),
        ("IN", "bangalore", "Bangalore", "Karnataka", "bengaluru,bangaluru", 98),
        ("IN", "hyderabad", "Hyderabad", "Telangana", "", 97),
        ("IN", "chennai", "Chennai", "Tamil Nadu", "madras", 96),
        ("IN", "kolkata", "Kolkata", "West Bengal", "calcutta", 95),
        ("IN", "pune", "Pune", "Maharashtra", "poona", 94),
        ("IN", "ahmedabad", "Ahmedabad", "Gujarat", "amdavad", 93),
        ("IN", "jaipur", "Jaipur", "Rajasthan", "", 92),
        ("IN", "surat", "Surat", "Gujarat", "", 91),
        ("IN", "lucknow", "Lucknow", "Uttar Pradesh", "", 90),
        ("IN", "kanpur", "Kanpur", "Uttar Pradesh", "", 89),
        ("IN", "nagpur", "Nagpur", "Maharashtra", "", 88),
        ("IN", "indore", "Indore", "Madhya Pradesh", "", 87),
        ("IN", "thane", "Thane", "Maharashtra", "", 86),
        ("IN", "bhopal", "Bhopal", "Madhya Pradesh", "", 85),
        ("IN", "visakhapatnam", "Visakhapatnam", "Andhra Pradesh", "vizag", 84),
        ("IN", "pimpri", "Pimpri-Chinchwad", "Maharashtra", "chinchwad", 83),
        ("IN", "patna", "Patna", "Bihar", "", 82),
        ("IN", "vadodara", "Vadodara", "Gujarat", "baroda", 81),
        
        # US (top 30 cities)
        ("US", "new york", "New York", "NY", "nyc,new york city", 100),
        ("US", "los angeles", "Los Angeles", "CA", "la,l.a.", 99),
        ("US", "chicago", "Chicago", "IL", "", 98),
        ("US", "houston", "Houston", "TX", "", 97),
        ("US", "phoenix", "Phoenix", "AZ", "", 96),
        ("US", "philadelphia", "Philadelphia", "PA", "philly", 95),
        ("US", "san antonio", "San Antonio", "TX", "", 94),
        ("US", "san diego", "San Diego", "CA", "", 93),
        ("US", "dallas", "Dallas", "TX", "", 92),
        ("US", "san jose", "San Jose", "CA", "", 91),
        ("US", "austin", "Austin", "TX", "", 90),
        ("US", "jacksonville", "Jacksonville", "FL", "", 89),
        ("US", "fort worth", "Fort Worth", "TX", "", 88),
        ("US", "columbus", "Columbus", "OH", "", 87),
        ("US", "charlotte", "Charlotte", "NC", "", 86),
        ("US", "san francisco", "San Francisco", "CA", "sf,frisco", 85),
        ("US", "indianapolis", "Indianapolis", "IN", "indy", 84),
        ("US", "seattle", "Seattle", "WA", "", 83),
        ("US", "denver", "Denver", "CO", "", 82),
        ("US", "boston", "Boston", "MA", "", 81),
        
        # Germany (top 20 cities)
        ("DE", "berlin", "Berlin", "Berlin", "", 100),
        ("DE", "hamburg", "Hamburg", "Hamburg", "", 99),
        ("DE", "munich", "Munich", "Bavaria", "münchen,muenchen", 98),
        ("DE", "cologne", "Cologne", "North Rhine-Westphalia", "köln,koeln", 97),
        ("DE", "frankfurt", "Frankfurt", "Hesse", "frankfurt am main", 96),
        ("DE", "stuttgart", "Stuttgart", "Baden-Württemberg", "", 95),
        ("DE", "düsseldorf", "Düsseldorf", "North Rhine-Westphalia", "dusseldorf,duesseldorf", 94),
        ("DE", "dortmund", "Dortmund", "North Rhine-Westphalia", "", 93),
        ("DE", "essen", "Essen", "North Rhine-Westphalia", "", 92),
        ("DE", "leipzig", "Leipzig", "Saxony", "", 91),
        ("DE", "bremen", "Bremen", "Bremen", "", 90),
        ("DE", "dresden", "Dresden", "Saxony", "", 89),
        ("DE", "hanover", "Hanover", "Lower Saxony", "hannover", 88),
        ("DE", "nuremberg", "Nuremberg", "Bavaria", "nürnberg,nuernberg", 87),
        ("DE", "duisburg", "Duisburg", "North Rhine-Westphalia", "", 86),
        
        # UK (top 20 cities)
        ("UK", "london", "London", "England", "", 100),
        ("UK", "birmingham", "Birmingham", "England", "", 99),
        ("UK", "manchester", "Manchester", "England", "", 98),
        ("UK", "leeds", "Leeds", "England", "", 97),
        ("UK", "glasgow", "Glasgow", "Scotland", "", 96),
        ("UK", "liverpool", "Liverpool", "England", "", 95),
        ("UK", "edinburgh", "Edinburgh", "Scotland", "", 94),
        ("UK", "bristol", "Bristol", "England", "", 93),
        ("UK", "cardiff", "Cardiff", "Wales", "", 92),
        ("UK", "sheffield", "Sheffield", "England", "", 91),
        ("UK", "newcastle", "Newcastle", "England", "newcastle upon tyne", 90),
        ("UK", "belfast", "Belfast", "Northern Ireland", "", 89),
        ("UK", "nottingham", "Nottingham", "England", "", 88),
        ("UK", "leicester", "Leicester", "England", "", 87),
        
        # Canada (top 15 cities)
        ("CA", "toronto", "Toronto", "Ontario", "", 100),
        ("CA", "montreal", "Montreal", "Quebec", "montréal", 99),
        ("CA", "vancouver", "Vancouver", "British Columbia", "", 98),
        ("CA", "calgary", "Calgary", "Alberta", "", 97),
        ("CA", "edmonton", "Edmonton", "Alberta", "", 96),
        ("CA", "ottawa", "Ottawa", "Ontario", "", 95),
        ("CA", "winnipeg", "Winnipeg", "Manitoba", "", 94),
        ("CA", "quebec city", "Quebec City", "Quebec", "québec", 93),
        ("CA", "hamilton", "Hamilton", "Ontario", "", 92),
        ("CA", "kitchener", "Kitchener", "Ontario", "", 91),
        
        # Singapore
        ("SG", "singapore", "Singapore", "Singapore", "", 100),
        
        # UAE (top 5 cities)
        ("AE", "dubai", "Dubai", "Dubai", "", 100),
        ("AE", "abu dhabi", "Abu Dhabi", "Abu Dhabi", "abudhabi", 99),
        ("AE", "sharjah", "Sharjah", "Sharjah", "", 98),
        ("AE", "ajman", "Ajman", "Ajman", "", 97),
        ("AE", "ras al khaimah", "Ras Al Khaimah", "Ras Al Khaimah", "rak", 96),
        
        # Australia (top 15 cities)
        ("AU", "sydney", "Sydney", "New South Wales", "", 100),
        ("AU", "melbourne", "Melbourne", "Victoria", "", 99),
        ("AU", "brisbane", "Brisbane", "Queensland", "", 98),
        ("AU", "perth", "Perth", "Western Australia", "", 97),
        ("AU", "adelaide", "Adelaide", "South Australia", "", 96),
        ("AU", "gold coast", "Gold Coast", "Queensland", "", 95),
        ("AU", "canberra", "Canberra", "Australian Capital Territory", "", 94),
        ("AU", "newcastle", "Newcastle", "New South Wales", "", 93),
        ("AU", "wollongong", "Wollongong", "New South Wales", "", 92),
        ("AU", "hobart", "Hobart", "Tasmania", "", 91),
    ]

def _get_seed_terms() -> List[Tuple]:
    """Get seed term data (country, kind, token_norm, weight, examples)."""
    return [
        # India terms
        ("IN", "tax", "gstin", 0.25, "GSTIN, GST Identification Number"),
        ("IN", "tax", "cgst", 0.20, "CGST (Central GST)"),
        ("IN", "tax", "sgst", 0.20, "SGST (State GST)"),
        ("IN", "tax", "igst", 0.20, "IGST (Integrated GST)"),
        ("IN", "tax", "pan", 0.15, "PAN (Permanent Account Number)"),
        ("IN", "address", "pin code", 0.15, "PIN Code, Pincode"),
        ("IN", "address", "pin", 0.10, "PIN"),
        ("IN", "currency", "inr", 0.10, "INR, ₹, Rs"),
        ("IN", "currency", "rupees", 0.10, "Rupees, Rs."),
        ("IN", "phone", "+91", 0.20, "+91, 91"),
        
        # US terms
        ("US", "tax", "sales tax", 0.20, "Sales Tax"),
        ("US", "tax", "tax id", 0.15, "Tax ID, TIN, EIN"),
        ("US", "tax", "ein", 0.15, "EIN (Employer Identification Number)"),
        ("US", "address", "zip", 0.15, "ZIP, ZIP Code"),
        ("US", "address", "zip code", 0.15, "ZIP Code"),
        ("US", "currency", "usd", 0.10, "USD, $"),
        ("US", "phone", "+1", 0.20, "+1, 1-"),
        ("US", "business", "llc", 0.10, "LLC, Inc., Corp."),
        ("US", "business", "inc", 0.10, "Inc., Incorporated"),
        
        # Germany terms
        ("DE", "tax", "mwst", 0.25, "MwSt (Mehrwertsteuer)"),
        ("DE", "tax", "ust-idnr", 0.25, "USt-IdNr (Umsatzsteuer-Identifikationsnummer)"),
        ("DE", "tax", "steuernummer", 0.20, "Steuernummer"),
        ("DE", "tax", "umsatzsteuer", 0.20, "Umsatzsteuer"),
        ("DE", "document", "rechnung", 0.15, "Rechnung (Invoice)"),
        ("DE", "document", "quittung", 0.15, "Quittung (Receipt)"),
        ("DE", "currency", "eur", 0.10, "EUR, €"),
        ("DE", "phone", "+49", 0.20, "+49"),
        ("DE", "address", "plz", 0.10, "PLZ (Postleitzahl)"),
        
        # UK terms
        ("UK", "tax", "vat", 0.25, "VAT (Value Added Tax)"),
        ("UK", "tax", "vat number", 0.25, "VAT Number, VAT Reg No"),
        ("UK", "tax", "vat reg", 0.20, "VAT Registration"),
        ("UK", "currency", "gbp", 0.10, "GBP, £"),
        ("UK", "phone", "+44", 0.20, "+44"),
        ("UK", "address", "postcode", 0.15, "Postcode, Post Code"),
        
        # Canada terms
        ("CA", "tax", "gst", 0.20, "GST (Goods and Services Tax)"),
        ("CA", "tax", "hst", 0.20, "HST (Harmonized Sales Tax)"),
        ("CA", "tax", "pst", 0.15, "PST (Provincial Sales Tax)"),
        ("CA", "currency", "cad", 0.10, "CAD, C$"),
        ("CA", "phone", "+1", 0.20, "+1"),
        ("CA", "address", "postal code", 0.15, "Postal Code"),
        
        # Singapore terms
        ("SG", "tax", "gst", 0.25, "GST (Goods and Services Tax)"),
        ("SG", "tax", "uen", 0.20, "UEN (Unique Entity Number)"),
        ("SG", "currency", "sgd", 0.10, "SGD, S$"),
        ("SG", "phone", "+65", 0.20, "+65"),
        
        # UAE terms
        ("AE", "tax", "trn", 0.25, "TRN (Tax Registration Number)"),
        ("AE", "tax", "vat", 0.20, "VAT"),
        ("AE", "currency", "aed", 0.10, "AED, Dirham"),
        ("AE", "phone", "+971", 0.20, "+971"),
        ("AE", "address", "dubai", 0.15, "Dubai"),
        ("AE", "address", "abu dhabi", 0.15, "Abu Dhabi"),
        
        # Australia terms
        ("AU", "tax", "abn", 0.25, "ABN (Australian Business Number)"),
        ("AU", "tax", "acn", 0.20, "ACN (Australian Company Number)"),
        ("AU", "tax", "gst", 0.20, "GST"),
        ("AU", "currency", "aud", 0.10, "AUD, A$"),
        ("AU", "phone", "+61", 0.20, "+61"),
        ("AU", "address", "postcode", 0.15, "Postcode"),
    ]

if __name__ == "__main__":
    bootstrap_geo_db()
