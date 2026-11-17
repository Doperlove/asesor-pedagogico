FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# util-linux aporta `unshare` para el modo de sandbox con namespace de red vacío
RUN apt-get update && apt-get install -y --no-install-recommends util-linux && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY static ./static
COPY sample_data ./sample_data
COPY scripts ./scripts

RUN useradd --create-home --uid 1000 asesor && mkdir -p /app/data && chown -R asesor /app/data
USER asesor
ENV STORAGE_DIR=/app/data/storage PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/salud')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
