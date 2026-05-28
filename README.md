# CarbonBridge

Multi-Tenant ESG Data Ingestion, Normalization, and Audit Review Platform

## Live Deployment

- **Frontend (Vercel):** [https://carbon-bridge-mauve.vercel.app/](https://carbon-bridge-mauve.vercel.app/)
- **Backend (Render):** [https://carbonbridge-1.onrender.com/](https://carbonbridge-1.onrender.com/)

## Overview

CarbonBridge is an Environmental, Social, and Governance (ESG) data ingestion platform designed to consolidate corporate carbon metrics from disparately formatted source systems.

ESG data ingestion is difficult because corporate data resides across multiple, unconnected systems (e.g., SAP ERP instances, regional utility portals, corporate travel platforms). Each system exports data in proprietary formats, varying languages, and different measurement units. Furthermore, ESG reporting requires an unbroken chain of custody and an immutable audit trail to comply with external assurance standards.

CarbonBridge solves this problem by providing a centralized ingestion engine that accepts raw exports directly from common enterprise systems. It maps proprietary headers, standardizes unit measurements, automatically categorizes emissions into Greenhouse Gas (GHG) Protocol scopes, and presents the normalized data in a unified review queue for analyst approval. The system maintains an immutable record of both the original payload and all subsequent transformations.

## Assignment Context

This project was built for the Breathe ESG Tech Intern Assignment.

## Key Features

- Multi-tenant architecture ensuring logical data isolation at the ORM level.
- SAP data ingestion supporting German-language headers and custom material units.
- Utility data ingestion supporting diverse billing periods and volumetric-to-energy conversions.
- Corporate travel data ingestion parsing Concur-style nested JSON arrays.
- Data normalization converting disparate units to standardized SI equivalents (liters, kWh, kg, km, USD).
- Scope 1, Scope 2, and Scope 3 classification automatically applied based on activity type.
- Suspicious record detection utilizing deterministic heuristics to flag anomalies.
- Analyst review workflow presenting pending records in an organized dashboard.
- Approval and rejection workflow to manage data progression.
- Record locking preventing modifications to approved entries via pre-save signals.
- Audit trail automatically generated via post-save signals.
- Source-of-truth tracking retaining the raw, unmodified JSON payload of every ingested record.

## Architecture

```text
       [Client/Analyst]
              |
              v
      +----------------+
      | React Frontend |
      +----------------+
              | (REST API via Axios)
              v
      +-------------------+
      | Django REST API   |
      +-------------------+
        /       |       \
       v        v        v
  [ SAP ]  [ Utility ]  [ Travel ]
  Adapter   Adapter      Adapter
       \        |        /
        v       v       v
      +-------------------+
      | Normalization &   |
      | Detection Engine  |
      +-------------------+
              |
              v
     +---------------------+
     | PostgreSQL Database |
     | (Tenant Isolated)   |
     +---------------------+
        /             \
       v               v
 [AuditLog]      [NormalizedRecord]
```

## Technology Stack

### Backend
- Django (5.x)
- Django REST Framework (3.x)
- PostgreSQL (via psycopg2)
- djangorestframework-simplejwt (Authentication)

### Frontend
- React (19.x)
- TypeScript
- Vite
- Axios
- Recharts

### Deployment
- Render (Backend Web Service and Managed PostgreSQL)
- Vercel (Frontend CDN)

## Data Sources

### SAP
- **Chosen Format:** Semicolon-delimited CSV.
- **Research Findings:** SAP ERP systems (MM60, MB51 reports) default to semicolon-delimited exports with localized column headers.
- **Supported Fields:** German aliases (`Buchungsdatum`, `Werk`, `Materialgruppe`, `Menge`, `Mengeneinheit`, `Währung`). Captures fuel consumption (Scope 1) and procurement purchases (Scope 3).

### Utility Data
- **Chosen Format:** Comma-delimited CSV.
- **Research Findings:** European utility portals (E.ON, RWE) export billing history as CSV using specific billing period conventions (`von`, `bis`).
- **Supported Fields:** Billing periods, electricity consumption, natural gas volumetric readings. Supports conversion of m³ and GJ to kWh.

### Travel Data
- **Chosen Format:** JSON arrays.
- **Research Findings:** Platforms like SAP Concur and Navan export expense records as structured JSON, nesting flight, hotel, and ground transport data.
- **Supported Fields:** Origin/destination airports, flight distances, hotel nights, ground transport costs, and cabin classes. Maps IATA codes and handles missing data gracefully.

## Data Model

- **Tenant:** The root isolation boundary representing a corporate division or client.
- **DataSource:** The pipeline configuration representing the origin system (e.g., "SAP Production", "Concur US"). Belongs to a Tenant.
- **UploadBatch:** Represents a single file ingestion run. Tracks processing status (Pending, Parsing, Completed, Failed).
- **RawRecord:** The immutable source-of-truth. Stores the exact JSON payload of a single row extracted from the uploaded file.
- **NormalizedRecord:** The processed ESG metric. Contains standardized units, calculated confidence scores, approval status, and GHG Scope. Belongs to a Tenant.
- **AuditLog:** An append-only ledger created automatically by signals. Records all creations, updates, approvals, and rejections of NormalizedRecords.

### Relationships
A `Tenant` owns `DataSources` and `NormalizedRecords`. A `DataSource` has many `UploadBatches`. An `UploadBatch` has many `RawRecords`. A `RawRecord` is processed into one or more `NormalizedRecords`. A `NormalizedRecord` has many `AuditLogs`.

## Project Structure

```text
CarbonBridge/
├── backend/
│   ├── adapters/          # Ingestion parsing logic
│   ├── carbonbridge/      # Django project settings
│   ├── core/              # Core models, signals, general API views
│   ├── emissions/         # GHG calculation engine and reporting
│   ├── ingest/            # Upload endpoints and batch processing
│   ├── manage.py
│   ├── requirements.txt
│   ├── build.sh           # Render build hook
│   └── Dockerfile         # Multi-stage production container
├── docs/                  # Architecture and design documentation
├── frontend/
│   ├── src/
│   │   ├── components/    # Reusable UI components
│   │   ├── pages/         # Dashboard and Review views
│   │   ├── services/      # Axios API client configuration
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── sample-data/           # Test datasets (SAP, Utility, Travel)
├── render.yaml            # Render Infrastructure as Code
└── README.md
```

## API Endpoints

### System
`GET /api/health/`
Returns system status.

### Ingestion
`POST /api/upload/sap/`
`POST /api/upload/utility/`
`POST /api/upload/travel/`

**Request Example (Multipart Form):**
```text
file: <binary_data>
source_name: "Q1 SAP Export"
delimiter: ";"
```

**Response Example:**
```json
{
    "batch_id": 42,
    "source_type": "SAP",
    "uploaded": 150,
    "normalized": 148,
    "failed": 2,
    "batch_status": "COMPLETED",
    "validation_errors": [
        {"row": 12, "field": "quantity", "message": "Cannot convert 'N/A' to a number."}
    ]
}
```

### Review Workflow
`GET /api/review/pending/`
`GET /api/review/suspicious/`
`GET /api/review/approved/`

`POST /api/review/approve/`
`POST /api/review/reject/`

**Request Example:**
```json
{
    "record_id": 1054
}
```

**Response Example:**
```json
{
    "status": "approved",
    "record_id": 1054
}
```

## Installation

### Backend Setup
1. Navigate to the backend directory:
   `cd backend`
2. Create and activate a virtual environment:
   `python -m venv .venv`
   `source .venv/bin/activate`  *(Linux/Mac)*
   `.venv\Scripts\activate` *(Windows)*
3. Install dependencies:
   `pip install -r requirements.txt`

### Database Setup
By default, the application uses SQLite for local development. To use PostgreSQL, set the database environment variables in `.env`.

### Environment Variables
Copy `.env.example` to `.env` in the `backend` directory:
`cp .env.example .env`

Update the `SECRET_KEY` and other configurations as necessary.

### Migrations
Apply database migrations:
`python manage.py migrate`

Create an initial superuser (required to bypass tenant restrictions during initial setup):
`python manage.py createsuperuser`

### Frontend Setup
1. Navigate to the frontend directory:
   `cd frontend`
2. Install dependencies:
   `npm install`
3. Configure environment variables by copying `.env.example`:
   `cp .env.example .env`

## Running Locally

1. Start the Django backend server:
   `cd backend`
   `python manage.py runserver 8000`

2. Start the Vite frontend server in a new terminal:
   `cd frontend`
   `npm run dev`

The application will be accessible at `http://localhost:5173`.

## Sample Data

The `sample-data` directory contains diverse, realistic datasets for testing the ingestion pipeline. These files include a mixture of valid records, unit inconsistencies, negative values, and missing fields to validate the normalization engine and anomaly detection logic.
- `sap/fuel_purchases.csv`
- `sap/procurement_purchases.csv`
- `utility/electricity_bills.csv`
- `utility/gas_billing_periods.csv`
- `travel/corporate_travel.json`

## Deployment

### Backend Deployment (Render)
The repository includes a `render.yaml` blueprint.
1. Connect the repository to Render using the "Blueprint" deployment option.
2. Render will automatically provision a PostgreSQL database and a Docker-based Web Service using the provided `Dockerfile` and `build.sh`.

### Frontend Deployment (Vercel)
1. Import the repository into Vercel.
2. Set the Root Directory to `frontend`.
3. Vercel will automatically detect the Vite framework and execute `npm run build`.
4. Define the `VITE_API_URL` environment variable to point to the deployed Render backend URL.

## Design Decisions

- **Multi-Tenancy at the ORM Level:** Tenant isolation is enforced via custom Django Managers (`SoftDeleteManager`), avoiding the operational complexity of schema-per-tenant architectures while ensuring cross-tenant queries cannot occur accidentally.
- **Signal-Based Audit Logging:** `AuditLog` entries are generated via Django `post_save` signals. This guarantees that all state changes are logged, even if records are modified outside the standard API views or via background tasks.
- **Centralized Unit Normalization:** Conversion logic and static exchange rates are centralized within a single `ConversionService`. This prevents divergence across different adapters (e.g., standardizing gallon-to-liter conversions universally).
- **Synchronous Suspicious Record Detection:** Anomaly detection runs synchronously during the ingestion pipeline rather than as a delayed background job. This ensures no record enters the pending review queue without an assigned confidence score.
