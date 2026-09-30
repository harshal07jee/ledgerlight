FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY apps/api/requirements.txt /app/apps/api/
RUN pip install --no-cache-dir -r apps/api/requirements.txt

# Copy application source code
COPY packages /app/packages
COPY apps/api /app/apps/api
COPY data/seeds /app/data/seeds
COPY pytest.ini /app/

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
