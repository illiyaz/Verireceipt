"""
Language pack system for VeriReceipt.

Provides multilingual keyword, label, and pattern support
without hardcoding language-specific terms in the pipeline.
"""

from .loader import LangPackLoader
from .router import LangPackRouter
from .schema import LangPack, KeywordGroup, LabelGroup, CompanyInfo, AddressInfo, CurrencyInfo
from .detect_script import ScriptDetector
from .normalizer import TextNormalizer

__all__ = [
    "LangPackLoader",
    "LangPackRouter", 
    "LangPack",
    "KeywordGroup",
    "LabelGroup",
    "CompanyInfo",
    "AddressInfo",
    "CurrencyInfo",
    "ScriptDetector",
    "TextNormalizer",
]
