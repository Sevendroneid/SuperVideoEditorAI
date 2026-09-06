FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY web ./web
COPY tests ./tests
COPY scripts ./scripts
COPY run.py ./run.py

RUN mkdir -p /app/storage/uploads /app/storage/projects /app/storage/outputs

EXPOSE 8000
CMD ["python", "run.py"]
