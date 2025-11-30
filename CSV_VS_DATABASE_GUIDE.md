# CSV vs Database Storage - Decision Guide

## TL;DR

**Use CSV now, switch to Database later.**

- **CSV**: Perfect for development and up to 10,000 receipts
- **Database**: Switch when you go to production or hit scale issues

---

## Current Status

Your system **already supports both** backends with zero code changes:

```bash
# CSV mode (default)
python run_api.py

# Database mode
export VERIRECEIPT_STORE_BACKEND=db
python run_api.py
```

---

## Comparison Table

| Feature | CSV | PostgreSQL |
|---------|-----|------------|
| **Setup Time** | 0 minutes | 15 minutes |
| **Performance (< 1K records)** | Fast | Fast |
| **Performance (> 10K records)** | Slow | Fast |
| **Concurrent Users** | ❌ File locking issues | ✅ Handles 100+ users |
| **Data Inspection** | ✅ Open in Excel | ❌ Need SQL client |
| **Backup** | ✅ Copy files | ❌ Need pg_dump |
| **Complex Queries** | ❌ Manual filtering | ✅ SQL queries |
| **Data Integrity** | ❌ No constraints | ✅ Foreign keys, constraints |
| **Transactions** | ❌ No ACID | ✅ Full ACID support |
| **Debugging** | ✅ Easy to read | ❌ Need SQL knowledge |
| **Production Ready** | ❌ Not recommended | ✅ Enterprise-grade |

---

## Decision Matrix

### Use CSV If:

✅ You're in development/testing phase  
✅ Processing < 100 receipts per day  
✅ Single user or small team (< 5 people)  
✅ Need to inspect data in Excel/Google Sheets  
✅ Want zero setup complexity  
✅ Building MVP or proof of concept  

### Switch to Database If:

✅ Processing 100+ receipts per day  
✅ Multiple concurrent users  
✅ Need complex reporting/analytics  
✅ Going to production  
✅ Need data integrity guarantees  
✅ Want to build dashboards  
✅ Need to query historical data frequently  

---

## Your Journey (Recommended Path)

### Phase 1: Now - Development (CSV)

**Current Stage:** Building and testing

```bash
# Already using CSV - keep it!
python run_api.py
python test_all_samples.py
```

**Why:**
- Zero setup
- Easy to debug
- Can share CSV files with team
- Perfect for experimentation

**Data Files:**
```
data/logs/
├── decisions.csv    # ~3 receipts analyzed
└── feedback.csv     # ~0 feedback entries
```

---

### Phase 2: Dataset Collection (CSV)

**Stage:** Collecting 50-100 receipts

```bash
# Still using CSV
# Easy to inspect and validate data
```

**Why:**
- Can manually review CSV in Excel
- Easy to fix data quality issues
- Simple to create test datasets
- Can share files for review

**Data Files:**
```
data/logs/
├── decisions.csv    # ~100 receipts
└── feedback.csv     # ~50 feedback entries
```

---

### Phase 3: Production Deployment (Switch to Database)

**Stage:** Going live with real users

**Trigger Points:**
- 50+ receipts per day
- 5+ concurrent users
- Need for reporting/dashboards
- Customer-facing deployment

**Migration Steps:**

#### 1. Start PostgreSQL

```bash
# Using Docker Compose (recommended)
docker-compose up -d db

# Or install locally
# brew install postgresql (Mac)
# sudo apt-get install postgresql (Linux)
```

#### 2. Create Database Schema

```bash
# Connect to database
docker exec -it verireceipt_db psql -U verireceipt -d verireceipt

# Run schema
\i create_db_schema.sql

# Verify tables
\dt
```

#### 3. Migrate Existing CSV Data

```bash
# Run migration script
python migrate_csv_to_db.py
```

**Output:**
```
================================================================================
VeriReceipt - CSV to Database Migration
================================================================================

Connecting to database...
✅ Connected to database

Migrating decisions.csv...
✅ Migrated 127 analyses

Migrating feedback.csv...
✅ Migrated 43 feedback entries

Database Statistics:
  Total Analyses: 127
  Real: 85
  Suspicious: 22
  Fake: 20
  Avg Score: 0.234

================================================================================
✅ Migration Complete!
================================================================================
```

#### 4. Switch Backend

```bash
# Set environment variable
export VERIRECEIPT_STORE_BACKEND=db

# Or create .env file
cat > .env << EOF
VERIRECEIPT_STORE_BACKEND=db
VERIRECEIPT_DATABASE_URL=postgresql://verireceipt:verireceipt@localhost:5432/verireceipt
EOF

# Restart API
python run_api.py
```

#### 5. Verify

