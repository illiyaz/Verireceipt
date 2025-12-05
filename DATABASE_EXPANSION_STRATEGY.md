# Database Expansion Strategy

## Current State
- PIN codes: 100+ (sample)
- Merchants: 7 chains
- Cities: 30+
- Total size: ~3 MB

## Target State
- PIN codes: 19,000+ (complete India)
- Merchants: 500+ chains
- Cities: 100+
- Total size: ~15 MB

---

## Strategy: Modular JSON Files

### **Why JSON?**
✅ Human-readable  
✅ Easy to edit  
✅ Version control friendly  
✅ Fast to load  
✅ No database server needed  

### **File Structure:**

```
app/validation/data/
├── pin_codes/
│   ├── telangana.json       # 1,500 PINs
│   ├── karnataka.json       # 1,800 PINs
│   ├── maharashtra.json     # 2,500 PINs
│   ├── delhi.json           # 200 PINs
│   ├── tamil_nadu.json      # 1,600 PINs
│   └── ... (28 more states)
│
├── merchants/
│   ├── electronics.json     # Reliance, Croma, Vijay Sales
│   ├── restaurants.json     # McDonald's, KFC, Domino's
│   ├── cafes.json          # Starbucks, CCD, Barista
│   ├── retail.json         # Big Bazaar, DMart, More
│   ├── pharmacy.json       # Apollo, MedPlus, Netmeds
│   └── ... (10+ categories)
│
├── cities.json             # City-state mapping
├── airports.json           # Airport PIN codes
└── metadata.json           # Database version info
```

---

## Phase 1: PIN Code Database (Priority: HIGH)

### **Data Sources:**

1. **India Post Official Data**
   - URL: https://www.indiapost.gov.in/
   - Format: CSV/Excel
   - Coverage: All 19,000+ PINs
   - Free & Official

2. **Government Open Data**
   - URL: https://data.gov.in/
   - Dataset: "PIN Code Directory"
   - Updated quarterly

3. **Backup: Web Scraping**
   - Pincode.net.in
   - Postal-codes.cybo.com
   - Last resort if official data unavailable

### **JSON Format:**

```json
{
  "state": "Telangana",
  "pins": {
    "500001": {
      "city": "Hyderabad",
      "district": "Hyderabad",
      "region": "Central",
      "post_office": "Abids",
      "delivery": "Delivery",
      "latitude": 17.3850,
      "longitude": 78.4867
    },
    "500002": {
      "city": "Hyderabad",
      "district": "Hyderabad",
      "region": "Central",
      "post_office": "Kachiguda",
      "delivery": "Delivery",
      "latitude": 17.3753,
      "longitude": 78.4983
    }
  }
}
```

### **Implementation:**

```python
# app/validation/data_loader.py

import json
from pathlib import Path
from typing import Dict

class PINCodeDatabase:
    def __init__(self):
        self.data_dir = Path(__file__).parent / "data" / "pin_codes"
        self.cache = {}
        self._load_all()
    
    def _load_all(self):
        """Load all state PIN files into memory."""
        for state_file in self.data_dir.glob("*.json"):
            with open(state_file) as f:
                state_data = json.load(f)
                self.cache.update(state_data["pins"])
    
    def lookup(self, pin_code: str) -> Dict:
        """Fast O(1) lookup."""
        return self.cache.get(pin_code)
    
    def get_by_city(self, city: str) -> list:
        """Get all PINs for a city."""
        return [
            pin for pin, data in self.cache.items()
            if data["city"].lower() == city.lower()
        ]
```

### **Automation Script:**

```python
# scripts/import_pin_codes.py

import pandas as pd
import json
from pathlib import Path

def import_from_csv(csv_path: str):
    """
    Import PIN codes from India Post CSV.
    CSV columns: PIN, City, District, State, PostOffice
    """
    df = pd.read_csv(csv_path)
    
    # Group by state
    states = {}
    for state in df['State'].unique():
        state_df = df[df['State'] == state]
        
        pins = {}
        for _, row in state_df.iterrows():
            pins[str(row['PIN'])] = {
                "city": row['City'],
                "district": row['District'],
                "region": row.get('Region', ''),
                "post_office": row['PostOffice'],
                "delivery": row.get('Delivery', 'Delivery')
            }
        
        states[state] = {
            "state": state,
            "pins": pins
        }
    
    # Save to JSON files
    output_dir = Path("app/validation/data/pin_codes")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for state, data in states.items():
        filename = state.lower().replace(" ", "_") + ".json"
        with open(output_dir / filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    print(f"✅ Imported {len(df)} PIN codes across {len(states)} states")

if __name__ == "__main__":
    import_from_csv("data/india_post_pins.csv")
```

