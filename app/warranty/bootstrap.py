"""
Bootstrap warranty claims database with schema and seed data.
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime


def get_warranty_db_path() -> str:
    """Get path to warranty database."""
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "warranty.sqlite")


def bootstrap_warranty_db(db_path: str = None) -> str:
    """
    Create warranty database with all required tables.
    
    Returns the path to the created database.
    """
    if db_path is None:
        db_path = get_warranty_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # =========================================================================
    # Main claims table
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_claims (
            id TEXT PRIMARY KEY,
            customer_name TEXT,
            dealer_id TEXT,
            dealer_name TEXT,
            
            -- Vehicle info
            vin TEXT,
            brand TEXT,
            model TEXT,
            year INTEGER,
            odometer INTEGER,
            
            -- Claim details
            issue_description TEXT,
            claim_date TEXT,
            decision_date TEXT,
            
            -- Amounts
            parts_cost REAL,
            labor_cost REAL,
            tax REAL,
            total_amount REAL,
            
            -- Status
            status TEXT,
            rejection_reason TEXT,
            
            -- Our analysis results
            risk_score REAL,
            triage_class TEXT,
            fraud_signals TEXT,
            warnings TEXT,
            is_suspicious INTEGER DEFAULT 0,
            
            -- Metadata
            pdf_path TEXT,
            raw_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_vin ON warranty_claims(vin)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_dealer ON warranty_claims(dealer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_brand ON warranty_claims(brand)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON warranty_claims(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_date ON warranty_claims(claim_date)")
    
    # =========================================================================
    # Image fingerprints for duplicate detection
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_claim_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            image_index INTEGER,
            
            -- Hashes for duplicate detection
            phash TEXT NOT NULL,
            dhash TEXT,
            file_hash TEXT,
            
            -- EXIF metadata
            exif_timestamp TEXT,
            exif_gps_lat REAL,
            exif_gps_lon REAL,
            exif_device TEXT,
            exif_software TEXT,
            
            -- Dimensions
            width INTEGER,
            height INTEGER,
            
            -- Extraction method
            extraction_method TEXT,
            page_number INTEGER,
            bbox TEXT,
            
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (claim_id) REFERENCES warranty_claims(id)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_phash ON warranty_claim_images(phash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_dhash ON warranty_claim_images(dhash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_claim ON warranty_claim_images(claim_id)")
    
    # =========================================================================
    # Duplicate matches found
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_duplicate_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id_1 TEXT NOT NULL,
            claim_id_2 TEXT NOT NULL,
            match_type TEXT,
            similarity_score REAL,
            image_index_1 INTEGER,
            image_index_2 INTEGER,
            details TEXT,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (claim_id_1) REFERENCES warranty_claims(id),
            FOREIGN KEY (claim_id_2) REFERENCES warranty_claims(id)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dup_claim1 ON warranty_duplicate_matches(claim_id_1)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dup_claim2 ON warranty_duplicate_matches(claim_id_2)")
    
    # =========================================================================
    # Feedback for model improvement
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL,
            adjuster_id TEXT,
            verdict TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (claim_id) REFERENCES warranty_claims(id)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_claim ON warranty_feedback(claim_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON warranty_feedback(verdict)")
    
    # =========================================================================
    # Historical benchmarks per brand/model/issue type
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT,
            model TEXT,
            issue_type TEXT,
            
            avg_parts_cost REAL,
            avg_labor_cost REAL,
            avg_total REAL,
            std_parts_cost REAL,
            std_labor_cost REAL,
            std_total REAL,
            
            min_total REAL,
            max_total REAL,
            
            avg_labor_parts_ratio REAL,
            avg_tax_rate REAL,
            
            sample_count INTEGER,
            last_updated TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bench_brand ON warranty_benchmarks(brand)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bench_issue ON warranty_benchmarks(issue_type)")
    
    # =========================================================================
    # Dealer statistics for anomaly detection
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dealer_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dealer_id TEXT NOT NULL UNIQUE,
            dealer_name TEXT,
            
            total_claims INTEGER DEFAULT 0,
            approved_claims INTEGER DEFAULT 0,
            rejected_claims INTEGER DEFAULT 0,
            fraud_confirmed INTEGER DEFAULT 0,
            
            avg_claim_amount REAL,
            avg_parts_cost REAL,
            avg_labor_cost REAL,
            
            duplicate_count INTEGER DEFAULT 0,
            suspicious_count INTEGER DEFAULT 0,
            
            first_claim_date TEXT,
            last_claim_date TEXT,
            last_updated TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dealer_id ON dealer_statistics(dealer_id)")
    
    # =========================================================================
    # Seed benchmark data
    # =========================================================================
    benchmark_data = _get_seed_benchmarks()
    cursor.executemany("""
        INSERT OR REPLACE INTO warranty_benchmarks 
        (brand, model, issue_type, avg_parts_cost, avg_labor_cost, avg_total,
         std_parts_cost, std_labor_cost, std_total, min_total, max_total,
         avg_labor_parts_ratio, avg_tax_rate, sample_count, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, benchmark_data)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Warranty database bootstrapped: {db_path}")
    print(f"   - warranty_claims table")
    print(f"   - warranty_claim_images table")
    print(f"   - warranty_duplicate_matches table")
    print(f"   - warranty_feedback table")
    print(f"   - warranty_benchmarks table ({len(benchmark_data)} seed records)")
    print(f"   - dealer_statistics table")
    
    return db_path


