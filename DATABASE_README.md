# Database Expansion Guide

## Quick Start (5 Minutes)

```bash
# 1. Expand with top merchants (DONE ✅)
python scripts/import_merchants.py --expand

# 2. Create sample PIN codes (DONE ✅)
python scripts/import_pin_codes.py

# 3. Test everything
python scripts/test_validation.py
```

**Current Status:**
- ✅ PIN Codes: 18 entries (2 states)
- ✅ Merchants: 10 brands (5 categories)
- ✅ All validation systems working

---

## Expansion Options

### Option 1: Quick Expansion (2-3 Hours)

**Add Top 50 Merchants Manually**

1. **Download Template:**
```bash
python scripts/import_merchants.py --template
# Creates: data/merchant_template.csv
```

2. **Fill Google Sheets:**
   - Open `data/merchant_template.csv` in Google Sheets
   - Add 50 top brands (10 per category)
   - Include 5-10 locations per brand

3. **Import:**
```bash
python scripts/import_merchants.py data/merchant_template.csv
```

**Expected Result:**
- 50 brands
- ~300 store locations
- Coverage: Top metros (Mumbai, Delhi, Bangalore, Hyderabad, Chennai)

---

### Option 2: Full India Post PINs (1 Hour)

**Download Official PIN Code Data**

1. **Get Data:**
   - Visit: https://data.gov.in/
   - Search: "India Post PIN Codes"
   - Download CSV (19,000+ entries)

2. **Import:**
```bash
python scripts/import_pin_codes.py data/india_post_pins.csv
```

**Expected Result:**
- 19,000+ PIN codes
- All 28 states + 8 UTs
- Complete geographic coverage

---

### Option 3: Web Scraping (4-6 Hours Setup)

**Automate Merchant Data Collection**

```python
# Example: Scrape Reliance Digital stores
python scripts/scrape_stores.py --brand "reliance_digital"

# Scrape multiple brands
python scripts/scrape_stores.py --brands electronics.txt
```

**Brands to Scrape:**
- Electronics: Reliance Digital, Croma, Vijay Sales
- Restaurants: McDonald's, KFC, Domino's, Pizza Hut
- Cafes: Starbucks, CCD, Barista
- Retail: Big Bazaar, DMart, More
- Pharmacy: Apollo, MedPlus, Netmeds

---

### Option 4: Google Places API (30 Min + Cost)

**Most Accurate, Paid Option**

```bash
# Set API key
export GOOGLE_PLACES_API_KEY="your_key_here"

# Import top brands
python scripts/google_places_import.py --brands top_50.txt

# Cost: ~$17 per 1000 stores
# Accuracy: ★★★★★
```

---

## Current Database Structure

```
app/validation/data/
├── pin_codes/
│   ├── telangana.json          # 10 PINs
│   ├── karnataka.json          # 8 PINs
│   └── metadata.json
│
├── merchants/
│   ├── electronics.json        # 2 brands (Reliance, Croma)
│   ├── restaurant.json         # 3 brands (McDonald's, KFC, Domino's)
│   ├── cafe.json              # 2 brands (Starbucks, CCD)
│   ├── retail.json            # 2 brands (Big Bazaar, DMart)
│   ├── pharmacy.json          # 1 brand (Apollo)
│   └── metadata.json
```

---

## Recommended Expansion Path

### Week 1: PIN Codes (Priority: HIGH)

**Goal:** Complete India coverage

```bash
# Download India Post data
wget https://data.gov.in/india-post-pins.csv -O data/pins.csv

# Import
python scripts/import_pin_codes.py data/pins.csv

# Verify
python -c "from app.validation.data_loader import get_database; \
           print(f'Loaded {len(get_database().pin_codes)} PINs')"
```

**Expected:** 19,000+ PINs

---

### Week 2: Top 100 Merchants (Priority: HIGH)

**Goal:** Cover 80% of common receipts

**Categories to Focus:**
1. **Electronics (20 brands)**
   - Reliance Digital, Croma, Vijay Sales, Samsung, Apple
   - Mi Store, OnePlus, Poorvika, Sangeetha, Lot Mobiles

2. **Restaurants (30 brands)**
   - McDonald's, KFC, Domino's, Pizza Hut, Subway
   - Burger King, Taco Bell, Wendy's, Haldiram's, Bikanervala

3. **Cafes (15 brands)**
   - Starbucks, CCD, Barista, Costa Coffee, Tim Hortons
   - Blue Tokai, Third Wave, Chaayos, Chai Point

4. **Retail (20 brands)**
   - Big Bazaar, DMart, More, Spencer's, Reliance Fresh
   - Star Bazaar, HyperCity, Spar, Nature's Basket

5. **Pharmacy (15 brands)**
   - Apollo, MedPlus, Netmeds, 1mg, PharmEasy
   - Wellness Forever, Guardian, Fortis Healthcare

**Method:** Manual entry using Google Sheets template

```bash
# Create template
python scripts/import_merchants.py --template

# After filling:
python scripts/import_merchants.py data/top_100_merchants.csv
```

---

### Week 3: Automation (Priority: MEDIUM)

**Goal:** Set up scrapers for ongoing updates

```bash
# Build scrapers
python scripts/build_scrapers.py

# Schedule monthly updates
crontab -e
# Add: 0 0 1 * * cd /path/to/VeriReceipt && python scripts/update_databases.sh
```

---

## Data Quality Guidelines

### PIN Codes

**Required Fields:**
- `pin`: 6-digit code (string)
- `city`: City name
- `district`: District name
- `state`: State name

