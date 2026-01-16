from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import yaml
except ModuleNotFoundError as e:
    yaml = None  # type: ignore
    _yaml_import_error = e

from app.pipelines.document_intent import DocumentIntentResult


DomainHintPayload = Dict[str, Any]


@dataclass
class DomainHint:
    domain: Optional[str] = None
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def make_domain_hint(*, domain: Optional[str], confidence: float, evidence: Optional[List[str]] = None) -> DomainHintPayload:
    return {
        "domain": domain,
        "confidence": float(confidence or 0.0),
        "evidence": list(evidence or []),
    }


_DOMAINPACK_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_domainpacks() -> List[Dict[str, Any]]:
    global _DOMAINPACK_CACHE
    if _DOMAINPACK_CACHE is not None:
        return _DOMAINPACK_CACHE

    if yaml is None:
        raise ModuleNotFoundError(
            "Missing dependency 'PyYAML'. Install it (e.g. `pip install PyYAML`) to use domain packs."
        ) from _yaml_import_error

    base_dir = Path("resources") / "domainpacks"
    packs: List[Dict[str, Any]] = []

    if not base_dir.exists():
        _DOMAINPACK_CACHE = []
        return _DOMAINPACK_CACHE

    for f in sorted(base_dir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        with open(f, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        if isinstance(data, dict) and data.get("id"):
            data["_source_file"] = str(f)
            packs.append(data)

    _DOMAINPACK_CACHE = packs
    return packs


def infer_domain_from_domainpacks(
    text_features: Dict[str, Any],
    lang_features: Dict[str, Any],
    layout_features: Dict[str, Any],
) -> DomainHintPayload:
    """Infer a lightweight domain hint by scoring domainpacks against extracted features.

    Returns a reusable payload:
        {"domain": str|None, "confidence": float, "evidence": [..], "intent_bias": {...}?}
    """

    candidates = _load_domainpacks()
    if not candidates:
        return make_domain_hint(domain=None, confidence=0.0, evidence=[])

    merged: Dict[str, Any] = {}
    merged.update(layout_features or {})
    merged.update(lang_features or {})
    merged.update(text_features or {})

    best_domain: Optional[str] = None
    best_conf: float = 0.0
    best_evidence: List[str] = []
    best_intent_bias: Optional[Dict[str, Any]] = None

    # Build full_text for negative keyword checking
    full_text_lower = " ".join(str(v).lower() for v in merged.values() if v).lower()

    for pack in candidates:
        pack_id = str(pack.get("id") or "").strip()
        if not pack_id:
            continue

        expectations = pack.get("expectations") or {}
        required_any = expectations.get("required_any") or []
        required_all = expectations.get("required_all") or []
        forbidden = expectations.get("forbidden") or []

        # NEGATIVE KEYWORDS: slam confidence to 0 if any forbidden keyword appears
        forbidden_hit = None
        for keyword in forbidden:
            if keyword and str(keyword).strip().lower() in full_text_lower:
                forbidden_hit = str(keyword).strip()
                break

        score = 0
        max_score = 0
        ev: List[str] = []

        if forbidden_hit:
            ev.append(f"{pack_id}:FORBIDDEN_KEYWORD:{forbidden_hit}")
            conf = 0.0
            # Skip scoring for this pack
            if conf > best_conf:
                best_conf = conf
                best_domain = pack_id
                best_evidence = sorted(set(ev))
                ib = pack.get("intent_bias")
                best_intent_bias = ib if isinstance(ib, dict) else None
            continue

        # required_any: OR across groups -> each satisfied group contributes.
        for group in required_any:
            if not isinstance(group, list):
                continue
            max_score += 1
            if any(bool(merged.get(k)) for k in group):
                score += 1
                ev.append(f"required_any:{pack_id}:{next((k for k in group if bool(merged.get(k))), 'hit')}")

        # required_all: AND across groups -> HARD GATE if any group fails.
        # required_all: AND across keys within a group -> group is satisfied only if ALL keys are present.
        required_all_failed = False
        for group in required_all:
            if not isinstance(group, list):
                continue
            max_score += 1
            if all(bool(merged.get(k)) for k in group):
                score += 1
                ev.append(f"required_all:{pack_id}:hit")
            else:
                missing = [k for k in group if not bool(merged.get(k))]
                ev.append(f"required_all:{pack_id}:missing:{','.join(missing[:5])}")
                required_all_failed = True

        if max_score <= 0:
            continue

        # HARD GATE: if any required_all group failed, confidence = 0.0
        if required_all_failed:
            conf = 0.0
            ev.append(f"{pack_id}:HARD_GATE:required_all_failed")
        else:
            conf = min(1.0, float(score) / float(max_score))

        if conf > best_conf:
            best_conf = conf
            best_domain = pack_id
            best_evidence = sorted(set(ev))
            ib = pack.get("intent_bias")
            best_intent_bias = ib if isinstance(ib, dict) else None

    payload = make_domain_hint(domain=best_domain, confidence=best_conf, evidence=best_evidence)
    if best_intent_bias:
        payload["intent_bias"] = best_intent_bias
    return payload


def infer_domain_hint(text: str, lines: Optional[List[str]] = None) -> DomainHint:
    t = (text or "").lower()

    patterns: List[Tuple[str, List[str]]] = [
        ("utility", ["electricity", "water", "gas", "utility", "meter", "kwh", "billing period"]),
        ("telecom", ["telecom", "mobile", "prepaid", "postpaid", "sim", "data", "broadband", "recharge"]),
        ("insurance", ["insurance", "policy", "premium", "insured", "policy number", "claim"]),
        ("medical", ["hospital", "patient", "doctor", "diagnosis", "treatment", "medical"]),
        ("ecommerce", ["order", "purchase order", "online order", "e-commerce", "tracking", "shipment"]),
        ("banking", ["bank", "statement", "opening balance", "closing balance", "utr", "rrn", "transaction id"]),
        ("transport", ["air waybill", "awb", "bill of lading", "container", "freight", "shipping"]),
    ]

    scores: Dict[str, int] = {}
    evidence: Dict[str, List[str]] = {}

    for domain, kws in patterns:
        for kw in kws:
            if kw in t:
                scores[domain] = scores.get(domain, 0) + 1
                evidence.setdefault(domain, []).append(kw)

    if not scores:
        return DomainHint(domain=None, confidence=0.0, evidence=[])

    best_domain = max(scores.items(), key=lambda kv: kv[1])[0]
    best_score = scores.get(best_domain, 0)
    conf = min(1.0, best_score / 3.0)

    ev = sorted(set(evidence.get(best_domain, [])))
    return DomainHint(domain=best_domain, confidence=conf, evidence=ev)


def validate_domain_pack(
    *,
    intent_result: DocumentIntentResult,
    domain_hint: Union[DomainHint, DomainHintPayload],
) -> Dict[str, Any]:
    intent = intent_result.intent.value
    intent_conf = float(intent_result.confidence or 0.0)

    if isinstance(domain_hint, DomainHint):
        domain_hint_payload: DomainHintPayload = domain_hint.to_dict()
    else:
        domain_hint_payload = dict(domain_hint or {})

    domain = domain_hint_payload.get("domain")
    domain_conf = float(domain_hint_payload.get("confidence") or 0.0)

    checks: List[Dict[str, Any]] = []

    def add_check(name: str, passed: bool, severity: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "severity": severity,
                "evidence": evidence or {},
            }
        )

    # Only enforce domain checks when both intent and domain are reasonably confident.
    enforce = bool(intent_conf >= 0.55 and domain_conf >= 0.60 and domain)

    add_check(
        "enforcement_gate",
        passed=enforce,
        severity="INFO",
        evidence={
            "intent": intent,
            "intent_confidence": intent_conf,
            "domain": domain,
            "domain_confidence": domain_conf,
        },
    )

    if enforce:
        expected_domains_by_intent = {
            "subscription": {"utility", "telecom", "insurance"},
            "statement": {"banking"},
            "transport": {"transport", "ecommerce"},
            "billing": {"utility", "telecom", "insurance", "ecommerce", "banking"},
            "purchase": {"ecommerce", "utility", "telecom", "insurance", "medical"},
        }

        expected = expected_domains_by_intent.get(intent)
        if expected is None:
            add_check("intent_has_domain_policy", passed=False, severity="INFO")
        else:
            add_check(
                "domain_matches_intent",
                passed=(domain in expected),
                severity="WARNING" if (domain not in expected) else "INFO",
                evidence={"expected_domains": sorted(expected), "observed_domain": domain},
            )

    passed = all(c.get("passed") is True for c in checks if c.get("severity") in ("WARNING", "CRITICAL"))

    return {
        "schema_version": "1.0",
        "domain_hint": domain_hint_payload,
        "intent": {
            "intent": intent,
            "confidence": intent_conf,
            "source": intent_result.source.value,
        },
        "enforced": enforce,
        "passed": bool(passed),
        "checks": checks,
    }
