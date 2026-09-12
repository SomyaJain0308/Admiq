FROM prom/prometheus:v2.37.0

USER root
COPY deploy/prometheus/prometheus.yml.template /etc/prometheus/prometheus.yml.template
COPY deploy/prometheus/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
USER nobody

EXPOSE 9090
ENTRYPOINT ["/entrypoint.sh"]
