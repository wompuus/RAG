FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Minimal runtime deps for common PDF/image libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit defaults
EXPOSE 8501

CMD ["bash", "docker/start-app.sh"]
