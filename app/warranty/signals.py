"""
Rule-based fraud signals for warranty claims.

Detects anomalies in:
- Math validation (totals, ratios)
- Date validation (future dates, expired warranty)
- Cost validation (vs benchmarks)
- Pattern detection (known fraud patterns)
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum

from .db import get_benchmark, get_dealer_statistics, get_connection, release_connection, _get_cursor, _sql, USE_POSTGRES
import re


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class FraudSignal:
    """A detected fraud signal."""
    signal_type: str
    severity: Severity
    description: str
    evidence: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity.value,
            "description": self.description,
            "evidence": self.evidence or {}
        }


class WarrantyFraudSignalDetector:
    """
    Detect fraud signals in warranty claims using rule-based logic.
    """
    
    # Thresholds
    MAX_LABOR_TO_PARTS_RATIO = 2.0  # Labor > 2x parts is suspicious
    MIN_LABOR_TO_PARTS_RATIO = 0.1  # Labor < 10% of parts is suspicious
    MAX_TAX_RATE = 0.15  # Tax > 15% of subtotal is suspicious
    MIN_TAX_RATE = 0.0  # Negative tax is suspicious
    BENCHMARK_STD_THRESHOLD = 2.5  # Flag if > 2.5 std devs from mean
    MAX_VEHICLE_AGE_FOR_WARRANTY = 10  # Years
    MAX_CLAIM_PROCESSING_DAYS = 180  # Days from claim to decision
    
    def __init__(self):
        pass
    
    def detect_signals(
        self,
        claim_id: str,
        parts_cost: Optional[float],
        labor_cost: Optional[float],
        tax: Optional[float],
        total_amount: Optional[float],
        brand: Optional[str],
        model: Optional[str],
        year: Optional[int],
        issue_description: Optional[str],
        claim_date: Optional[str],
        decision_date: Optional[str],
        status: Optional[str],
        dealer_id: Optional[str] = None,
        vin: Optional[str] = None,
        odometer: Optional[int] = None,
        labor_hours: Optional[float] = None,
        parts_list: Optional[List[Dict]] = None,
        image_count: Optional[int] = None,
        country_code: Optional[str] = None
    ) -> Tuple[List[FraudSignal], List[str]]:
        """
        Detect all fraud signals for a claim.
        
        Returns:
            Tuple of (fraud_signals, warnings)
        """
        signals = []
        warnings = []
        
        # Math validation
        math_signals, math_warnings = self._check_math(
            parts_cost, labor_cost, tax, total_amount
        )
        signals.extend(math_signals)
        warnings.extend(math_warnings)
        
        # Date validation
        date_signals, date_warnings = self._check_dates(
            claim_date, decision_date, year
        )
        signals.extend(date_signals)
        warnings.extend(date_warnings)
        
        # Benchmark validation
        if issue_description:
            bench_signals, bench_warnings = self._check_against_benchmark(
                brand=brand,
                issue_type=issue_description,
                parts_cost=parts_cost,
                labor_cost=labor_cost,
                total_amount=total_amount
            )
            signals.extend(bench_signals)
            warnings.extend(bench_warnings)
        
        # Dealer history check
        if dealer_id:
            dealer_signals, dealer_warnings = self._check_dealer_history(dealer_id)
            signals.extend(dealer_signals)
            warnings.extend(dealer_warnings)
        
        # Pattern checks
        pattern_signals = self._check_known_patterns(
            parts_cost=parts_cost,
            labor_cost=labor_cost,
            tax=tax,
            total_amount=total_amount,
            issue_description=issue_description,
            status=status
        )
        signals.extend(pattern_signals)
        
        # VIN validation
        if vin:
            vin_signals, vin_warnings = self._check_vin(
                vin=vin,
                brand=brand,
                model=model,
                year=year
            )
            signals.extend(vin_signals)
            warnings.extend(vin_warnings)
        
        # Odometer regression check
        if vin and odometer is not None:
            odo_signals = self._check_odometer_regression(
                vin=vin,
                odometer=odometer,
                claim_id=claim_id,
                claim_date=claim_date
            )
            signals.extend(odo_signals)
        
        # Labor hours check
        if labor_hours is not None and labor_cost is not None:
            labor_signals = self._check_labor_hours(
                labor_hours=labor_hours,
                labor_cost=labor_cost,
                issue_description=issue_description
            )
            signals.extend(labor_signals)
        
        # Tax geo consistency
        if country_code and tax is not None:
            tax_geo_signals = self._check_tax_geo_consistency(
                tax=tax,
                total_amount=total_amount,
                country_code=country_code
            )
            signals.extend(tax_geo_signals)
        
        # Dealer claim spike
        if dealer_id:
            spike_signals = self._check_dealer_claim_spike(dealer_id)
            signals.extend(spike_signals)
        
        # Repeat claim check
        if vin and issue_description:
            repeat_signals = self._check_repeat_claims(
                vin=vin,
                issue_description=issue_description,
                claim_id=claim_id,
                claim_date=claim_date
            )
            signals.extend(repeat_signals)
        
        # Excessive claims for same vehicle
        if vin:
            excessive_signals = self._check_vin_excessive_claims(
                vin=vin,
                claim_id=claim_id
            )
            signals.extend(excessive_signals)
        
        # Image count policy check
        if image_count is not None:
            img_signals = self._check_image_count(image_count, issue_description)
            signals.extend(img_signals)
        
        return signals, warnings
    
    def _check_math(
        self,
        parts_cost: Optional[float],
        labor_cost: Optional[float],
        tax: Optional[float],
        total_amount: Optional[float]
    ) -> Tuple[List[FraudSignal], List[str]]:
        """Check mathematical consistency."""
        signals = []
        warnings = []
        
        # Check for negative values
        if tax is not None and tax < 0:
            signals.append(FraudSignal(
                signal_type="NEGATIVE_TAX",
                severity=Severity.HIGH,
                description=f"Negative tax amount: ${tax:.2f}",
                evidence={"tax": tax}
            ))
        
        if parts_cost is not None and parts_cost < 0:
            signals.append(FraudSignal(
                signal_type="NEGATIVE_PARTS_COST",
                severity=Severity.HIGH,
                description=f"Negative parts cost: ${parts_cost:.2f}",
                evidence={"parts_cost": parts_cost}
            ))
        
        if labor_cost is not None and labor_cost < 0:
            signals.append(FraudSignal(
                signal_type="NEGATIVE_LABOR_COST",
                severity=Severity.HIGH,
                description=f"Negative labor cost: ${labor_cost:.2f}",
                evidence={"labor_cost": labor_cost}
            ))
        
        # Check total calculation
        if all(v is not None for v in [parts_cost, labor_cost, tax, total_amount]):
            expected_total = parts_cost + labor_cost + tax
            diff = abs(expected_total - total_amount)
            
            if diff > 1.0:  # Allow $1 rounding tolerance
                signals.append(FraudSignal(
                    signal_type="TOTAL_MISMATCH",
                    severity=Severity.MEDIUM,
                    description=f"Total ${total_amount:.2f} doesn't match components "
                               f"(${parts_cost:.2f} + ${labor_cost:.2f} + ${tax:.2f} = ${expected_total:.2f})",
                    evidence={
                        "total": total_amount,
                        "expected_total": expected_total,
                        "difference": diff
                    }
                ))
        
        # Check labor/parts ratio
        if parts_cost and parts_cost > 0 and labor_cost is not None:
            ratio = labor_cost / parts_cost
            
            if ratio > self.MAX_LABOR_TO_PARTS_RATIO:
                signals.append(FraudSignal(
                    signal_type="LABOR_PARTS_RATIO_HIGH",
                    severity=Severity.MEDIUM,
                    description=f"Labor/parts ratio unusually high: {ratio:.2f} "
                               f"(labor ${labor_cost:.2f}, parts ${parts_cost:.2f})",
                    evidence={"ratio": ratio, "threshold": self.MAX_LABOR_TO_PARTS_RATIO}
                ))
            elif ratio < self.MIN_LABOR_TO_PARTS_RATIO and labor_cost > 0:
                warnings.append(f"Labor/parts ratio unusually low: {ratio:.2f}")
        
        # Check tax rate
        if parts_cost and labor_cost and tax is not None:
            subtotal = parts_cost + labor_cost
            if subtotal > 0:
                tax_rate = tax / subtotal
                
                if tax_rate > self.MAX_TAX_RATE:
                    signals.append(FraudSignal(
                        signal_type="TAX_RATE_HIGH",
                        severity=Severity.MEDIUM,
                        description=f"Tax rate unusually high: {tax_rate*100:.1f}%",
                        evidence={"tax_rate": tax_rate, "threshold": self.MAX_TAX_RATE}
                    ))
        
        return signals, warnings
    
    def _check_dates(
        self,
        claim_date: Optional[str],
        decision_date: Optional[str],
        vehicle_year: Optional[int]
    ) -> Tuple[List[FraudSignal], List[str]]:
        """Check date-related anomalies."""
        signals = []
        warnings = []
        
        today = date.today()
        
        # Parse claim date
        claim_dt = None
        if claim_date:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    claim_dt = datetime.strptime(claim_date, fmt).date()
                    break
                except ValueError:
                    continue
        
        # Check for future claim date
        if claim_dt and claim_dt > today:
            signals.append(FraudSignal(
                signal_type="FUTURE_CLAIM_DATE",
                severity=Severity.HIGH,
                description=f"Claim date is in the future: {claim_date}",
                evidence={"claim_date": claim_date}
            ))
        
        # Check vehicle age vs warranty
        if vehicle_year and claim_dt:
            vehicle_age = claim_dt.year - vehicle_year
            
            if vehicle_age > self.MAX_VEHICLE_AGE_FOR_WARRANTY:
                signals.append(FraudSignal(
                    signal_type="VEHICLE_TOO_OLD",
                    severity=Severity.MEDIUM,
                    description=f"Vehicle is {vehicle_age} years old at claim time "
                               f"(manufactured {vehicle_year})",
                    evidence={"vehicle_age": vehicle_age, "year": vehicle_year}
                ))
            elif vehicle_age < 0:
                signals.append(FraudSignal(
                    signal_type="CLAIM_BEFORE_MANUFACTURE",
                    severity=Severity.HIGH,
                    description=f"Claim date {claim_date} is before vehicle manufacture year {vehicle_year}",
                    evidence={"claim_date": claim_date, "year": vehicle_year}
                ))
        
        # Check processing time
        if claim_dt and decision_date:
            decision_dt = None
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    decision_dt = datetime.strptime(decision_date, fmt).date()
                    break
                except ValueError:
                    continue
            
            if decision_dt:
                processing_days = (decision_dt - claim_dt).days
                
                if processing_days < 0:
                    signals.append(FraudSignal(
                        signal_type="DECISION_BEFORE_CLAIM",
                        severity=Severity.HIGH,
                        description=f"Decision date {decision_date} is before claim date {claim_date}",
                        evidence={"claim_date": claim_date, "decision_date": decision_date}
                    ))
                elif processing_days > self.MAX_CLAIM_PROCESSING_DAYS:
                    warnings.append(
                        f"Unusually long processing time: {processing_days} days"
                    )
        
        return signals, warnings
    
    def _check_against_benchmark(
        self,
        brand: Optional[str],
        issue_type: str,
        parts_cost: Optional[float],
        labor_cost: Optional[float],
        total_amount: Optional[float]
    ) -> Tuple[List[FraudSignal], List[str]]:
        """Check costs against historical benchmarks."""
        signals = []
        warnings = []
        
        benchmark = get_benchmark(brand, issue_type)
        
        if not benchmark:
            warnings.append(f"No benchmark data for {brand or 'generic'} / {issue_type}")
            return signals, warnings
        
        # Check total amount
        if total_amount is not None and benchmark.get("avg_total"):
            avg = benchmark["avg_total"]
            std = benchmark.get("std_total", avg * 0.3)  # Default 30% std
            
            if std > 0:
                z_score = (total_amount - avg) / std
                
                if z_score > self.BENCHMARK_STD_THRESHOLD:
                    signals.append(FraudSignal(
                        signal_type="TOTAL_ABOVE_BENCHMARK",
                        severity=Severity.MEDIUM,
                        description=f"Total ${total_amount:.2f} is {z_score:.1f} std devs above "
                                   f"average ${avg:.2f} for {issue_type}",
                        evidence={
                            "total": total_amount,
                            "benchmark_avg": avg,
                            "benchmark_std": std,
                            "z_score": z_score
                        }
                    ))
                elif z_score < -self.BENCHMARK_STD_THRESHOLD:
                    warnings.append(
                        f"Total ${total_amount:.2f} is unusually low for {issue_type} "
                        f"(avg: ${avg:.2f})"
                    )
        
        # Check parts cost
        if parts_cost is not None and benchmark.get("avg_parts_cost"):
            avg = benchmark["avg_parts_cost"]
            std = benchmark.get("std_parts_cost", avg * 0.3)
            
            if std > 0:
                z_score = (parts_cost - avg) / std
                
                if z_score > self.BENCHMARK_STD_THRESHOLD:
                    signals.append(FraudSignal(
                        signal_type="PARTS_COST_ABOVE_BENCHMARK",
                        severity=Severity.LOW,
                        description=f"Parts cost ${parts_cost:.2f} is {z_score:.1f} std devs above "
                                   f"average ${avg:.2f}",
                        evidence={
                            "parts_cost": parts_cost,
                            "benchmark_avg": avg,
                            "z_score": z_score
                        }
                    ))
        
        # Check labor cost
        if labor_cost is not None and benchmark.get("avg_labor_cost"):
            avg = benchmark["avg_labor_cost"]
            std = benchmark.get("std_labor_cost", avg * 0.3)
            
            if std > 0:
                z_score = (labor_cost - avg) / std
                
                if z_score > self.BENCHMARK_STD_THRESHOLD:
                    signals.append(FraudSignal(
                        signal_type="LABOR_COST_ABOVE_BENCHMARK",
                        severity=Severity.LOW,
                        description=f"Labor cost ${labor_cost:.2f} is {z_score:.1f} std devs above "
                                   f"average ${avg:.2f}",
                        evidence={
                            "labor_cost": labor_cost,
                            "benchmark_avg": avg,
                            "z_score": z_score
                        }
                    ))
        
        return signals, warnings
    
    def _check_dealer_history(
        self,
        dealer_id: str
    ) -> Tuple[List[FraudSignal], List[str]]:
        """Check dealer's historical fraud patterns."""
        signals = []
        warnings = []
        
        stats = get_dealer_statistics(dealer_id)
        
        if not stats:
            return signals, warnings
        
        # High fraud rate
        if stats.get("fraud_confirmed", 0) > 0 and stats.get("total_claims", 0) > 5:
            fraud_rate = stats["fraud_confirmed"] / stats["total_claims"]
            
            if fraud_rate > 0.1:  # > 10% fraud rate
                signals.append(FraudSignal(
                    signal_type="HIGH_RISK_DEALER",
                    severity=Severity.HIGH,
                    description=f"Dealer has {fraud_rate*100:.1f}% confirmed fraud rate "
                               f"({stats['fraud_confirmed']}/{stats['total_claims']} claims)",
                    evidence={
                        "dealer_id": dealer_id,
                        "fraud_rate": fraud_rate,
                        "fraud_count": stats["fraud_confirmed"],
                        "total_claims": stats["total_claims"]
                    }
                ))
            elif fraud_rate > 0.05:  # > 5% fraud rate
                warnings.append(
                    f"Dealer has elevated fraud rate: {fraud_rate*100:.1f}%"
                )
        
        # High duplicate rate
        if stats.get("duplicate_count", 0) > 2:
            warnings.append(
                f"Dealer has {stats['duplicate_count']} duplicate image submissions"
            )
        
        return signals, warnings
    
    def _check_known_patterns(
        self,
        parts_cost: Optional[float],
        labor_cost: Optional[float],
        tax: Optional[float],
        total_amount: Optional[float],
        issue_description: Optional[str],
        status: Optional[str]
    ) -> List[FraudSignal]:
        """Check for known fraud patterns."""
        signals = []
        
        # Pattern: Round number amounts (often fabricated)
        if total_amount and total_amount > 100:
            if total_amount == int(total_amount):
                signals.append(FraudSignal(
                    signal_type="ROUND_TOTAL",
                    severity=Severity.LOW,
                    description=f"Suspiciously round total: ${total_amount:.2f}",
                    evidence={"total": total_amount}
                ))
        
        # Pattern: All amounts ending in same digits
        if all(v is not None for v in [parts_cost, labor_cost, tax]):
            cents = [
                int((v * 100) % 100) for v in [parts_cost, labor_cost, tax]
                if v > 0
            ]
            if len(cents) >= 2 and len(set(cents)) == 1 and cents[0] != 0:
                signals.append(FraudSignal(
                    signal_type="MATCHING_CENTS",
                    severity=Severity.LOW,
                    description="All amounts have matching cents values",
                    evidence={
                        "parts_cost": parts_cost,
                        "labor_cost": labor_cost,
                        "tax": tax
                    }
                ))
        
        # Pattern: Zero labor for complex repair
        complex_issues = ["transmission", "engine", "steering", "suspension"]
        if issue_description and labor_cost == 0:
            issue_lower = issue_description.lower()
            for issue in complex_issues:
                if issue in issue_lower:
                    signals.append(FraudSignal(
                        signal_type="ZERO_LABOR_COMPLEX_REPAIR",
                        severity=Severity.MEDIUM,
                        description=f"Zero labor cost for complex repair: {issue_description}",
                        evidence={"issue": issue_description, "labor_cost": 0}
                    ))
                    break
        
        return signals
    
    def _check_vin(
        self,
        vin: str,
        brand: Optional[str],
        model: Optional[str],
        year: Optional[int]
    ) -> Tuple[List[FraudSignal], List[str]]:
        """Validate VIN format and check for model mismatch."""
        signals = []
        warnings = []
        
        # VIN format validation
        if len(vin) != 17:
            signals.append(FraudSignal(
                signal_type="VIN_INVALID_FORMAT",
                severity=Severity.MEDIUM,
                description=f"VIN length is {len(vin)}, expected 17 characters",
                evidence={"vin": vin, "length": len(vin)}
            ))
        
        # Check for illegal characters (I, O, Q not allowed in VINs)
        illegal_chars = set(vin.upper()) & {'I', 'O', 'Q'}
        if illegal_chars:
            signals.append(FraudSignal(
                signal_type="VIN_INVALID_FORMAT",
                severity=Severity.MEDIUM,
                description=f"VIN contains illegal characters: {illegal_chars}",
                evidence={"vin": vin, "illegal_chars": list(illegal_chars)}
            ))
        
        # Basic VIN decode for brand check (position 1-3 = WMI)
        if len(vin) >= 3 and brand:
            wmi_brand_map = {
                "1G": "Chevrolet", "2G": "Chevrolet",
                "1F": "Ford", "1FA": "Ford", "1FB": "Ford",
                "1H": "Honda", "2H": "Honda", "JH": "Honda",
                "1N": "Nissan", "JN": "Nissan",
                "2T": "Toyota", "4T": "Toyota", "JT": "Toyota",
                "WA": "Audi", "WV": "Volkswagen", "WB": "BMW",
                "JM": "Mazda", "4F": "Mazda",
                "KM": "Hyundai", "5N": "Hyundai",
                "KN": "Kia",
                "JF": "Subaru", "4S": "Subaru",
            }
            vin_prefix = vin[:2].upper()
            vin_prefix3 = vin[:3].upper()
            
            expected_brand = wmi_brand_map.get(vin_prefix3) or wmi_brand_map.get(vin_prefix)
            if expected_brand and brand.lower() != expected_brand.lower():
                signals.append(FraudSignal(
                    signal_type="VIN_MODEL_MISMATCH",
                    severity=Severity.HIGH,
                    description=f"VIN indicates {expected_brand} but claim says {brand}",
                    evidence={
                        "vin": vin,
                        "vin_brand": expected_brand,
                        "claimed_brand": brand
                    }
                ))
        
        # Check year from VIN (position 10)
        if len(vin) >= 10 and year:
            year_char = vin[9].upper()
            year_map = {
                'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014,
                'F': 2015, 'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019,
                'L': 2020, 'M': 2021, 'N': 2022, 'P': 2023, 'R': 2024,
                'S': 2025, 'T': 2026, 'V': 2027, 'W': 2028, 'X': 2029,
                '1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005,
                '6': 2006, '7': 2007, '8': 2008, '9': 2009,
            }
            vin_year = year_map.get(year_char)
            if vin_year and abs(vin_year - year) > 1:  # Allow 1 year tolerance
                signals.append(FraudSignal(
                    signal_type="VIN_MODEL_MISMATCH",
                    severity=Severity.HIGH,
                    description=f"VIN indicates year {vin_year} but claim says {year}",
                    evidence={
                        "vin": vin,
                        "vin_year": vin_year,
                        "claimed_year": year
                    }
                ))
        
        return signals, warnings
    
    def _check_odometer_regression(
        self,
        vin: str,
        odometer: int,
        claim_id: str,
        claim_date: Optional[str]
    ) -> List[FraudSignal]:
        """Check if odometer has gone backwards compared to previous claims."""
        signals = []
        
        conn = get_connection()
        try:
            cursor = _get_cursor(conn)
            
            # Find previous claims for this VIN
            cursor.execute(_sql("""
                SELECT id, odometer, claim_date 
                FROM warranty_claims 
                WHERE vin = ? AND id != ? AND odometer IS NOT NULL
                ORDER BY claim_date DESC
            """), (vin, claim_id))
            
            for row in cursor.fetchall():
                prev_odometer = row["odometer"]
                prev_date = row["claim_date"]
                
                if prev_odometer and prev_odometer > odometer:
                    signals.append(FraudSignal(
                        signal_type="ODOMETER_REGRESSION",
                        severity=Severity.HIGH,
                        description=f"Odometer went backwards: prior claim shows {prev_odometer:,} miles, "
                                   f"current claim shows {odometer:,} miles",
                        evidence={
                            "current_odometer": odometer,
                            "prior_odometer": prev_odometer,
                            "prior_claim_id": row["id"],
                            "prior_claim_date": prev_date
                        }
                    ))
                    break  # One signal is enough
        finally:
            release_connection(conn)
        
        return signals
    
    def _check_labor_hours(
        self,
        labor_hours: float,
        labor_cost: float,
        issue_description: Optional[str]
    ) -> List[FraudSignal]:
        """Check labor rate and hours for anomalies."""
        signals = []
        
        # Calculate hourly rate
        if labor_hours > 0:
            hourly_rate = labor_cost / labor_hours
            
            # Typical labor rates: $75-$200/hour
            if hourly_rate < 30:
                signals.append(FraudSignal(
                    signal_type="LABOR_RATE_OUTLIER",
                    severity=Severity.MEDIUM,
                    description=f"Labor rate unusually low: ${hourly_rate:.2f}/hour",
                    evidence={"hourly_rate": hourly_rate, "expected_range": "$75-$200"}
                ))
            elif hourly_rate > 300:
                signals.append(FraudSignal(
                    signal_type="LABOR_RATE_OUTLIER",
                    severity=Severity.MEDIUM,
                    description=f"Labor rate unusually high: ${hourly_rate:.2f}/hour",
                    evidence={"hourly_rate": hourly_rate, "expected_range": "$75-$200"}
                ))
        
        # Check hours against typical repair times
        if issue_description:
            issue_lower = issue_description.lower()
            typical_hours = {
                "battery": (0.5, 2),
                "oil leak": (1, 4),
                "brake": (1, 4),
                "alternator": (1, 3),
                "fuel pump": (2, 5),
                "transmission": (4, 12),
                "engine": (4, 20),
                "steering": (2, 6),
            }
            
            for issue, (min_hrs, max_hrs) in typical_hours.items():
                if issue in issue_lower:
                    if labor_hours > max_hrs * 2:  # More than 2x typical max
                        signals.append(FraudSignal(
                            signal_type="EXCESSIVE_LABOR_HOURS_FOR_PART",
                            severity=Severity.MEDIUM,
                            description=f"Labor hours ({labor_hours}h) excessive for {issue} "
                                       f"(typical: {min_hrs}-{max_hrs}h)",
                            evidence={
                                "labor_hours": labor_hours,
                                "issue": issue,
                                "typical_range": f"{min_hrs}-{max_hrs}h"
                            }
                        ))
                    break
        
        return signals
    
    def _check_tax_geo_consistency(
        self,
        tax: float,
        total_amount: Optional[float],
        country_code: str
    ) -> List[FraudSignal]:
        """Check if tax is consistent with geographic location."""
        signals = []
        
        if total_amount and total_amount > 0:
            tax_rate = tax / total_amount
            
            # Expected tax rates by country
            expected_rates = {
                "US": (0.04, 0.12),   # 4-12% sales tax
                "CA": (0.05, 0.15),   # 5-15% GST/PST
                "UK": (0.20, 0.20),   # 20% VAT
                "DE": (0.19, 0.19),   # 19% VAT
                "IN": (0.05, 0.28),   # 5-28% GST
                "AE": (0.05, 0.05),   # 5% VAT
            }
            
            if country_code in expected_rates:
                min_rate, max_rate = expected_rates[country_code]
                if tax_rate < min_rate - 0.02 or tax_rate > max_rate + 0.02:
                    signals.append(FraudSignal(
                        signal_type="TAX_INCONSISTENT_WITH_GEO",
                        severity=Severity.MEDIUM,
                        description=f"Tax rate {tax_rate*100:.1f}% inconsistent with {country_code} "
                                   f"(expected {min_rate*100:.0f}-{max_rate*100:.0f}%)",
                        evidence={
                            "tax_rate": tax_rate,
                            "country": country_code,
                            "expected_range": f"{min_rate*100:.0f}-{max_rate*100:.0f}%"
                        }
                    ))
        
        return signals
    
    def _check_dealer_claim_spike(self, dealer_id: str) -> List[FraudSignal]:
        """Check if dealer has unusual spike in claims."""
        signals = []
        
        conn = get_connection()
        try:
            cursor = _get_cursor(conn)
            
            # Count claims in last 30 days vs previous 30 days
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN claim_date >= (CURRENT_DATE - INTERVAL '30 days')::TEXT THEN 1 ELSE 0 END) as recent,
                        SUM(CASE WHEN claim_date >= (CURRENT_DATE - INTERVAL '60 days')::TEXT 
                                 AND claim_date < (CURRENT_DATE - INTERVAL '30 days')::TEXT THEN 1 ELSE 0 END) as prior
                    FROM warranty_claims
                    WHERE dealer_id = %s
                """, (dealer_id,))
            else:
                cursor.execute("""
                    SELECT 
                        SUM(CASE WHEN claim_date >= date('now', '-30 days') THEN 1 ELSE 0 END) as recent,
                        SUM(CASE WHEN claim_date >= date('now', '-60 days') 
                                 AND claim_date < date('now', '-30 days') THEN 1 ELSE 0 END) as prior
                    FROM warranty_claims
                    WHERE dealer_id = ?
                """, (dealer_id,))
            
            row = cursor.fetchone()
            if row:
                recent = row["recent"] or 0
                prior = row["prior"] or 0
                
                if prior > 0 and recent > prior * 2.5:  # 2.5x spike
                    signals.append(FraudSignal(
                        signal_type="DEALER_SPIKE_IN_CLAIMS",
                        severity=Severity.MEDIUM,
                        description=f"Dealer claim volume spiked: {recent} claims in last 30 days "
                                   f"vs {prior} in prior 30 days ({recent/prior:.1f}x increase)",
                        evidence={
                            "dealer_id": dealer_id,
                            "recent_claims": recent,
                            "prior_claims": prior,
                            "spike_ratio": recent / prior if prior > 0 else None
                        }
                    ))
        finally:
            release_connection(conn)
        
        return signals
    
    def _check_repeat_claims(
        self,
        vin: str,
        issue_description: str,
        claim_id: str,
        claim_date: Optional[str]
    ) -> List[FraudSignal]:
        """Check for repeated claims for same part on same vehicle."""
        signals = []
        
        conn = get_connection()
        try:
            cursor = _get_cursor(conn)
            
            # Find similar claims for same VIN in last 90 days
            if USE_POSTGRES:
                cursor.execute("""
                    SELECT id, issue_description, claim_date
                    FROM warranty_claims
                    WHERE vin = %s AND id != %s
                    AND claim_date >= (CURRENT_DATE - INTERVAL '90 days')::TEXT
                """, (vin, claim_id))
            else:
                cursor.execute("""
                    SELECT id, issue_description, claim_date
                    FROM warranty_claims
                    WHERE vin = ? AND id != ?
                    AND claim_date >= date('now', '-90 days')
                """, (vin, claim_id))
            
            issue_words = set(issue_description.lower().split())
            
            for row in cursor.fetchall():
                prev_issue = row["issue_description"] or ""
                prev_words = set(prev_issue.lower().split())
                
                # Check word overlap
                overlap = len(issue_words & prev_words)
                if overlap >= 2:  # At least 2 common words
                    signals.append(FraudSignal(
                        signal_type="REPEAT_CLAIM_SAME_PART_SHORT_WINDOW",
                        severity=Severity.MEDIUM,
                        description=f"Similar claim for same VIN within 90 days: "
                                   f"'{prev_issue}' (claim {row['id']})",
                        evidence={
                            "current_issue": issue_description,
                            "prior_issue": prev_issue,
                            "prior_claim_id": row["id"],
                            "prior_claim_date": row["claim_date"]
                        }
                    ))
                    break  # One signal is enough
        finally:
            release_connection(conn)
        
        return signals
    
    def _check_image_count(
        self,
        image_count: int,
        issue_description: Optional[str]
    ) -> List[FraudSignal]:
        """Check if image count meets policy requirements."""
        signals = []
        
        # Minimum expected images by issue type
        min_images = 2  # Default minimum
        
        if issue_description:
            issue_lower = issue_description.lower()
            if any(x in issue_lower for x in ["engine", "transmission", "body"]):
                min_images = 3
        
        if image_count < min_images:
            signals.append(FraudSignal(
                signal_type="IMAGE_COUNT_MISMATCH",
                severity=Severity.LOW,
                description=f"Only {image_count} image(s) provided, expected at least {min_images}",
                evidence={
                    "image_count": image_count,
                    "expected_minimum": min_images
                }
            ))
        
        return signals
    
    def _check_vin_excessive_claims(
        self,
        vin: str,
        claim_id: str
    ) -> List[FraudSignal]:
        """Check if vehicle has excessive number of claims overall."""
        signals = []
        
        conn = get_connection()
        try:
            cursor = _get_cursor(conn)
            
            # Count total claims for this VIN
            cursor.execute(_sql("""
                SELECT COUNT(*) as claim_count,
                       MIN(claim_date) as first_claim,
                       MAX(claim_date) as last_claim,
                       SUM(total_amount) as total_claimed
                FROM warranty_claims
                WHERE vin = ? AND id != ?
            """), (vin, claim_id))
            
            row = cursor.fetchone()
            if row and row["claim_count"]:
                claim_count = row["claim_count"]
                total_claimed = row["total_claimed"] or 0
                
                # Flag if more than 3 claims for same vehicle
                if claim_count >= 3:
                    signals.append(FraudSignal(
                        signal_type="VIN_EXCESSIVE_CLAIMS",
                        severity=Severity.HIGH,
                        description=f"Vehicle has {claim_count + 1} total claims (including this one), "
                                   f"total claimed: ${total_claimed:,.2f}",
                        evidence={
                            "vin": vin,
                            "prior_claim_count": claim_count,
                            "total_claims": claim_count + 1,
                            "total_amount_claimed": total_claimed,
                            "first_claim_date": row["first_claim"],
                            "last_claim_date": row["last_claim"]
                        }
                    ))
                elif claim_count >= 2:
                    signals.append(FraudSignal(
                        signal_type="VIN_MULTIPLE_CLAIMS",
                        severity=Severity.MEDIUM,
                        description=f"Vehicle has {claim_count + 1} total claims",
                        evidence={
                            "vin": vin,
                            "total_claims": claim_count + 1
                        }
                    ))
        finally:
            release_connection(conn)
        
        return signals


def detect_fraud_signals(
    claim_id: str,
    parts_cost: Optional[float] = None,
    labor_cost: Optional[float] = None,
    tax: Optional[float] = None,
    total_amount: Optional[float] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    issue_description: Optional[str] = None,
    claim_date: Optional[str] = None,
    decision_date: Optional[str] = None,
    status: Optional[str] = None,
    dealer_id: Optional[str] = None
) -> Tuple[List[FraudSignal], List[str]]:
    """Convenience function for fraud signal detection."""
    detector = WarrantyFraudSignalDetector()
    return detector.detect_signals(
        claim_id=claim_id,
        parts_cost=parts_cost,
        labor_cost=labor_cost,
        tax=tax,
        total_amount=total_amount,
        brand=brand,
        model=model,
        year=year,
        issue_description=issue_description,
        claim_date=claim_date,
        decision_date=decision_date,
        status=status,
        dealer_id=dealer_id
    )
