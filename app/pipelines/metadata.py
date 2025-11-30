# app/pipelines/metadata.py

from typing import Dict, Any
import os
import datetime

import fitz  # PyMuPDF
from PIL import Image


def _fs_metadata(path: str) -> Dict[str, Any]:
    """Basic filesystem metadata for any file."""
    stat = os.stat(path)
    return {
        "fs_created_at": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "fs_modified_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "file_size_bytes": stat.st_size,
    }


def extract_pdf_metadata(path: str) -> Dict[str, Any]:
    """
    Extracts PDF-level metadata (producer, creator, dates, etc.)
    using PyMuPDF.
    """
    meta: Dict[str, Any] = {}
    with fitz.open(path) as doc:
        meta_raw = doc.metadata or {}
        meta["source_type"] = "pdf"
        meta["producer"] = meta_raw.get("producer")
        meta["creator"] = meta_raw.get("creator")
        meta["creation_date"] = meta_raw.get("creationDate")
        meta["mod_date"] = meta_raw.get("modDate")
        meta["title"] = meta_raw.get("title")
        meta["author"] = meta_raw.get("author")
        meta["pages"] = doc.page_count

    meta.update(_fs_metadata(path))
    return meta


def extract_image_metadata(path: str) -> Dict[str, Any]:
    """
    Extracts basic image metadata + filesystem metadata.
    """
    meta: Dict[str, Any] = {}
    meta["source_type"] = "image"
    with Image.open(path) as img:
        meta["format"] = img.format
        meta["mode"] = img.mode
        meta["size"] = img.size  # (width, height)

        exif = img.getexif()
        if exif:
            # We'll decode specific EXIF fields later; for now just keep keys count
            meta["exif_present"] = True
            meta["exif_keys_count"] = len(exif.keys())
        else:
            meta["exif_present"] = False
            meta["exif_keys_count"] = 0

    meta.update(_fs_metadata(path))
    return meta