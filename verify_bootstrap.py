#!/usr/bin/env python3
"""
Verify bootstrap data in geo.sqlite database.
"""

import sqlite3
from pathlib import Path

# First, bootstrap the database
print("🔧 Bootstrapping database...")
from app.geo.bootstrap import bootstrap_geo_db
bootstrap_geo_db()

# Now verify the data
db_path = Path("app/data/geo.sqlite")
if not db_path.exists():
    print("❌ Database not found!")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("\n" + "="*80)
print("📊 GEO PROFILES (US, IN, EU)")
print("="*80)

cursor.execute("""
    SELECT country_code, country_name, primary_currency, enforcement_tier, region
    FROM geo_profiles
    WHERE country_code IN ('US', 'IN', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT', 'IE', 'FI', 'GR', 'UK')
    ORDER BY region, country_code
""")

for row in cursor.fetchall():
    print(f"  {row['country_code']:3} | {row['country_name']:20} | {row['primary_currency']:3} | {row['enforcement_tier']:8} | {row['region']}")

print(f"\n✅ Total geo profiles: {cursor.rowcount}")

print("\n" + "="*80)
print("💰 VAT RULES (US, IN, EU)")
print("="*80)

cursor.execute("""
    SELECT country_code, tax_name, rate, description
    FROM vat_rules
    WHERE country_code IN ('US', 'IN', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT', 'IE', 'FI', 'GR', 'UK')
    ORDER BY country_code, rate DESC
""")

current_country = None
for row in cursor.fetchall():
    if row['country_code'] != current_country:
        current_country = row['country_code']
        print(f"\n  {current_country}:")
    rate_pct = row['rate'] * 100 if row['rate'] else 0
    print(f"    • {row['tax_name']:12} {rate_pct:5.2f}% - {row['description']}")

cursor.execute("SELECT COUNT(*) as count FROM vat_rules WHERE country_code IN ('US', 'IN', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT', 'IE', 'FI', 'GR', 'UK')")
print(f"\n✅ Total VAT rules: {cursor.fetchone()['count']}")

print("\n" + "="*80)
print("💱 CURRENCY MAPPINGS")
print("="*80)

cursor.execute("""
    SELECT currency, GROUP_CONCAT(country_code, ', ') as countries, COUNT(*) as count
    FROM currency_country_map
    WHERE country_code IN ('US', 'IN', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT', 'IE', 'FI', 'GR', 'UK')
    GROUP BY currency
    ORDER BY currency
""")

for row in cursor.fetchall():
    print(f"  {row['currency']:3} → {row['countries']}")

cursor.execute("SELECT COUNT(*) as count FROM currency_country_map WHERE country_code IN ('US', 'IN', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'PT', 'IE', 'FI', 'GR', 'UK')")
print(f"\n✅ Total currency mappings: {cursor.fetchone()['count']}")

print("\n" + "="*80)
print("📈 SUMMARY")
print("="*80)

cursor.execute("SELECT COUNT(*) as count FROM geo_profiles")
total_profiles = cursor.fetchone()['count']

cursor.execute("SELECT COUNT(*) as count FROM vat_rules")
total_vat = cursor.fetchone()['count']

cursor.execute("SELECT COUNT(*) as count FROM currency_country_map")
total_currency = cursor.fetchone()['count']

print(f"  Total geo profiles:      {total_profiles}")
print(f"  Total VAT rules:         {total_vat}")
print(f"  Total currency mappings: {total_currency}")

print("\n✅ Bootstrap verification complete!")

conn.close()
