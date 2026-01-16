"""
Language pack loader with validation and caching.

Loads YAML language packs, validates them against schema, and provides
runtime access to language-specific keywords and patterns.
"""

import os
try:
    import yaml
except ModuleNotFoundError as e:
    yaml = None  # type: ignore
    _yaml_import_error = e
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging
from dataclasses import dataclass

from .schema import LangPack, KeywordGroup, LabelGroup, CompanyInfo, AddressInfo, CurrencyInfo


logger = logging.getLogger(__name__)


@dataclass
class LoadedPack:
    """Container for a loaded language pack with metadata."""
    pack: LangPack
    source_file: str
    is_common: bool
    compiled_patterns: Dict[str, 're.Pattern'] = None
    
    def __post_init__(self):
        """Compile regex patterns after loading."""
        if self.compiled_patterns is None:
            self.compiled_patterns = {}
            # Compile postal code patterns
            for pattern in self.pack.address.postal_code_patterns:
                try:
                    import re
                    self.compiled_patterns[f'postal_{pattern}'] = re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    logger.warning(f"Failed to compile postal pattern '{pattern}': {e}")


class LangPackLoader:
    """Loads and manages language packs with validation."""
    
    def __init__(self, langpack_dir: Optional[str] = None, strict: bool = True):
        """
        Initialize language pack loader.
        
        Args:
            langpack_dir: Directory containing language pack YAML files
            strict: Whether to enforce strict validation
        """
        self.langpack_dir = Path(langpack_dir or os.getenv('LANGPACK_DIR', 'resources/langpacks'))
        self.strict = strict
        self._packs: Dict[str, LoadedPack] = {}
        self._merged_packs: Dict[str, LangPack] = {}
        self._loaded = False
    
    def load_all(self) -> None:
        """Load all language packs from the directory."""
        if self._loaded:
            return

        if yaml is None:
            raise ModuleNotFoundError(
                "Missing dependency 'PyYAML'. Install it (e.g. `pip install PyYAML`) to use language packs."
            ) from _yaml_import_error
        
        if not self.langpack_dir.exists():
            raise FileNotFoundError(f"Language pack directory not found: {self.langpack_dir}")
        
        # Load common.yaml first (base pack)
        common_file = self.langpack_dir / 'common.yaml'
        if common_file.exists():
            self._load_single_pack(common_file, is_common=True)
        else:
            logger.warning(f"Common pack not found: {common_file}")
        
        # Load all other YAML files
        # Skip documentation / helper files like _schema.yaml
        for yaml_file in self.langpack_dir.glob('*.yaml'):
            if yaml_file.name == 'common.yaml':
                continue
            if yaml_file.name.startswith('_'):
                continue
            self._load_single_pack(yaml_file, is_common=False)
        
        # Create merged packs
        self._create_merged_packs()
        
        self._loaded = True
        logger.info(f"Loaded {len(self._packs)} language packs")
    
    def _load_single_pack(self, yaml_file: Path, is_common: bool) -> None:
        """Load a single YAML language pack."""
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not isinstance(data, dict):
                raise ValueError(f"Expected a YAML mapping/object at top-level, got {type(data).__name__}")
            
            # Validate against schema
            pack = LangPack(**data)
            
            # Store loaded pack
            loaded = LoadedPack(
                pack=pack,
                source_file=str(yaml_file),
                is_common=is_common
            )
            
            self._packs[pack.id] = loaded
            logger.debug(f"Loaded language pack: {pack.id} v{pack.version} from {yaml_file}")
            
        except yaml.YAMLError as e:
            error_msg = f"Invalid YAML in {yaml_file}: {e}"
            if self.strict:
                raise ValueError(error_msg)
            else:
                logger.error(error_msg)
        except Exception as e:
            error_msg = f"Failed to load pack {yaml_file}: {e}"
            if self.strict:
                raise ValueError(error_msg)
            else:
                logger.error(error_msg)
    
    def _create_merged_packs(self) -> None:
        """Create merged packs (common + language-specific)."""
        common_pack = self._packs.get('common')
        
        for pack_id, loaded in self._packs.items():
            if pack_id == 'common':
                continue
            
            # Start with common pack if available
            if common_pack:
                merged = self._merge_packs(common_pack.pack, loaded.pack)
            else:
                merged = loaded.pack
            
            self._merged_packs[pack_id] = merged
    
    def _merge_packs(self, base: LangPack, override: LangPack) -> LangPack:
        """Merge two language packs with override taking precedence."""
        # Merge keyword groups
        merged_keywords = KeywordGroup(
            doc_titles=base.keywords.doc_titles + override.keywords.doc_titles,
            invoice=base.keywords.invoice + override.keywords.invoice,
            receipt=base.keywords.receipt + override.keywords.receipt,
            tax_invoice=base.keywords.tax_invoice + override.keywords.tax_invoice,
            ecommerce=base.keywords.ecommerce + override.keywords.ecommerce,
            fuel=base.keywords.fuel + override.keywords.fuel,
            parking=base.keywords.parking + override.keywords.parking,
            hotel_folio=base.keywords.hotel_folio + override.keywords.hotel_folio,
            utility=base.keywords.utility + override.keywords.utility,
            telecom=base.keywords.telecom + override.keywords.telecom,
            commercial_invoice=base.keywords.commercial_invoice + override.keywords.commercial_invoice,
            air_waybill=base.keywords.air_waybill + override.keywords.air_waybill,
            shipping_bill=base.keywords.shipping_bill + override.keywords.shipping_bill,
            bill_of_lading=base.keywords.bill_of_lading + override.keywords.bill_of_lading,
            total=base.keywords.total + override.keywords.total,
            subtotal=base.keywords.subtotal + override.keywords.subtotal,
            tax=base.keywords.tax + override.keywords.tax,
            date=base.keywords.date + override.keywords.date,
            amount=base.keywords.amount + override.keywords.amount,
            logistics=base.keywords.logistics + override.keywords.logistics,
        )
        
        # Merge label groups
        merged_labels = LabelGroup(
            structural=base.labels.structural + override.labels.structural,
            next_line_preference=base.labels.next_line_preference + override.labels.next_line_preference,
        )
        
        # Merge company info
        merged_company = CompanyInfo(
            suffixes=base.company.suffixes + override.company.suffixes,
            prefixes=base.company.prefixes + override.company.prefixes,
        )
        
        # Merge address info
        merged_address = AddressInfo(
            keywords=base.address.keywords + override.address.keywords,
            postal_code_patterns=base.address.postal_code_patterns + override.address.postal_code_patterns,
        )
        
        # Merge currency info
        merged_currency = CurrencyInfo(
            symbols=base.currency.symbols + override.currency.symbols,
            codes=base.currency.codes + override.currency.codes,
        )
        
        # Override metadata with language-specific pack
        return LangPack(
            id=override.id,
            version=override.version,
            name=override.name,
            scripts=override.scripts,
            locales=override.locales,
            keywords=merged_keywords,
            labels=merged_labels,
            company=merged_company,
            address=merged_address,
            currency=merged_currency,
            extensions={**base.extensions, **override.extensions} if base.extensions or override.extensions else {},
        )
    
    def get_pack(self, pack_id: str) -> Optional[LangPack]:
        """
        Get a merged language pack by ID.
        
        Args:
            pack_id: Language pack ID (e.g., 'en', 'ar', 'zh')
            
        Returns:
            Merged language pack or None if not found
        """
        if not self._loaded:
            self.load_all()
        
        return self._merged_packs.get(pack_id)
    
    def get_available_packs(self) -> List[str]:
        """Get list of available language pack IDs."""
        if not self._loaded:
            self.load_all()
        
        return [pack_id for pack_id in self._merged_packs.keys() if pack_id != 'common']
    
    def get_packs_by_script(self, script: str) -> List[str]:
        """Get language pack IDs that support a specific script."""
        if not self._loaded:
            self.load_all()
        
        matching_packs = []
        for pack_id, pack in self._merged_packs.items():
            if script in pack.scripts:
                matching_packs.append(pack_id)
        
        return matching_packs
    
    def get_pack_by_locale(self, locale: str) -> Optional[LangPack]:
        """
        Get language pack by locale code.
        
        Args:
            locale: Locale code (e.g., 'en-US', 'ar-SA')
            
        Returns:
            Language pack or None if not found
        """
        if not self._loaded:
            self.load_all()
        
        # Try exact locale match first
        for pack_id, pack in self._merged_packs.items():
            if pack.locales and locale in pack.locales:
                return pack
        
        # Try language-only match
        lang = locale.split('-')[0]
        return self._merged_packs.get(lang)
    
    def get_fallback_pack(self) -> LangPack:
        """Get fallback language pack (usually English)."""
        if not self._loaded:
            self.load_all()
        
        # Try English first
        en_pack = self._merged_packs.get('en')
        if en_pack:
            return en_pack
        
        # Fall back to first available pack
        if self._merged_packs:
            return next(iter(self._merged_packs.values()))
        
        raise ValueError("No language packs available")
    
    def validate_all_packs(self) -> Dict[str, List[str]]:
        """
        Validate all loaded packs.
        
        Returns:
            Dictionary mapping pack IDs to list of validation errors
        """
        if not self._loaded:
            self.load_all()
        
        errors = {}
        
        for pack_id, pack in self._merged_packs.items():
            pack_errors = []
            
            # Check for essential keywords
            if not pack.keywords.invoice:
                pack_errors.append("Missing invoice keywords")
            if not pack.keywords.receipt:
                pack_errors.append("Missing receipt keywords")
            if not pack.keywords.total:
                pack_errors.append("Missing total keywords")
            
            # Check for valid scripts
            if not pack.scripts:
                pack_errors.append("No scripts specified")
            
            # Check version format
            if not pack.version or not pack.version.count('.') == 2:
                pack_errors.append("Invalid version format")
            
            if pack_errors:
                errors[pack_id] = pack_errors
        
        return errors
    
    def reload(self) -> None:
        """Reload all language packs from disk."""
        self._packs.clear()
        self._merged_packs.clear()
        self._loaded = False
        self.load_all()
        logger.info("Language packs reloaded")
