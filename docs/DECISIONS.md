# CarbonBridge — Design Decisions

This document records the rationale behind key architectural and implementation decisions made during the CarbonBridge build. Each decision includes context, the option chosen, and why alternatives were rejected.

---

## 1. Why SAP CSV (semicolon-delimited) was chosen as a source format

**Context:** SAP ERP systems are the dominant ERP platform in large European enterprises (>50% market share in manufacturing and energy). SAP's standard data export mechanism — used in MM60, MB51, and CO3-series reports — produces semicolon-delimited CSV files with German column headers by default, regardless of system locale in many configurations.

**Decision:** The SAP adapter accepts semicolon-delimited CSV with German header aliases (`Buchungsdatum`, `Menge`, `Mengeneinheit`, `Werk`, etc.) as first-class inputs, not as an afterthought.

**Alternatives rejected:**
- **SAP OData API (direct integration):** Requires RFC authorization, network access, and SAP Basis cooperation. Adds 2–4 weeks of setup overhead. Out of scope for a data normalisation assignment.
- **IDoc/BAPI via RFC:** Complex binary protocol. Requires SAP JCo library (commercial license). Entirely inappropriate for this context.
- **SAP BW/4HANA export:** Only available in enterprise SAP landscapes with BI module. Not universally available.

**Why this matters:** Real-world sustainability teams at SAP customers routinely export MB51 (material documents) or ME2N (purchase orders) and email CSV files to ESG teams. The adapter must meet these teams where they are.

---

## 2. Why Utility CSV was chosen as a source format

**Context:** Utility suppliers (electricity, gas, water) provide billing data in one of two ways: a structured online portal export (CSV), or a PDF invoice. PDF parsing is computationally expensive and brittle. All major UK, German, and Dutch utility portals (E.ON, RWE, Vattenfall, Eneco) offer CSV exports of billing history with configurable date ranges.

**Decision:** The Utility adapter ingests CSV exports with flexible German/English header aliasing. The `von`/`bis` billing period convention is specifically supported, as it matches the export format of German utilities (Stadtwerke, E.ON Energie Deutschland).

**Alternatives rejected:**
- **PDF invoice parsing (OCR):** 30–40% error rate on non-standard layouts. Requires third-party OCR service. Too fragile for a production audit trail.
- **EDI/EDIFACT (UTILMD):** Used for meter data exchange between DSOs and suppliers in DACH markets. Extremely complex to parse. Not accessible without utility industry credentials.
- **Direct API (SMETS2 / smart meter):** Smart meter API access requires DCCAS authorisation in the UK and is only available in regulated markets. Not portable across geographies.

---

## 3. Why Concur-style JSON was chosen for Travel

**Context:** SAP Concur is the dominant corporate travel and expense management platform globally (~70 million users). Concur's expense export API produces JSON arrays of trip/expense objects. The field naming conventions (`expense_type`, `booking_id`, `cabin_class`, etc.) are well-documented and widely replicated by competitors (Coupa, Navan, Egencia).

**Decision:** The Travel adapter accepts Concur-compatible JSON with an extensive field alias map that also covers Navan, Egencia, and generic corporate travel report conventions.

**Alternatives rejected:**
- **CSV travel reports:** Concur does produce CSV exports, but the nested structure of trips (flight + hotel + taxi in one booking) is poorly represented in flat CSV. JSON preserves the object graph naturally.
- **GDS (Amadeus/Sabre) PNR data:** Contains the richest flight data but requires IATA agent credentials. Not accessible to ESG teams without airline industry partnerships.
- **IATA NDC API:** New distribution capability — modern but adoption is still limited. Not representative of what most corporate travel managers actually use today.

---

## 4. Multi-Tenancy Architecture

**Decision:** Tenant isolation is enforced at the **Django ORM manager level**, not at the database level (row-level security) or application level (manual `WHERE tenant=X` clauses in every view).

Every primary model's default `objects` manager returns only `is_deleted=False` records. A separate `all_objects` unfiltered manager is available for admin/audit use. The `Tenant` foreign key is present on every leaf model (`NormalizedRecord`, `RawRecord`, `UploadBatch`, `DataSource`) and is always resolved from `request.user.tenant` in API views, not from request parameters.

