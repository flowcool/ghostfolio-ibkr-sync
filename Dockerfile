FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

WORKDIR /app

# Install supercronic for cron support.
# SHA256 of each release binary, verified against the official release asset.
# When bumping SUPERCRONIC_VERSION, update both sums — dependabot does not track
# this download, so a stale sum fails the build (which is the intended guard).
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA256SUM_amd64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256SUM_arm64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" && \
    case "${TARGETARCH}" in \
      amd64) EXPECTED="${SUPERCRONIC_SHA256SUM_amd64}" ;; \
      arm64) EXPECTED="${SUPERCRONIC_SHA256SUM_arm64}" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    echo "${EXPECTED}  supercronic-linux-${TARGETARCH}" | sha256sum -c - && \
    chmod +x "supercronic-linux-${TARGETARCH}" && \
    mv "supercronic-linux-${TARGETARCH}" /usr/local/bin/supercronic && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# pip is build-time only; removing it keeps its vendored packages out of the
# runtime image and its scans.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip

# Set by CI from `git describe --tags --always`; logged at start
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY ibkr_to_ghostfolio.py .

COPY entrypoint.sh .
RUN chmod 0555 /app /app/entrypoint.sh \
    && chmod 0444 /app/ibkr_to_ghostfolio.py /app/requirements.txt

# Keep application files owned by root; runtime crontabs live under /tmp.
# Stable IDs let operators grant access to read-only bind mounts without relying
# on world permissions or a distro-assigned system UID.
RUN addgroup --gid 10001 appuser \
    && adduser --uid 10001 --no-create-home --gecos "" --ingroup appuser \
        --disabled-password --shell /usr/sbin/nologin appuser

USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
