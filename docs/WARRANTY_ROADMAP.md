# VeriReceipt Warranty Enhancement Roadmap

> Last updated: 2026-02-14
> Status: Planning phase — pick up items as sprints

---

## Current State (What's Built)

- [x] PDF upload and text extraction (pdfplumber + Tesseract OCR)
- [x] Image extraction and perceptual hashing (phash + file hash)
- [x] Duplicate detection (exact image match, similar image match, VIN+issue match)
- [x] Rule-based fraud signals (cost anomalies, date validation, odometer regression, dealer spikes)
- [x] Risk scoring and triage classification (AUTO_APPROVE / REVIEW / INVESTIGATE)
- [x] Dealer tracking (dealer_id, dealer statistics)
- [x] Adjuster feedback collection (VALID_CLAIM / FALSE_POSITIVE / CONFIRMED_FRAUD)
- [x] Analytics dashboard (claim stats, triage breakdown, feedback summary)
- [x] Dual-mode database (PostgreSQL on Render, SQLite locally)
- [x] No-cache middleware for HTML (ensures fresh UI after deploys)
- [x] Vision LLM integration ready (Ollama endpoint configurable)

---

## Phase 1: Authentication & Access Control (Priority: CRITICAL)

**Why**: Can't go to production without knowing who is doing what.

### 1.1 JWT Authentication
- [ ] Login page with username/password
- [ ] JWT token generation and validation
- [ ] Protected API endpoints (require auth header)
- [ ] Session timeout (configurable, e.g., 8 hours)
- [ ] Password hashing (bcrypt)
- [ ] Token refresh mechanism

### 1.2 Role-Based Access Control (RBAC)
- [ ] Roles: `admin`, `senior_auditor`, `auditor`, `viewer`
- [ ] Permission matrix:
  - `admin`: full access, user management, system config
  - `senior_auditor`: review claims, approve/reject, view all analytics
  - `auditor`: review assigned claims, submit verdicts
  - `viewer`: read-only access to analytics
- [ ] Role assignment in user management page
- [ ] API-level permission checks

### 1.3 User Management
- [ ] Admin page to create/edit/disable users
- [ ] Password reset flow
- [ ] Login audit log (who logged in, when, from where)

### Estimated effort: 3-5 days

---

## Phase 2: Auditor Review Queue (Priority: HIGH)

**Why**: Auditors need a dedicated workflow page, not just analytics charts.

### 2.1 Claims Queue Page (`/web/review-queue.html`)
- [ ] Table view of all claims with sortable columns:
  - Claim ID, Date, Dealer, VIN, Amount, Risk Score, Triage Class, Status
- [ ] Filter by: triage class, date range, dealer, risk score range, status
- [ ] Search by: claim ID, VIN, dealer ID, customer name
- [ ] Pagination (50 claims per page)
- [ ] Click row to expand full claim details

### 2.2 Claim Detail View
- [ ] Full extracted data display
- [ ] Fraud signals with severity indicators
- [ ] Duplicate matches with side-by-side image comparison
- [ ] Extracted images gallery
- [ ] Original PDF viewer (embedded)
- [ ] Claim history timeline (all actions taken)

### 2.3 Auditor Actions
- [ ] Verdict buttons: Approve / Reject / Request More Info / Escalate
- [ ] Required reason/notes field when rejecting or escalating
- [ ] Claim assignment (assign to specific auditor)
- [ ] Bulk actions: select multiple claims, batch approve/reject
- [ ] Status workflow: Pending → In Review → Decided → Closed

### 2.4 SLA Tracking
- [ ] Time-in-queue metric per claim
- [ ] Overdue claims highlighted (configurable SLA, e.g., 48 hours)
- [ ] SLA dashboard for managers

### Estimated effort: 5-7 days

---

## Phase 3: Complete Audit Trail (Priority: HIGH)

**Why**: Compliance requirement — every action must be logged immutably.

### 3.1 Audit Log Table
- [ ] Schema: `audit_log(id, timestamp, user_id, action, entity_type, entity_id, details, ip_address)`
- [ ] Actions to log:
  - Claim uploaded / analyzed
  - Claim viewed
  - Verdict submitted
  - Verdict changed
  - Claim assigned / reassigned
  - User login / logout
  - Settings changed
  - Export generated

### 3.2 Audit Log UI
- [ ] Searchable audit log page (admin only)
- [ ] Filter by: user, action type, date range, entity
- [ ] Export audit log to CSV/PDF

### 3.3 Tamper Protection
- [ ] Hash-chain integrity (each log entry includes hash of previous entry)
- [ ] Audit logs are append-only (no delete/update API)
- [ ] Periodic integrity verification

### Estimated effort: 2-3 days

---

## Phase 4: ML Feedback Loop (Priority: HIGH)

**Why**: Makes the system smarter over time using auditor feedback.

### 4.1 Rule Threshold Auto-Tuning (Phase 4a — Low effort)
- [ ] Track which fraud signals fire on claims that auditors mark as FALSE_POSITIVE
- [ ] Calculate per-signal false positive rate
- [ ] Auto-adjust signal thresholds when FP rate exceeds threshold (e.g., 60%)
- [ ] Dashboard showing signal accuracy metrics
- [ ] Manual override for signal weights

### 4.2 Supervised ML Model (Phase 4b — Medium effort)
- [ ] Feature extraction from claims:
  - Cost ratios (parts/labor/total)
  - Dealer history features (claim volume, fraud rate)
  - VIN history features (claim count, time between claims)
  - Image duplicate counts
  - Signal counts by severity
- [ ] Train XGBoost/RandomForest classifier on (features, verdict) pairs
- [ ] Hybrid scoring: blend ML score with rule-based score
- [ ] Model retraining pipeline (periodic, e.g., weekly)
- [ ] A/B testing framework (compare ML vs rules-only)
- [ ] Model performance dashboard (precision, recall, F1, AUC)

