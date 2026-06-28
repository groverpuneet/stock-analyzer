# dagster/Dockerfile — Python 3.9 image with all stock-analyzer + Dagster deps
#
# NOTE: First build takes ~15-20 min on M1 Mac due to PyTorch (~2.5GB).
# After that, layer cache makes rebuilds fast (deps change rarely).
#
# Used by docker-compose services: user-code, dagster-webserver, dagster-daemon
# The same image runs with different CMD overrides per service.

FROM python:3.9-slim

# System deps: lxml needs libxml2/libxslt; Playwright needs various libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt1-dev \
    libpq-dev \
    gcc \
    g++ \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/dagster/app

# Install Python deps in two layers:
# Layer 1 — project requirements (changes less often)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2 — packages in venv but not in requirements.txt + dagster packages
# (torch is large; split so layer cache survives most other changes)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir \
    transformers \
    feedparser \
    flashtext \
    rapidfuzz \
    pnsea \
    nsepython \
    scikit-learn

# Dagster packages (webserver + daemon in same image for simplicity)
RUN pip install --no-cache-dir \
    dagster \
    dagster-webserver \
    dagster-postgres

# Install Playwright browser for Kite auto-login
RUN playwright install --with-deps chromium

# Copy project code (when running without volume mount, e.g. standalone build)
COPY . .

# Default: run as user-code gRPC server
EXPOSE 4000
CMD ["dagster", "code-server", "start", "--host", "0.0.0.0", "--port", "4000", \
     "-f", "/opt/dagster/app/dagster/repository.py"]
