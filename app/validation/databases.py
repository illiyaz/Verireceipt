"""
Offline Databases for Validation
PIN codes, Merchants, Cities
"""

# Indian PIN Code Database (Sample - Top 100 major cities)
# In production, load from JSON file with 19,000+ entries
PIN_CODE_DB = {
    # Hyderabad
    "500001": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Central"},
    "500002": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Central"},
    "500003": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Secunderabad"},
    "500016": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Malakpet"},
    "500081": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Gachibowli"},
    "500032": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Jubilee Hills"},
    "500034": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "Somajiguda"},
    "500082": {"city": "Hyderabad", "state": "Telangana", "district": "Hyderabad", "region": "HITEC City"},
    
    # Bangalore
    "560001": {"city": "Bangalore", "state": "Karnataka", "district": "Bangalore Urban", "region": "Central"},
    "560002": {"city": "Bangalore", "state": "Karnataka", "district": "Bangalore Urban", "region": "Shivaji Nagar"},
    "560034": {"city": "Bangalore", "state": "Karnataka", "district": "Bangalore Urban", "region": "Indiranagar"},
    "560066": {"city": "Bangalore", "state": "Karnataka", "district": "Bangalore Urban", "region": "Whitefield"},
    "560100": {"city": "Bangalore", "state": "Karnataka", "district": "Bangalore Urban", "region": "Electronic City"},
    
    # Mumbai
    "400001": {"city": "Mumbai", "state": "Maharashtra", "district": "Mumbai", "region": "Fort"},
    "400050": {"city": "Mumbai", "state": "Maharashtra", "district": "Mumbai", "region": "Bandra"},
    "400099": {"city": "Mumbai", "state": "Maharashtra", "district": "Mumbai", "region": "Airport"},
    "400051": {"city": "Mumbai", "state": "Maharashtra", "district": "Mumbai", "region": "Andheri"},
    
    # Delhi
    "110001": {"city": "New Delhi", "state": "Delhi", "district": "Central Delhi", "region": "Connaught Place"},
    "110037": {"city": "New Delhi", "state": "Delhi", "district": "South West Delhi", "region": "Airport"},
    "110016": {"city": "New Delhi", "state": "Delhi", "district": "South Delhi", "region": "Lajpat Nagar"},
    "110019": {"city": "New Delhi", "state": "Delhi", "district": "South Delhi", "region": "Defence Colony"},
    
    # Chennai
    "600001": {"city": "Chennai", "state": "Tamil Nadu", "district": "Chennai", "region": "Central"},
    "600027": {"city": "Chennai", "state": "Tamil Nadu", "district": "Chennai", "region": "Airport"},
    "600028": {"city": "Chennai", "state": "Tamil Nadu", "district": "Chennai", "region": "T Nagar"},
    
    # Pune
    "411001": {"city": "Pune", "state": "Maharashtra", "district": "Pune", "region": "Central"},
    "411014": {"city": "Pune", "state": "Maharashtra", "district": "Pune", "region": "Hinjewadi"},
    
    # Kolkata
    "700001": {"city": "Kolkata", "state": "West Bengal", "district": "Kolkata", "region": "Central"},
    "700016": {"city": "Kolkata", "state": "West Bengal", "district": "Kolkata", "region": "Park Street"},
}

# City-State mapping
CITY_STATE_MAP = {
    "hyderabad": ["telangana"],
    "bangalore": ["karnataka"],
    "bengaluru": ["karnataka"],
    "mumbai": ["maharashtra"],
    "delhi": ["delhi"],
    "new delhi": ["delhi"],
    "chennai": ["tamil nadu"],
    "pune": ["maharashtra"],
    "kolkata": ["west bengal"],
    "ahmedabad": ["gujarat"],
    "jaipur": ["rajasthan"],
    "lucknow": ["uttar pradesh"],
    "kanpur": ["uttar pradesh"],
    "nagpur": ["maharashtra"],
    "indore": ["madhya pradesh"],
    "thane": ["maharashtra"],
    "bhopal": ["madhya pradesh"],
    "visakhapatnam": ["andhra pradesh"],
    "pimpri": ["maharashtra"],
    "patna": ["bihar"],
}