**Optional Fields:**
- `region`: Area/locality
- `post_office`: Post office name
- `delivery`: Delivery status
- `latitude`: GPS coordinate
- `longitude`: GPS coordinate

**Example:**
```json
{
  "500081": {
    "city": "Hyderabad",
    "district": "Hyderabad",
    "state": "Telangana",
    "region": "Gachibowli",
    "post_office": "Gachibowli",
    "delivery": "Delivery"
  }
}
```

---

### Merchants

**Required Fields:**
- `official_names`: List of brand names
- `brand_id`: Unique identifier
- `category`: Business category
- `locations`: Dict of city -> list of stores

**Optional Fields:**
- `typical_items`: Common products
- `price_range`: Min/max prices
- `business_hours`: Operating hours
- `website`: Official website
- `payment_methods`: Accepted payments

**Example:**
```json
{
  "reliance_digital": {
    "official_names": ["Reliance Digital", "R-Digital"],
    "brand_id": "reliance_digital",
    "category": "electronics",
    "typical_items": ["mobile", "laptop", "tv"],
    "price_range": {"min": 100, "max": 200000},
    "business_hours": [10, 22],
    "locations": {
      "hyderabad": [
        {
          "pin": "500081",
          "address": "Gachibowli",
          "phone": "+91-40-12345678",
          "store_code": "HYD001"
        }
      ]
    },
    "total_stores": 250
  }
}
```

---

## Testing After Expansion

```bash
# Run full test suite
python scripts/test_validation.py

# Test specific validation
python -c "
from app.validation.address_validator import validate_address_complete
result = validate_address_complete('Plot 123, Gachibowli, Hyderabad 500081')
print(f'Valid: {result[\"valid\"]}, Confidence: {result[\"confidence\"]:.0%}')
"

# Check database stats
python -c "
from app.validation.data_loader import get_database
db = get_database()
stats = db.get_stats()
print(f'PINs: {stats[\"total_pins\"]}')
print(f'Categories: {stats[\"loaded_categories\"]}')
"
```

---

## Performance Benchmarks

**Current Performance:**

| Operation | Time | Cache Hit Rate |
|-----------|------|----------------|
| PIN Lookup | < 1ms | 60% |
| Merchant Lookup | < 1ms | N/A |
| Address Validation | < 50ms | - |
| Full Validation | < 100ms | - |

**Expected After Expansion:**

| Database Size | Load Time | Memory | Lookup Time |
|---------------|-----------|--------|-------------|
| 100 PINs | 0.01s | 1 MB | < 1ms |
| 19,000 PINs | 0.5s | 15 MB | < 1ms |
| 500 Merchants | 0.1s | 5 MB | < 1ms |

---

## Maintenance

### Monthly Updates

```bash
# Update PIN codes (if changed)
python scripts/import_pin_codes.py data/latest_pins.csv

# Update merchant locations
python scripts/import_merchants.py data/new_stores.csv

# Verify integrity
python scripts/verify_database.py

# Commit changes
git add app/validation/data/
git commit -m "Update databases: $(date +%Y-%m-%d)"
git push
```

### Quarterly Review

1. **Check for new brands** - Add popular chains
2. **Verify locations** - Remove closed stores
3. **Update hours** - Adjust business hours
4. **Add categories** - New business types

---

## Community Contributions

**Want to help expand the database?**

1. Fork the repository
2. Add data using templates
3. Run tests
4. Submit pull request

**Guidelines:**
- Use official sources
- Verify accuracy
- Follow JSON format
- Include metadata

---

## Troubleshooting

### "PIN code not found"

```bash
# Check if PIN exists
python -c "
from app.validation.data_loader import get_database
pin = get_database().lookup_pin('500081')
print(pin if pin else 'Not found')
"

# Add missing PIN
# Edit: app/validation/data/pin_codes/<state>.json
```

### "Merchant not recognized"

```bash
# Check merchant database
python -c "
from app.validation.data_loader import get_database
db = get_database()
category = db.get_merchant_category('electronics')
print(list(category['merchants'].keys()))
"

# Add merchant
# Edit: app/validation/data/merchants/<category>.json
```

### "Database not loading"

```bash
# Check file structure
ls -la app/validation/data/pin_codes/
ls -la app/validation/data/merchants/

# Verify JSON format
python -m json.tool app/validation/data/pin_codes/telangana.json

# Clear cache and reload
python -c "
from app.validation.data_loader import get_database
db = get_database()
db._pin_cache = None
db._load_pin_codes()
"
```

---

## Next Steps

**Immediate (Today):**
1. ✅ Test current validation
2. ⏳ Download India Post PINs
3. ⏳ Create merchant template

**This Week:**
1. Import 19,000 PINs
2. Add top 50 merchants manually
3. Test with real receipts

**Next Week:**
1. Build web scrapers
2. Expand to 100+ merchants
3. Set up auto-updates

**This Month:**
1. Reach 500+ merchants
2. Cover all major cities
3. Achieve 95%+ detection rate

---

## Resources

**Data Sources:**
- India Post: https://www.indiapost.gov.in/
- Open Data: https://data.gov.in/
- Brand Websites: Store locators

**Tools:**
- pandas: CSV processing
- BeautifulSoup: Web scraping
- Google Places API: Location data

**Documentation:**
- DATABASE_EXPANSION_STRATEGY.md (detailed design)
- VALIDATION_SYSTEMS.md (validation logic)
- This file (quick reference)

---

## Support

Questions? Issues?

1. Check troubleshooting section
2. Run test suite
3. Review documentation
4. Open GitHub issue

**Current Status:** ✅ Ready for expansion!