---

## Phase 2: Merchant Database (Priority: HIGH)

### **Data Sources:**

1. **Manual Curation (Most Reliable)**
   - Official brand websites
   - Store locator pages
   - Franchise directories
   - Quality: High, Effort: Medium

2. **Google Places API (Optional)**
   - Verify locations
   - Get coordinates
   - Quality: High, Cost: Paid

3. **Web Scraping (Backup)**
   - Brand websites
   - Justdial, Zomato, Swiggy
   - Quality: Medium, Legal: Check ToS

### **Merchant Categories:**

```
1. Electronics (50+ chains)
   - Reliance Digital, Croma, Vijay Sales, Samsung, Apple
   
2. Restaurants (100+ chains)
   - McDonald's, KFC, Domino's, Pizza Hut, Subway, Burger King
   
3. Cafes (30+ chains)
   - Starbucks, CCD, Barista, Costa Coffee, Tim Hortons
   
4. Retail (50+ chains)
   - Big Bazaar, DMart, More, Spencer's, Reliance Fresh
   
5. Pharmacy (40+ chains)
   - Apollo, MedPlus, Netmeds, 1mg, PharmEasy
   
6. Fashion (80+ chains)
   - Zara, H&M, Pantaloons, Westside, Max, Lifestyle
   
7. Grocery (30+ chains)
   - DMart, Big Bazaar, Reliance Fresh, More, Spencer's
   
8. Fast Food (50+ chains)
   - McDonald's, KFC, Subway, Domino's, Pizza Hut
   
9. Banks (50+ chains)
   - HDFC, ICICI, SBI, Axis, Kotak
   
10. Fuel Stations (20+ chains)
    - Indian Oil, HP, Bharat Petroleum, Shell
```

### **JSON Format:**

```json
{
  "category": "electronics",
  "merchants": {
    "reliance_digital": {
      "official_names": ["Reliance Digital", "R-Digital"],
      "brand_id": "reliance_digital",
      "category": "electronics",
      "subcategory": "consumer_electronics",
      "founded": 2006,
      "parent_company": "Reliance Retail",
      "website": "https://www.reliancedigital.in",
      
      "typical_items": [
        "mobile", "laptop", "tv", "tablet", "camera",
        "headphone", "speaker", "watch", "appliance"
      ],
      
      "price_range": {
        "min": 100,
        "max": 200000,
        "avg_transaction": 15000
      },
      
      "payment_methods": ["card", "upi", "cash", "emi", "wallet"],
      
      "business_hours": {
        "weekday": [10, 22],
        "weekend": [10, 22],
        "holidays": "open"
      },
      
      "locations": {
        "hyderabad": [
          {
            "pin": "500001",
            "address": "Abids, Hyderabad",
            "store_code": "HYD001",
            "phone": "+91-40-12345678",
            "latitude": 17.3850,
            "longitude": 78.4867
          },
          {
            "pin": "500081",
            "address": "Gachibowli, Hyderabad",
            "store_code": "HYD002",
            "phone": "+91-40-87654321",
            "latitude": 17.4400,
            "longitude": 78.3489
          }
        ],
        "bangalore": [
          {
            "pin": "560001",
            "address": "MG Road, Bangalore",
            "store_code": "BLR001",
            "phone": "+91-80-12345678"
          }
        ]
      },
      
      "total_stores": 250,
      "last_updated": "2025-12-05"
    }
  }
}
```

### **Automation Script:**

