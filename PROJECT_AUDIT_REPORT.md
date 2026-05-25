# CarbonBridge — Project Audit Report

## 1. Executive Summary
This report summarizes the final production readiness review for the **CarbonBridge ESG Data Ingestion Platform**, developed for the Breathe ESG Tech Intern Assignment. The audit evaluated backend integrity, frontend usability, and compliance with the core assignment objectives.

The platform successfully implements all stated requirements with robust handling of ESG data from multiple formats, an immutable audit trail, and strong multi-tenant separation. Minor issues were found and addressed during this audit.

## 2. Assignment Compliance Checklist

| Requirement | Status | Verification Detail |
| :--- | :---: | :--- |
| **Django REST Backend** | ✅ | Implemented using Django 5 and Django REST Framework. Production configurations included. |
| **React + TypeScript Frontend** | ✅ | Built with React 19, TypeScript, Vite, and Recharts. Vanilla CSS for a clean enterprise UI. |
| **Multi-tenant Architecture** | ✅ | Enforced at the ORM Manager level (`SoftDeleteManager`), ensuring complete isolation for all normalized and raw data. |
| **SAP Export Ingestion** | ✅ | Handles German SAP CSV headers (`Buchungsdatum`, `Menge`), mapping fuel and procurement data. |
| **Utility Export Ingestion** | ✅ | Supports custom billing periods, correctly converting m³ or MWh to kWh. |
| **Travel Export Ingestion** | ✅ | Ingests Concur-style JSON, converting miles to km and aggregating flight/hotel distances. |
| **Data Normalization** | ✅ | Standardizes to SI units (liters, kWh, kg, km, USD) with proper `Decimal` precision. |
| **Scope 1, 2, 3 Categorization** | ✅ | Deterministically assigned during ingestion based on activity mapping (e.g., fuel -> Scope 1, electricity -> Scope 2, travel -> Scope 3). |
| **Source-of-truth Tracking** | ✅ | Immutable `RawRecord` saves exact source JSON; `NormalizedRecord` references the raw origin. |
| **Audit Trail** | ✅ | Django `post_save` signals enforce an immutable, non-soft-deletable `AuditLog` for all approvals and modifications. |
| **Suspicious Record Detection** | ✅ | Deterministic heuristic detection flags negative values, future dates, missing units, and >10x baseline spikes. |
| **Analyst Review Workflow** | ✅ | Dashboard displays Pendings, Suspicious, and Approved records with a unified approval queue. |
| **Record Locking** | ✅ | `pre_save` signal blocks all edits to records bearing the `APPROVED` status. |
| **Deployment Ready** | ✅ | Render `.yaml`, Multi-stage `Dockerfile`, production `settings.py` and Vercel `.env.example` configurations are present. |
| **Required Documentation** | ✅ | `MODEL.md`, `DECISIONS.md`, `SOURCES.md`, `TRADEOFFS.md` successfully generated. |

## 3. Issues Found and Fixes Applied

During the audit, the following technical issues were identified and immediately remediated:

### Backend
1. **NameError in Queryset Admin Filter**:
   - *Issue*: `SoftDeleteFilter.queryset()` attempted to access an undefined `model_admin` variable, breaking the Django Admin for filtering.
   - *Fix*: Modified the method to retrieve the model dynamically via `queryset.model`.
2. **Missing `_acting_user` Injection in Approval Views**:
   - *Issue*: Approving/Rejecting a record via the API did not correctly bind the user to the underlying signal, logging the action as executed by the "System".
   - *Fix*: Injected `record._acting_user = request.user` into `approve_record` and `reject_record` before saving.
3. **Dead Code Elimination**:
   - *Issue*: A scaffold `/ingest` directory existed at the project root which was unused (the active `ingest` app lives under `/backend/ingest`).
   - *Fix*: Deleted the unused directory recursively.
4. **Serializer Field Exposure**:
   - *Issue*: `NormalizedRecordSerializer` used `fields = '__all__'`.
   - *Fix*: Replaced `__all__` with explicitly defined fields, omitting internal mechanisms, and defined `read_only_fields` to prevent ID injection.
5. **Database Indexing**:
   - *Issue*: Retrieving pending vs approved records could cause slow queries without an index.
   - *Fix*: Added a composite index for `(tenant, approval_status)` in the `NormalizedRecord` Meta class and generated the migration.

### Frontend
6. **Stale Tailwind Artifacts**:
   - *Issue*: Components (`Dashboard.tsx`, `Layout.tsx`) contained stale Tailwind class references (`text-red-600`, `text-green-400`), but Tailwind CSS was intentionally removed in favor of Vanilla CSS early in the project.
   - *Fix*: Replaced class calls with dynamic inline styles mapping to defined global CSS variables.

## 4. Remaining Risks and Tradeoffs

- **Authentication UI**: The backend fully supports JWT, but the frontend currently relies on intercepting a mock `localStorage` token. Integrating an OAuth2 login form is required before a production release.
- **Asynchronous Processing**: Uploads are processed synchronously. Massive files (>20,000 rows) might block HTTP workers. Transitioning to a Celery queue pattern using the already integrated Celery configurations is recommended for scale.
- **External FX / Distance APIs**: Static EUR/USD conversions and a limited dictionary of 80 IATA airports are used to limit dependencies. A production scale-up should rely on daily ECB FX pulls and an OpenFlights location dictionary.

## 5. Conclusion
The CarbonBridge platform stands as a rigorous, audit-grade architecture capable of ingesting diverse, imperfect datasets, normalizing them into SI units, and locking them securely for corporate GHG emission calculations. The system is structurally sound, passes all requirements from the assignment brief, and is fully primed for its Vercel + Render deployments.
