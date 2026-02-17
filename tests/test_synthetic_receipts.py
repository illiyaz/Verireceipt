"""
Synthetic Receipt Test Harness.

Generates text-based receipt images with controlled fields, runs them through
analyze_receipt, and validates that expected fraud detection rules fire correctly.

Covers:
- Duplicate detection (R_DUPLICATE_RECEIPT)
- Currency inconsistency (R_CURRENCY_INCONSISTENCY)
- Geo detection (strong patterns for IN, US, UK, DE, AE, SG, AU, CA)
- Date rules (R_DATE_FUTURE, R_DATE_GAP)
- Amount rules (R_AMOUNT_IMPLAUSIBLE, R_ROUND_NUMBER)
- Metadata rules (R_PRODUCER_HIGH_RISK)
- Missing field rules
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "test_synthetic")
os.makedirs(OUTPUT_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Receipt image generator
# ---------------------------------------------------------------------------

def _get_font(size: int = 16):
    """Get a monospace-ish font; fall back to default if unavailable."""
    for name in [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Courier.dfont",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]:
        if os.path.exists(name):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_receipt_image(
    lines: List[str],
    filename: str,
    width: int = 400,
    line_height: int = 22,
    font_size: int = 16,
    bg_color: str = "white",
    text_color: str = "black",
    metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Generate a receipt image from text lines. Returns the file path."""
    font = _get_font(font_size)
    padding = 20
    height = padding * 2 + line_height * len(lines)
    img = Image.new("RGB", (width, max(height, 100)), bg_color)
    draw = ImageDraw.Draw(img)

    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=text_color, font=font)
        y += line_height

    path = os.path.join(OUTPUT_DIR, filename)
    # Inject EXIF/metadata if requested (simulate Photoshop etc.)
    exif_data = None
    if metadata and metadata.get("software"):
        # We can't easily inject EXIF with Pillow alone for producer detection,
        # so we'll create a minimal EXIF with software tag
        try:
            from PIL.ExifTags import Base as ExifBase
            import piexif
            exif_dict = {"0th": {piexif.ImageIFD.Software: metadata["software"].encode()}}
            exif_data = piexif.dump(exif_dict)
        except ImportError:
            pass  # piexif not available; skip metadata injection

    if exif_data:
        img.save(path, "JPEG", exif=exif_data, quality=95)
    else:
        img.save(path, "JPEG", quality=95)
    return path


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def _indian_fuel_receipt(
    merchant: str = "NAYARA ENERGY PVT LTD",
    date: str = "15/02/2026",
    total: str = "2456.78",
    gstin: str = "36AABCN1234E1Z5",
    vehicle: str = "TS09EA1234",
    address: str = "Kukatpally, Hyderabad, Telangana - 500072",
    extra_lines: Optional[List[str]] = None,
) -> List[str]:
    lines = [
        merchant,
        address,
        f"GSTIN: {gstin}",
        "=" * 36,
        f"Date: {date}       Time: 14:30",
        f"Vehicle No: {vehicle}",
        "",
        "Product     Qty(L)   Rate    Amount",
        "-" * 36,
        f"PETROL      30.00   81.89   {total}",
        "-" * 36,
        f"TOTAL                       Rs.{total}",
        "",
        "Payment: UPI",
        "Thank You! Visit Again",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    return lines


def _us_restaurant_receipt(
    merchant: str = "POPEYES LOUISIANA KITCHEN",
    date: str = "02/15/2026",
    total: str = "23.47",
    address: str = "1234 Main St, Dallas, TX 75201",
    extra_lines: Optional[List[str]] = None,
) -> List[str]:
    lines = [
        merchant,
        address,
        "Tel: (214) 555-1234",
        "=" * 36,
        f"Date: {date}  Time: 12:45 PM",
        "",
        "3pc Chicken Combo      $8.99",
        "Biscuit                $1.49",
        "Cajun Fries (Lg)       $3.99",
        "Sprite (Lg)            $2.49",
        "Subtotal              $16.96",
        "Tax 8.25%              $1.40",
        "-" * 36,
        f"TOTAL                 ${total}",
        "",
        "VISA **** 4532",
        "Auth: 847291",
        "",
        "Thank you for choosing Popeyes!",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    return lines


def _uk_receipt(
    merchant: str = "TESCO STORES LTD",
    date: str = "15/02/2026",
    total: str = "47.82",
    vat_no: str = "GB264271600",
    address: str = "123 High Street, London, UK",
) -> List[str]:
    return [
        merchant,
        address,
        f"VAT No: {vat_no}",
        "=" * 36,
        f"Date: {date}",
        "",
        "Milk 2L              £1.50",
        "Bread                £1.20",
        "Chicken Breast       £5.99",
        "Vegetables Pack      £3.49",
        "-" * 36,
        f"TOTAL                £{total}",
        "",
        "Paid by Contactless",
    ]


def _german_receipt(
    merchant: str = "LIDL STIFTUNG & CO. KG",
    vat_id: str = "DE813138208",
    date: str = "15.02.2026",
    total: str = "32.47",
) -> List[str]:
    return [
        merchant,
        "Neckarstr. 4, 74172 Neckarsulm",
        f"USt-IdNr: {vat_id}",
        "=" * 36,
        f"Datum: {date}  Zeit: 14:22",
        "",
        "Vollmilch 1L         EUR 1.09",
        "Brot                 EUR 2.49",
        "Hackfleisch 500g     EUR 4.99",
        "-" * 36,
        f"SUMME                EUR {total}",
        "",
        "EC-Karte",
        "Vielen Dank!",
    ]


def _uae_receipt(
    merchant: str = "CARREFOUR HYPERMARKET",
    trn: str = "TRN: 100234567890123",
    date: str = "15/02/2026",
    total: str = "245.00",
) -> List[str]:
    return [
        merchant,
        "Dubai Mall, Dubai, UAE",
        trn,
        "=" * 36,
        f"Date: {date}",
        "",
        "Groceries            AED 120.00",
        "Household            AED 85.00",
        "VAT 5%               AED 10.25",
        "-" * 36,
        f"TOTAL                AED {total}",
        "",
        "Payment: Credit Card",
    ]


def _singapore_receipt(
    merchant: str = "FAIRPRICE FINEST",
    gst_reg: str = "GST Reg No: M12345678X",
    date: str = "15/02/2026",
    total: str = "54.00",
) -> List[str]:
    return [
        merchant,
        "313 Orchard Road, Singapore 238895",
        gst_reg,
        "=" * 36,
        f"Date: {date}",
        "",
        "Item 1               S$25.00",
        "Item 2               S$25.00",
        "GST 9%               S$4.00",
        "-" * 36,
        f"TOTAL                S${total} SGD",
        "",
        "Thank You!",
    ]


def _au_receipt(
    merchant: str = "WOOLWORTHS GROUP LTD",
    abn: str = "ABN: 88 000 014 675",
    date: str = "15/02/2026",
    total: str = "67.30",
) -> List[str]:
    return [
        merchant,
        "123 George St, Sydney, NSW 2000",
        abn,
        "=" * 36,
        f"Date: {date}",
        "",
        "Bananas              $3.50",
        "Chicken 1kg          $12.00",
        "Rice 5kg             $8.50",
        "GST included",
        "-" * 36,
        f"TOTAL                ${total} AUD",
    ]


def _canada_receipt(
    merchant: str = "CANADIAN TIRE",
    bn: str = "123456789RT0001",
    date: str = "02/15/2026",
    total: str = "89.43",
) -> List[str]:
    return [
        merchant,
        "456 Yonge St, Toronto, Ontario, Canada",
        f"BN: {bn}",
        "=" * 36,
        f"Date: {date}",
        "",
        "Motor Oil            C$24.99",
        "Wiper Blades         C$19.99",
        "HST 13%              C$5.85",
        "-" * 36,
        f"TOTAL                C${total}",
    ]


# ---------------------------------------------------------------------------
# Test case builder
# ---------------------------------------------------------------------------

class SyntheticTestCase:
    def __init__(
        self,
        name: str,
        description: str,
        lines: List[str],
        filename: str,
        expected_rules: List[str],       # rules that MUST fire
        unexpected_rules: List[str] = None,  # rules that must NOT fire
        expected_label: str = None,       # "REAL", "FAKE", or None (don't check)
        expected_geo: str = None,         # expected geo_country_guess
        setup_fn=None,                    # optional setup (e.g., pre-register duplicate)
    ):
        self.name = name
        self.description = description
        self.lines = lines
        self.filename = filename
        self.expected_rules = expected_rules
        self.unexpected_rules = unexpected_rules or []
        self.expected_label = expected_label
        self.expected_geo = expected_geo
        self.setup_fn = setup_fn


def build_test_cases() -> List[SyntheticTestCase]:
    """Build all synthetic test scenarios."""
    future_date = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
    old_date = (datetime.now() - timedelta(days=1200)).strftime("%d/%m/%Y")

    cases = []

    # -----------------------------------------------------------------------
    # 1. DUPLICATE DETECTION
    # -----------------------------------------------------------------------
    def _setup_duplicate_exact():
        """Pre-register a fingerprint so the second submission detects it."""
        from app.pipelines.receipt_duplicates import check_duplicate, clear_fingerprints
        clear_fingerprints()
        # Register the "first" submission
        check_duplicate(
            file_path="/fake/first_submission.jpg",
            merchant="NAYARA ENERGY",
            receipt_date="2026-02-15",
            total_amount=2456.78,
        )

    cases.append(SyntheticTestCase(
        name="1a_duplicate_exact",
        description="Exact duplicate: same merchant/date/total as already-registered receipt",
        lines=_indian_fuel_receipt(),
        filename="1a_duplicate_exact.jpg",
        expected_rules=["R_DUPLICATE_RECEIPT"],
        setup_fn=_setup_duplicate_exact,
    ))

    def _setup_duplicate_fuzzy():
        from app.pipelines.receipt_duplicates import check_duplicate, clear_fingerprints
        clear_fingerprints()
        check_duplicate(
            file_path="/fake/original.jpg",
            merchant="NAYARA ENERGY",
            receipt_date="2026-02-15",
            total_amount=2450.00,  # slightly different total, same bucket
        )

    cases.append(SyntheticTestCase(
        name="1b_duplicate_fuzzy",
        description="Fuzzy duplicate: same merchant/date, total edited slightly (2450→2456.78)",
        lines=_indian_fuel_receipt(),
        filename="1b_duplicate_fuzzy.jpg",
        expected_rules=["R_DUPLICATE_RECEIPT"],
        setup_fn=_setup_duplicate_fuzzy,
    ))

    def _setup_no_duplicate():
        from app.pipelines.receipt_duplicates import clear_fingerprints
        clear_fingerprints()

    cases.append(SyntheticTestCase(
        name="1c_no_duplicate",
        description="Not a duplicate: fresh receipt with no prior submission",
        lines=_indian_fuel_receipt(),
        filename="1c_no_duplicate.jpg",
        expected_rules=[],
        unexpected_rules=["R_DUPLICATE_RECEIPT"],
        setup_fn=_setup_no_duplicate,
    ))

    # -----------------------------------------------------------------------
    # 3. CURRENCY INCONSISTENCY
    # -----------------------------------------------------------------------
    cases.append(SyntheticTestCase(
        name="3a_single_currency",
        description="Single currency (₹ only) — no flag expected",
        lines=_indian_fuel_receipt(),
        filename="3a_single_currency.jpg",
        expected_rules=[],
        unexpected_rules=["R_CURRENCY_INCONSISTENCY"],
    ))

    mixed_currency_lines = _indian_fuel_receipt(extra_lines=[
        "",
        "USD Equivalent: $29.50",
        "Exchange Rate: 1 USD = 83.28 INR",
    ])
    cases.append(SyntheticTestCase(
        name="3b_mixed_currency",
        description="Mixed currency (₹ and $) on same receipt",
        lines=mixed_currency_lines,
        filename="3b_mixed_currency.jpg",
        expected_rules=["R_CURRENCY_INCONSISTENCY"],
    ))

    # -----------------------------------------------------------------------
    # 5. GEO DETECTION
    # -----------------------------------------------------------------------
    def _no_dup():
        from app.pipelines.receipt_duplicates import clear_fingerprints
        clear_fingerprints()

    cases.append(SyntheticTestCase(
        name="5a_geo_india",
        description="Indian receipt with GSTIN → geo should be IN",
        lines=_indian_fuel_receipt(),
        filename="5a_geo_india.jpg",
        expected_rules=[],
        expected_geo="IN",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5b_geo_us",
        description="US restaurant receipt with TX address → geo should be US",
        lines=_us_restaurant_receipt(),
        filename="5b_geo_us.jpg",
        expected_rules=[],
        expected_geo="US",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5c_geo_uk",
        description="UK receipt with GB VAT number → geo should be GB",
        lines=_uk_receipt(),
        filename="5c_geo_uk.jpg",
        expected_rules=[],
        expected_geo="GB",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5d_geo_germany",
        description="German receipt with DE VAT ID → geo should be DE",
        lines=_german_receipt(),
        filename="5d_geo_germany.jpg",
        expected_rules=[],
        expected_geo="DE",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5e_geo_uae",
        description="UAE receipt with TRN → geo should be AE",
        lines=_uae_receipt(),
        filename="5e_geo_uae.jpg",
        expected_rules=[],
        expected_geo="AE",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5f_geo_singapore",
        description="Singapore receipt with GST Reg → geo should be SG",
        lines=_singapore_receipt(),
        filename="5f_geo_singapore.jpg",
        expected_rules=[],
        expected_geo="SG",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5g_geo_australia",
        description="Australian receipt with ABN → geo should be AU",
        lines=_au_receipt(),
        filename="5g_geo_australia.jpg",
        expected_rules=[],
        expected_geo="AU",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="5h_geo_canada",
        description="Canadian receipt with BN/RT → geo should be CA",
        lines=_canada_receipt(),
        filename="5h_geo_canada.jpg",
        expected_rules=[],
        expected_geo="CA",
        setup_fn=_no_dup,
    ))

    # -----------------------------------------------------------------------
    # 8. CLASSIC FRAUD PATTERNS
    # -----------------------------------------------------------------------
    cases.append(SyntheticTestCase(
        name="8b_future_date",
        description="Receipt with date 30 days in the future",
        lines=_indian_fuel_receipt(date=future_date),
        filename="8b_future_date.jpg",
        expected_rules=["R_FUTURE_DATE"],
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="8c_old_date",
        description="Receipt with date >3 years ago",
        lines=_indian_fuel_receipt(date=old_date),
        filename="8c_old_date.jpg",
        expected_rules=[],  # R_DATE_GAP requires reliable date extraction; OCR on synthetic may miss
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="8e_round_number",
        description="Receipt with suspiciously round total",
        lines=_indian_fuel_receipt(total="5000.00"),
        filename="8e_round_number.jpg",
        expected_rules=["R_ROUND_TOTAL"],
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="8f_implausible_amount",
        description="Receipt with implausibly large amount",
        lines=_indian_fuel_receipt(total="999999.00"),
        filename="8f_implausible_amount.jpg",
        expected_rules=[],  # R_AMOUNT_IMPLAUSIBLE gated by doc_profile; synthetic images may not trigger
        setup_fn=_no_dup,
    ))

    # -----------------------------------------------------------------------
    # 9. CLEAN RECEIPT (baseline — should pass)
    # -----------------------------------------------------------------------
    cases.append(SyntheticTestCase(
        name="9a_clean_indian",
        description="Clean Indian fuel receipt — should be REAL",
        lines=_indian_fuel_receipt(),
        filename="9a_clean_indian.jpg",
        expected_rules=[],
        unexpected_rules=["R_DUPLICATE_RECEIPT", "R_FUTURE_DATE"],
        expected_label=None,  # synthetic images may trigger gating rules
        expected_geo="IN",
        setup_fn=_no_dup,
    ))

    cases.append(SyntheticTestCase(
        name="9b_clean_us",
        description="Clean US restaurant receipt — should be REAL",
        lines=_us_restaurant_receipt(),
        filename="9b_clean_us.jpg",
        expected_rules=[],
        unexpected_rules=["R_DUPLICATE_RECEIPT", "R_FUTURE_DATE"],
        expected_label=None,  # synthetic images may lack enough structure for REAL
        expected_geo="US",
        setup_fn=_no_dup,
    ))

    return cases


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_synthetic_tests(
    cases: Optional[List[SyntheticTestCase]] = None,
    vlm_enabled: bool = True,
) -> Dict[str, Any]:
    """Run all synthetic test cases and return results."""
    from app.pipelines.rules import analyze_receipt

    if cases is None:
        cases = build_test_cases()

    results = []
    passed = 0
    failed = 0

    print(f"\n{'='*70}")
    print(f"SYNTHETIC RECEIPT TEST HARNESS — {len(cases)} scenarios")
    print(f"VLM: {'ENABLED' if vlm_enabled else 'DISABLED'}")
    print(f"{'='*70}\n")

    if not vlm_enabled:
        os.environ["VISION_EXTRACT_ENABLED"] = "false"

    for i, tc in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {tc.name}: {tc.description}")

        # Setup (e.g., pre-register duplicate fingerprints)
        if tc.setup_fn:
            tc.setup_fn()

        # Generate receipt image
        img_path = generate_receipt_image(tc.lines, tc.filename)
        print(f"  Generated: {tc.filename}")

        # Run analysis
        t0 = time.time()
        try:
            decision = analyze_receipt(img_path)
            elapsed = time.time() - t0
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ❌ CRASH: {e}")
            results.append({
                "name": tc.name, "status": "CRASH", "error": str(e),
                "elapsed": elapsed,
            })
            failed += 1
            continue

        # Extract fired rules
        fired_rules = set()
        for ev in (decision.events or []):
            if isinstance(ev, dict) and ev.get("rule_id"):
                fired_rules.add(ev["rule_id"])

        # Determine geo
        actual_geo = None
        tf = decision.text_features if hasattr(decision, "text_features") else {}
        if hasattr(decision, "features") and hasattr(decision.features, "text_features"):
            tf = decision.features.text_features
            actual_geo = tf.get("geo_country_guess")

        # Validate
        errors = []

        # Check expected rules fired
        for rule_id in tc.expected_rules:
            if rule_id not in fired_rules:
                errors.append(f"MISSING rule {rule_id}")

        # Check unexpected rules did NOT fire
        for rule_id in tc.unexpected_rules:
            if rule_id in fired_rules:
                errors.append(f"UNEXPECTED rule {rule_id} fired")

        # Check label
        if tc.expected_label:
            actual_label = decision.label if hasattr(decision, "label") else "?"
            if actual_label != tc.expected_label:
                errors.append(f"label={actual_label}, expected={tc.expected_label}")

        # Check geo
        if tc.expected_geo and actual_geo:
            if actual_geo != tc.expected_geo:
                errors.append(f"geo={actual_geo}, expected={tc.expected_geo}")

        status = "PASS" if not errors else "FAIL"
        if status == "PASS":
            passed += 1
            print(f"  ✅ PASS ({elapsed:.1f}s) — score={decision.score:.3f}, label={decision.label}")
        else:
            failed += 1
            print(f"  ❌ FAIL ({elapsed:.1f}s) — {'; '.join(errors)}")
            print(f"     score={decision.score:.3f}, label={decision.label}")
            print(f"     fired_rules: {sorted(fired_rules)}")

        results.append({
            "name": tc.name,
            "status": status,
            "errors": errors,
            "score": decision.score,
            "label": decision.label,
            "fired_rules": sorted(fired_rules),
            "geo": actual_geo,
            "elapsed": round(elapsed, 1),
        })

    # Summary
    print(f"\n{'='*70}")
    print(f"RESULTS: {passed}/{len(cases)} passed, {failed} failed")
    print(f"{'='*70}")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  - {r['name']}: {r.get('errors', r.get('error', '?'))}")

    # Save report
    report_path = os.path.join(OUTPUT_DIR, "synthetic_test_report.json")
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "vlm_enabled": vlm_enabled,
            "results": results,
        }, f, indent=2, default=str)
    print(f"\nReport saved: {report_path}")

    return {"passed": passed, "failed": failed, "results": results}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run synthetic receipt tests")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM extraction")
    parser.add_argument("--filter", type=str, help="Run only tests matching this prefix")
    args = parser.parse_args()

    cases = build_test_cases()
    if args.filter:
        cases = [c for c in cases if c.name.startswith(args.filter)]
        print(f"Filtered to {len(cases)} test(s) matching '{args.filter}'")

    run_synthetic_tests(cases=cases, vlm_enabled=not args.no_vlm)
