# CarbonBridge — Data Model Documentation

## Overview

CarbonBridge uses a layered, multi-tenant relational schema in PostgreSQL (via Django ORM). The model separates raw ingested data from processed, normalised records, enabling full data lineage from source upload through to carbon accounting.

---

## Entity Hierarchy

```
Tenant
 └── User (auth)
 └── DataSource (SAP / Utility / Travel)
      └── UploadBatch
           └── RawRecord (immutable raw payload)
                └── NormalizedRecord (processed, scopeable record)
                     └── AuditLog (immutable change ledger)
```

---

## Core Entities

### `Tenant`
The root isolation boundary. Every record in the system is scoped to a tenant. No cross-tenant queries are possible through the standard ORM manager.

| Field | Type | Notes |
|---|---|---|
| `name` | CharField | Legal entity name |
| `slug` | SlugField (unique) | URL-safe identifier for API routing |

---

### `User`
Extends Django's `AbstractUser`. Linked to exactly one `Tenant`, or `null` for global system administrators.

| Field | Type | Notes |
|---|---|---|
| `tenant` | FK → Tenant | Null = global admin |

Authentication is handled via **SimpleJWT** (short-lived access tokens + refresh tokens). The tenant is resolved at request time from `request.user.tenant`.

---

### `DataSource`
Named pipeline configuration per tenant. A single tenant may have multiple data sources (e.g. two SAP systems, one utility portal).

| Field | Type | Notes |
|---|---|---|
| `source_type` | Enum | `SAP`, `UTILITY`, `TRAVEL` |
| `name` | CharField | Human-readable label |
| `tenant` | FK → Tenant | Ownership boundary |

---

### `UploadBatch`
Represents one file ingestion run. Status progresses: `PENDING → PARSING → COMPLETED / FAILED`.

| Field | Type | Notes |
|---|---|---|
| `source` | FK → DataSource | Which pipeline produced this batch |
| `upload_timestamp` | DateTimeField | When the file was received |
| `uploaded_by` | FK → User | Who triggered the upload |
| `status` | Enum | `PENDING`, `PARSING`, `COMPLETED`, `FAILED` |

Batches are the unit of retry and auditability. A failed batch can be re-ingested without touching previously successful records.

---

### `RawRecord`
Stores the **unmodified source payload** as JSON. This is the primary data lineage anchor — regardless of future parser changes, the original data is preserved forever.

| Field | Type | Notes |
|---|---|---|
| `batch` | FK → UploadBatch | Parent batch |
| `original_payload_json` | JSONField | Verbatim row from CSV/JSON |
| `parsing_status` | Enum | `PENDING`, `PARSED`, `FAILED` |
| `parsing_errors` | JSONField (nullable) | Per-field validation error list |

---

### `NormalizedRecord`
The primary ESG accounting record. Stores both the original and normalised values for full conversion traceability.

| Field | Type | Notes |
|---|---|---|
| `tenant` | FK → Tenant | Isolation |
| `source_type` | Enum | Source system type |
| `activity_type` | Enum | `fuel`, `electricity`, `procurement`, `flight`, `hotel`, `ground_transport` |
| `scope` | Enum | `Scope1`, `Scope2`, `Scope3` |
| `original_value` | Decimal(18,6) | Raw value before conversion |
| `original_unit` | CharField | Unit as it appeared in source |
| `normalized_value` | Decimal(18,6) | Converted value in SI base unit |
| `normalized_unit` | CharField | Target unit (`L`, `kWh`, `km`, `USD`) |
| `activity_date` | DateField | When the physical activity occurred |
| `confidence_score` | Decimal(5,4) | Heuristic quality score (0.0000–1.0000) |
| `suspicious_flag` | BooleanField | Set by `SuspiciousRecordDetector` |
| `approval_status` | Enum | `Pending`, `Approved`, `Rejected` |
| `approved_by` | FK → User | Null until reviewed |
| `source_reference` | CharField | Upstream invoice/document ID |

**Approved records are immutable.** The `pre_save` signal raises `ValidationError` if an attempt is made to modify an `Approved` record.

---

### `AuditLog`
Append-only, non-soft-deletable change ledger. Created automatically by `post_save` signals on `NormalizedRecord`.

| Field | Type | Notes |
|---|---|---|
| `record` | FK → NormalizedRecord | Target record |
| `action` | CharField | `CREATE`, `UPDATE`, `APPROVE`, `REJECT`, `SOFT_DELETE`, `RESTORE` |
| `user` | FK → User (nullable) | Actor; null = system action |
| `timestamp` | DateTimeField (auto) | Immutable creation time |
| `old_values` | JSONField | State snapshot before change |
| `new_values` | JSONField | State snapshot after change |

`AuditLog` does **not** inherit from `SoftDeleteModel`. It has no `delete()` override. Records can only be hard-deleted by a DBA with direct database access — by design.

---

## Soft Delete Pattern

All primary models inherit from `SoftDeleteModel`, which overrides `.delete()` to set `is_deleted=True` and `deleted_at=now()`. The default ORM manager (`objects`) automatically filters `is_deleted=False`. A secondary manager (`all_objects`) provides unfiltered access for admin and audit operations.

---

## Normalised Units Reference

| Activity Type | Normalised Unit | Rationale |
|---|---|---|
| `fuel` | Liters (L) | Volumetric; compatible with DEFRA/GHG Protocol emission factors |
| `electricity` | kWh | Energy; standard for purchased electricity (Scope 2) |
| `procurement` | kg | Mass; compatible with spend-based/material emission factors |
| `flight` | km | Distance; standard for passenger-km emission factors |
| `ground_transport` | km | Distance |
| `hotel` | nights | Room-nights; standard lodging emission factor input |
| `currency` | USD | Reserve currency for monetary normalisation |
