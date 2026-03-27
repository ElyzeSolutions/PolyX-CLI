# Build stage
FROM python:3.12-alpine AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY polyx/ polyx/
RUN pip install --no-cache-dir --prefix=/install ".[ai,rich]"

# Runtime stage
FROM python:3.12-alpine
WORKDIR /app
COPY --from=builder /install /usr/local
COPY polyx/ polyx/

ENV POLYX_DATA_DIR=/data
VOLUME /data

HEALTHCHECK --interval=60s --timeout=5s \
  CMD polyx health || exit 1

ENTRYPOINT ["polyx"]
CMD ["--help"]
