FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements-render.txt ./backend/requirements-render.txt
RUN pip install --no-cache-dir -r backend/requirements-render.txt

COPY backend/ ./backend/

# create a non-root user and switch to it
RUN useradd --create-home appuser
# create the prometheus dir and hand ownership to appuser
RUN mkdir -p /tmp/prometheus_multiproc && chown -R appuser:appuser /tmp/prometheus_multiproc
RUN mkdir -p /tmp/prometheus_multiproc /tmp/celerybeat && chown -R appuser:appuser /tmp/prometheus_multiproc /tmp/celerybeat
USER appuser

EXPOSE 8000

CMD ["fastapi", "run", "backend/app/main.py", "--host", "0.0.0.0", "--port", "8000"]