def _get_seed_benchmarks():
    """
    Seed benchmark data for common brands and issue types.
    Based on typical warranty claim patterns.
    """
    now = datetime.now().isoformat()
    
    return [
        # Honda
        ("Honda", None, "Fuel pump issue", 800, 400, 1300, 200, 100, 350, 500, 2500, 0.5, 0.08, 100, now),
        ("Honda", None, "Battery drainage", 150, 80, 250, 50, 30, 80, 100, 500, 0.53, 0.08, 150, now),
        ("Honda", None, "Transmission fluid leak", 600, 500, 1200, 150, 120, 300, 400, 2500, 0.83, 0.08, 80, now),
        ("Honda", None, "Oil leak", 200, 150, 400, 80, 60, 150, 150, 800, 0.75, 0.08, 200, now),
        ("Honda", None, "Power steering failure", 700, 600, 1400, 200, 150, 400, 500, 3000, 0.86, 0.08, 60, now),
        ("Honda", None, "Alternator malfunction", 400, 250, 700, 100, 80, 200, 300, 1500, 0.63, 0.08, 90, now),
        
        # Toyota
        ("Toyota", None, "Fuel pump issue", 750, 380, 1230, 180, 90, 320, 450, 2400, 0.51, 0.08, 120, now),
        ("Toyota", None, "Battery drainage", 140, 75, 235, 45, 28, 75, 90, 480, 0.54, 0.08, 180, now),
        ("Toyota", None, "Transmission fluid leak", 580, 480, 1160, 140, 110, 280, 380, 2400, 0.83, 0.08, 75, now),
        ("Toyota", None, "Oil leak", 190, 140, 380, 75, 55, 140, 140, 780, 0.74, 0.08, 220, now),
        ("Toyota", None, "Power steering failure", 680, 580, 1360, 190, 140, 380, 480, 2900, 0.85, 0.08, 55, now),
        ("Toyota", None, "Alternator malfunction", 380, 240, 680, 95, 75, 190, 280, 1450, 0.63, 0.08, 85, now),
        
        # Chevrolet
        ("Chevrolet", None, "Fuel pump issue", 850, 420, 1380, 220, 110, 380, 520, 2700, 0.49, 0.07, 90, now),
        ("Chevrolet", None, "Battery drainage", 160, 85, 270, 55, 32, 90, 110, 550, 0.53, 0.07, 140, now),
        ("Chevrolet", None, "Transmission fluid leak", 650, 520, 1280, 160, 130, 320, 420, 2700, 0.80, 0.07, 70, now),
        ("Chevrolet", None, "Oil leak", 220, 160, 420, 85, 65, 160, 160, 850, 0.73, 0.07, 190, now),
        ("Chevrolet", None, "Power steering failure", 750, 640, 1500, 220, 160, 420, 540, 3200, 0.85, 0.07, 50, now),
        ("Chevrolet", None, "Alternator malfunction", 420, 260, 740, 110, 85, 210, 320, 1580, 0.62, 0.07, 80, now),
        
        # Ford
        ("Ford", None, "Fuel pump issue", 820, 400, 1330, 210, 105, 360, 500, 2600, 0.49, 0.075, 95, now),
        ("Ford", None, "Battery drainage", 155, 82, 260, 52, 30, 85, 105, 530, 0.53, 0.075, 145, now),
        ("Ford", None, "Transmission fluid leak", 630, 510, 1250, 155, 125, 310, 410, 2600, 0.81, 0.075, 72, now),
        ("Ford", None, "Oil leak", 210, 155, 400, 82, 62, 155, 155, 820, 0.74, 0.075, 200, now),
        
        # Subaru
        ("Subaru", None, "Fuel pump issue", 780, 390, 1270, 195, 98, 340, 480, 2480, 0.50, 0.08, 85, now),
        ("Subaru", None, "Power steering failure", 720, 610, 1440, 205, 155, 410, 510, 3050, 0.85, 0.08, 52, now),
        ("Subaru", None, "Oil leak", 200, 148, 390, 78, 58, 148, 148, 800, 0.74, 0.08, 210, now),
        
        # Mazda
        ("Mazda", None, "Fuel pump issue", 760, 385, 1250, 190, 95, 335, 470, 2450, 0.51, 0.08, 88, now),
        ("Mazda", None, "Alternator malfunction", 390, 245, 695, 98, 78, 195, 295, 1480, 0.63, 0.08, 82, now),
        
        # Generic fallbacks (when brand not found)
        (None, None, "Fuel pump issue", 800, 400, 1300, 200, 100, 350, 450, 2600, 0.50, 0.08, 500, now),
        (None, None, "Battery drainage", 150, 80, 250, 50, 30, 85, 100, 520, 0.53, 0.08, 600, now),
        (None, None, "Transmission fluid leak", 620, 500, 1220, 155, 125, 310, 400, 2600, 0.81, 0.08, 400, now),
        (None, None, "Oil leak", 200, 150, 400, 80, 60, 150, 150, 820, 0.75, 0.08, 700, now),
        (None, None, "Power steering failure", 710, 600, 1420, 200, 150, 400, 500, 3000, 0.85, 0.08, 300, now),
        (None, None, "Alternator malfunction", 400, 250, 710, 100, 80, 200, 300, 1500, 0.63, 0.08, 450, now),
        (None, None, "Starter motor failure", 350, 280, 690, 90, 70, 180, 280, 1400, 0.80, 0.08, 350, now),
        (None, None, "AC compressor failure", 600, 400, 1100, 150, 100, 280, 400, 2200, 0.67, 0.08, 280, now),
        (None, None, "Radiator leak", 300, 250, 600, 80, 65, 160, 250, 1200, 0.83, 0.08, 320, now),
        (None, None, "Brake system issue", 400, 300, 770, 100, 80, 200, 300, 1600, 0.75, 0.08, 400, now),
    ]


