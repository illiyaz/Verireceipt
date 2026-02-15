# Warranty Claim Duplicate Detection

## Overview

The warranty claims system includes intelligent duplicate detection to identify:
1. **Exact image duplicates** - Same image submitted across multiple claims
2. **Similar images** - Perceptually similar images (using pHash)
3. **Claim-level duplicates** - Same VIN + similar issue + close dates

## Dynamic Template Filtering

### Problem
Warranty claim forms contain standard template elements (logos, headers, footers) that appear in every claim. Without filtering, these cause false positive duplicate alerts.

### Solution: Multi-Signal Template Detection

Instead of hardcoding known template hashes (which doesn't scale), we use **dynamic detection** based on image characteristics:

| Check | Threshold | Catches |
|-------|-----------|---------|
| **Aspect Ratio** | > 5:1 or < 1:5 | Horizontal/vertical banners |
| **Short Height** | < 200px + wide aspect | Header strips |
| **Narrow Width** | < 200px + tall aspect | Sidebar elements |
| **File Size** | < 5KB | Icons, tiny logos |
| **Frequency** | ≥ 3 claims | Any repeated template |

### Configuration

Thresholds are defined in `app/warranty/duplicates.py`:

```python
class DuplicateDetector:
    # Dynamic template detection thresholds
    MIN_IMAGE_SIZE_BYTES = 5_000      # 5KB minimum
    MAX_ASPECT_RATIO = 5.0            # Width/height > 5 = banner
    MIN_ASPECT_RATIO = 0.2            # Width/height < 0.2 = vertical
    MIN_HEIGHT_PX = 200               # Short images likely decorative
    MIN_WIDTH_PX = 200                # Narrow images likely decorative
    TEMPLATE_FREQUENCY_THRESHOLD = 3  # 3+ claims = template
```

### Why This Works

1. **Banners/Headers**: Typically have extreme aspect ratios (e.g., 2480x265 = 9.36:1)
2. **Logos/Icons**: Small file sizes and dimensions
3. **Form Elements**: Appear across many claims (frequency detection)
4. **Damage Photos**: Have normal aspect ratios (4:3, 3:2, 1:1) and larger dimensions

### Examples

| Image | Dimensions | Aspect Ratio | Filtered? | Reason |
|-------|------------|--------------|-----------|--------|
| Header banner | 2480x265 | 9.36:1 | ✅ Yes | Aspect ratio > 5:1 |
| Form logo | 277x147 | 1.88:1 | ✅ Yes | Appears in 5+ claims |
| Small icon | 32x32 | 1:1 | ✅ Yes | Size < 5KB |
| Damage photo | 1116x928 | 1.2:1 | ❌ No | Normal photo |
| Car photo | 916x958 | 0.96:1 | ❌ No | Normal photo |

## Duplicate Detection Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Image Extraction                         │
│              (from PDF via embedded or render)              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Dynamic Template Detection                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Aspect Ratio│ │ Dimensions  │ │  Frequency  │           │
│  │   Check     │ │   Check     │ │   Check     │           │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘           │
│         │               │               │                   │
│         └───────────────┼───────────────┘                   │
│                         ▼                                   │
│              Is Template? ──Yes──► SKIP                     │
│                   │                                         │
│                   No                                        │
│                   ▼                                         │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                 Duplicate Detection                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Exact Hash  │ │   pHash     │ │ VIN+Issue   │           │
│  │   Match     │ │ Similarity  │ │   Match     │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

## Testing

Run the golden tests:

```bash
pytest tests/test_warranty_duplicate_detection.py -v
```

The tests cover:
- Banner/header detection (aspect ratio)
- Icon/logo detection (size)
- Valid photo preservation (no false negatives)
- Edge cases (missing dimensions, borderline ratios)
- Known golden cases from actual warranty forms

## Database Schema

### warranty_claim_images
Stores image fingerprints for duplicate detection:
- `phash` - Perceptual hash (64-bit)
- `dhash` - Difference hash
- `file_hash` - MD5 of raw bytes
- `width`, `height` - Dimensions for aspect ratio filtering

### warranty_duplicate_matches
Records detected duplicates:
- `match_type` - IMAGE_EXACT, IMAGE_SIMILAR, IMAGE_LIKELY_SAME, VIN_ISSUE_DUPLICATE
- `similarity_score` - 0.0 to 1.0
- `image_index_1`, `image_index_2` - Which images matched

## API Endpoints

- `POST /warranty/analyze` - Analyze a warranty claim PDF
- `GET /warranty/stats` - Get statistics including duplicate counts
- `GET /warranty/{claim_id}` - Get claim details including duplicates found

## Troubleshooting

### False Positives (Template flagged as duplicate)
1. Check the image dimensions in logs
2. Verify aspect ratio calculation
3. May need to adjust `MAX_ASPECT_RATIO` threshold

### False Negatives (Actual duplicate not detected)
1. Check if pHash distance threshold is too high
2. Verify images are being extracted correctly
3. Check `IMAGE_SIMILAR_THRESHOLD` (default: 10)

### Logs
Enable debug logging to see template detection decisions:
```python
import logging
logging.getLogger("warranty.duplicates").setLevel(logging.DEBUG)
```
