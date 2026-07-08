# Root-level Dockerfile, used specifically for single-container hosts like
# Hugging Face Spaces, which require a file literally named "Dockerfile" at
# the repo root (no custom filename support via metadata). This builds the
# React frontend, then copies its static output into the FastAPI backend's
# app/static/ directory so one uvicorn process serves both the UI and the
# API on one port -- see the static-serving block at the bottom of
# backend/app/main.py.
#
# This is separate from backend/Dockerfile + frontend/Dockerfile, which are
# for the two-container docker-compose (VPS) deployment -- both paths stay
# available, use whichever fits where you're hosting.
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /frontend/dist ./app/static

# Hugging Face Spaces expects the container to listen on 7860 by default.
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