# Known Merchants Database
KNOWN_MERCHANTS = {
    "reliance_digital": {
        "official_names": ["Reliance Digital", "Reliance Digital Store", "R-Digital"],
        "category": "electronics",
        "locations": {
            "hyderabad": ["500001", "500002", "500016", "500081", "500032"],
            "bangalore": ["560001", "560034", "560066"],
            "mumbai": ["400001", "400050", "400051"],
            "delhi": ["110001", "110016"],
        },
        "typical_items": ["mobile", "laptop", "tv", "tablet", "camera", "headphone", "speaker", "watch", "appliance"],
        "price_range": {"min": 100, "max": 200000},
        "accepts_payment": ["card", "upi", "cash", "emi"],
        "business_hours": (10, 22),  # 10 AM - 10 PM
    },
    "mcdonalds": {
        "official_names": ["McDonald's", "McDonalds", "Mc Donald's"],
        "category": "restaurant",
        "locations": {
            "hyderabad": ["500001", "500016", "500081", "500032", "500034"],
            "bangalore": ["560001", "560034", "560066"],
            "mumbai": ["400001", "400050", "400051"],
            "delhi": ["110001", "110016", "110019"],
        },
        "typical_items": ["burger", "fries", "mcaloo", "chicken", "nugget", "wrap", "coke", "coffee", "ice cream"],
        "price_range": {"min": 50, "max": 1000},
        "accepts_payment": ["card", "upi", "cash"],
        "business_hours": (7, 23),  # 7 AM - 11 PM
    },
    "starbucks": {
        "official_names": ["Starbucks", "Starbucks Coffee"],
        "category": "cafe",
        "locations": {
            "hyderabad": ["500032", "500034", "500081"],
            "bangalore": ["560001", "560034", "560066"],
            "mumbai": ["400001", "400050", "400051"],
            "delhi": ["110001", "110016"],
        },
        "typical_items": ["coffee", "latte", "cappuccino", "frappuccino", "tea", "sandwich", "cake", "cookie"],
        "price_range": {"min": 100, "max": 2000},
        "accepts_payment": ["card", "upi"],
        "business_hours": (7, 23),
    },
    "big_bazaar": {
        "official_names": ["Big Bazaar", "BigBazaar"],
        "category": "retail",
        "locations": {
            "hyderabad": ["500001", "500016", "500081"],
            "bangalore": ["560001", "560034"],
            "mumbai": ["400001", "400050"],
            "delhi": ["110001", "110016"],
        },
        "typical_items": ["grocery", "clothing", "home", "kitchen", "personal care", "food"],
        "price_range": {"min": 50, "max": 50000},
        "accepts_payment": ["card", "upi", "cash"],
        "business_hours": (9, 22),
    },
    "dmart": {
        "official_names": ["DMart", "D-Mart", "D Mart"],
        "category": "grocery",
        "locations": {
            "hyderabad": ["500016", "500081"],
            "bangalore": ["560034", "560066"],
            "mumbai": ["400050", "400051"],
            "pune": ["411001", "411014"],
        },
        "typical_items": ["grocery", "food", "personal care", "home", "kitchen"],
        "price_range": {"min": 50, "max": 20000},
        "accepts_payment": ["card", "upi", "cash"],
        "business_hours": (8, 22),
    },
    "apollo_pharmacy": {
        "official_names": ["Apollo Pharmacy", "Apollo"],
        "category": "pharmacy",
        "locations": {
            "hyderabad": ["500001", "500002", "500016", "500081"],
            "bangalore": ["560001", "560034"],
            "mumbai": ["400001", "400050"],
            "delhi": ["110001", "110016"],
        },
        "typical_items": ["medicine", "tablet", "syrup", "injection", "health", "wellness"],
        "price_range": {"min": 10, "max": 10000},
        "accepts_payment": ["card", "upi", "cash"],
        "business_hours": (0, 24),  # 24/7
    },
    "dominos": {
        "official_names": ["Domino's Pizza", "Dominos", "Domino's"],
        "category": "restaurant",
        "locations": {
            "hyderabad": ["500001", "500016", "500081", "500032"],
            "bangalore": ["560001", "560034", "560066"],
            "mumbai": ["400001", "400050"],
            "delhi": ["110001", "110016"],
        },
        "typical_items": ["pizza", "pasta", "garlic bread", "coke", "dessert"],
        "price_range": {"min": 100, "max": 2000},
        "accepts_payment": ["card", "upi", "cash"],
        "business_hours": (10, 23),
    },
}

# Airport PIN codes (for airport merchant validation)
AIRPORT_PINS = {
    "560300": "Bangalore Airport",
    "400099": "Mumbai Airport",
    "110037": "Delhi Airport",
    "500409": "Hyderabad Airport",
    "600027": "Chennai Airport",
}

# Valid phone prefixes (India)
VALID_MOBILE_PREFIXES = ['6', '7', '8', '9']
VALID_LANDLINE_CODES = ['11', '22', '33', '40', '44', '80', '20', '79', '120', '124']

# Business category hours
BUSINESS_HOURS = {
    "restaurant": (6, 23),
    "cafe": (7, 23),
    "retail": (9, 22),
    "grocery": (7, 22),
    "electronics": (10, 22),
    "pharmacy": (0, 24),
    "gas_station": (0, 24),
    "convenience_store": (0, 24),
    "mall": (10, 22),
    "airport": (0, 24),
}

# Famous brand names (for typo detection)
FAMOUS_BRANDS = [
    "mcdonalds", "starbucks", "dominos", "pizza hut", "kfc", "subway",
    "reliance", "big bazaar", "dmart", "more", "spencer",
    "apollo", "medplus", "netmeds",
    "croma", "vijay sales", "samsung", "apple", "mi",
]
