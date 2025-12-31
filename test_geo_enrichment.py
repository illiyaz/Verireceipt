"""
Quick test script to verify geo enrichment system works end-to-end.
"""

from app.geo import infer_geo
from app.pipelines.geo_detection import detect_geo_and_profile

# Test 1: Direct geo inference
print("=" * 80)
print("TEST 1: Direct Geo Inference")
print("=" * 80)

india_text = """
ABC Store
123 Main Street, Chennai 600001
Tamil Nadu, India
GSTIN: 29ABCDE1234F1Z5

Invoice #12345
Date: 2024-01-15

Item 1: Rs. 500
Item 2: Rs. 300
CGST: Rs. 40
SGST: Rs. 40
Total: Rs. 880
"""

result = infer_geo(india_text)
print(f"\n📍 Country: {result['geo_country_guess']}")
print(f"📊 Confidence: {result['geo_confidence']}")
print(f"🔍 Mixed Signals: {result['geo_mixed']}")
print(f"\n📋 Evidence ({len(result['geo_evidence'])} signals):")
for e in result['geo_evidence']:
    print(f"   - {e['type']:15s} | {e['country']:2s} | {e['match']:20s} | weight: {e['weight']}")

print(f"\n🏆 Candidates:")
for c in result['candidates'][:5]:
    print(f"   {c['country']:2s}: {c['score']:.2f}")

# Test 2: Full geo detection pipeline
print("\n" + "=" * 80)
print("TEST 2: Full Geo Detection Pipeline (with doc profile)")
print("=" * 80)

lines = india_text.split("\n")
profile = detect_geo_and_profile(india_text, lines)

print(f"\n🌍 Geo Results:")
print(f"   Country: {profile.get('geo_country_guess')}")
print(f"   Confidence: {profile.get('geo_confidence')}")
print(f"   Mixed: {profile.get('geo_mixed')}")

print(f"\n📄 Document Profile:")
print(f"   Family: {profile.get('doc_family_guess')}")
print(f"   Subtype: {profile.get('doc_subtype_guess')}")
print(f"   Confidence: {profile.get('doc_profile_confidence')}")

print(f"\n🗣️ Language:")
print(f"   Guess: {profile.get('lang_guess')}")
print(f"   Confidence: {profile.get('lang_confidence')}")

# Test 3: UNKNOWN geo case
print("\n" + "=" * 80)
print("TEST 3: UNKNOWN Geo (No Clear Signals)")
print("=" * 80)

unknown_text = """
Store Name
123 Street
Some City

Item 1: 50.00
Item 2: 30.00
Total: 80.00
"""

result_unknown = infer_geo(unknown_text)
print(f"\n📍 Country: {result_unknown['geo_country_guess']}")
print(f"📊 Confidence: {result_unknown['geo_confidence']}")
print(f"📋 Evidence: {len(result_unknown['geo_evidence'])} signals")

# Test 4: Germany receipt
print("\n" + "=" * 80)
print("TEST 4: Germany Receipt")
print("=" * 80)

germany_text = """
Supermarkt Berlin
Hauptstraße 45
10115 Berlin
Deutschland

Rechnung Nr. 98765
Datum: 15.01.2024

Artikel 1: 25,00 EUR
Artikel 2: 15,50 EUR
MwSt. 19%: 7,70 EUR
USt-IdNr: DE123456789
Gesamt: 48,20 EUR
"""

result_de = infer_geo(germany_text)
print(f"\n📍 Country: {result_de['geo_country_guess']}")
print(f"📊 Confidence: {result_de['geo_confidence']}")
print(f"\n📋 Evidence:")
for e in result_de['geo_evidence']:
    print(f"   - {e['type']:15s} | {e['country']:2s} | {e['match']:20s} | weight: {e['weight']}")

print("\n" + "=" * 80)
print("✅ All tests completed successfully!")
print("=" * 80)
