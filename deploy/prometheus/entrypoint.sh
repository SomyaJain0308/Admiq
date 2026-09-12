#!/bin/sh
# Render (and Prometheus itself) don't do $VAR interpolation inside
# prometheus.yml, so this substitutes the placeholders in
# prometheus.yml.template with real env var values at container start,
# then hands off to the real Prometheus binary.
set -e

: "${BACKEND_METRICS_TARGET:?BACKEND_METRICS_TARGET is not set - see deploy/README.md}"
: "${REDIS_EXPORTER_TARGET:?REDIS_EXPORTER_TARGET is not set - see deploy/README.md}"
: "${SUPABASE_METRICS_PASSWORD:?SUPABASE_METRICS_PASSWORD is not set - see deploy/README.md}"

sed \
  -e "s|__BACKEND_METRICS_TARGET__|${BACKEND_METRICS_TARGET}|g" \
  -e "s|__REDIS_EXPORTER_TARGET__|${REDIS_EXPORTER_TARGET}|g" \
  -e "s|__SUPABASE_METRICS_PASSWORD__|${SUPABASE_METRICS_PASSWORD}|g" \
  /etc/prometheus/prometheus.yml.template > /etc/prometheus/prometheus.yml

exec /bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.listen-address=0.0.0.0:9090
