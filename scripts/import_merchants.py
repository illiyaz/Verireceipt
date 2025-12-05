"""
Import merchant data from CSV to JSON format
Supports manual entry and web scraping
"""

import pandas as pd
import json
from pathlib import Path
import sys
from typing import Dict, List


def import_from_csv(csv_path: str, output_dir: str = "app/validation/data/merchants"):
    """
    Import merchants from CSV.
    
    Expected CSV columns:
    - Brand (required)
    - Category (required)
    - City (required)
    - PIN (required)
    - Address (optional)
    - Phone (optional)
    - StoreCode (optional)
    - Website (optional)
    
    Args:
        csv_path: Path to CSV file
        output_dir: Output directory for JSON files
    """
    print(f"📂 Reading CSV from: {csv_path}")
    
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return
    
    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()
    
    # Validate required columns
    required = ['brand', 'category', 'city', 'pin']
    missing = [col for col in required if col not in df.columns]
    
    if missing:
        print(f"❌ Error: Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        return
    
    print(f"✅ Found all required columns")
    print(f"📊 Total records: {len(df)}")
    
    # Group by category
    categories = {}
    for category in df['category'].unique():
        if pd.isna(category):
            continue
        
        category_df = df[df['category'] == category]
        merchants = {}
        
        # Group by brand within category
        for brand in category_df['brand'].unique():
            if pd.isna(brand):
                continue
            
            brand_df = category_df[category_df['brand'] == brand]
            brand_key = brand.lower().replace(" ", "_").replace("'", "").replace("-", "_")
            
            # Group locations by city
            locations = {}
            for city in brand_df['city'].unique():
                if pd.isna(city):
                    continue
                
                city_df = brand_df[brand_df['city'] == city]
                city_key = city.lower().strip()
                
                city_locations = []
                for _, row in city_df.iterrows():
                    location = {
                        "pin": str(row['pin']).strip(),
                        "address": str(row.get('address', '')).strip() if 'address' in row and not pd.isna(row.get('address')) else "",
                        "phone": str(row.get('phone', '')).strip() if 'phone' in row and not pd.isna(row.get('phone')) else "",
                        "store_code": str(row.get('storecode', '')).strip() if 'storecode' in row and not pd.isna(row.get('storecode')) else ""
                    }
                    city_locations.append(location)
                
                locations[city_key] = city_locations
            
            # Build merchant entry
            merchants[brand_key] = {
                "official_names": [brand],
                "brand_id": brand_key,
                "category": category.lower().strip(),
                "website": str(brand_df.iloc[0].get('website', '')).strip() if 'website' in brand_df.columns else "",
                "locations": locations,
                "total_stores": len(brand_df)
            }
        
        if merchants:
            categories[category.lower().strip()] = {
                "category": category,
                "total_brands": len(merchants),
                "merchants": merchants
            }
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save to JSON files (one per category)
    total_brands = 0
    total_stores = 0
    
    for category_key, data in categories.items():
        filename = category_key.replace(" ", "_") + ".json"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        total_brands += data["total_brands"]
        total_stores += sum(m["total_stores"] for m in data["merchants"].values())
        
        print(f"✅ {data['category']}: {data['total_brands']} brands → {filename}")
    
    # Save metadata
    metadata = {
        "version": "1.0.0",
        "last_updated": pd.Timestamp.now().isoformat(),
        "source": csv_path,
        "total_categories": len(categories),
        "total_brands": total_brands,
        "total_stores": total_stores
    }
    
    with open(output_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n🎉 Import complete!")
    print(f"   Categories: {len(categories)}")
    print(f"   Total Brands: {total_brands}")
    print(f"   Total Stores: {total_stores}")
    print(f"   Output: {output_path}")


def create_template_csv(output_path: str = "data/merchant_template.csv"):
    """Create a template CSV for manual merchant entry."""
    template_data = {
        "Brand": ["Reliance Digital", "Reliance Digital", "McDonald's", "Starbucks"],
        "Category": ["electronics", "electronics", "restaurant", "cafe"],
        "City": ["Hyderabad", "Bangalore", "Hyderabad", "Bangalore"],
        "PIN": ["500081", "560001", "500032", "560034"],
        "Address": [
            "Gachibowli, Hyderabad",
            "MG Road, Bangalore",
            "Jubilee Hills, Hyderabad",
            "Indiranagar, Bangalore"
        ],
        "Phone": ["+91-40-12345678", "+91-80-12345678", "+91-40-87654321", "+91-80-87654321"],
        "StoreCode": ["HYD001", "BLR001", "HYD001", "BLR001"],
        "Website": [
            "https://www.reliancedigital.in",
            "https://www.reliancedigital.in",
            "https://www.mcdonalds.in",
            "https://www.starbucks.in"
        ]
    }
    
    df = pd.DataFrame(template_data)
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_file, index=False)
    print(f"✅ Template created: {output_file}")
    print(f"\nColumns:")
    for col in df.columns:
        print(f"   - {col}")
    print(f"\nFill this template and run:")
    print(f"   python scripts/import_merchants.py {output_file}")


def expand_with_top_merchants():
    """Add top Indian merchant chains to database."""
    
    top_merchants = {
        "electronics": {
            "reliance_digital": {
                "official_names": ["Reliance Digital", "R-Digital"],
                "category": "electronics",
                "typical_items": ["mobile", "laptop", "tv", "tablet", "camera", "headphone", "speaker"],
                "price_range": {"min": 100, "max": 200000},
                "business_hours": [10, 22],
                "locations": {
                    "hyderabad": [
                        {"pin": "500001", "address": "Abids"},
                        {"pin": "500016", "address": "Malakpet"},
                        {"pin": "500081", "address": "Gachibowli"},
                        {"pin": "500032", "address": "Jubilee Hills"}
                    ],
                    "bangalore": [
                        {"pin": "560001", "address": "MG Road"},
                        {"pin": "560034", "address": "Indiranagar"},
                        {"pin": "560066", "address": "Whitefield"}
                    ],
                    "mumbai": [
                        {"pin": "400001", "address": "Fort"},
                        {"pin": "400050", "address": "Bandra"},
                        {"pin": "400051", "address": "Andheri"}
                    ]
                }
            },
            "croma": {
                "official_names": ["Croma", "Croma Retail"],
                "category": "electronics",
                "typical_items": ["mobile", "laptop", "tv", "appliance"],
                "price_range": {"min": 100, "max": 150000},
                "business_hours": [10, 22],
                "locations": {
                    "hyderabad": [{"pin": "500081", "address": "Gachibowli"}],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}],
                    "mumbai": [{"pin": "400050", "address": "Bandra"}]
                }
            }
        },
        "restaurant": {
            "mcdonalds": {
                "official_names": ["McDonald's", "McDonalds"],
                "category": "restaurant",
                "typical_items": ["burger", "fries", "mcaloo", "chicken", "nugget", "coke"],
                "price_range": {"min": 50, "max": 1000},
                "business_hours": [7, 23],
                "locations": {
                    "hyderabad": [
                        {"pin": "500001", "address": "Abids"},
                        {"pin": "500016", "address": "Dilsukhnagar"},
                        {"pin": "500032", "address": "Jubilee Hills"},
                        {"pin": "500081", "address": "Gachibowli"}
                    ],
                    "bangalore": [
                        {"pin": "560001", "address": "MG Road"},
                        {"pin": "560034", "address": "Indiranagar"}
                    ]
                }
            },
            "kfc": {
                "official_names": ["KFC", "Kentucky Fried Chicken"],
                "category": "restaurant",
                "typical_items": ["chicken", "burger", "fries", "wings", "bucket"],
                "price_range": {"min": 100, "max": 1500},
                "business_hours": [11, 23],
                "locations": {
                    "hyderabad": [{"pin": "500081", "address": "Gachibowli"}],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}]
                }
            },
            "dominos": {
                "official_names": ["Domino's Pizza", "Dominos"],
                "category": "restaurant",
                "typical_items": ["pizza", "pasta", "garlic bread", "coke"],
                "price_range": {"min": 100, "max": 2000},
                "business_hours": [10, 23],
                "locations": {
                    "hyderabad": [
                        {"pin": "500001", "address": "Abids"},
                        {"pin": "500081", "address": "Gachibowli"}
                    ],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}]
                }
            }
        },
        "cafe": {
            "starbucks": {
                "official_names": ["Starbucks", "Starbucks Coffee"],
                "category": "cafe",
                "typical_items": ["coffee", "latte", "cappuccino", "frappuccino", "sandwich"],
                "price_range": {"min": 100, "max": 2000},
                "business_hours": [7, 23],
                "locations": {
                    "hyderabad": [{"pin": "500032", "address": "Jubilee Hills"}],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}]
                }
            },
            "ccd": {
                "official_names": ["Cafe Coffee Day", "CCD"],
                "category": "cafe",
                "typical_items": ["coffee", "cappuccino", "sandwich", "cake"],
                "price_range": {"min": 50, "max": 500},
                "business_hours": [8, 23],
                "locations": {
                    "hyderabad": [{"pin": "500081", "address": "Gachibowli"}],
                    "bangalore": [{"pin": "560001", "address": "MG Road"}]
                }
            }
        },
        "retail": {
            "big_bazaar": {
                "official_names": ["Big Bazaar", "BigBazaar"],
                "category": "retail",
                "typical_items": ["grocery", "clothing", "home", "kitchen"],
                "price_range": {"min": 50, "max": 50000},
                "business_hours": [9, 22],
                "locations": {
                    "hyderabad": [{"pin": "500016", "address": "Dilsukhnagar"}],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}]
                }
            },
            "dmart": {
                "official_names": ["DMart", "D-Mart"],
                "category": "grocery",
                "typical_items": ["grocery", "food", "personal care"],
                "price_range": {"min": 50, "max": 20000},
                "business_hours": [8, 22],
                "locations": {
                    "hyderabad": [{"pin": "500081", "address": "Gachibowli"}],
                    "bangalore": [{"pin": "560066", "address": "Whitefield"}]
                }
            }
        },
        "pharmacy": {
            "apollo_pharmacy": {
                "official_names": ["Apollo Pharmacy", "Apollo"],
                "category": "pharmacy",
                "typical_items": ["medicine", "tablet", "syrup", "health"],
                "price_range": {"min": 10, "max": 10000},
                "business_hours": [0, 24],
                "locations": {
                    "hyderabad": [
                        {"pin": "500001", "address": "Abids"},
                        {"pin": "500081", "address": "Gachibowli"}
                    ],
                    "bangalore": [{"pin": "560034", "address": "Indiranagar"}]
                }
            }
        }
    }
    
    output_dir = Path("app/validation/data/merchants")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for category, merchants in top_merchants.items():
        data = {
            "category": category,
            "total_brands": len(merchants),
            "merchants": {k: {**v, "brand_id": k, "total_stores": sum(len(locs) for locs in v["locations"].values())} 
                         for k, v in merchants.items()}
        }
        
        filepath = output_dir / f"{category}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Created {category}.json with {len(merchants)} brands")
    
    print(f"\n✅ Top merchants database created!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--template":
            create_template_csv()
        elif sys.argv[1] == "--expand":
            expand_with_top_merchants()
        else:
            csv_path = sys.argv[1]
            import_from_csv(csv_path)
    else:
        print("Usage:")
        print("  python import_merchants.py <csv_file>       # Import from CSV")
        print("  python import_merchants.py --template       # Create template CSV")
        print("  python import_merchants.py --expand         # Add top merchants")
        print("\nExpanding with top merchants...")
        expand_with_top_merchants()
