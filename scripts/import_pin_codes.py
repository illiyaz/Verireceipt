"""
Import PIN codes from CSV to JSON format
Supports India Post CSV format
"""

import pandas as pd
import json
from pathlib import Path
import sys


def import_from_csv(csv_path: str, output_dir: str = "app/validation/data/pin_codes"):
    """
    Import PIN codes from India Post CSV.
    
    Expected CSV columns:
    - PIN / Pincode / PIN Code
    - City / Office Name
    - District
    - State / StateName
    - Region (optional)
    - Division (optional)
    - Delivery (optional)
    
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
    
    # Find PIN column
    pin_col = None
    for col in ['pin', 'pincode', 'pin code', 'pin_code']:
        if col in df.columns:
            pin_col = col
            break
    
    if not pin_col:
        print("❌ Error: Could not find PIN code column")
        print(f"Available columns: {list(df.columns)}")
        return
    
    # Find other columns
    city_col = 'city' if 'city' in df.columns else 'office name'
    district_col = 'district'
    state_col = 'state' if 'state' in df.columns else 'statename'
    
    print(f"✅ Found columns: PIN={pin_col}, City={city_col}, State={state_col}")
    print(f"📊 Total records: {len(df)}")
    
    # Group by state
    states = {}
    for state in df[state_col].unique():
        if pd.isna(state):
            continue
        
        state_df = df[df[state_col] == state]
        
        pins = {}
        for _, row in state_df.iterrows():
            pin_code = str(row[pin_col]).strip()
            
            # Skip invalid PINs
            if len(pin_code) != 6 or not pin_code.isdigit():
                continue
            
            pins[pin_code] = {
                "city": str(row[city_col]).strip() if not pd.isna(row[city_col]) else "",
                "district": str(row[district_col]).strip() if not pd.isna(row[district_col]) else "",
                "region": str(row.get('region', '')).strip() if 'region' in row and not pd.isna(row.get('region')) else "",
                "post_office": str(row[city_col]).strip() if not pd.isna(row[city_col]) else "",
                "delivery": str(row.get('delivery', 'Delivery')).strip() if 'delivery' in row else "Delivery"
            }
        
        if pins:
            states[state] = {
                "state": state,
                "total_pins": len(pins),
                "pins": pins
            }
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save to JSON files (one per state)
    total_pins = 0
    for state, data in states.items():
        filename = state.lower().replace(" ", "_").replace("&", "and") + ".json"
        filepath = output_path / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        total_pins += data["total_pins"]
        print(f"✅ {state}: {data['total_pins']} PINs → {filename}")
    
    # Save metadata
    metadata = {
        "version": "1.0.0",
        "last_updated": pd.Timestamp.now().isoformat(),
        "source": csv_path,
        "total_states": len(states),
        "total_pins": total_pins
    }
    
    with open(output_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n🎉 Import complete!")
    print(f"   States: {len(states)}")
    print(f"   Total PINs: {total_pins}")
    print(f"   Output: {output_path}")


def create_sample_data():
    """Create sample PIN code data for testing."""
    output_dir = Path("app/validation/data/pin_codes")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample data for major cities
    sample_data = {
        "telangana": {
            "state": "Telangana",
            "total_pins": 10,
            "pins": {
                "500001": {"city": "Hyderabad", "district": "Hyderabad", "region": "Central", "post_office": "Abids", "delivery": "Delivery"},
                "500002": {"city": "Hyderabad", "district": "Hyderabad", "region": "Central", "post_office": "Kachiguda", "delivery": "Delivery"},
                "500003": {"city": "Hyderabad", "district": "Hyderabad", "region": "Secunderabad", "post_office": "Secunderabad", "delivery": "Delivery"},
                "500016": {"city": "Hyderabad", "district": "Hyderabad", "region": "Malakpet", "post_office": "Malakpet", "delivery": "Delivery"},
                "500032": {"city": "Hyderabad", "district": "Hyderabad", "region": "Jubilee Hills", "post_office": "Jubilee Hills", "delivery": "Delivery"},
                "500034": {"city": "Hyderabad", "district": "Hyderabad", "region": "Somajiguda", "post_office": "Somajiguda", "delivery": "Delivery"},
                "500081": {"city": "Hyderabad", "district": "Hyderabad", "region": "Gachibowli", "post_office": "Gachibowli", "delivery": "Delivery"},
                "500082": {"city": "Hyderabad", "district": "Hyderabad", "region": "HITEC City", "post_office": "HITEC City", "delivery": "Delivery"},
                "500084": {"city": "Hyderabad", "district": "Hyderabad", "region": "Kondapur", "post_office": "Kondapur", "delivery": "Delivery"},
                "500409": {"city": "Hyderabad", "district": "Hyderabad", "region": "Airport", "post_office": "Shamshabad Airport", "delivery": "Delivery"},
            }
        },
        "karnataka": {
            "state": "Karnataka",
            "total_pins": 8,
            "pins": {
                "560001": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Central", "post_office": "Bangalore GPO", "delivery": "Delivery"},
                "560002": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Shivaji Nagar", "post_office": "Shivaji Nagar", "delivery": "Delivery"},
                "560034": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Indiranagar", "post_office": "Indiranagar", "delivery": "Delivery"},
                "560066": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Whitefield", "post_office": "Whitefield", "delivery": "Delivery"},
                "560100": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Electronic City", "post_office": "Electronic City", "delivery": "Delivery"},
                "560103": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Koramangala", "post_office": "Koramangala", "delivery": "Delivery"},
                "560300": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Airport", "post_office": "Kempegowda Airport", "delivery": "Delivery"},
                "560076": {"city": "Bangalore", "district": "Bangalore Urban", "region": "Marathahalli", "post_office": "Marathahalli", "delivery": "Delivery"},
            }
        }
    }
    
    for state_key, data in sample_data.items():
        filepath = output_dir / f"{state_key}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Created sample: {filepath}")
    
    print(f"\n✅ Sample data created in {output_dir}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        import_from_csv(csv_path)
    else:
        print("Usage: python import_pin_codes.py <csv_file>")
        print("\nOr creating sample data...")
        create_sample_data()
