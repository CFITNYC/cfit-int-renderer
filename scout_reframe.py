"""Library Reframe: a tall (9:16) portrait copy of a wide library video. Private, admin-only modes; publishing stays off.

scout_reframe_measure : looks at one library video (low resolution, nothing kept) and returns its size, length and, for
                        every second, where things move left to right (fractions of the width). Optionally a few small
                        still frames for the optional AI Reframe. Free (no AI).
scout_reframe_preview : a small low-resolution preview of the tall crop (box path per second), nothing saved.
scout_reframe_save    : the full-quality tall crop as a NEW mp4 (no sound). The caller stores it beside the original;
                        this module only ever reads the original.
"""
import base64, subprocess, tempfile, pathlib

import scout_story as ss   # shared helpers (looked up at call time, so tests can swap them)

MAX_SECONDS = 180          # longest library video that can be measured
MAX_CROP_SECONDS = 120     # longest part that can be previewed or saved
MEASURE_W, MEASURE_H, MEASURE_FPS = 96, 54, 4
LEVEL = 0.1                # movement counts at 10% of the clip's strongest movement
AI_FRAMES_MAX = 8

def _private(job, mode):
    if job.get("mode") != mode or job.get("publishing_enabled") is not False:
        raise ValueError("Private reframe required")
    url = str(job.get("signed_url") or "")
    if "/storage/v1/object/sign/cfit-exercise-videos/" not in url:
        raise ValueError("Private library video required")
    return url

def box_width(w, h):
    """The tall box's width in pixels (9:16 of the full height, even)."""
    return min(w, int(round(h * 9 / 16 / 2)) * 2)

def _gray(path, seconds):
    args = [ss.FFMPEG, "-nostdin", "-v", "error", "-t", f"{seconds:.2f}", "-i", str(path),
            "-vf", f"fps={MEASURE_FPS},scale={MEASURE_W}:{MEASURE_H},format=gray", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    raw = subprocess.run(args, capture_output=True, check=True, timeout=150).stdout
    n = MEASURE_W * MEASURE_H
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]

def movement_by_second(frames, fps=MEASURE_FPS, w=MEASURE_W, h=MEASURE_H):
    """Per second: (left, right) of where things move, as fractions of the width, or None when nothing clearly moves."""
    per = {}
    for i, (p, q) in enumerate(zip(frames, frames[1:])):
        col = [0.0] * w
        for r in range(h):
            row_p, row_q = p[r * w:(r + 1) * w], q[r * w:(r + 1) * w]
            for c in range(w):
                col[c] += abs(row_p[c] - row_q[c])
        sec = (i + 1) // fps
        acc = per.setdefault(sec, [[0.0] * w, 0])
        acc[0] = [a + b / h for a, b in zip(acc[0], col)]
        acc[1] += 1
    if not per:
        return []
    energy = {s: [v / n for v in e] for s, (e, n) in per.items()}
    smooth = {s: [sum(e[max(0, c - 1):c + 2]) / len(e[max(0, c - 1):c + 2]) for c in range(w)] for s, e in energy.items()}
    peak = max(max(e) for e in smooth.values())
    level = max(peak * LEVEL, 1.0)        # sensitive: a head or hand that only moves a little still counts
    raw = []
    for s in range(max(smooth) + 1):
        e = smooth.get(s)
        cols = [c for c, v in enumerate(e or []) if v >= level]
        raw.append((cols[0] / w, (cols[-1] + 1) / w) if cols else None)
    out = []                              # each second also keeps where things moved just before and after it (the body
    for s in range(len(raw)):             # holds still at the turn of a rep, e.g. the head at the bottom of a hinge)
        near = [x for x in raw[max(0, s - 1):s + 2] if x and x[1] - x[0] < 0.9]
        if raw[s] and raw[s][1] - raw[s][0] >= 0.9:
            near = [raw[s]]               # the whole picture changing (a cut or a fade) stays as it is
        out.append([round(min(x[0] for x in near), 4), round(max(x[1] for x in near), 4)] if near and raw[s] else None)
    return out

