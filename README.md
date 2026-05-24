# CarbonBridge ESG Platform

Welcome to **CarbonBridge**, a premium enterprise-grade Environmental, Social, and Governance (ESG) and carbon auditing dashboard platform. CarbonBridge integrates a production-ready Django 5 REST backend with a modern, glassmorphic React/Vite/TypeScript frontend, creating an interactive command center for corporate sustainability metrics.

---

## Folder Layout

```
CarbonBridge/
├── backend/            # Django 5 Backend
│   ├── carbonbridge/   # Django Project settings
│   ├── core/           # Core app (Health checks, general API)
│   ├── .env.example    # Env template
│   ├── requirements.txt
│   └── manage.py
├── frontend/           # React + TS + Vite Frontend
│   ├── src/            # Application source files
│   ├── package.json
│   └── vite.config.ts
├── docs/               # System and architecture documentation
│   └── architecture.md
├── sample-data/        # ESG mock datasets
│   └── esg_sample.json
└── README.md           # Getting started guide (this file)
```

---

## Backend Installation & Setup (Django 5)

### Prerequisites
- Python 3.10 or higher
- `pip` package manager

### Steps
1. **Navigate to the Backend directory**:
   ```bash
   cd backend
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Windows PowerShell**:
     ```powershell
     .venv\Scripts\Activate.ps1
     ```
   - **Windows Command Prompt**:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install backend dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment Variables**:
   - Copy the `.env.example` file to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Adjust options inside `.env` if using a PostgreSQL instance instead of the default SQLite configuration.

6. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

7. **Start the local backend dev server**:
   ```bash
   python manage.py runserver 8000
   ```
   The API will now be active at `http://localhost:8000/`.
   Health check endpoint is live at `http://localhost:8000/api/health/`.

---

## Frontend Installation & Setup (React + TS + Vite)

### Prerequisites
- Node.js (version 18 or higher recommended)
- `npm` package manager

### Steps
1. **Navigate to the Frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install frontend dependencies**:
   ```bash
   npm install
   ```

3. **Start the Vite development server**:
   ```bash
   npm run dev
   ```
   The frontend application will boot and show the live dashboard URL (usually `http://localhost:5173`).

---

## Integration Health Check

The frontend dashboard automatically connects to the backend REST endpoint `/api/health/` using **Axios**. 
- It displays a glowing network activity pulse, measuring connection status and latency.
- Features a **Check Connection** manual refetch button.
- Handles server downtime gracefully with an error boundary diagnostic message, guiding developers on running configurations.
