#!/usr/bin/env python3
"""
Batch Receipt Analysis — Side-by-Side Expert vs Tool Comparison

Usage:
    python scripts/batch_test.py [folder_path]

Default folder: data/test_batch/
Supported formats: .jpg .jpeg .png .gif .bmp .tiff .pdf
"""

import sys, os, json, time, logging
from pathlib import Path
from datetime import datetime

# Suppress noisy warnings during batch run
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("VISION_EXTRACT_ENABLED", "true")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".pdf"}


def analyze_single(filepath: str) -> dict:
    """Run full analysis on a single receipt file."""
    from app.pipelines.rules import analyze_receipt

    start = time.time()
    try:
        result = analyze_receipt(filepath)
        elapsed = time.time() - start

        # Extract weighted events
        weighted_events = []
        info_events = []
        for e in result.events:
            ev = e if isinstance(e, dict) else vars(e)
            if ev.get("weight", 0) > 0:
                weighted_events.append({
                    "rule_id": ev.get("rule_id", ""),
                    "severity": ev.get("severity", ""),
                    "weight": round(ev.get("weight", 0), 4),
                    "message": ev.get("message", "")[:120],
                    "reason_text": ev.get("reason_text", "")[:200],
                })
            else:
                rule_id = ev.get("rule_id", "")
                # Skip debug/meta events
                if rule_id not in ("DOC_PROFILE_DEBUG", "DOMAIN_PACK_VALIDATION", "MERCHANT_DEBUG"):
                    info_events.append({
                        "rule_id": rule_id,
                        "message": ev.get("message", "")[:120],
                    })

        return {
            "file": os.path.basename(filepath),
            "verdict": result.label,
            "score": round(result.score, 4),
            "geo": getattr(result, "geo_country_guess", ""),
            "geo_confidence": round(getattr(result, "geo_confidence", 0), 2),
            "doc_subtype": getattr(result, "doc_subtype", ""),
            "doc_profile_confidence": round(getattr(result, "doc_profile_confidence", 0), 2),
            "weighted_events": weighted_events,
            "info_events": info_events,
            "elapsed_sec": round(elapsed, 1),
            "error": None,
        }
    except Exception as exc:
        elapsed = time.time() - start
        return {
            "file": os.path.basename(filepath),
            "verdict": "ERROR",
            "score": 0,
            "weighted_events": [],
            "info_events": [],
            "elapsed_sec": round(elapsed, 1),
            "error": str(exc)[:200],
        }


def print_result(idx: int, total: int, r: dict):
    """Pretty-print a single result."""
    fname = r["file"]
    verdict = r["verdict"]
    score = r["score"]
    geo = r.get("geo", "")
    subtype = r.get("doc_subtype", "")
    elapsed = r["elapsed_sec"]

    # Color coding for terminal
    if verdict == "fake":
        verdict_display = f"\033[91m{verdict.upper()}\033[0m"
    elif verdict == "suspicious":
        verdict_display = f"\033[93m{verdict.upper()}\033[0m"
    elif verdict == "real":
        verdict_display = f"\033[92m{verdict.upper()}\033[0m"
    else:
        verdict_display = verdict.upper()

    print(f"\n{'='*78}")
    print(f"[{idx}/{total}] {fname}")
    print(f"{'='*78}")
    print(f"  VERDICT: {verdict_display} (score={score:.4f})  |  Geo: {geo}  |  Subtype: {subtype}  |  {elapsed}s")

    if r["error"]:
        print(f"  \033[91mERROR: {r['error']}\033[0m")
        return

    if r["weighted_events"]:
        print(f"\n  FIRED RULES ({len(r['weighted_events'])}):")
        for e in r["weighted_events"]:
            sev = e["severity"]
            sev_icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
            print(f"    {sev_icon} {e['rule_id']:35s} w={e['weight']:.4f}  {e['message'][:70]}")
    else:
        print(f"\n  FIRED RULES: (none)")

    # Show key info events
    key_info = [e for e in r["info_events"] if e["rule_id"] in (
        "R_GSTIN_FORMAT", "R_NO_ELECTRONIC_ID", "R_PIN_CITY_MISMATCH",
        "GATE_MISSING_FIELDS", "GEO_CROSS_BORDER_HINTS",
    )]
    if key_info:
        print(f"\n  KEY INFO:")
        for e in key_info:
            print(f"    ℹ️  {e['rule_id']}: {e['message'][:70]}")


def print_summary(results: list):
    """Print aggregate summary."""
    total = len(results)
    verdicts = {"real": 0, "suspicious": 0, "fake": 0, "ERROR": 0}
    all_rules = {}
    total_time = 0

    for r in results:
        v = r["verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
        total_time += r["elapsed_sec"]
        for e in r["weighted_events"]:
            rid = e["rule_id"]
            all_rules[rid] = all_rules.get(rid, 0) + 1

    print(f"\n{'='*78}")
    print(f"BATCH SUMMARY — {total} receipts analyzed in {total_time:.1f}s")
    print(f"{'='*78}")
    print(f"  \033[92mREAL\033[0m: {verdicts.get('real', 0)}  |  "
          f"\033[93mSUSPICIOUS\033[0m: {verdicts.get('suspicious', 0)}  |  "
          f"\033[91mFAKE\033[0m: {verdicts.get('fake', 0)}  |  "
          f"ERROR: {verdicts.get('ERROR', 0)}")

    if all_rules:
        print(f"\n  RULE FREQUENCY:")
        for rid, count in sorted(all_rules.items(), key=lambda x: -x[1]):
            bar = "█" * count
            print(f"    {rid:40s} {count:2d}  {bar}")

    print(f"\n  Avg time per receipt: {total_time/max(total,1):.1f}s")
    print()


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/test_batch"
    folder_path = Path(folder)

    if not folder_path.exists():
        print(f"Folder not found: {folder_path}")
        sys.exit(1)

    files = sorted([
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ])

    if not files:
        print(f"No supported files found in {folder_path}")
        print(f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
        sys.exit(1)

    print(f"\n🔍 Batch Receipt Analysis — {len(files)} files in {folder_path}")
    print(f"   VLM: {'enabled' if os.environ.get('VISION_EXTRACT_ENABLED','true').lower()=='true' else 'disabled'}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for idx, fpath in enumerate(files, 1):
        r = analyze_single(str(fpath))
        results.append(r)
        print_result(idx, len(files), r)

    print_summary(results)

    # Save JSON report
    report_path = folder_path / "_batch_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "folder": str(folder_path),
            "file_count": len(files),
            "results": results,
        }, f, indent=2)
    print(f"📄 JSON report saved: {report_path}")


if __name__ == "__main__":
    main()
