# syntax=docker/dockerfile:1
# Build context is the REPOSITORY ROOT:  docker build -f backend/Dockerfile .

# Stage 1: optional native accelerator (the app works without it).
FROM python:3.12-slim AS native
RUN apt-get update && apt-get install -y --no-install-recommends g++ make && rm -rf /var/lib/apt/lists/*
COPY services/cpp-accelerator /build
RUN make -C /build

# Stage 2: runtime. The repo-relative layout is preserved so migrations, sample data and the accelerator are found.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 NEXUS_DATA_DIR=/data
RUN useradd --system --uid 10001 --home-dir /srv nexus && mkdir -p /data && chown nexus /data
WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY database /srv/database
COPY data/sample /srv/data/sample
COPY --from=native /build/build/libnexus_accel.so /srv/services/cpp-accelerator/build/libnexus_accel.so
USER nexus
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
