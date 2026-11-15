FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Source code contains no secrets and must be readable by the
# unprivileged runtime UID/GID selected in Compose.
RUN chmod -R a+rX /app/src

ENTRYPOINT ["python", "/app/src/main.py"]
