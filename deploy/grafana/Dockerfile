FROM grafana/grafana:9.0.0

USER root
COPY grafana/provisioning /etc/grafana/provisioning
RUN chown -R grafana:grafana /etc/grafana/provisioning
USER grafana

EXPOSE 3000