```python
# scripts/import_merchants.py

import json
import requests
from pathlib import Path

class MerchantImporter:
    def __init__(self):
        self.output_dir = Path("app/validation/data/merchants")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def import_from_website(self, brand: str, store_locator_url: str):
        """
        Import merchant locations from store locator.
        """
        # Example: Scrape store locator page
        # This is brand-specific, needs customization
        pass
    
    def import_from_csv(self, csv_path: str, category: str):
        """
        Import from CSV with columns:
        Brand, City, PIN, Address, Phone, StoreCode
        """
        import pandas as pd
        
        df = pd.read_csv(csv_path)
        merchants = {}
        
        for brand in df['Brand'].unique():
            brand_df = df[df['Brand'] == brand]
            brand_key = brand.lower().replace(" ", "_")
            
            locations = {}
            for city in brand_df['City'].unique():
                city_df = brand_df[brand_df['City'] == city]
                city_key = city.lower()
                
                locations[city_key] = [
                    {
                        "pin": str(row['PIN']),
                        "address": row['Address'],
                        "phone": row.get('Phone', ''),
                        "store_code": row.get('StoreCode', '')
                    }
                    for _, row in city_df.iterrows()
                ]
            
            merchants[brand_key] = {
                "official_names": [brand],
                "brand_id": brand_key,
                "category": category,
                "locations": locations,
                "total_stores": len(brand_df)
            }
        
        # Save to JSON
        output_file = self.output_dir / f"{category}.json"
        with open(output_file, 'w') as f:
            json.dump({
                "category": category,
                "merchants": merchants
            }, f, indent=2)
        
        print(f"✅ Imported {len(merchants)} merchants in {category}")

if __name__ == "__main__":
    importer = MerchantImporter()
    importer.import_from_csv("data/electronics_stores.csv", "electronics")
```

---

## Phase 3: Data Collection Methods

### **Method 1: Manual Entry (Best Quality)**

**Template Spreadsheet:**
```
Brand | Category | City | PIN | Address | Phone | Store Code
Reliance Digital | electronics | Hyderabad | 500001 | Abids | +91-40-12345678 | HYD001
McDonald's | restaurant | Bangalore | 560001 | MG Road | +91-80-12345678 | BLR001
```

**Process:**
1. Create Google Sheet template
2. Team members fill data
3. Export as CSV
4. Run import script
5. Verify and commit

**Effort:** 2-3 hours per 100 stores  
**Quality:** ★★★★★

---

### **Method 2: Web Scraping (Automated)**

**Target Sites:**
- Brand official websites (store locators)
- Justdial.com (business listings)
- Google Maps (via API)

**Example Script:**

```python
# scripts/scrape_store_locator.py

import requests
from bs4 import BeautifulSoup
import json

def scrape_reliance_digital():
    """
    Scrape Reliance Digital store locator.
    Note: Check robots.txt and ToS first!
    """
    url = "https://www.reliancedigital.in/store-locator"
    
    # This is pseudo-code - actual implementation varies
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    stores = []
    for store in soup.find_all('div', class_='store-item'):
        stores.append({
            "city": store.find('span', class_='city').text,
            "pin": store.find('span', class_='pin').text,
            "address": store.find('div', class_='address').text,
            "phone": store.find('span', class_='phone').text
        })
    
    return stores
```

**Effort:** 1-2 hours per brand (setup)  
**Quality:** ★★★★☆  
**Legal:** Check ToS, robots.txt

---

### **Method 3: Google Places API (Most Accurate)**

```python
# scripts/google_places_import.py

import googlemaps
import json

def import_from_google_places(api_key: str, brand: str, cities: list):
    """
    Use Google Places API to find store locations.
    Cost: ~$17 per 1000 requests
    """
    gmaps = googlemaps.Client(key=api_key)
    
    stores = []
    for city in cities:
        # Search for brand in city
        places = gmaps.places(
            query=f"{brand} {city}",
            type="store"
        )
        
        for place in places['results']:
            details = gmaps.place(place['place_id'])
            
            stores.append({
                "city": city,
                "address": details['formatted_address'],
                "phone": details.get('formatted_phone_number'),
                "latitude": details['geometry']['location']['lat'],
                "longitude": details['geometry']['location']['lng'],
                "rating": details.get('rating'),
                "place_id": place['place_id']
            })
    
    return stores
```

**Effort:** 30 min per brand  
**Quality:** ★★★★★  
**Cost:** ~$17 per 1000 stores

---

## Phase 4: Database Loader (Optimized)

### **Lazy Loading Strategy:**

