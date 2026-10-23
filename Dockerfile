FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

WORKDIR /app

# Install supercronic for cron support.
# SHA256 of each release binary, verified against the official release asset.
# When bumping SUPERCRONIC_VERSION, update both sums — dependabot does not track
# this download, so a stale sum fails the build (which is the intended guard).
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256SUM_amd64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256SUM_arm64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
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
# The package is built from /build and installed into site-packages, so the
# runtime has no source tree to mount over; /build never reaches the final
# filesystem. pip is build-time only; removing it keeps its vendored packages
# out of the runtime image and its scans.
COPY pyproject.toml /build/pyproject.toml
COPY ghostfolio_ibkr_sync/*.py /build/ghostfolio_ibkr_sync/
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip install --no-cache-dir --no-deps /build \
    && rm -rf /build \
    && pip uninstall -y pip

# Set by CI from `git describe --tags --always`; logged at start
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY entrypoint.sh .
RUN chmod 0555 /app /app/entrypoint.sh \
    && chmod 0444 /app/requirements.txt

# Keep application files owned by root; runtime crontabs live under /tmp.
# Stable IDs let operators grant access to read-only bind mounts without relying
# on world permissions or a distro-assigned system UID.
RUN addgroup --gid 10001 appuser \
    && adduser --uid 10001 --no-create-home --gecos "" --ingroup appuser \
        --disabled-password --shell /usr/sbin/nologin appuser

USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
