#!/usr/bin/env bash
# build.sh — Render build hook for CarbonBridge backend.
# This script is executed during the build phase on Render.
set -o errexit

echo "==> Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Build complete."
