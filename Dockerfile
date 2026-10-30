# FairProctor in one image: the FastAPI backend serving the built React app, with the compilers the coding test runs
# (g++, a JDK, Node; Python is the image's own). Used by docker-compose.yml locally and by Render in production.

# ---- 1. build the frontend into /web/dist
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. the app
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ default-jdk-headless nodejs \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ backend/
COPY fairproctor/ fairproctor/
COPY pilot/ pilot/
COPY data/generate.py data/generate.py
COPY --from=web /web/dist frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh && rm -rf backend/data backend/tests

# The server runs as root inside the container on purpose: the code runner starts every candidate program as the
# unprivileged "nobody" user with CPU, memory, file and process limits, which needs root to switch users. Candidate
# programs then cannot read the server's files, its environment (secrets) or other processes.
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
