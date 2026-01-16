"""Golden Test: R7B Invoice Total Reconciliation"""
import pytest
from app.pipelines.rules import _score_and_explain
from app.pipelines.features import ReceiptFeatures


def create_test_features(**kwargs):
    features = ReceiptFeatures(
        file_features={}, text_features={}, layout_features={}, forensic_features={}
    )
    for key, value in kwargs.items():
        setattr(features, key, value)
    return features


def test_commercial_invoice_warning_not_critical():
    features = create_test_features(
        doc_class="COMMERCIAL_INVOICE", doc_subtype_guess="COMMERCIAL_INVOICE",
        doc_family_guess="INVOICE", doc_profile_confidence=0.85,
        total_amount=1200.0, subtotal=1000.0, tax_amount=100.0,
        ocr_confidence=0.80, has_line_items=False
    )
    result = _score_and_explain(features, apply_learned=False)
    r7b = [e for e in result.events if e.rule_id == "R7B_INVOICE_TOTAL_RECONCILIATION"]
    assert len(r7b) == 1 and r7b[0].severity == "WARNING"


def test_tax_invoice_stricter_tolerance():
    features = create_test_features(
        doc_class="TAX_INVOICE", doc_subtype_guess="TAX_INVOICE",
        doc_family_guess="INVOICE", doc_profile_confidence=0.85,
        total_amount=1030.0, subtotal=1000.0, tax_amount=0.0,
        ocr_confidence=0.80, has_line_items=False
    )
    result = _score_and_explain(features, apply_learned=False)
    r7b = [e for e in result.events if e.rule_id == "R7B_INVOICE_TOTAL_RECONCILIATION"]
    assert len(r7b) == 1 and r7b[0].evidence.get("tolerance") == 0.01


def test_minimum_delta_floor():
    features = create_test_features(
        doc_class="COMMERCIAL_INVOICE", doc_subtype_guess="COMMERCIAL_INVOICE",
        doc_family_guess="INVOICE", doc_profile_confidence=0.85,
        total_amount=5.0, subtotal=4.5, tax_amount=0.0,
        ocr_confidence=0.80, has_line_items=False
    )
    result = _score_and_explain(features, apply_learned=False)
    r7b = [e for e in result.events if e.rule_id == "R7B_INVOICE_TOTAL_RECONCILIATION"]
    assert len(r7b) == 0


def test_multi_currency_skip():
    features = create_test_features(
        doc_class="COMMERCIAL_INVOICE", doc_subtype_guess="COMMERCIAL_INVOICE",
        doc_family_guess="INVOICE", doc_profile_confidence=0.85,
        total_amount=1200.0, subtotal=1000.0, tax_amount=100.0,
        ocr_confidence=0.80, has_line_items=False, multi_currency_detected=True
    )
    result = _score_and_explain(features, apply_learned=False)
    r7b = [e for e in result.events if e.rule_id == "R7B_INVOICE_TOTAL_RECONCILIATION"]
    assert len(r7b) == 0