```python
# app/validation/data_loader.py

import json
from pathlib import Path
from typing import Dict, Optional
from functools import lru_cache

class DatabaseLoader:
    """
    Lazy-loading database with caching.
    Only loads data when needed.
    """
    
    def __init__(self):
        self.data_dir = Path(__file__).parent / "data"
        self._pin_cache = None
        self._merchant_cache = {}
    
    @property
    def pin_codes(self) -> Dict:
        """Lazy load PIN codes."""
        if self._pin_cache is None:
            self._pin_cache = self._load_pin_codes()
        return self._pin_cache
    
    def _load_pin_codes(self) -> Dict:
        """Load all PIN codes into memory (~15 MB)."""
        pins = {}
        pin_dir = self.data_dir / "pin_codes"
        
        for state_file in pin_dir.glob("*.json"):
            with open(state_file) as f:
                state_data = json.load(f)
                pins.update(state_data["pins"])
        
        print(f"✅ Loaded {len(pins)} PIN codes")
        return pins
    
    def get_merchant_category(self, category: str) -> Dict:
        """Lazy load merchant category."""
        if category not in self._merchant_cache:
            merchant_file = self.data_dir / "merchants" / f"{category}.json"
            
            if merchant_file.exists():
                with open(merchant_file) as f:
                    self._merchant_cache[category] = json.load(f)
            else:
                self._merchant_cache[category] = {"merchants": {}}
        
        return self._merchant_cache[category]
    
    @lru_cache(maxsize=1000)
    def lookup_pin(self, pin_code: str) -> Optional[Dict]:
        """Fast cached PIN lookup."""
        return self.pin_codes.get(pin_code)
    
    @lru_cache(maxsize=500)
    def lookup_merchant(self, merchant_key: str, category: str) -> Optional[Dict]:
        """Fast cached merchant lookup."""
        category_data = self.get_merchant_category(category)
        return category_data["merchants"].get(merchant_key)

# Global singleton
_db_loader = None

def get_database() -> DatabaseLoader:
    """Get global database instance."""
    global _db_loader
    if _db_loader is None:
        _db_loader = DatabaseLoader()
    return _db_loader
```

---

## Phase 5: Update Strategy

### **Version Control:**

```json
// app/validation/data/metadata.json
{
  "version": "1.0.0",
  "last_updated": "2025-12-05",
  "databases": {
    "pin_codes": {
      "total_entries": 19000,
      "states": 28,
      "last_updated": "2025-12-01"
    },
    "merchants": {
      "total_brands": 500,
      "total_stores": 15000,
      "categories": 10,
      "last_updated": "2025-12-05"
    }
  }
}
```

### **Update Process:**

```bash
# Monthly update script
./scripts/update_databases.sh

# Steps:
# 1. Download latest PIN codes from India Post
# 2. Scrape updated merchant locations
# 3. Validate data quality
# 4. Generate diff report
# 5. Commit to git
# 6. Deploy to production
```

---

## Recommended Approach

### **Week 1: PIN Codes**
1. Download India Post CSV
2. Run import script
3. Verify 19,000+ entries
4. Test lookups

### **Week 2-3: Top 100 Merchants**
1. Create spreadsheet template
2. Manual entry for top 100 brands
3. Focus on major cities (10+)
4. ~5,000 store locations

### **Week 4: Automation**
1. Build web scrapers for top brands
2. Set up Google Places API (optional)
3. Automate updates

### **Ongoing: Maintenance**
1. Monthly PIN code updates
2. Quarterly merchant updates
3. Community contributions

---

## Effort Estimation

| Task | Method | Time | Quality |
|------|--------|------|---------|
| PIN Codes (19K) | Import CSV | 2 hours | ★★★★★ |
| Top 10 Merchants | Manual | 8 hours | ★★★★★ |
| Next 40 Merchants | Manual | 20 hours | ★★★★★ |
| Next 50 Merchants | Scraping | 10 hours | ★★★★☆ |
| Automation Scripts | Coding | 16 hours | - |
| **Total** | | **56 hours** | |

**Timeline:** 2-3 weeks with 1 person  
**Or:** 1 week with 3 people

---

## Quick Start (Next 2 Hours)

```bash
# 1. Download India Post PIN codes
wget https://data.gov.in/india-post-pin-codes.csv

# 2. Run import script
python scripts/import_pin_codes.py

# 3. Create merchant template
python scripts/create_merchant_template.py

# 4. Fill top 10 merchants manually
# (Use Google Sheets)

# 5. Import merchants
python scripts/import_merchants.py data/top_10_merchants.csv

# 6. Test
python -m pytest tests/test_validation.py
```

---

## Next Steps?

Would you like me to:

1. **Create import scripts** - PIN codes + merchants
2. **Download sample data** - India Post PINs
3. **Build scraper** - For specific brand
4. **Create template** - Google Sheets for manual entry
5. **Start with top 10** - Most common merchants

Let me know and I'll implement it! 🚀
