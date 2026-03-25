FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg and other connectors
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 3800

CMD ["uvicorn", "datagen.api.server:app", "--host", "0.0.0.0", "--port", "3800"]
