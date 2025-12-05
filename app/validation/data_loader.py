"""
Optimized Database Loader
Lazy loading with caching for fast lookups
"""

import json
from pathlib import Path
from typing import Dict, Optional, List
from functools import lru_cache
import time


class DatabaseLoader:
    """
    Lazy-loading database with caching.
    Only loads data when needed.
    Memory efficient for large datasets.
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent / "data"
        
        self._pin_cache = None
        self._merchant_cache = {}
        self._stats = {
            "pin_lookups": 0,
            "merchant_lookups": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    @property
    def pin_codes(self) -> Dict:
        """Lazy load PIN codes on first access."""
        if self._pin_cache is None:
            self._load_pin_codes()
        return self._pin_cache
    
    def _load_pin_codes(self):
        """Load all PIN codes into memory."""
        start = time.time()
        self._pin_cache = {}
        pin_dir = self.data_dir / "pin_codes"
        
        if not pin_dir.exists():
            print(f"Warning: PIN codes directory not found: {pin_dir}")
            return
        
        # Load all state files
        state_files = list(pin_dir.glob("*.json"))
        
        for state_file in state_files:
            if state_file.name == "metadata.json":
                continue
            
            try:
                with open(state_file, encoding='utf-8') as f:
                    state_data = json.load(f)
                    if "pins" in state_data:
                        self._pin_cache.update(state_data["pins"])
            except Exception as e:
                print(f"Warning: Error loading {state_file.name}: {e}")
        
        elapsed = time.time() - start
        print(f"Loaded {len(self._pin_cache)} PIN codes from {len(state_files)} states in {elapsed:.2f}s")
    
    def get_merchant_category(self, category: str) -> Dict:
        """Lazy load merchant category on first access."""
        if category not in self._merchant_cache:
            self._load_merchant_category(category)
        return self._merchant_cache.get(category, {"merchants": {}})
    
    def _load_merchant_category(self, category: str):
        """Load a specific merchant category."""
        merchant_file = self.data_dir / "merchants" / f"{category}.json"
        
        if merchant_file.exists():
            try:
                with open(merchant_file, encoding='utf-8') as f:
                    self._merchant_cache[category] = json.load(f)
            except Exception as e:
                print(f"Warning: Error loading {category}: {e}")
                self._merchant_cache[category] = {"merchants": {}}
        else:
            self._merchant_cache[category] = {"merchants": {}}
    
    @lru_cache(maxsize=2000)
    def lookup_pin(self, pin_code: str) -> Optional[Dict]:
        """Fast cached PIN lookup."""
        self._stats["pin_lookups"] += 1
        result = self.pin_codes.get(pin_code)
        
        if result:
            self._stats["cache_hits"] += 1
        else:
            self._stats["cache_misses"] += 1
        
        return result
    
    @lru_cache(maxsize=1000)
    def lookup_merchant(self, merchant_key: str, category: str) -> Optional[Dict]:
        """Fast cached merchant lookup."""
        self._stats["merchant_lookups"] += 1
        category_data = self.get_merchant_category(category)
        result = category_data.get("merchants", {}).get(merchant_key)
        
        if result:
            self._stats["cache_hits"] += 1
        else:
            self._stats["cache_misses"] += 1
        
        return result
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        return {
            **self._stats,
            "total_pins": len(self._pin_cache) if self._pin_cache else 0,
            "loaded_categories": len(self._merchant_cache),
            "cache_hit_rate": self._stats["cache_hits"] / max(1, self._stats["cache_hits"] + self._stats["cache_misses"])
        }


# Global singleton instance
_db_loader = None

def get_database() -> DatabaseLoader:
    """Get global database instance (singleton pattern)."""
    global _db_loader
    if _db_loader is None:
        _db_loader = DatabaseLoader()
    return _db_loader


# Convenience functions
def lookup_pin_code(pin: str) -> Optional[Dict]:
    """Quick PIN code lookup."""
    return get_database().lookup_pin(pin)


def lookup_merchant_by_key(merchant_key: str, category: str) -> Optional[Dict]:
    """Quick merchant lookup."""
    return get_database().lookup_merchant(merchant_key, category)
