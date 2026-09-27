# SamudraVani API server. Works on Hugging Face Spaces (Docker SDK) and any Docker host.
# Secrets (set in the host's settings, never in this file):
#   COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD  satellite SST + chlorophyll
# Optional: CDSAPI_URL / CDSAPI_KEY, MOSDAC_USERNAME / MOSDAC_PASSWORD, OPENMETEO_API_KEY.
FROM python:3.12-slim

# Hugging Face runs containers as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SAMUDRAVANI_CACHE_DB=/tmp/samudravani.sqlite \
    PORT=7860
WORKDIR /home/user/app

COPY --chown=user requirements-server.txt .
RUN pip install --no-cache-dir --user -r requirements-server.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