def bootstrap_warranty_db_pg(conn) -> None:
    """
    Create warranty tables in PostgreSQL.
    Called automatically on first connection from db.py.
    
    Args:
        conn: Active psycopg2 connection
    """
    cursor = conn.cursor()

    # =========================================================================
    # Main claims table
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_claims (
            id TEXT PRIMARY KEY,
            customer_name TEXT,
            dealer_id TEXT,
            dealer_name TEXT,
            vin TEXT,
            brand TEXT,
            model TEXT,
            year INTEGER,
            odometer INTEGER,
            issue_description TEXT,
            claim_date TEXT,
            decision_date TEXT,
            parts_cost DOUBLE PRECISION,
            labor_cost DOUBLE PRECISION,
            tax DOUBLE PRECISION,
            total_amount DOUBLE PRECISION,
            status TEXT,
            rejection_reason TEXT,
            risk_score DOUBLE PRECISION,
            triage_class TEXT,
            fraud_signals TEXT,
            warnings TEXT,
            is_suspicious INTEGER DEFAULT 0,
            pdf_path TEXT,
            raw_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_vin ON warranty_claims(vin)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_dealer ON warranty_claims(dealer_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_brand ON warranty_claims(brand)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON warranty_claims(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_date ON warranty_claims(claim_date)")

    # =========================================================================
    # Image fingerprints for duplicate detection
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_claim_images (
            id SERIAL PRIMARY KEY,
            claim_id TEXT NOT NULL REFERENCES warranty_claims(id),
            image_index INTEGER,
            phash TEXT NOT NULL,
            dhash TEXT,
            file_hash TEXT,
            exif_timestamp TEXT,
            exif_gps_lat DOUBLE PRECISION,
            exif_gps_lon DOUBLE PRECISION,
            exif_device TEXT,
            exif_software TEXT,
            width INTEGER,
            height INTEGER,
            extraction_method TEXT,
            page_number INTEGER,
            bbox TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_phash ON warranty_claim_images(phash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_dhash ON warranty_claim_images(dhash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_claim ON warranty_claim_images(claim_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_file_hash ON warranty_claim_images(file_hash)")

    # =========================================================================
    # Duplicate matches found
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_duplicate_matches (
            id SERIAL PRIMARY KEY,
            claim_id_1 TEXT NOT NULL REFERENCES warranty_claims(id),
            claim_id_2 TEXT NOT NULL REFERENCES warranty_claims(id),
            match_type TEXT,
            similarity_score DOUBLE PRECISION,
            image_index_1 INTEGER,
            image_index_2 INTEGER,
            details TEXT,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dup_claim1 ON warranty_duplicate_matches(claim_id_1)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dup_claim2 ON warranty_duplicate_matches(claim_id_2)")

    # =========================================================================
    # Feedback for model improvement
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_feedback (
            id SERIAL PRIMARY KEY,
            claim_id TEXT NOT NULL REFERENCES warranty_claims(id),
            adjuster_id TEXT,
            verdict TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_claim ON warranty_feedback(claim_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_verdict ON warranty_feedback(verdict)")

    # =========================================================================
    # Historical benchmarks per brand/model/issue type
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warranty_benchmarks (
            id SERIAL PRIMARY KEY,
            brand TEXT,
            model TEXT,
            issue_type TEXT,
            avg_parts_cost DOUBLE PRECISION,
            avg_labor_cost DOUBLE PRECISION,
            avg_total DOUBLE PRECISION,
            std_parts_cost DOUBLE PRECISION,
            std_labor_cost DOUBLE PRECISION,
            std_total DOUBLE PRECISION,
            min_total DOUBLE PRECISION,
            max_total DOUBLE PRECISION,
            avg_labor_parts_ratio DOUBLE PRECISION,
            avg_tax_rate DOUBLE PRECISION,
            sample_count INTEGER,
            last_updated TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bench_brand ON warranty_benchmarks(brand)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bench_issue ON warranty_benchmarks(issue_type)")

    # =========================================================================
    # Dealer statistics for anomaly detection
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dealer_statistics (
            id SERIAL PRIMARY KEY,
            dealer_id TEXT NOT NULL UNIQUE,
            dealer_name TEXT,
            total_claims INTEGER DEFAULT 0,
            approved_claims INTEGER DEFAULT 0,
            rejected_claims INTEGER DEFAULT 0,
            fraud_confirmed INTEGER DEFAULT 0,
            avg_claim_amount DOUBLE PRECISION,
            avg_parts_cost DOUBLE PRECISION,
            avg_labor_cost DOUBLE PRECISION,
            duplicate_count INTEGER DEFAULT 0,
            suspicious_count INTEGER DEFAULT 0,
            first_claim_date TEXT,
            last_claim_date TEXT,
            last_updated TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dealer_id ON dealer_statistics(dealer_id)")

    # =========================================================================
    # Seed benchmark data (only if table is empty)
    # =========================================================================
    cursor.execute("SELECT COUNT(*) FROM warranty_benchmarks")
    count = cursor.fetchone()[0]

    if count == 0:
        benchmark_data = _get_seed_benchmarks()
        for row in benchmark_data:
            cursor.execute("""
                INSERT INTO warranty_benchmarks 
                (brand, model, issue_type, avg_parts_cost, avg_labor_cost, avg_total,
                 std_parts_cost, std_labor_cost, std_total, min_total, max_total,
                 avg_labor_parts_ratio, avg_tax_rate, sample_count, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, row)
        print(f"   Seeded {len(benchmark_data)} benchmark records")

    conn.commit()
    print("\u2705 PostgreSQL warranty schema bootstrapped")


if __name__ == "__main__":
    bootstrap_warranty_db()
