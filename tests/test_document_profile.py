#!/usr/bin/env python3
"""
Unit tests for document profile detection feature.

Tests the _detect_document_profile() function that classifies receipts
into document families and subtypes based on keyword analysis.
"""

import pytest

from app.pipelines.features import _detect_document_profile


@pytest.mark.parametrize(
    "text, expected_family, expected_subtype, must_contain_kw",
    [
        # --- TRANSACTIONAL / RECEIPT ---
        ("RECEIPT\nTable 12\nServer: John\nGratuity\nTip\n", "TRANSACTIONAL", "POS_RESTAURANT", "gratuity"),
        ("Thank you\nSKU 123\nBarcode\nCashier\nReceipt\n", "TRANSACTIONAL", "POS_RETAIL", "barcode"),
        ("Order ID: 123\nFulfilled by\nTracking\nDelivered\n", "TRANSACTIONAL", "ECOMMERCE", "order id"),
        ("Hotel\nFolio\nRoom No 203\nCheck-in\nCheck-out\n", "TRANSACTIONAL", "HOTEL_FOLIO", "folio"),
        ("Fuel Pump\nNozzle 2\nTotal litres 10.5\nPrice per litre\n", "TRANSACTIONAL", "FUEL", "nozzle"),
        ("Parking\nEntry time 10:00\nExit time 12:00\nParking fee\n", "TRANSACTIONAL", "PARKING", "parking fee"),
        ("Trip\nDriver\nKM\nFare\n", "TRANSACTIONAL", "TRANSPORT", "fare"),
        ("Cash memo\nReceipt\nBill\n", "TRANSACTIONAL", "MISC", "receipt"),

        # --- TRANSACTIONAL / INVOICE ---
        ("TAX INVOICE\nGSTIN\nHSN\nPlace of Supply\nCGST\nSGST\n", "TRANSACTIONAL", "TAX_INVOICE", "gstin"),
        ("VAT INVOICE\nVAT Registration\nVAT% VAT amount\n", "TRANSACTIONAL", "VAT_INVOICE", "vat invoice"),
        ("COMMERCIAL INVOICE\nIncoterms\nCountry of origin\nConsignee\nShipper\n", "TRANSACTIONAL", "COMMERCIAL_INVOICE", "incoterms"),
        ("SERVICE INVOICE\nService period\nProfessional fee\nConsulting\n", "TRANSACTIONAL", "SERVICE_INVOICE", "service period"),
        ("SHIPPING INVOICE\nFreight charges\nCarrier\nAWB\n", "TRANSACTIONAL", "SHIPPING_INVOICE", "freight"),
        ("PROFORMA INVOICE\nQuotation\nQuote\n", "TRANSACTIONAL", "PROFORMA", "proforma"),
        ("CREDIT NOTE\nCredit memo\nCN No\n", "TRANSACTIONAL", "CREDIT_NOTE", "credit note"),
        ("DEBIT NOTE\nDebit memo\nDN No\n", "TRANSACTIONAL", "DEBIT_NOTE", "debit note"),

        # --- TRANSACTIONAL / BILL ---
        ("Electricity bill\nMeter\nkWh\nBilling period\n", "TRANSACTIONAL", "UTILITY", "kwh"),
        ("Mobile bill\nPostpaid\nData usage\nRoaming\n", "TRANSACTIONAL", "TELECOM", "data usage"),
        ("Subscription\nBilling cycle\nAuto-renew\nPlan\n", "TRANSACTIONAL", "SUBSCRIPTION", "auto-renew"),
        ("Rent\nTenant\nLandlord\nLease\n", "TRANSACTIONAL", "RENT", "tenant"),
        ("Insurance\nPolicy number\nPremium\nCoverage\n", "TRANSACTIONAL", "INSURANCE", "policy number"),

        # --- LOGISTICS ---
        ("Shipping bill\nCustoms\nLet export order\nAD code\n", "LOGISTICS", "SHIPPING_BILL", "customs"),
        ("Bill of Lading\nPort of loading\nPort of discharge\nContainer\n", "LOGISTICS", "BILL_OF_LADING", "bill of lading"),
        ("Air Waybill\nAWB\nIATA\nAir cargo\n", "LOGISTICS", "AIR_WAYBILL", "awb"),
        ("Delivery note\nDelivery challan\nProof of delivery\nReceived by\n", "LOGISTICS", "DELIVERY_NOTE", "proof of delivery"),

        # --- PAYMENT ---
        ("Payment receipt\nTransaction ID\nUTR\nPayment successful\n", "PAYMENT", "PAYMENT_RECEIPT", "transaction id"),
        ("Deposit slip\nBank slip\nIFSC\nBranch\n", "PAYMENT", "BANK_SLIP", "ifsc"),
        ("Charge slip\nTerminal ID\nApproval code\nMerchant copy\n", "PAYMENT", "CARD_CHARGE_SLIP", "terminal id"),
        ("Refund receipt\nRefunded\nReversal\nReturn\n", "PAYMENT", "REFUND_RECEIPT", "refund"),
    ],
)
def test_detect_document_profile_subtype(text, expected_family, expected_subtype, must_contain_kw):
    lines = text.splitlines()
    prof = _detect_document_profile(text, lines)

    assert prof["doc_family_guess"] == expected_family
    assert prof["doc_subtype_guess"] == expected_subtype
    assert 0.0 <= prof["doc_profile_confidence"] <= 1.0

    # Ensure the evidence includes at least one expected "anchor" keyword
    ev = [e.lower() for e in prof.get("doc_profile_evidence", [])]
    assert must_contain_kw.lower() in ev


def test_detect_document_profile_unknown_when_no_hits():
    text = "hello world\njust some random words\n"
    prof = _detect_document_profile(text, text.splitlines())
    assert prof["doc_family_guess"] == "UNKNOWN"
    assert prof["doc_subtype_guess"] == "UNKNOWN"
    assert prof["doc_profile_confidence"] == 0.0
    assert prof["doc_profile_evidence"] == []


def test_detect_document_profile_ambiguity_penalizes_confidence():
    # Intentionally mix strong signals from two buckets
    text = "TAX INVOICE\nGSTIN\nCGST\nSGST\n\nPAYMENT RECEIPT\nUTR\nTransaction ID\n"
    prof = _detect_document_profile(text, text.splitlines())

    assert prof["doc_family_guess"] in {"TRANSACTIONAL", "PAYMENT"}
    assert prof["doc_subtype_guess"] in {"TAX_INVOICE", "PAYMENT_RECEIPT"}
    # Confidence should not be absurdly high under conflict
    assert prof["doc_profile_confidence"] <= 0.75
