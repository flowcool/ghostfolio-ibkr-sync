FROM python:3.12-slim

WORKDIR /app

# Install supercronic for cron support
ARG SUPERCRONIC_VERSION=v0.2.44
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" && \
    chmod +x "supercronic-linux-${TARGETARCH}" && \
    mv "supercronic-linux-${TARGETARCH}" /usr/local/bin/supercronic && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ibkr_to_ghostfolio.py .

# Default mount point for the mapping file
VOLUME ["/app/mapping.yaml"]

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create a non-root service account and hand ownership of /app to it.
# entrypoint.sh writes /app/crontab at runtime — appuser must own /app.
# Note: bind-mounted files (e.g. mapping.yaml) must be world-readable
# (o+r) on the host, or the container will fail to read them.
RUN adduser --system --no-create-home --gecos "" appuser \
    && chown -R appuser:appuser /app

# VOLUME is declared after chown so the ownership intent is visible in
# layer order. The mount point itself is still /app/mapping.yaml.
VOLUME ["/app/mapping.yaml"]

USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
