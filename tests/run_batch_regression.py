"""
Batch Regression Runner.

Processes all receipt images in data/test_batch/unique/ through analyze_receipt
and saves a JSON report with scores, labels, fired rules, geo, and timing.

Usage:
    python tests/run_batch_regression.py [--no-vlm] [--batch BATCH_NAME] [--limit N]

Outputs:
    data/test_batch/unique/_batch_regression_YYYYMMDD_HHMMSS.json
"""

import glob
import json
import os
import sys
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BATCH_DIR = os.path.join(PROJECT_ROOT, "data", "test_batch", "unique")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".bmp", ".webp"}


def find_images(batch_dir: str, batch_filter: str = None) -> list:
    """Find all receipt images, optionally filtered by sub-batch."""
    images = []
    for root, dirs, files in os.walk(batch_dir):
        # Skip output/report files
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in EXTENSIONS:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, batch_dir)
                if batch_filter and not rel.startswith(batch_filter):
                    continue
                images.append(full)
    return images


def run_batch(images: list, vlm_enabled: bool = True) -> dict:
    """Run analyze_receipt on all images and collect results."""
    from app.pipelines.rules import analyze_receipt
    from app.pipelines.receipt_duplicates import clear_fingerprints

    # Clear fingerprints so batch images don't trigger duplicates against each other
    clear_fingerprints()

    results = []
    real_count = 0
    fake_count = 0
    suspicious_count = 0
    error_count = 0
    total_time = 0

    print(f"\n{'='*70}")
    print(f"BATCH REGRESSION — {len(images)} images")
    print(f"VLM: {'ENABLED' if vlm_enabled else 'DISABLED'}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    if not vlm_enabled:
        os.environ["VISION_EXTRACT_ENABLED"] = "false"
    else:
        os.environ.pop("VISION_EXTRACT_ENABLED", None)

    for i, img_path in enumerate(images, 1):
        basename = os.path.basename(img_path)
        rel_path = os.path.relpath(img_path, BATCH_DIR)
        print(f"[{i}/{len(images)}] {rel_path} ... ", end="", flush=True)

        t0 = time.time()
        try:
            decision = analyze_receipt(img_path)
            elapsed = time.time() - t0
            total_time += elapsed

            fired_rules = sorted(set(
                ev.get("rule_id") for ev in (decision.events or [])
                if isinstance(ev, dict) and ev.get("rule_id")
                and ev.get("weight", 0) > 0  # only rules with positive weight
            ))

            label = decision.label
            score = round(decision.score, 4)

            if label == "real":
                real_count += 1
                icon = "✅"
            elif label == "fake":
                fake_count += 1
                icon = "🔴"
            else:
                suspicious_count += 1
                icon = "🟡"

            print(f"{icon} {label} ({score:.3f}) [{elapsed:.1f}s]")

            results.append({
                "file": rel_path,
                "label": label,
                "score": score,
                "fired_rules": fired_rules,
                "elapsed": round(elapsed, 1),
            })

        except Exception as e:
            elapsed = time.time() - t0
            total_time += elapsed
            error_count += 1
            print(f"❌ ERROR: {e} [{elapsed:.1f}s]")
            results.append({
                "file": rel_path,
                "label": "ERROR",
                "score": -1,
                "error": str(e),
                "elapsed": round(elapsed, 1),
            })

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"  Total:      {len(images)}")
    print(f"  Real:       {real_count}")
    print(f"  Fake:       {fake_count}")
    print(f"  Suspicious: {suspicious_count}")
    print(f"  Errors:     {error_count}")
    print(f"  Total time: {total_time:.0f}s ({total_time/max(len(images),1):.1f}s avg)")
    print(f"{'='*70}")

    # Collect all fired rules across all images
    all_rules = {}
    for r in results:
        for rule in r.get("fired_rules", []):
            all_rules[rule] = all_rules.get(rule, 0) + 1
    
    print(f"\nRule firing frequency:")
    for rule, count in sorted(all_rules.items(), key=lambda x: -x[1]):
        print(f"  {rule}: {count}/{len(images)} ({count/len(images)*100:.0f}%)")

    return {
        "timestamp": datetime.now().isoformat(),
        "image_count": len(images),
        "vlm_enabled": vlm_enabled,
        "summary": {
            "real": real_count,
            "fake": fake_count,
            "suspicious": suspicious_count,
            "errors": error_count,
            "total_seconds": round(total_time, 1),
            "avg_seconds": round(total_time / max(len(images), 1), 1),
        },
        "rule_frequency": dict(sorted(all_rules.items(), key=lambda x: -x[1])),
        "results": results,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run batch regression on test images")
    parser.add_argument("--no-vlm", action="store_true", help="Disable VLM extraction")
    parser.add_argument("--batch", type=str, help="Only run images from a specific sub-batch folder")
    parser.add_argument("--limit", type=int, help="Limit number of images to process")
    args = parser.parse_args()

    images = find_images(BATCH_DIR, batch_filter=args.batch)
    if args.limit:
        images = images[:args.limit]

    if not images:
        print(f"No images found in {BATCH_DIR}")
        sys.exit(1)

    report = run_batch(images, vlm_enabled=not args.no_vlm)

    # Save report
    vlm_tag = "vlm" if not args.no_vlm else "novlm"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(BATCH_DIR, f"_batch_regression_{vlm_tag}_{ts}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved: {report_path}")