def _thumbs(path, dur, count):
    out = []
    for k in range(count):
        t = dur * (k + 0.5) / count
        jpg = subprocess.run([ss.FFMPEG, "-nostdin", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                              "-vf", "scale=384:-2", "-q:v", "6", "-f", "image2", "-c:v", "mjpeg", "pipe:1"], capture_output=True, timeout=30).stdout
        if jpg:
            out.append({"t": round(t, 2), "jpeg_base64": base64.b64encode(jpg).decode()})
    return out

def reframe_measure(job, get=None):
    url = _private(job, "scout_reframe_measure")
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "source"
        (get or ss.fetch)(url, src)
        dur = ss.duration(src)
        if not 1.0 <= dur <= MAX_SECONDS:
            raise ValueError(f"Video must be 1-{MAX_SECONDS} seconds")
        w, h = ss.video_size(src)
        seconds = movement_by_second(_gray(src, dur))
        frames = min(int(job.get("ai_frames") or 0), AI_FRAMES_MAX)
        return {"status": "REFRAME_MEASURED", "publishing_enabled": False, "width": w, "height": h, "duration": round(dur, 2),
                "box": box_width(w, h), "box_frac": round(box_width(w, h) / w, 4), "seconds": seconds,
                **({"frames": _thumbs(src, dur, frames)} if frames > 0 else {})}

def crop_x_expr(path, start, w, box):
    """ffmpeg crop x for the box path [[t, centre], ...] (source seconds, centre as a fraction of the width), straight lines
    between keyframes, never outside the picture. t in the expression starts at 0 at `start`."""
    pts = [(float(t) - start, float(c) * w - box / 2) for t, c in path]
    pts = [(t, min(max(x, 0.0), w - box)) for t, x in pts]
    expr = f"{pts[-1][1]:.2f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pts, pts[1:]))):
        seg = f"{x0:.2f}" if t1 - t0 < 1e-6 else f"{x0:.2f}+({x1 - x0:.2f})*(t-{t0:.3f})/{t1 - t0:.3f}"
        expr = f"if(lt(t,{t1:.3f}),{seg},{expr})"
    return f"if(lt(t,{pts[0][0]:.3f}),{pts[0][1]:.2f},{expr})"

def check_crop(job):
    start, end = float(job.get("start", 0)), float(job.get("end", 0))
    if not 0 <= start < end or end - start > MAX_CROP_SECONDS:
        raise ValueError(f"Choose a part of 0.5-{MAX_CROP_SECONDS} seconds")
    if end - start < 0.5:
        raise ValueError(f"Choose a part of 0.5-{MAX_CROP_SECONDS} seconds")
    path = job.get("path")
    if not isinstance(path, list) or not 1 <= len(path) <= 400:
        raise ValueError("A box path is required")
    clean = []
    for p in path:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("Each box point is [seconds, centre]")
        t, c = float(p[0]), float(p[1])
        if not (0 <= t <= MAX_SECONDS and 0 <= c <= 1):
            raise ValueError("Box point out of range")
        clean.append((t, c))
    clean.sort()
    return start, end, clean

def reframe_render(job, get=None):
    preview = job.get("mode") == "scout_reframe_preview"
    url = _private(job, "scout_reframe_preview" if preview else "scout_reframe_save")
    start, end, path = check_crop(job)
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        src, out = t / "source", t / "portrait.mp4"
        (get or ss.fetch)(url, src)
        dur = ss.duration(src)
        if end > dur + 0.05:
            raise ValueError("The part ends after the video")
        w, h = ss.video_size(src)
        box = box_width(w, h)
        if box >= w:
            raise ValueError("This video is already tall")
        crop = f"crop=w={box}:h={h}:x='{crop_x_expr(path, start, w, box)}':y=0"
        colour = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
        vf = f"{crop},scale=270:-2,fps=15,format=yuv420p" if preview else f"{crop},{colour},setsar=1,format=yuv420p"
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30"] if preview else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
        subprocess.run([ss.FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(src),
                        "-vf", vf, "-an", *enc, "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                       check=True, timeout=170, capture_output=True)
        data = out.read_bytes()
        if len(data) < 2000:
            raise ValueError("The crop produced no video")
        return data
