"""Intake trim (Nick: "Approved", Nov 5 2026): a shorter copy of one waiting upload. Private, admin-only; publishing stays off.

intake_trim_save : downloads the upload's current file, cuts start to end exact to the frame, checks the result, and stores it
                   straight in private storage through a one-time signed upload link. Answers with facts, never the video, so
                   a large clip is never held in memory here or in the function that called this. This module never deletes
                   anything: the caller switches the upload to the new file, then removes the old one.
"""
import json, os, pathlib, subprocess, tempfile, time, urllib.parse, urllib.request

import scout_story as ss   # shared helpers (looked up at call time, so tests can swap them)

MIN_SECONDS, MAX_SECONDS = 2.0, 120.0   # the part kept
MAX_SOURCE_BYTES = 250_000_000          # a little over the largest waiting upload (204 MB), and the project's file limit
LENGTH_TOLERANCE = 0.25                 # the new file must be this close to the part asked for
BUDGET_SECONDS = 120                    # the function waits 145 s: past this nothing is uploaded, so no file arrives after it gave up
UPLOAD_TIMEOUT = 20
CRF = "20"                              # looks the same as the original and comes out smaller; Reframe's 17 came out bigger

def _intake_link(url, prefix, label):
    p = urllib.parse.urlsplit(url or "")
    path = urllib.parse.unquote(p.path)
    if p.scheme != "https" or p.hostname != ss.HOST or not path.startswith(prefix + "cfit-exercise-videos/intake/"):
        raise ValueError(label)

def check_job(job):
    if job.get("mode") != "intake_trim_save" or job.get("publishing_enabled") is not False:
        raise ValueError("Private trim required")
    _intake_link(job.get("signed_url"), "/storage/v1/object/sign/", "Private upload link required")
    _intake_link(job.get("upload_url"), "/storage/v1/object/upload/sign/", "Private storage link required")
    if not urllib.parse.urlsplit(job["upload_url"]).path.endswith(".mp4"):
        raise ValueError("Private storage link required")
    start, end = float(job.get("start", -1)), float(job.get("end", -1))
    if not (0 <= start < end) or not MIN_SECONDS <= round(end - start, 3) <= MAX_SECONDS:
        raise ValueError(f"Choose a part of {MIN_SECONDS:g}-{MAX_SECONDS:g} seconds")
    return start, end

def download(url, dest):
    with urllib.request.urlopen(url, timeout=45) as r, open(dest, "wb") as f:
        n = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                return
            n += len(chunk)
            if n > MAX_SOURCE_BYTES:
                raise ValueError("Video over 250 MB")
            f.write(chunk)

def cut_args(src, out, start, seconds):
    """Exact to the frame: seek first, then encode only the part kept, so the time depends on the part, not the whole video.
    ffmpeg turns iPhone clips upright by itself; no colour filter, so the source's colour tags (HDR included) carry over."""
    return [ss.FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", CRF, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-map_metadata", "-1", "-movflags", "+faststart", str(out)]

def upload(url, path):
    req = urllib.request.Request(url, method="PUT", data=open(path, "rb"),
                                 headers={"Content-Type": "video/mp4", "Content-Length": str(path.stat().st_size), "x-upsert": "false"})
    try:
        with urllib.request.urlopen(req, timeout=UPLOAD_TIMEOUT) as r:
            if not 200 <= r.status < 300:
                raise ValueError("Could not store the trimmed clip")
    finally:
        req.data.close()

def intake_trim(job, get=None, put=None):
    start, end = check_job(job)
    began = time.monotonic()
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        src, out = t / "source", t / "trimmed.mp4"
        (get or download)(job["signed_url"], src)
        dur = ss.duration(src)
        if end > dur + 0.05:
            raise ValueError("The part ends after the video")
        want = min(end, dur) - start
        made = subprocess.run(cut_args(src, out, start, want), capture_output=True,
                              timeout=max(5, BUDGET_SECONDS - (time.monotonic() - began)))
        if made.returncode != 0:
            print("intake trim stopped:", made.stderr[-500:].decode("utf-8", "replace"), flush=True)
            raise ValueError("The cut stopped. Nothing was changed.")
        if not out.exists() or out.stat().st_size < 2000:
            raise ValueError("The cut produced no video. Nothing was changed.")
        got = ss.duration(out)
        if abs(got - want) > LENGTH_TOLERANCE:
            raise ValueError(f"The cut came out {got:.1f} s, not {want:.1f} s. Nothing was changed.")
        if time.monotonic() - began > BUDGET_SECONDS:
            raise ValueError("The cut took too long. Nothing was changed.")
        width, height = ss.video_size(out)
        size = out.stat().st_size
        (put or upload)(job["upload_url"], out)
    return {"status": "TRIM_SAVED", "publishing_enabled": False, "source_seconds": round(dur, 2), "seconds": round(got, 2),
            "width": width, "height": height, "bytes": size}
