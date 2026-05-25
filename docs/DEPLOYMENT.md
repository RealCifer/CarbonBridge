# CarbonBridge — Deployment Guide

Step-by-step instructions for deploying the CarbonBridge backend to **Render** and the frontend to **Vercel**.

---

## Architecture Overview

```
┌─────────────────┐         ┌──────────────────────┐
│   Vercel CDN    │  HTTPS  │   Render Web Service  │
│   (React SPA)   │────────▶│   (Django + Gunicorn) │
│   Frontend      │         │   Backend API         │
└─────────────────┘         └──────────┬───────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  Render Managed       │
                            │  PostgreSQL           │
                            └──────────────────────┘
```

---

## Prerequisites

- GitHub repository: `https://github.com/RealCifer/CarbonBridge`
- [Render account](https://render.com/) (free tier works)
- [Vercel account](https://vercel.com/) (free tier works)
- Git pushed to `main` branch

---

## Part 1: Backend on Render

### Option A: One-Click Deploy (render.yaml)

1. Go to [Render Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**
2. Connect your GitHub repository (`RealCifer/CarbonBridge`)
3. Render will auto-detect `render.yaml` in the repo root
4. It will provision:
   - **Web Service** (`carbonbridge-api`) — Docker-based
   - **PostgreSQL Database** (`carbonbridge-db`) — Free tier
5. Click **Apply** and wait for the first deploy

### Option B: Manual Setup

#### Step 1: Create PostgreSQL Database

1. Render Dashboard → **New** → **PostgreSQL**
2. Settings:
   - Name: `carbonbridge-db`
   - Database: `carbonbridge`
   - User: `carbonbridge_user`
   - Region: Oregon (or closest)
   - Plan: Free
3. Click **Create Database**
4. Copy the **Internal Database URL** (starts with `postgresql://`)

#### Step 2: Create Web Service

1. Render Dashboard → **New** → **Web Service**
2. Connect your GitHub repo
3. Settings:
   - Name: `carbonbridge-api`
   - Region: Same as database
   - Runtime: **Docker**
   - Docker Context: `./backend`
   - Dockerfile Path: `./backend/Dockerfile`
   - Plan: Free

4. **Environment Variables** — Add the following:

| Variable | Value |
|---|---|
| `SECRET_KEY` | *(click "Generate")* |
| `DEBUG` | `False` |
| `DATABASE_URL` | *(paste Internal DB URL from Step 1)* |
| `ALLOWED_HOSTS` | `carbonbridge-api.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | `https://carbonbridge.vercel.app` |
| `CORS_ALLOW_ALL_ORIGINS` | `False` |
| `DJANGO_SETTINGS_MODULE` | `carbonbridge.settings_production` |
| `GUNICORN_WORKERS` | `2` |
| `GUNICORN_THREADS` | `2` |

5. Click **Create Web Service**

#### Step 3: Run Initial Migrations

After the first deploy succeeds, open the **Shell** tab on the Render web service and run:

```bash
python manage.py migrate
python manage.py createsuperuser
```

#### Step 4: Verify

Visit: `https://carbonbridge-api.onrender.com/api/health/`

Expected response:
```json
{"status": "ok"}
```

---

## Part 2: Frontend on Vercel

### Step 1: Import Project

1. Go to [Vercel Dashboard](https://vercel.com/dashboard) → **Add New** → **Project**
2. Import the GitHub repository `RealCifer/CarbonBridge`
3. Configure:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### Step 2: Environment Variables

Add the following environment variable:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://carbonbridge-api.onrender.com/api` |

> **Important:** Vite bakes environment variables into the build at compile time. The `VITE_` prefix is required. Any change to `VITE_API_URL` requires a redeploy.

### Step 3: Deploy

1. Click **Deploy**
2. Vercel will:
   - Install `node_modules`
   - Run `npm run build` (TypeScript compilation + Vite bundle)
   - Deploy to CDN

### Step 4: Update Backend CORS

After the Vercel deploy, you'll get a URL like `https://carbonbridge.vercel.app` (or a random subdomain). If it differs from what was set in `CORS_ALLOWED_ORIGINS`, update the environment variable on Render:

```
CORS_ALLOWED_ORIGINS=https://your-actual-vercel-url.vercel.app
```

Then redeploy the Render service.

### Step 5: Verify

Visit the Vercel URL. The dashboard should load. If the backend is running, API calls will work (pending authentication setup).

---

## Part 3: Post-Deployment Checklist

### Backend Verification

| Check | Command / URL |
|---|---|
| Health endpoint | `GET /api/health/` → `{"status": "ok"}` |
| Database connectivity | `python manage.py dbshell` (Render Shell) |
| Static files | Visit `https://<api-url>/static/admin/css/base.css` |
| Admin panel | `https://<api-url>/admin/` (use superuser credentials) |
| Migrations applied | `python manage.py showmigrations` (Render Shell) |

### Frontend Verification

| Check | How |
|---|---|
| Dashboard loads | Visit Vercel URL |
| API connection | Open browser DevTools → Network tab → check for `200` responses to `/api/review/` calls |
| No CORS errors | Console should be free of `Access-Control-Allow-Origin` errors |

---

## Environment Variables Reference

### Backend (Render)

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | Django secret key. Use Render's "Generate" button. |
| `DEBUG` | No | `True` | **Must be `False` in production.** |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string. Auto-injected by Render when linked. |
| `ALLOWED_HOSTS` | Yes | `*` | Comma-separated. Set to your Render hostname. |
| `CORS_ALLOWED_ORIGINS` | Yes | `localhost:5173` | Comma-separated frontend origins. |
| `CORS_ALLOW_ALL_ORIGINS` | No | `False` | Set `True` only for debugging. |
| `DJANGO_SETTINGS_MODULE` | No | `carbonbridge.settings` | Set to `carbonbridge.settings_production` for production. |
| `GUNICORN_WORKERS` | No | `2` | Gunicorn worker process count. |
| `GUNICORN_THREADS` | No | `2` | Threads per worker. |

### Frontend (Vercel)

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_API_URL` | **Yes** | `http://localhost:8000/api` | Full URL to the backend API (including `/api`). |

---

## Render Free Tier Notes

> **Warning:** Render free-tier web services spin down after 15 minutes of inactivity. The first request after spin-down takes 30–60 seconds as the container cold-starts. This is expected behaviour, not a bug.

> **Warning:** Render free-tier PostgreSQL databases expire after 90 days. You will receive email warnings before expiration. Upgrade to a paid plan ($7/month) to retain the database long-term.

---

## File Reference

| File | Purpose |
|---|---|
| `backend/Dockerfile` | Multi-stage Docker build (Python 3.12 slim, gunicorn, non-root user) |
| `backend/build.sh` | Render build hook (pip install, collectstatic, migrate) |
| `backend/requirements.txt` | Python dependencies including gunicorn, whitenoise, dj-database-url |
| `backend/carbonbridge/settings.py` | Base settings with DATABASE_URL auto-detection |
| `backend/carbonbridge/settings_production.py` | Production overrides: HTTPS, HSTS, WhiteNoise, structured logging |
| `backend/.env.example` | Template for local development environment variables |
| `frontend/.env.example` | Template for Vite environment variables |
| `render.yaml` | Render Infrastructure-as-Code blueprint (web service + database) |
