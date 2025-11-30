# test_run.py — run from project root: VeriReceipt/test_run.py

from app.pipelines.rules import analyze_receipt
from app.utils.logger import log_decision   # <-- NEW


def main():
    # Update this path to point to any sample receipt you have
    sample_path = "data/raw/Gas_bill.jpeg"

    decision = analyze_receipt(sample_path)

    print("=== VeriReceipt Decision ===")
    print(f"Label : {decision.label}")
    print(f"Score : {decision.score:.2f}")
    print("Reasons:")
    for r in decision.reasons:
        print(f" - {r}")

    if decision.minor_notes:
        print("\nMinor Notes:")
        for note in decision.minor_notes:
            print(f" - {note}")

    # Log this analysis to CSV for future ML training
    log_decision(sample_path, decision)
    print("\n[LOG] Decision appended to data/logs/decisions.csv")

    # Optional: debug features
    # print("\nFile features:", decision.features.file_features)
    # print("Text features:", decision.features.text_features)
    # print("Forensic features:", decision.features.forensic_features)


if __name__ == "__main__":
    main()