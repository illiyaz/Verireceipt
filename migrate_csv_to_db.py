#!/usr/bin/env python3
"""
Migrate data from CSV files to PostgreSQL database.

Usage:
    python migrate_csv_to_db.py
"""

import csv
import os
from pathlib import Path
from datetime import datetime
import psycopg2
from psycopg2.extras import Json


def get_db_connection():
    """Get database connection from environment."""
    db_url = os.getenv(
        'VERIRECEIPT_DATABASE_URL',
        'postgresql://verireceipt:verireceipt@localhost:5432/verireceipt'
    )
    
    # Parse URL (simplified)
    # Format: postgresql://user:pass@host:port/dbname
    parts = db_url.replace('postgresql://', '').replace('postgresql+psycopg2://', '')
    user_pass, host_port_db = parts.split('@')
    user, password = user_pass.split(':')
    host_port, dbname = host_port_db.split('/')
    host, port = host_port.split(':')
    
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )


def migrate_decisions_csv(conn):
    """Migrate decisions.csv to receipts and analyses tables."""
    csv_file = Path('data/logs/decisions.csv')
    
    if not csv_file.exists():
        print(f"⚠️  No decisions.csv found at {csv_file}")
        return 0
    
    cursor = conn.cursor()
    migrated = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                # Insert receipt
                cursor.execute("""
                    INSERT INTO receipts (file_name, source_type, file_size_bytes)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """, (
                    row.get('file_path', ''),
                    row.get('source_type', 'unknown'),
                    int(row.get('file_size_bytes', 0)) if row.get('file_size_bytes') else None
                ))
                
                result = cursor.fetchone()
                if result:
                    receipt_id = result[0]
                else:
                    # Receipt already exists, get its ID
                    cursor.execute(
                        "SELECT id FROM receipts WHERE file_name = %s ORDER BY id DESC LIMIT 1",
                        (row.get('file_path', ''),)
                    )
                    receipt_id = cursor.fetchone()[0]
                
                # Parse reasons (stored as string in CSV)
                reasons = row.get('reasons', '').split(';') if row.get('reasons') else []
                
                # Build features JSON
                features = {
                    'file_size_bytes': int(row.get('file_size_bytes', 0)) if row.get('file_size_bytes') else None,
                    'num_pages': int(row.get('num_pages', 1)) if row.get('num_pages') else 1,
                    'has_any_amount': row.get('has_any_amount', '').lower() == 'true',
                    'has_date': row.get('has_date', '').lower() == 'true',
                    'has_merchant': row.get('has_merchant', '').lower() == 'true',
                    'total_mismatch': row.get('total_mismatch', '').lower() == 'true',
                    'num_lines': int(row.get('num_lines', 0)) if row.get('num_lines') else 0,
                    'suspicious_producer': row.get('suspicious_producer', '').lower() == 'true',
                }
                
                # Insert analysis
                cursor.execute("""
                    INSERT INTO analyses (
                        receipt_id, engine_label, engine_score, engine_version,
                        reasons, features, analyzed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    receipt_id,
                    row.get('label', 'unknown'),
                    float(row.get('score', 0.0)),
                    'rules-v1.0',
                    reasons,
                    Json(features),
                    row.get('timestamp', datetime.now().isoformat())
                ))
                
                migrated += 1
                
            except Exception as e:
                print(f"❌ Error migrating row: {e}")
                print(f"   Row: {row}")
                continue
    
    conn.commit()
    cursor.close()
    
    return migrated


def migrate_feedback_csv(conn):
    """Migrate feedback.csv to feedback table."""
    csv_file = Path('data/logs/feedback.csv')
    
    if not csv_file.exists():
        print(f"⚠️  No feedback.csv found at {csv_file}")
        return 0
    
    cursor = conn.cursor()
    migrated = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                # Find receipt by analysis_ref (file_name)
                cursor.execute(
                    "SELECT id FROM receipts WHERE file_name = %s ORDER BY id DESC LIMIT 1",
                    (row.get('analysis_ref', ''),)
                )
                result = cursor.fetchone()
                
                if not result:
                    print(f"⚠️  Receipt not found for: {row.get('analysis_ref')}")
                    continue
                
                receipt_id = result[0]
                
                # Find latest analysis for this receipt
                cursor.execute(
                    "SELECT id FROM analyses WHERE receipt_id = %s ORDER BY analyzed_at DESC LIMIT 1",
                    (receipt_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    print(f"⚠️  Analysis not found for receipt: {receipt_id}")
                    continue
                
                analysis_id = result[0]
                
                # Insert feedback
                cursor.execute("""
                    INSERT INTO feedback (
                        receipt_id, analysis_id, given_label, reviewer_id,
                        comment, reason_code, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    receipt_id,
                    analysis_id,
                    row.get('given_label', 'unknown'),
                    row.get('reviewer_id'),
                    row.get('comment'),
                    row.get('reason_code'),
                    row.get('timestamp', datetime.now().isoformat())
                ))
                
                migrated += 1
                
            except Exception as e:
                print(f"❌ Error migrating feedback: {e}")
                print(f"   Row: {row}")
                continue
    
    conn.commit()
    cursor.close()
    
    return migrated


def main():
    print("=" * 80)
    print("VeriReceipt - CSV to Database Migration")
    print("=" * 80)
    print()
    
    # Connect to database
    print("Connecting to database...")
    try:
        conn = get_db_connection()
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        print()
        print("Make sure:")
        print("1. PostgreSQL is running (docker-compose up -d db)")
        print("2. Database schema is created (psql < create_db_schema.sql)")
        print("3. VERIRECEIPT_DATABASE_URL is set correctly")
        return
    
    print()
    
    # Migrate decisions
    print("Migrating decisions.csv...")
    decisions_count = migrate_decisions_csv(conn)
    print(f"✅ Migrated {decisions_count} analyses")
    print()
    
    # Migrate feedback
    print("Migrating feedback.csv...")
    feedback_count = migrate_feedback_csv(conn)
    print(f"✅ Migrated {feedback_count} feedback entries")
    print()
    
    # Show statistics
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_statistics")
    stats = cursor.fetchone()
    
    if stats:
        print("Database Statistics:")
        print(f"  Total Analyses: {stats[0]}")
        print(f"  Real: {stats[1]}")
        print(f"  Suspicious: {stats[2]}")
        print(f"  Fake: {stats[3]}")
        print(f"  Avg Score: {stats[4]:.3f}")
    
    cursor.close()
    conn.close()
    
    print()
    print("=" * 80)
    print("✅ Migration Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Set environment variable: export VERIRECEIPT_STORE_BACKEND=db")
    print("2. Restart API: python run_api.py")
    print("3. Test: curl http://localhost:8080/stats")


if __name__ == "__main__":
    main()
