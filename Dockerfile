FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY worker.py ./
RUN useradd -r -u 10001 worker
USER worker
ENV PORT=8765 PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["python","worker.py"]