**Why not database-level RLS (PostgreSQL Row Level Security)?**
- RLS policies are powerful but opaque — bugs are invisible in application code and difficult to test with Django's test client.
- Django's ORM does not natively understand RLS; raw SQL queries bypass it silently.
- The manager-level approach is fully testable with standard Django TestCase patterns.

**Why not schema-per-tenant?**
- Schema-per-tenant (e.g. using `django-tenants`) is appropriate for very large enterprise SaaS with hundreds of tenants and strict legal data residency requirements. It comes with significant operational overhead (migrations must run per schema, cross-tenant analytics is hard).
- For a platform processing ESG data for 10–200 corporate clients, shared schema with tenant FKs is the correct tradeoff.

---

## 5. Audit Trail Design

**Decision:** Audit logs are generated by Django `post_save` signals, not by application code in views or services. The `pre_save` signal captures the `old_values` snapshot; the `post_save` signal writes the `AuditLog` entry.

**Why signals, not explicit service calls?**
- Signals fire unconditionally — even if a developer writes a raw `record.save()` without going through the service layer, the audit log is still created.
- This prevents audit gaps from developer error, future refactoring, or background job code paths.

**Why not PostgreSQL triggers?**
- Triggers produce audit records in the database but these records are invisible to the Django application layer unless explicitly queried. Reporting them via the API requires a separate audit query model.
- Django signals keep the audit log accessible through the standard ORM with no special tooling.

**Why `AuditLog` does not inherit `SoftDeleteModel`?**
- Soft delete on an audit log defeats its purpose. An audit record that can be soft-deleted is not a reliable audit record.
- `AuditLog` rows can only be removed by a DBA with direct `psql` access, which creates an operational barrier commensurate with the sensitivity of the operation.

---

## 6. Scope Categorisation

**Decision:** GHG Protocol scope is assigned at the **adapter level** based on `activity_type`, not user-specified per record.

| Activity Type | Scope | Rationale |
|---|---|---|
| `fuel` | Scope 1 | Direct combustion of fuel owned by the company |
| `electricity` | Scope 2 | Purchased energy — indirect Scope 2 under market-based/location-based method |
| `procurement` | Scope 3 | Purchased goods and services — Scope 3 Category 1 |
| `flight` | Scope 3 | Business travel — Scope 3 Category 6 |
| `hotel` | Scope 3 | Business travel — Scope 3 Category 6 |
| `ground_transport` | Scope 3 | Business travel — Scope 3 Category 6 |

**Why automated, not user-assigned?**
- Scope is a function of the **economic relationship** between the company and the emission source, not of the data entry operator's judgement. It should be deterministic.
- User-assigned scope introduces audit risk: an analyst could incorrectly scope a Scope 3 flight as Scope 1, inflating direct emissions.

---

## 7. Unit Normalisation Design

**Decision:** All conversion logic is centralised in `core/conversion.py` (`ConversionService`). Adapters call `ConversionService.convert(activity_type, quantity, unit)` and receive `(normalised_value, normalised_unit)`.

**Why centralised?**
- Before centralisation, each adapter had its own `_normalise_unit` method with different conversion factors. This created divergence: the SAP adapter used one gallon-to-litre factor, and the Utility adapter used a slightly different one for a different commodity.
- A single source of truth guarantees that `1 US Gallon` always equals exactly `3.78541 L` across all ingestion paths.

**Why `Decimal`, not `float`?**
- ESG reporting requires audit-grade numeric precision. Float arithmetic is lossy (IEEE 754). A difference of `0.000001 L` per record, multiplied across 10 million records, produces a measurable reporting error.
- All conversion factors and results are `Decimal` with 6 decimal places of precision.

---

## 8. Suspicious Record Detection

**Decision:** Detection runs **synchronously in the ingestion loop**, not as a post-processing background job.

**Why synchronous?**
- Background detection introduces a window where records exist in the database with no confidence score — this would appear as clean records to any dashboard polling immediately after ingestion.
- Synchronous detection ensures that every persisted `NormalizedRecord` has a `confidence_score` and `suspicious_flag` at the moment of creation.

**Confidence score algorithm:**
- Starts at 100, deducted per anomaly, floored at 0, stored as `Decimal` in `[0.0000, 1.0000]`.
- Not a probabilistic ML score — intentionally a **deterministic heuristic** for auditability. Every score can be fully explained without a model card.