```bash
# Test stats endpoint (uses database)
curl http://localhost:8080/stats

# Analyze a receipt (saves to database)
curl -X POST http://localhost:8080/analyze -F "file=@receipt.jpg"

# Submit feedback (saves to database)
curl -X POST http://localhost:8080/feedback \
  -H "Content-Type: application/json" \
  -d '{"analysis_ref": "receipt.jpg", "given_label": "fake"}'
```

---

## Detailed Comparison

### CSV Backend

#### How It Works

```python
# app/repository/receipt_store.py
class CsvReceiptStore:
    def save_analysis(self, file_path, decision):
        # Appends to data/logs/decisions.csv
        log_decision(file_path, decision)
        return os.path.basename(file_path)
    
    def save_feedback(self, ...):
        # Appends to data/logs/feedback.csv
        log_feedback(...)
        return timestamp
```

#### Data Format

**decisions.csv:**
```csv
timestamp,file_path,label,score,reasons,file_size_bytes,num_pages,...
2025-11-30T10:00:00,receipt1.jpg,real,0.0,"No anomalies",123456,1,...
2025-11-30T10:05:00,receipt2.pdf,fake,0.85,"Canva producer",234567,1,...
```

**feedback.csv:**
```csv
timestamp,analysis_ref,receipt_ref,engine_label,engine_score,given_label,reviewer_id,comment,reason_code
2025-11-30T11:00:00,receipt1.jpg,,real,0.0,real,john@co.com,Verified,VERIFIED
```

#### Pros

✅ **Zero Setup**
```bash
# Just works
python run_api.py
```

✅ **Human Readable**
```bash
# Open in any text editor
cat data/logs/decisions.csv

# Open in Excel
open data/logs/decisions.csv
```

✅ **Easy Backup**
```bash
# Copy files
cp data/logs/*.csv backups/$(date +%Y%m%d)/

# Commit to Git (optional)
git add data/logs/*.csv
```

✅ **Simple Debugging**
```bash
# Find specific receipt
grep "receipt1.jpg" data/logs/decisions.csv

# Count by label
cut -d',' -f3 data/logs/decisions.csv | sort | uniq -c
```

#### Cons

❌ **Performance Issues at Scale**
```bash
# Slow with 10,000+ rows
# Every query reads entire file
```

❌ **No Concurrent Access**
```python
# Multiple processes writing simultaneously = corruption
# File locking issues
```

❌ **Limited Querying**
```bash
# Want receipts from last week with score > 0.5?
# Need to write custom Python script
```

❌ **No Data Integrity**
```csv
# Typos possible
receipt1.jpg,rael,0.0  # Should be "real"

# No foreign key constraints
# Can reference non-existent receipts
```

---

### Database Backend

#### How It Works

```python
# app/repository/receipt_store.py
class DbReceiptStore:
    def save_analysis(self, file_path, decision):
        # Insert into receipts and analyses tables
        session = SessionLocal()
        receipt = Receipt(file_name=file_path, ...)
        analysis = Analysis(receipt_id=receipt.id, ...)
        session.add_all([receipt, analysis])
        session.commit()
        return analysis.id
```

#### Database Schema

```sql
receipts (id, file_name, source_type, file_size_bytes, ...)
  ↓
analyses (id, receipt_id, engine_label, engine_score, features, ...)
  ↓
feedback (id, receipt_id, analysis_id, given_label, reviewer_id, ...)
```

#### Pros

✅ **Fast Queries**
```sql
-- Find all fake receipts from last week
SELECT * FROM analyses 
WHERE engine_label = 'fake' 
  AND analyzed_at > NOW() - INTERVAL '7 days';

-- Milliseconds even with millions of rows
```

✅ **Concurrent Access**
```python
# 100 users analyzing simultaneously
# No problem with transactions
```

✅ **Data Integrity**
```sql
-- Foreign keys ensure referential integrity
-- Can't create feedback for non-existent receipt

-- Constraints ensure data quality
CHECK (engine_label IN ('real', 'suspicious', 'fake'))
```

✅ **Complex Analytics**
```sql
-- Accuracy by reviewer
SELECT 
    reviewer_id,
    COUNT(*) as total_reviews,
    AVG(CASE WHEN given_label = engine_label THEN 1.0 ELSE 0.0 END) as agreement_rate
FROM feedback_with_predictions
GROUP BY reviewer_id;
```

✅ **Transactions**
```python
# All-or-nothing operations
with session.begin():
    receipt = Receipt(...)
    analysis = Analysis(...)
    session.add_all([receipt, analysis])
    # Both saved or both rolled back
```

#### Cons

