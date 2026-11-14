FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app

COPY requirements.txt requirements-docker.lock ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt -c requirements-docker.lock \
    && python -m pip check \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

# .dockerignore is an allowlist: credentials, private data and host environments
# never enter the build context. Frozen model/source bytes are copied unchanged.
COPY . .
RUN python scripts/check_publication.py \
    && mkdir -p /app/data/private && chown app:app /app/data/private
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import json,os,urllib.request; port=os.environ.get('APP_PORT','8000'); r=urllib.request.urlopen('http://127.0.0.1:'+port+'/api/health',timeout=3); assert json.load(r)['status']=='ok'"]
CMD ["python", "-m", "backend.server", "--host", "0.0.0.0", "--port", "8000"]
