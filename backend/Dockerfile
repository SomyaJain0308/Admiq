FROM python:3.13-slim

WORKDIR /app

# copy requirements first (from backend/, since context is root now)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# copy the rest of the backend code
COPY backend/ ./backend/

EXPOSE 8000

CMD ["fastapi", "dev", "backend/app/main.py", "--host", "0.0.0.0", "--port", "8000"]