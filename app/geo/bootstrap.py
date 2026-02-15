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
    
    # Create geo_profiles table
    cursor.execute("""
        CREATE TABLE geo_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT NOT NULL,
            country_name TEXT,
            primary_currency TEXT,
            secondary_currencies TEXT,
            enforcement_tier TEXT,
            region TEXT,
            effective_from TEXT,
            effective_to TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_geo_profiles_country ON geo_profiles(country_code)
    """)
    
    # Create vat_rules table
    cursor.execute("""
        CREATE TABLE vat_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_code TEXT NOT NULL,
            tax_name TEXT NOT NULL,
            rate REAL,
            description TEXT,
            effective_from TEXT,
            effective_to TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_vat_rules_country ON vat_rules(country_code)
    """)
    
    # Create currency_country_map table
    cursor.execute("""
        CREATE TABLE currency_country_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT NOT NULL,
            country_code TEXT NOT NULL,
            is_primary BOOLEAN,
            weight REAL,
            effective_from TEXT,
            effective_to TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_currency_country_map_currency ON currency_country_map(currency)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_currency_country_map_country ON currency_country_map(country_code)
    """)
    
    # Create doc_expectations_by_geo table
    cursor.execute("""
        CREATE TABLE doc_expectations_by_geo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            geo_scope TEXT NOT NULL,
            geo_code TEXT NOT NULL,
            doc_family TEXT NOT NULL,
            doc_subtype TEXT NOT NULL,
            expectations TEXT,
            effective_from TEXT,
            effective_to TEXT
        )
    """)
    
    cursor.execute("""
        CREATE INDEX idx_doc_expectations_geo ON doc_expectations_by_geo(geo_scope, geo_code)
    """)
    
    # Seed postal patterns
    # NOTE: Removed standalone \b\d{6}\b for IN and SG - too ambiguous (overlaps with reference numbers, dates, etc.)
    postal_patterns = [
        # ("IN", r"\b\d{6}\b", 0.50, "India 6-digit PIN code"),  # REMOVED - Fix #1
        ("US", r"\b\d{5}(?:-\d{4})?\b", 0.25, "US ZIP code (5 or 9 digit)"),
        ("DE", r"\b\d{5}\b", 0.25, "Germany 5-digit postal code"),
        ("UK", r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b", 0.50, "UK postcode"),
        ("CA", r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", 0.50, "Canada postal code"),
        # ("SG", r"\b\d{6}\b", 0.30, "Singapore 6-digit postal code"),  # REMOVED - Fix #1
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
    
    # Seed geo_profiles
    geo_profiles = _get_geo_profiles()
    cursor.executemany("""
        INSERT INTO geo_profiles (country_code, country_name, primary_currency, secondary_currencies, enforcement_tier, region, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, geo_profiles)
    
    # Seed vat_rules
    vat_rules = _get_vat_rules()
    cursor.executemany("""
        INSERT INTO vat_rules (country_code, tax_name, rate, description, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?, ?)
    """, vat_rules)
    
    # Seed currency_country_map
    currency_map = _get_currency_country_map()
    cursor.executemany("""
        INSERT INTO currency_country_map (currency, country_code, is_primary, weight, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?, ?)
    """, currency_map)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Geo database bootstrapped: {db_path}")
    print(f"   - {len(postal_patterns)} postal patterns")
    print(f"   - {len(cities)} cities")
    print(f"   - {len(terms)} terms")
    print(f"   - {len(geo_profiles)} geo profiles")
    print(f"   - {len(vat_rules)} VAT rules")
    print(f"   - {len(currency_map)} currency mappings")

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
        
        # Kenya (top cities)
        ("KE", "nairobi", "Nairobi", "Nairobi County", "", 100),
        ("KE", "mombasa", "Mombasa", "Mombasa County", "", 99),
        ("KE", "kisumu", "Kisumu", "Kisumu County", "", 98),
        ("KE", "nakuru", "Nakuru", "Nakuru County", "", 97),
        ("KE", "eldoret", "Eldoret", "Uasin Gishu County", "", 96),
        ("KE", "thika", "Thika", "Kiambu County", "", 95),
        ("KE", "malindi", "Malindi", "Kilifi County", "", 94),
        
        # Nigeria (top cities)
        ("NG", "lagos", "Lagos", "Lagos", "", 100),
        ("NG", "abuja", "Abuja", "FCT", "", 99),
        ("NG", "kano", "Kano", "Kano", "", 98),
        ("NG", "ibadan", "Ibadan", "Oyo", "", 97),
        ("NG", "port harcourt", "Port Harcourt", "Rivers", "", 96),
        
        # South Africa (top cities)
        ("ZA", "johannesburg", "Johannesburg", "Gauteng", "joburg,jozi", 100),
        ("ZA", "cape town", "Cape Town", "Western Cape", "kaapstad", 99),
        ("ZA", "durban", "Durban", "KwaZulu-Natal", "ethekwini", 98),
        ("ZA", "pretoria", "Pretoria", "Gauteng", "tshwane", 97),
        ("ZA", "port elizabeth", "Port Elizabeth", "Eastern Cape", "gqeberha", 96),
        
        # Tanzania
        ("TZ", "dar es salaam", "Dar es Salaam", "Dar es Salaam", "dar", 100),
        ("TZ", "dodoma", "Dodoma", "Dodoma", "", 99),
        ("TZ", "mwanza", "Mwanza", "Mwanza", "", 98),
        
        # Uganda
        ("UG", "kampala", "Kampala", "Central", "", 100),
        ("UG", "entebbe", "Entebbe", "Wakiso", "", 99),
        
        # Japan (top cities)
        ("JP", "tokyo", "Tokyo", "Tokyo", "", 100),
        ("JP", "osaka", "Osaka", "Osaka", "", 99),
        ("JP", "yokohama", "Yokohama", "Kanagawa", "", 98),
        ("JP", "nagoya", "Nagoya", "Aichi", "", 97),
        ("JP", "sapporo", "Sapporo", "Hokkaido", "", 96),
        ("JP", "fukuoka", "Fukuoka", "Fukuoka", "", 95),
        ("JP", "kyoto", "Kyoto", "Kyoto", "", 94),
        
        # South Korea (top cities)
        ("KR", "seoul", "Seoul", "Seoul", "", 100),
        ("KR", "busan", "Busan", "Busan", "pusan", 99),
        ("KR", "incheon", "Incheon", "Incheon", "", 98),
        ("KR", "daegu", "Daegu", "Daegu", "taegu", 97),
        
        # Brazil (top cities)
        ("BR", "sao paulo", "São Paulo", "São Paulo", "são paulo", 100),
        ("BR", "rio de janeiro", "Rio de Janeiro", "Rio de Janeiro", "rio", 99),
        ("BR", "brasilia", "Brasília", "Distrito Federal", "brasília", 98),
        ("BR", "salvador", "Salvador", "Bahia", "", 97),
        ("BR", "fortaleza", "Fortaleza", "Ceará", "", 96),
        
        # Mexico (top cities)
        ("MX", "mexico city", "Mexico City", "CDMX", "ciudad de mexico,cdmx", 100),
        ("MX", "guadalajara", "Guadalajara", "Jalisco", "", 99),
        ("MX", "monterrey", "Monterrey", "Nuevo León", "", 98),
        ("MX", "puebla", "Puebla", "Puebla", "", 97),
        
        # Saudi Arabia (top cities)
        ("SA", "riyadh", "Riyadh", "Riyadh", "", 100),
        ("SA", "jeddah", "Jeddah", "Makkah", "jidda", 99),
        ("SA", "mecca", "Mecca", "Makkah", "makkah", 98),
        ("SA", "medina", "Medina", "Madinah", "madinah", 97),
        ("SA", "dammam", "Dammam", "Eastern Province", "", 96),
        
        # China (top cities)
        ("CN", "shanghai", "Shanghai", "Shanghai", "", 100),
        ("CN", "beijing", "Beijing", "Beijing", "peking", 99),
        ("CN", "guangzhou", "Guangzhou", "Guangdong", "canton", 98),
        ("CN", "shenzhen", "Shenzhen", "Guangdong", "", 97),
        ("CN", "chengdu", "Chengdu", "Sichuan", "", 96),
    ]

def _get_geo_profiles() -> List[Tuple]:
    """Get geo profile data (country_code, country_name, primary_currency, secondary_currencies, enforcement_tier, region, effective_from, effective_to)."""
    return [
        # India
        ("IN", "India", "INR", None, "STRICT", "APAC", "2020-01-01", None),
        
        # United States
        ("US", "United States", "USD", None, "STRICT", "AMERICAS", "2020-01-01", None),
        
        # Major EU Countries (80% coverage)
        ("DE", "Germany", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("FR", "France", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("IT", "Italy", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("ES", "Spain", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("NL", "Netherlands", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("BE", "Belgium", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("AT", "Austria", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("PT", "Portugal", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("IE", "Ireland", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("FI", "Finland", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        ("GR", "Greece", "EUR", None, "STRICT", "EU", "2020-01-01", None),
        
        # UK (non-EU but important)
        ("UK", "United Kingdom", "GBP", None, "STRICT", "EU", "2020-01-01", None),
        
        # Other important countries
        ("CA", "Canada", "CAD", None, "STRICT", "AMERICAS", "2020-01-01", None),
        ("AU", "Australia", "AUD", None, "RELAXED", "APAC", "2020-01-01", None),
        ("SG", "Singapore", "SGD", None, "RELAXED", "APAC", "2020-01-01", None),
        ("AE", "United Arab Emirates", "AED", None, "STRICT", "MENA", "2020-01-01", None),
        
        # Africa
        ("KE", "Kenya", "KES", None, "RELAXED", "AFRICA", "2020-01-01", None),
        ("NG", "Nigeria", "NGN", None, "RELAXED", "AFRICA", "2020-01-01", None),
        ("ZA", "South Africa", "ZAR", None, "RELAXED", "AFRICA", "2020-01-01", None),
        ("TZ", "Tanzania", "TZS", None, "RELAXED", "AFRICA", "2020-01-01", None),
        ("UG", "Uganda", "UGX", None, "RELAXED", "AFRICA", "2020-01-01", None),
        
        # Asia (additional)
        ("JP", "Japan", "JPY", None, "STRICT", "APAC", "2020-01-01", None),
        ("KR", "South Korea", "KRW", None, "STRICT", "APAC", "2020-01-01", None),
        ("CN", "China", "CNY", "RMB", "STRICT", "APAC", "2020-01-01", None),
        
        # Americas (additional)
        ("BR", "Brazil", "BRL", None, "STRICT", "AMERICAS", "2020-01-01", None),
        ("MX", "Mexico", "MXN", None, "STRICT", "AMERICAS", "2020-01-01", None),
        
        # Middle East (additional)
        ("SA", "Saudi Arabia", "SAR", None, "STRICT", "MENA", "2020-01-01", None),
    ]

def _get_vat_rules() -> List[Tuple]:
    """Get VAT rule data (country_code, tax_name, rate, description, effective_from, effective_to)."""
    return [
        # India - GST
        ("IN", "GST", 0.18, "Standard GST rate in India", "2020-01-01", None),
        ("IN", "GST", 0.12, "Reduced GST rate in India", "2020-01-01", None),
        ("IN", "GST", 0.05, "Lower GST rate in India", "2020-01-01", None),
        ("IN", "CGST", 0.09, "Central GST (half of 18% standard)", "2020-01-01", None),
        ("IN", "SGST", 0.09, "State GST (half of 18% standard)", "2020-01-01", None),
        
        # United States - Sales Tax (varies by state, these are examples)
        ("US", "SALES_TAX", 0.0725, "California sales tax (example)", "2020-01-01", None),
        ("US", "SALES_TAX", 0.0625, "Texas sales tax (example)", "2020-01-01", None),
        ("US", "SALES_TAX", 0.08875, "New York City sales tax (example)", "2020-01-01", None),
        
        # Germany - VAT
        ("DE", "VAT", 0.19, "Standard VAT rate in Germany", "2020-01-01", None),
        ("DE", "VAT", 0.07, "Reduced VAT rate in Germany", "2020-01-01", None),
        
        # France - VAT
        ("FR", "VAT", 0.20, "Standard VAT rate in France", "2020-01-01", None),
        ("FR", "VAT", 0.10, "Intermediate VAT rate in France", "2020-01-01", None),
        ("FR", "VAT", 0.055, "Reduced VAT rate in France", "2020-01-01", None),
        
        # Italy - VAT
        ("IT", "VAT", 0.22, "Standard VAT rate in Italy", "2020-01-01", None),
        ("IT", "VAT", 0.10, "Reduced VAT rate in Italy", "2020-01-01", None),
        ("IT", "VAT", 0.04, "Super-reduced VAT rate in Italy", "2020-01-01", None),
        
        # Spain - VAT
        ("ES", "VAT", 0.21, "Standard VAT rate in Spain", "2020-01-01", None),
        ("ES", "VAT", 0.10, "Reduced VAT rate in Spain", "2020-01-01", None),
        ("ES", "VAT", 0.04, "Super-reduced VAT rate in Spain", "2020-01-01", None),
        
        # Netherlands - VAT
        ("NL", "VAT", 0.21, "Standard VAT rate in Netherlands", "2020-01-01", None),
        ("NL", "VAT", 0.09, "Reduced VAT rate in Netherlands", "2020-01-01", None),
        
        # Belgium - VAT
        ("BE", "VAT", 0.21, "Standard VAT rate in Belgium", "2020-01-01", None),
        ("BE", "VAT", 0.12, "Intermediate VAT rate in Belgium", "2020-01-01", None),
        ("BE", "VAT", 0.06, "Reduced VAT rate in Belgium", "2020-01-01", None),
        
        # Austria - VAT
        ("AT", "VAT", 0.20, "Standard VAT rate in Austria", "2020-01-01", None),
        ("AT", "VAT", 0.10, "Reduced VAT rate in Austria", "2020-01-01", None),
        
        # Portugal - VAT
        ("PT", "VAT", 0.23, "Standard VAT rate in Portugal", "2020-01-01", None),
        ("PT", "VAT", 0.13, "Intermediate VAT rate in Portugal", "2020-01-01", None),
        ("PT", "VAT", 0.06, "Reduced VAT rate in Portugal", "2020-01-01", None),
        
        # Ireland - VAT
        ("IE", "VAT", 0.23, "Standard VAT rate in Ireland", "2020-01-01", None),
        ("IE", "VAT", 0.135, "Reduced VAT rate in Ireland", "2020-01-01", None),
        ("IE", "VAT", 0.09, "Second reduced VAT rate in Ireland", "2020-01-01", None),
        
        # Finland - VAT
        ("FI", "VAT", 0.24, "Standard VAT rate in Finland", "2020-01-01", None),
        ("FI", "VAT", 0.14, "Intermediate VAT rate in Finland", "2020-01-01", None),
        ("FI", "VAT", 0.10, "Reduced VAT rate in Finland", "2020-01-01", None),
        
        # Greece - VAT
        ("GR", "VAT", 0.24, "Standard VAT rate in Greece", "2020-01-01", None),
        ("GR", "VAT", 0.13, "Reduced VAT rate in Greece", "2020-01-01", None),
        ("GR", "VAT", 0.06, "Super-reduced VAT rate in Greece", "2020-01-01", None),
        
        # United Kingdom - VAT
        ("UK", "VAT", 0.20, "Standard VAT rate in UK", "2020-01-01", None),
        ("UK", "VAT", 0.05, "Reduced VAT rate in UK", "2020-01-01", None),
        
        # Canada - GST/HST/PST
        ("CA", "GST", 0.05, "Federal GST in Canada", "2020-01-01", None),
        ("CA", "HST", 0.13, "Harmonized Sales Tax (Ontario)", "2020-01-01", None),
        ("CA", "HST", 0.15, "Harmonized Sales Tax (Atlantic provinces)", "2020-01-01", None),
        ("CA", "PST", 0.07, "Provincial Sales Tax (BC)", "2020-01-01", None),
        
        # Australia - GST
        ("AU", "GST", 0.10, "Goods and Services Tax in Australia", "2020-01-01", None),
        
        # Singapore - GST
        ("SG", "GST", 0.08, "Goods and Services Tax in Singapore (current)", "2023-01-01", None),
        ("SG", "GST", 0.09, "Goods and Services Tax in Singapore (2024)", "2024-01-01", None),
        
        # UAE - VAT
        ("AE", "VAT", 0.05, "Value Added Tax in UAE", "2020-01-01", None),
    ]

def _get_currency_country_map() -> List[Tuple]:
    """Get currency-country mapping data (currency, country_code, is_primary, weight, effective_from, effective_to)."""
    return [
        # INR - India
        ("INR", "IN", True, 1.0, "2020-01-01", None),
        
        # USD - United States
        ("USD", "US", True, 1.0, "2020-01-01", None),
        
        # EUR - Eurozone countries
        ("EUR", "DE", True, 1.0, "2020-01-01", None),
        ("EUR", "FR", True, 1.0, "2020-01-01", None),
        ("EUR", "IT", True, 1.0, "2020-01-01", None),
        ("EUR", "ES", True, 1.0, "2020-01-01", None),
        ("EUR", "NL", True, 1.0, "2020-01-01", None),
        ("EUR", "BE", True, 1.0, "2020-01-01", None),
        ("EUR", "AT", True, 1.0, "2020-01-01", None),
        ("EUR", "PT", True, 1.0, "2020-01-01", None),
        ("EUR", "IE", True, 1.0, "2020-01-01", None),
        ("EUR", "FI", True, 1.0, "2020-01-01", None),
        ("EUR", "GR", True, 1.0, "2020-01-01", None),
        
        # GBP - United Kingdom
        ("GBP", "UK", True, 1.0, "2020-01-01", None),
        
        # CAD - Canada
        ("CAD", "CA", True, 1.0, "2020-01-01", None),
        
        # AUD - Australia
        ("AUD", "AU", True, 1.0, "2020-01-01", None),
        
        # SGD - Singapore
        ("SGD", "SG", True, 1.0, "2020-01-01", None),
        
        # AED - UAE
        ("AED", "AE", True, 1.0, "2020-01-01", None),
        
        # Africa
        ("KES", "KE", True, 1.0, "2020-01-01", None),
        ("NGN", "NG", True, 1.0, "2020-01-01", None),
        ("ZAR", "ZA", True, 1.0, "2020-01-01", None),
        ("TZS", "TZ", True, 1.0, "2020-01-01", None),
        ("UGX", "UG", True, 1.0, "2020-01-01", None),
        
        # Asia (additional)
        ("JPY", "JP", True, 1.0, "2020-01-01", None),
        ("KRW", "KR", True, 1.0, "2020-01-01", None),
        ("CNY", "CN", True, 1.0, "2020-01-01", None),
        
        # Americas (additional)
        ("BRL", "BR", True, 1.0, "2020-01-01", None),
        ("MXN", "MX", True, 1.0, "2020-01-01", None),
        
        # Middle East (additional)
        ("SAR", "SA", True, 1.0, "2020-01-01", None),
    ]

def _get_seed_terms() -> List[Tuple]:
    """Get seed term data (country, kind, token_norm, weight, examples)."""
    return [
        # India terms
        ("IN", "tax", "gstin", 0.25, "GSTIN, GST Identification Number"),
        ("IN", "tax", "gst", 0.15, "GST (shared with SG/CA/AU, lower weight)"),
        ("IN", "tax", "cgst", 0.20, "CGST (Central GST)"),
        ("IN", "tax", "sgst", 0.20, "SGST (State GST)"),
        ("IN", "tax", "igst", 0.20, "IGST (Integrated GST)"),
        ("IN", "tax", "pan", 0.15, "PAN (Permanent Account Number)"),
        ("IN", "address", "pin code", 0.15, "PIN Code, Pincode"),
        ("IN", "address", "pin", 0.10, "PIN"),
        ("IN", "currency", "inr", 0.10, "INR, ₹, Rs"),
        ("IN", "currency", "₹", 0.20, "₹ (Rupee symbol - strong India signal)"),
        ("IN", "currency", "rs", 0.10, "Rs, Rs."),
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
        
        # Kenya terms
        ("KE", "address", "kenya", 0.25, "Kenya"),
        ("KE", "address", "nairobi", 0.20, "Nairobi"),
        ("KE", "address", "mombasa", 0.15, "Mombasa"),
        ("KE", "currency", "kes", 0.20, "KES, Kenyan Shilling"),
        ("KE", "currency", "ksh", 0.15, "KSh"),
        ("KE", "phone", "+254", 0.20, "+254"),
        ("KE", "business", "ltd", 0.05, "Ltd, Limited"),
        ("KE", "tax", "kra", 0.20, "KRA (Kenya Revenue Authority)"),
        ("KE", "tax", "pin", 0.10, "PIN (Personal Identification Number)"),
        
        # Nigeria terms
        ("NG", "address", "nigeria", 0.25, "Nigeria"),
        ("NG", "address", "lagos", 0.20, "Lagos"),
        ("NG", "currency", "ngn", 0.20, "NGN, Naira"),
        ("NG", "phone", "+234", 0.20, "+234"),
        ("NG", "tax", "tin", 0.15, "TIN (Tax Identification Number)"),
        ("NG", "tax", "firs", 0.15, "FIRS (Federal Inland Revenue Service)"),
        
        # South Africa terms
        ("ZA", "address", "south africa", 0.25, "South Africa"),
        ("ZA", "currency", "zar", 0.20, "ZAR, Rand"),
        ("ZA", "phone", "+27", 0.20, "+27"),
        ("ZA", "tax", "sars", 0.20, "SARS (South African Revenue Service)"),
        
        # Tanzania terms
        ("TZ", "address", "tanzania", 0.25, "Tanzania"),
        ("TZ", "currency", "tzs", 0.20, "TZS, Tanzanian Shilling"),
        ("TZ", "phone", "+255", 0.20, "+255"),
        
        # Uganda terms
        ("UG", "address", "uganda", 0.25, "Uganda"),
        ("UG", "currency", "ugx", 0.20, "UGX, Ugandan Shilling"),
        ("UG", "phone", "+256", 0.20, "+256"),
        
        # Japan terms
        ("JP", "address", "japan", 0.25, "Japan"),
        ("JP", "currency", "jpy", 0.20, "JPY, Yen"),
        ("JP", "phone", "+81", 0.20, "+81"),
        ("JP", "tax", "consumption tax", 0.20, "Consumption Tax"),
        
        # South Korea terms
        ("KR", "address", "south korea", 0.25, "South Korea"),
        ("KR", "address", "korea", 0.20, "Korea"),
        ("KR", "currency", "krw", 0.20, "KRW, Won"),
        ("KR", "phone", "+82", 0.20, "+82"),
        
        # Brazil terms
        ("BR", "address", "brazil", 0.25, "Brazil, Brasil"),
        ("BR", "currency", "brl", 0.20, "BRL, Real"),
        ("BR", "phone", "+55", 0.20, "+55"),
        ("BR", "tax", "cnpj", 0.25, "CNPJ (company tax ID)"),
        ("BR", "tax", "cpf", 0.20, "CPF (individual tax ID)"),
        
        # Mexico terms
        ("MX", "address", "mexico", 0.25, "Mexico, México"),
        ("MX", "currency", "mxn", 0.20, "MXN, Peso"),
        ("MX", "phone", "+52", 0.20, "+52"),
        ("MX", "tax", "rfc", 0.25, "RFC (Registro Federal de Contribuyentes)"),
        ("MX", "tax", "cfdi", 0.20, "CFDI (digital invoice)"),
        
        # Saudi Arabia terms
        ("SA", "address", "saudi arabia", 0.25, "Saudi Arabia, KSA"),
        ("SA", "currency", "sar", 0.20, "SAR, Riyal"),
        ("SA", "phone", "+966", 0.20, "+966"),
        ("SA", "tax", "vat", 0.15, "VAT"),
        ("SA", "tax", "zatca", 0.20, "ZATCA"),
        
        # China terms
        ("CN", "address", "china", 0.25, "China, PRC"),
        ("CN", "currency", "cny", 0.20, "CNY, Yuan, RMB"),
        ("CN", "currency", "rmb", 0.15, "RMB"),
        ("CN", "phone", "+86", 0.20, "+86"),
        ("CN", "tax", "fapiao", 0.25, "Fapiao (official invoice)"),
    ]

if __name__ == "__main__":
    bootstrap_geo_db()
