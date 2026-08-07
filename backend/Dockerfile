FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip uninstall -y opencv-python \
    && pip install --no-cache-dir --force-reinstall opencv-python-headless==5.0.0.93

COPY backend/ ./backend/

# create a non-root user and switch to it
RUN useradd --create-home appuser
# create the prometheus dir and hand ownership to appuser
RUN mkdir -p /tmp/prometheus_multiproc && chown -R appuser:appuser /tmp/prometheus_multiproc
USER appuser

EXPOSE 8000

CMD ["fastapi", "dev", "backend/app/main.py", "--host", "0.0.0.0", "--port", "8000"]