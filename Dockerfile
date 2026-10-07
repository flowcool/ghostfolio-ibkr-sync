FROM python:3.12-slim

WORKDIR /app

# Install supercronic for cron support.
# SHA1 of each release binary, verified against the official release asset.
# When bumping SUPERCRONIC_VERSION, update both sums — dependabot does not track
# this download, so a stale sum fails the build (which is the intended guard).
ARG SUPERCRONIC_VERSION=v0.2.44
ARG SUPERCRONIC_SHA1SUM_amd64=6eb0a8e1e6673675dc67668c1a9b6409f79c37bc
ARG SUPERCRONIC_SHA1SUM_arm64=6c6cba4cde1dd4a1dd1e7fb23498cde1b57c226c
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" && \
    case "${TARGETARCH}" in \
      amd64) EXPECTED="${SUPERCRONIC_SHA1SUM_amd64}" ;; \
      arm64) EXPECTED="${SUPERCRONIC_SHA1SUM_arm64}" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    echo "${EXPECTED}  supercronic-linux-${TARGETARCH}" | sha1sum -c - && \
    chmod +x "supercronic-linux-${TARGETARCH}" && \
    mv "supercronic-linux-${TARGETARCH}" /usr/local/bin/supercronic && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set by CI from `git describe --tags --always`; logged at start
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY ibkr_to_ghostfolio.py .

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create a non-root service account and hand ownership of /app to it.
# entrypoint.sh writes /app/crontab at runtime — appuser must own /app.
# Note: bind-mounted files (e.g. mapping.yaml) must be world-readable
# (o+r) on the host, or the container will fail to read them.
RUN addgroup --system appuser \
    && adduser --system --no-create-home --gecos "" --ingroup appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