### 4.3 Anomaly Detection (Phase 4c — Advanced)
- [ ] Unsupervised clustering on claim features (DBSCAN/Isolation Forest)
- [ ] Detect statistical outliers that rules don't cover
- [ ] Dealer behavior profiling (claim volume patterns, cost distributions)
- [ ] Alert when new anomaly patterns emerge

### Estimated effort: 4a: 2 days, 4b: 5-7 days, 4c: 3-5 days

---

## Phase 5: Enhanced Analytics & Reporting (Priority: MEDIUM)

### 5.1 Dealer Scoring Dashboard
- [ ] Risk-rank dealers by: fraud rate, claim volume trends, average costs, FP rate
- [ ] Dealer profile page with claim history
- [ ] Dealer comparison view
- [ ] Dealer watchlist (flag high-risk dealers)

### 5.2 VIN History Timeline
- [ ] Visual timeline of all claims for a vehicle
- [ ] Odometer progression chart
- [ ] Cross-dealer claim detection for same VIN

### 5.3 Export & Reporting
- [ ] CSV export of claims, decisions, audit trail
- [ ] PDF report generation per claim (for compliance)
- [ ] Scheduled reports (weekly/monthly email summaries)
- [ ] Custom date range reporting

### 5.4 Predictive Analytics
- [ ] Forecast claim volumes by period
- [ ] Predict high-risk periods/regions
- [ ] Cost trend analysis

### Estimated effort: 5-8 days total

---

## Phase 6: Advanced Fraud Detection (Priority: MEDIUM)

### 6.1 Image Tampering Detection
- [ ] EXIF metadata analysis (creation date, software, GPS)
- [ ] Error Level Analysis (ELA) — detect edited regions
- [ ] Copy-move forgery detection
- [ ] Image consistency checks (lighting, shadows, noise patterns)

### 6.2 Parts Price Database
- [ ] Seed OEM parts price lists by brand/model
- [ ] Cross-reference claimed parts costs vs OEM prices
- [ ] Flag outlier parts pricing (>2x standard deviation)
- [ ] Regional price adjustment factors

### 6.3 NLP Claim Analysis
- [ ] Semantic similarity between claim descriptions across dealers
- [ ] Detect templated/copy-paste descriptions
- [ ] Sentiment analysis on claim narratives
- [ ] Key entity extraction (part names, failure modes)

### 6.4 Network Analysis
- [ ] Detect fraud rings: dealers + repair shops + customers colluding
- [ ] Graph visualization of claim relationships
- [ ] Shared addresses/phone numbers/VINs across entities

### Estimated effort: 8-12 days total

---

## Phase 7: Integrations & Enterprise Features (Priority: LOW)

### 7.1 Real-time Claim Scoring API
- [ ] REST API for external systems to submit claims and get scores
- [ ] API key management
- [ ] Rate limiting
- [ ] Webhook callbacks for async processing

### 7.2 Notifications
- [ ] Email alerts when high-risk claims arrive
- [ ] Webhook notifications to Slack/Teams
- [ ] Daily digest of pending claims

### 7.3 Multi-language Support
- [ ] Support warranty docs in multiple languages
- [ ] Leverage existing language pack system (en, ar, zh, ja, ko, th, ms, vi, de)

### 7.4 Customer Portal
- [ ] Claimants can submit claims directly
- [ ] Track claim status
- [ ] Upload additional documents

### 7.5 SSO / Enterprise Auth
- [ ] SAML integration (Azure AD, Okta)
- [ ] Multi-factor authentication (MFA)
- [ ] LDAP/Active Directory support

### 7.6 IoT Integration
- [ ] Cross-reference vehicle telematics data (odometer, engine codes, GPS)
- [ ] OBD-II data validation against claimed issues

### Estimated effort: Variable, 2-4 weeks for full suite

---

## Infrastructure & DevOps

### Cost Optimization
- [ ] Render: Use free/starter tier for dev, pro for production
- [ ] GPU: Use persistent volumes for LLM model weights (avoid re-download on restart)
- [ ] Database: Upgrade from free PostgreSQL before 90-day expiry
- [ ] Consider cron job to suspend service during off-hours

### Monitoring
- [ ] Health check endpoint (`/health`)
- [ ] Error tracking (Sentry or similar)
- [ ] Performance metrics (response times, error rates)
- [ ] Database connection pool monitoring

### Testing
- [ ] Unit tests for fraud signal detection
- [ ] Integration tests against PostgreSQL
- [ ] End-to-end tests for upload → analyze → feedback flow
- [ ] Load testing for concurrent claim submissions

---

## Suggested Sprint Order

| Sprint | Items | Duration |
|--------|-------|----------|
| **Sprint 1** | Authentication + RBAC (Phase 1) | 1 week |
| **Sprint 2** | Review Queue (Phase 2) | 1 week |
| **Sprint 3** | Audit Trail + Rule Auto-Tuning (Phase 3 + 4a) | 1 week |
| **Sprint 4** | ML Model + Enhanced Analytics (Phase 4b + 5) | 2 weeks |
| **Sprint 5** | Advanced Fraud Detection (Phase 6) | 2 weeks |
| **Sprint 6** | Integrations & Enterprise (Phase 7) | 2-4 weeks |

Total estimated timeline: **8-12 weeks** for full product.

---

## Quick Wins (Can do anytime, < 1 day each)

- [ ] Health check endpoint for uptime monitoring
- [ ] Claim PDF download link in results
- [ ] Dark mode toggle on all pages
- [ ] Mobile-responsive layout improvements
- [ ] Keyboard shortcuts for auditor actions
- [ ] Claim count badge on navigation links