❌ **Setup Required**
```bash
# Need to install PostgreSQL
# Create database
# Run migrations
# Configure connection
```

❌ **Harder to Inspect**
```bash
# Need SQL client
psql -U verireceipt -d verireceipt

# Or pgAdmin, DBeaver, etc.
```

❌ **Complex Backup**
```bash
# Need pg_dump
pg_dump -U verireceipt verireceipt > backup.sql

# Restore
psql -U verireceipt verireceipt < backup.sql
```

❌ **SQL Knowledge Required**
```sql
-- Need to know SQL for queries
-- More complex than opening CSV in Excel
```

---

## Migration Guide

### When to Migrate

Migrate when you hit **any** of these:

1. **Performance**: CSV queries taking > 1 second
2. **Scale**: 10,000+ receipts analyzed
3. **Concurrency**: Multiple users getting errors
4. **Production**: Deploying to customers
5. **Analytics**: Need complex reporting

### Migration Checklist

- [ ] Install PostgreSQL (or use Docker)
- [ ] Create database schema (`create_db_schema.sql`)
- [ ] Run migration script (`migrate_csv_to_db.py`)
- [ ] Verify data integrity
- [ ] Update environment variables
- [ ] Test all endpoints
- [ ] Backup CSV files (keep as archive)
- [ ] Monitor performance
- [ ] Update documentation

### Rollback Plan

If database has issues, you can always roll back:

```bash
# Switch back to CSV
export VERIRECEIPT_STORE_BACKEND=csv

# Restart API
python run_api.py

# Your CSV files are still there!
```

---

## Best Practices

### For CSV Backend

1. **Regular Backups**
   ```bash
   # Daily backup
   cp data/logs/*.csv backups/$(date +%Y%m%d)/
   ```

2. **Monitor File Size**
   ```bash
   # Alert if > 10 MB
   ls -lh data/logs/decisions.csv
   ```

3. **Periodic Cleanup**
   ```bash
   # Archive old data
   head -1 decisions.csv > decisions_2025.csv
   grep "2025-" decisions.csv >> decisions_2025.csv
   ```

4. **Validate Data**
   ```python
   # Check for corrupted rows
   import pandas as pd
   df = pd.read_csv('data/logs/decisions.csv')
   print(df.isnull().sum())
   ```

### For Database Backend

1. **Regular Backups**
   ```bash
   # Daily backup
   pg_dump -U verireceipt verireceipt > backup_$(date +%Y%m%d).sql
   ```

2. **Monitor Performance**
   ```sql
   -- Slow queries
   SELECT * FROM pg_stat_statements 
   ORDER BY mean_exec_time DESC LIMIT 10;
   ```

3. **Vacuum Regularly**
   ```sql
   -- Reclaim space
   VACUUM ANALYZE;
   ```

4. **Index Optimization**
   ```sql
   -- Check index usage
   SELECT * FROM pg_stat_user_indexes;
   ```

---

## Cost Comparison

### CSV Backend

**Infrastructure:**
- $0 - Just disk space
- ~1 MB per 1,000 receipts

**Maintenance:**
- Minimal - just backup files

**Total:** ~$0/month

---

### Database Backend

**Infrastructure:**
- **Development**: $0 (Docker on local machine)
- **Production**: $15-50/month (managed PostgreSQL)
  - AWS RDS: $15/month (db.t3.micro)
  - DigitalOcean: $15/month (1 GB RAM)
  - Heroku: $9/month (Hobby tier)

**Maintenance:**
- Backups: Included in managed services
- Monitoring: $0-10/month

**Total:** $15-60/month for production

---

## Recommendation Summary

### For You Right Now: **Use CSV** ✅

**Why:**
- You're in development phase
- Have only 3 sample receipts
- Need to inspect data easily
- Want zero setup complexity
- Building and testing

**Keep CSV until:**
- You have 100+ receipts analyzed
- You're deploying to production
- You have multiple users
- You need complex queries

### When to Switch: **After MVP Validation**

**Switch when:**
- Processing 50+ receipts per day
- 5+ team members using it
- Need reporting/dashboards
- Going live with customers

**How to switch:**
1. Run `docker-compose up -d db`
2. Run `psql < create_db_schema.sql`
3. Run `python migrate_csv_to_db.py`
4. Set `VERIRECEIPT_STORE_BACKEND=db`
5. Restart API

---

## Summary

| Stage | Storage | Why |
|-------|---------|-----|
| **Now** | CSV | Zero setup, easy debugging |
| **Dataset Collection** | CSV | Easy to inspect/validate |
| **Production** | Database | Scale, performance, integrity |

**Your system is ready for both - switch when you need to!** 🚀
