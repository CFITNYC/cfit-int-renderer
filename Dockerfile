FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY worker.py private_intake_frames.py worker_integrated_STAGING.py worker_v6_repetition_detection_STAGING.py worker_v7_branded_preview_STAGING.py rep_cycles_staging.py story_visual_sampler.py worker_autonomous_private_STAGING.py scout_branded.py scout_story.py scout_reframe.py scout_framing.py ./
RUN useradd -r -u 10001 worker
USER worker
ENV PORT=8765 PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp/fontcache
EXPOSE 8765
CMD ["python","worker_integrated_STAGING.py"]