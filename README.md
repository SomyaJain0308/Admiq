source backend/.venv/bin/activate
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
mkdir -p /tmp/prometheus_multiproc
rm -f /tmp/prometheus_multiproc/*   # clear stale data from previous runs
fastapi dev backend/main.py



source backend/.venv/bin/activate
export PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc
celery -A backend.backgroundTasks.celery_app worker --loglevel=info --concurrency=1



source backend/.venv/bin/activate
cd backend
curl -X POST "http://127.0.0.1:8000/router/colleges/1/documents" -F "uploaded_by=1" -F "file=@test.pdf"
curl "http://127.0.0.1:8000/router/colleges/1/documents/1"