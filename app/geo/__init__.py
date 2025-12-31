"""
Geo enrichment module for VeriReceipt.
Provides location detection and validation using postal patterns, cities, and terms.
"""

from .infer import infer_geo

__all__ = ["infer_geo"]
