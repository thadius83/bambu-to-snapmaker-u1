# ---- Stage 1: build the Svelte frontend ------------------------------------
FROM node:22-alpine AS frontend-build

ARG VITE_SITE_URL=https://u1convert.com
ENV VITE_SITE_URL=${VITE_SITE_URL}
ARG VITE_GA_MEASUREMENT_ID=
ENV VITE_GA_MEASUREMENT_ID=${VITE_GA_MEASUREMENT_ID}
ARG VITE_CF_BEACON_TOKEN=
ENV VITE_CF_BEACON_TOKEN=${VITE_CF_BEACON_TOKEN}

WORKDIR /build/frontend
COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime -----------------------------------------------
FROM python:3.14-slim AS runtime

# Minimal system deps for zipfile / pillow (thumbnails) if ever needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (cached layer).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application sources.
COPY backend/ ./backend/
COPY profiles/ ./profiles/

# Pull in the built frontend.
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# Create runtime directories (volumes will be mounted over these).
RUN mkdir -p /app/user_profiles /app/rules /app/tmp /app/outputs /app/feedback /app/bambu_profiles

# Environment defaults (override in docker-compose or at run time).
ENV PYTHONPATH=/app/backend \
    U13MF_APP_ROOT=/app \
    U13MF_PROFILES=/app/profiles \
    U13MF_BAMBU_PROFILES=/app/bambu_profiles \
    U13MF_FEEDBACK=/app/feedback \
    U13MF_USER_PROFILES=/app/user_profiles \
    U13MF_RULES=/app/rules \
    U13MF_TMP=/app/tmp \
    U13MF_FRONTEND_DIST=/app/frontend/dist \
    MAX_UPLOAD_MB=100 \
    CLEANUP_TEMP_AFTER_SECONDS=300 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Non-root user for least-privilege operation.
# Entrypoint starts as root to chown bind-mount paths, then drops to this UID.
RUN useradd -m -u 1000 converter
RUN chown -R converter:converter /app

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

# Entrypoint normalises bind-mount ownership, then drops to converter via gosu.
# tini stays as PID 1 inside the gosu invocation for signal forwarding.
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
