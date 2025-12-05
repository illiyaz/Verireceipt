"""
Test validation systems with sample data
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.validation.address_validator import validate_address_complete
from app.validation.merchant_validator import validate_merchant_complete
from app.validation.phone_validator import validate_phone_number
from app.validation.business_hours_validator import validate_business_hours
from app.validation.data_loader import get_database


def test_pin_lookup():
    """Test PIN code database lookup."""
    print("\n" + "="*60)
    print("TEST 1: PIN Code Lookup")
    print("="*60)
    
    db = get_database()
    
    test_pins = ["500001", "500081", "560001", "999999"]
    
    for pin in test_pins:
        result = db.lookup_pin(pin)
        if result:
            print(f"✅ {pin}: {result['city']}, {result['district']}, {result.get('state', 'N/A')}")
        else:
            print(f"❌ {pin}: Not found")
    
    stats = db.get_stats()
    print(f"\nStats: {stats['total_pins']} PINs loaded, {stats['pin_lookups']} lookups")


def test_address_validation():
    """Test address validation."""
    print("\n" + "="*60)
    print("TEST 2: Address Validation")
    print("="*60)
    
    test_addresses = [
        ("Plot 123, Gachibowli, Hyderabad 500081", "Reliance Digital"),
        ("AAAAA BBBBB 500001", None),
        ("123 Main Street", None),
        ("Hyderabad 110001", None),  # Wrong PIN for city
    ]
    
    for address, merchant in test_addresses:
        print(f"\n📍 Address: {address[:50]}...")
        result = validate_address_complete(address, merchant)
        
        status = "✅ VALID" if result["valid"] else "❌ INVALID"
        print(f"   {status} (Confidence: {result['confidence']:.0%})")
        
        if result["issues"]:
            print(f"   Issues: {result['issues'][0]}")


def test_merchant_validation():
    """Test merchant validation."""
    print("\n" + "="*60)
    print("TEST 3: Merchant Validation")
    print("="*60)
    
    test_merchants = [
        ("Reliance Digital", "hyderabad", "500081", None),
        ("McDonald's", "bangalore", "560001", None),
        ("Test Store", None, None, None),
        ("Starbucks", "hyderabad", "999999", None),  # Wrong PIN
    ]
    
    for merchant, city, pin, items in test_merchants:
        print(f"\n🏪 Merchant: {merchant}")
        if city and pin:
            print(f"   Location: {city}, PIN {pin}")
        
        result = validate_merchant_complete(merchant, city, pin, items)
        
        status = "✅ VALID" if result["valid"] else "❌ INVALID"
        known = "🔍 KNOWN" if result["known_merchant"] else "❓ UNKNOWN"
        verified = "✓ VERIFIED" if result["verified"] else "✗ NOT VERIFIED"
        
        print(f"   {status} {known} {verified}")
        print(f"   Confidence: {result['confidence']:.0%}")
        
        if result["issues"]:
            print(f"   Issues: {result['issues'][0]}")


def test_phone_validation():
    """Test phone number validation."""
    print("\n" + "="*60)
    print("TEST 4: Phone Number Validation")
    print("="*60)
    
    test_phones = [
        ("+91-98765-43210", "IN"),
        ("9999999999", "IN"),
        ("1234567890", "IN"),
        ("040-12345678", "IN"),
        ("5123456789", "IN"),  # Invalid prefix
    ]
    
    for phone, country in test_phones:
        print(f"\n📞 Phone: {phone}")
        result = validate_phone_number(phone, country)
        
        status = "✅ VALID" if result["valid"] else "❌ INVALID"
        print(f"   {status} (Confidence: {result['confidence']:.0%})")
        
        if result["formatted"]:
            print(f"   Formatted: {result['formatted']}")
        
        if result["type"]:
            print(f"   Type: {result['type']}")
        
        if result["issues"]:
            print(f"   Issues: {result['issues'][0]}")


def test_business_hours():
    """Test business hours validation."""
    print("\n" + "="*60)
    print("TEST 5: Business Hours Validation")
    print("="*60)
    
    test_cases = [
        ("Reliance Digital", "14:30", None),
        ("McDonald's", "20:00", None),
        ("Apollo Pharmacy", "03:00", None),  # 24/7
        ("Reliance Digital", "03:00", None),  # Outside hours
    ]
    
    for merchant, time, date in test_cases:
        print(f"\n🕐 {merchant} at {time}")
        result = validate_business_hours(merchant, time, date)
        
        status = "✅ VALID" if result["valid"] else "❌ INVALID"
        print(f"   {status} (Confidence: {result['confidence']:.0%})")
        
        if result.get("business_hours"):
            hours = result["business_hours"]
            if hours == (0, 24):
                print(f"   Hours: 24/7")
            else:
                print(f"   Hours: {hours[0]:02d}:00 - {hours[1]:02d}:00")
        
        if result["issues"]:
            print(f"   Issues: {result['issues'][0]}")


def test_database_stats():
    """Show database statistics."""
    print("\n" + "="*60)
    print("DATABASE STATISTICS")
    print("="*60)
    
    db = get_database()
    stats = db.get_stats()
    
    print(f"\n📊 PIN Codes:")
    print(f"   Total: {stats['total_pins']}")
    print(f"   Lookups: {stats['pin_lookups']}")
    
    print(f"\n🏪 Merchants:")
    print(f"   Categories Loaded: {stats['loaded_categories']}")
    print(f"   Lookups: {stats['merchant_lookups']}")
    
    print(f"\n⚡ Cache Performance:")
    print(f"   Hit Rate: {stats['cache_hit_rate']:.1%}")
    print(f"   Hits: {stats['cache_hits']}")
    print(f"   Misses: {stats['cache_misses']}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("VALIDATION SYSTEMS TEST SUITE")
    print("="*60)
    
    try:
        test_pin_lookup()
        test_address_validation()
        test_merchant_validation()
        test_phone_validation()
        test_business_hours()
        test_database_stats()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
