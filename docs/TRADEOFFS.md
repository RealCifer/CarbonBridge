# CarbonBridge — Tradeoffs

Conscious tradeoffs, intentional omissions, and real deployment risks.

---

## What Was Intentionally Ignored

### 1. Real-Time Currency Exchange Rates
**Done:** Hardcoded static rates in `ConversionService` (EUR→USD, INR→USD).

**Ignored:** Live FX rates from ECB or Open Exchange Rates API.

**Why:** ESG reporting uses **annual average rates** from national treasuries (HMRC, US Treasury), not spot rates. A live rate would make historical records non-reproducible on re-run.

**Production fix:** Replace `CONVERSION_RATES` dict with a nightly-synced `ExchangeRate` database table. Store `exchange_rate_date` on each `NormalizedRecord`.

---

### 2. CO₂e Emission Calculation
**Done:** `NormalizedRecord` stores `normalized_value` in SI units (kWh, L, km). No carbon math is applied.

**Ignored:** Multiplying activity data by an emission factor (EF) to produce `kgCO₂e`.

**Why:** Emission factors are jurisdiction-specific (DEFRA, EPA, IPCC AR6) and year-specific. Embedding them requires maintaining a versioned ~2,000-factor database — a product in itself (Watershed, Persefoni charge for EF databases). The normalisation layer is the correct architectural boundary; EF application belongs in a downstream `EmissionsService`.

**Production fix:** `EmissionFactor` model, joined on `(activity_type, scope, country, year)` by a `calculate_emissions` Celery task.

---

### 3. Asynchronous Ingestion
**Done:** File ingestion runs synchronously inside the upload HTTP request.

**Ignored:** Celery task queue for background processing.

**Why:** For hundreds to low-thousands of rows, synchronous processing completes in <2s. Celery adds Redis/RabbitMQ broker, worker management, and result backend — significant overhead for no gain at this scale.

**Production fix:** Wrap `run_ingestion()` in a `@celery.task`. Upload endpoint returns HTTP 202 + `batch_id` immediately. Frontend polls `GET /api/batches/{id}/status/`.

---

### 4. Frontend Authentication UI
**Done:** Axios interceptor reads `Bearer` token from `localStorage`. No login page.

**Ignored:** OAuth2/JWT login flow, token refresh, session expiry UX, role-based UI access control.

**Why:** Assignment focus is the backend data pipeline. Auth UI adds scope without demonstrating new architectural concepts.

**Production fix:** OAuth2 PKCE login page hitting `POST /api/token/`. Move token storage from `localStorage` to `httpOnly` cookie (XSS mitigation).

---

### 5. IATA Airport Database Completeness
**Done:** Travel adapter embeds ~80 major airport coordinate pairs. Unknown pairs → `distance = 0 km` with a warning log.

**Ignored:** Full IATA dataset (~10,000 airports) or live coordinate API.

**Why:** For 95th-percentile corporate travel (hub-and-spoke between major business hubs), 80 airports provide sufficient coverage without adding bulk to the codebase.

**Production fix:** Import [OpenFlights dataset](https://openflights.org/data.html) (~14,000 airports, free) as a Django fixture, replace `_AIRPORT_COORDS` dict with a PostGIS `Airport` model.

---

### 6. GDPR / PII Handling
**Done:** Traveller employee IDs stored verbatim in `RawRecord.original_payload_json` and `source_reference`.

**Ignored:** PII pseudonymisation, right-to-erasure (GDPR Art. 17) workflow, and data retention policies.

**Why:** Out of scope for a data normalisation assignment.

**Production fix:** HMAC-pseudonymise traveller identifiers on ingestion using a per-tenant secret. Implement `DataDeletionRequest` model to trigger cascading soft-delete by traveller ID.

---

### 7. Multi-File Upload
**Done:** Single file per upload request.

**Ignored:** ZIP archive extraction, multi-file multipart, bulk batch API.

**Why:** Simplicity. The single-file pattern fully demonstrates the ingestion pipeline.

---

### 8. Water and Heat GHG Scoping
**Done:** Utility adapter correctly converts water (m³) and district heat (GJ→kWh). These commodity types parse without error.

**Ignored:** `water` and `heat` are absent from `NormalizedRecord.ActivityType` choices and have no scope assignment.

**Why:** Their emission factors are highly location-specific and rarely required in Scope 1/2 reporting. Adding them would require a migration without demonstrating new patterns.

---

## Real Deployment Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Static FX rates becoming stale | **High** | Nightly ECB rate sync into `ExchangeRate` table |
| Synchronous ingestion blocking HTTP workers at scale | **High** | Celery async task with HTTP 202 Accepted pattern |
| PII (employee IDs) in raw JSON payloads | **High** | HMAC pseudonymisation on ingestion |
| No rate limiting on upload endpoints | **Medium** | `django-ratelimit` or API gateway throttling |
| `localStorage` JWT token storage (XSS risk) | **Medium** | Migrate to `httpOnly` cookie with CSRF double-submit |
| SAP CSV encoding variance (cp1252/latin-1/utf-8) | **Medium** | Extend encoding auto-detection in `SAPAdapter` |
| Airport distance = 0 for unknown IATA pairs | **Medium** | Integrate OpenFlights dataset as Django fixture |
| `AuditLog` growing unboundedly | **Medium** | PostgreSQL time-based table partitioning + archival job |
| `SuspiciousRecordDetector` N+1 query risk on cold cache | **Low** | Pre-warm averages cache on batch start; add DB index |
| No composite index on `(tenant, approval_status)` | **Low** | Add index migration for review queue performance at scale |
