FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS sqlite
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL https://www.sqlite.org/2026/sqlite-autoconf-3510300.tar.gz -o sqlite.tar.gz \
 && echo '81f5be397049b0cae1b167f2225af7646fc0f82e4a9b3c48c9ea3a533e21d77a  sqlite.tar.gz' | sha256sum -c - \
 && tar xzf sqlite.tar.gz \
 && cd sqlite-autoconf-3510300 && ./configure --prefix=/opt/sqlite --disable-static && make -j2 && make install

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/backend:/app/scripts LD_LIBRARY_PATH=/opt/sqlite/lib SHIFTPROOF_DATA_DIR=/data
COPY --from=sqlite /opt/sqlite /opt/sqlite
RUN python -c "import sqlite3; assert sqlite3.sqlite_version_info == (3,51,3), sqlite3.sqlite_version"
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend/shiftproof /app/backend/shiftproof
COPY scripts/pilot_server.py scripts/pilot_backup.py scripts/pilot_health.py scripts/pilot_retention.py /app/scripts/
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --create-home shiftproof && mkdir /data && chown shiftproof /data
USER shiftproof
EXPOSE 8000
CMD ["uvicorn","pilot_server:create_app","--factory","--host","0.0.0.0","--port","8000","--no-access-log","--proxy-headers","--forwarded-allow-ips=172.29.0.10"]
