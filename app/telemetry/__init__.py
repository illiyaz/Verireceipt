"""
Telemetry and Metrics Package

Lightweight observability for VeriReceipt features.
"""

from .address_metrics import (
    AddressMetrics,
    get_global_metrics,
    reset_global_metrics,
    record_address_features,
)

__all__ = [
    "AddressMetrics",
    "get_global_metrics",
    "reset_global_metrics",
    "record_address_features",
]
