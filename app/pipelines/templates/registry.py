"""
Template Registry

Manages collection of receipt templates from multiple sources:
- SROIE dataset (auto-generated)
- Custom user templates (YAML config)
- Learned templates (from processing)

Provides caching and lazy loading for performance.
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union
from functools import lru_cache

from .fingerprint import TemplateFingerprint

logger = logging.getLogger(__name__)

# Default paths
TEMPLATES_DIR = Path(__file__).parent.parent.parent.parent / "resources" / "templates"
BUILTIN_TEMPLATES_DIR = TEMPLATES_DIR / "builtin"
SROIE_TEMPLATES_DIR = TEMPLATES_DIR / "sroie"
CUSTOM_TEMPLATES_DIR = TEMPLATES_DIR / "custom"


class TemplateRegistry:
    """
    Central registry for receipt templates.
    
    Manages loading, caching, and querying of templates from:
    - SROIE dataset templates
    - Custom YAML templates
    - Runtime-learned templates
    """
    
    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        sroie_dir: Optional[Path] = None,
        custom_dir: Optional[Path] = None,
        auto_load: bool = True
    ):
        """
        Initialize template registry.
        
        Args:
            builtin_dir: Directory containing built-in templates
            sroie_dir: Directory containing SROIE templates
            custom_dir: Directory containing custom YAML templates
            auto_load: Whether to load templates on init
        """
        self.builtin_dir = Path(builtin_dir) if builtin_dir else BUILTIN_TEMPLATES_DIR
        self.sroie_dir = Path(sroie_dir) if sroie_dir else SROIE_TEMPLATES_DIR
        self.custom_dir = Path(custom_dir) if custom_dir else CUSTOM_TEMPLATES_DIR
        
        self._templates: Dict[str, TemplateFingerprint] = {}
        self._loaded = False
        
        if auto_load:
            self.load_all()
    
    def load_all(self) -> int:
        """
        Load all templates from configured directories.
        
        Returns:
            Number of templates loaded
        """
        count = 0
        
        # Load built-in templates first (always available)
        count += self._load_builtin_templates()
        
        # Load SROIE templates (if downloaded)
        count += self._load_sroie_templates()
        
        # Load custom templates (user-defined, highest priority)
        count += self._load_custom_templates()
        
        self._loaded = True
        logger.info(f"Loaded {count} templates ({len(self._templates)} unique)")
        
        return count
    
    def _load_builtin_templates(self) -> int:
        """Load built-in templates from builtin directory."""
        if not self.builtin_dir.exists():
            logger.debug(f"Built-in templates dir not found: {self.builtin_dir}")
            return 0
        
        count = 0
        index_file = self.builtin_dir / "index.json"
        
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
                for template_data in index.get("templates", []):
                    fp = TemplateFingerprint.from_dict(template_data)
                    self._templates[fp.template_id] = fp
                    count += 1
                logger.info(f"Loaded {count} built-in templates")
            except Exception as e:
                logger.warning(f"Failed to load built-in index: {e}")
        
        return count
    
    def _load_sroie_templates(self) -> int:
        """Load templates from SROIE directory."""
        if not self.sroie_dir.exists():
            logger.debug(f"SROIE templates dir not found: {self.sroie_dir}")
            return 0
        
        count = 0
        index_file = self.sroie_dir / "index.json"
        
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
                for template_data in index.get("templates", []):
                    fp = TemplateFingerprint.from_dict(template_data)
                    self._templates[fp.template_id] = fp
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to load SROIE index: {e}")
        
        return count
    
    def _load_custom_templates(self) -> int:
        """Load templates from custom YAML files."""
        if not self.custom_dir.exists():
            logger.debug(f"Custom templates dir not found: {self.custom_dir}")
            return 0
        
        count = 0
        for yaml_file in self.custom_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                
                if not data:
                    continue
                
                # Handle single template or list of templates
                templates = data if isinstance(data, list) else [data]
                
                for template_data in templates:
                    if "template_id" not in template_data:
                        template_data["template_id"] = yaml_file.stem
                    template_data["source"] = "custom"
                    
                    fp = TemplateFingerprint.from_dict(template_data)
                    self._templates[fp.template_id] = fp
                    count += 1
                    logger.debug(f"Loaded custom template: {fp.template_id}")
                    
            except Exception as e:
                logger.warning(f"Failed to load custom template {yaml_file}: {e}")
        
        return count
    
    def get_all(self) -> List[TemplateFingerprint]:
        """Get all loaded templates."""
        if not self._loaded:
            self.load_all()
        return list(self._templates.values())
    
    def get_by_id(self, template_id: str) -> Optional[TemplateFingerprint]:
        """Get template by ID."""
        if not self._loaded:
            self.load_all()
        return self._templates.get(template_id)
    
    def get_by_source(self, source: str) -> List[TemplateFingerprint]:
        """Get all templates from a specific source."""
        if not self._loaded:
            self.load_all()
        return [t for t in self._templates.values() if t.source == source]
    
    def add_template(self, template: TemplateFingerprint) -> None:
        """Add a template to the registry (runtime only)."""
        self._templates[template.template_id] = template
    
    def save_custom_template(
        self,
        template: TemplateFingerprint,
        filename: Optional[str] = None
    ) -> Path:
        """
        Save a template to custom templates directory.
        
        Args:
            template: Template to save
            filename: Optional filename (without extension)
        
        Returns:
            Path to saved file
        """
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        
        if not filename:
            filename = template.template_id
        
        filepath = self.custom_dir / f"{filename}.yaml"
        
        with open(filepath, 'w') as f:
            yaml.dump(template.to_dict(), f, default_flow_style=False)
        
        logger.info(f"Saved custom template to: {filepath}")
        return filepath
    
    def count(self) -> int:
        """Get total number of templates."""
        if not self._loaded:
            self.load_all()
        return len(self._templates)
    
    def clear(self) -> None:
        """Clear all loaded templates."""
        self._templates.clear()
        self._loaded = False


# Global registry instance
_registry: Optional[TemplateRegistry] = None


def get_registry() -> TemplateRegistry:
    """Get the global template registry (lazy loaded)."""
    global _registry
    if _registry is None:
        _registry = TemplateRegistry(auto_load=True)
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
