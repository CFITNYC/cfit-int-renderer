"""Library rep timing (Nov 11 2026): how long one rep of a library exercise takes, from its demonstration video.

library_rep_timing : reads one private library video (low resolution, nothing kept, nothing published) and returns
                     - a movement line (how much moves, every half second, 0-9),
                     - candidate rep cycles (leave a start pose, move, come back to it) found by rep_cycles_staging,
                     - up to 16 small still frames placed on the first cycles, so an AI can confirm what one full rep
                       (or one full drill sequence) is.
                     Free (no AI). The caller decides seconds per rep.
"""
import base64, subprocess, tempfile, pathlib

import scout_story as ss            # shared helpers (fetch, duration, size, FFMPEG), looked up at call time
from rep_cycles_staging import find_cycles

MODE = "library_rep_timing"
MAX_SECONDS = 180                    # longest library video that can be timed
FPS = 5                              # frames per second read for the movement line and the cycles
GRID_W, GRID_H = 48, 84              # tiny grey frames (enough for movement, nothing recognisable kept)
CYCLE_MIN, CYCLE_MAX = 1.0, 24.0     # one rep or one drill sequence: 1 to 24 seconds
STILLS_MAX = 16
STILL_WIDTH = 384

def _private(job):
    if job.get("mode") != MODE or job.get("publishing_enabled") is not False:
        raise ValueError("Private timing required")
    url = str(job.get("signed_url") or "")
    if "/storage/v1/object/sign/cfit-exercise-videos/" not in url:
        raise ValueError("Private library video required")
    return url

def _grey(path, seconds):
    args = [ss.FFMPEG, "-nostdin", "-v", "error", "-t", f"{seconds:.2f}", "-i", str(path),
            "-vf", f"fps={FPS},scale={GRID_W}:{GRID_H},format=gray", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    raw = subprocess.run(args, capture_output=True, check=True, timeout=150).stdout
    n = GRID_W * GRID_H
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]

def _diff(a, b):
    return sum(abs(x - y) for x, y in zip(a[::3], b[::3])) / max(1, len(a[::3]))

def movement_line(frames, fps=FPS):
    """How much moves in each half second, scaled 0-9 against the clip's own strongest half second."""
    step = max(1, fps // 2)
    raw = [_diff(frames[i - 1], frames[i]) for i in range(1, len(frames))]
    bins = [sum(raw[i:i + step]) / len(raw[i:i + step]) for i in range(0, len(raw), step)]
    top = max(bins) if bins else 0
    return [int(round(9 * b / top)) if top > 0 else 0 for b in bins]

def cycles_of(frames, fps=FPS):
    out = []
    for c in find_cycles(frames, float(fps), CYCLE_MIN, CYCLE_MAX):
        out.append({"start": round(c.start, 2), "end": round(c.end, 2), "seconds": round(c.end - c.start, 2),
                    "confidence": round(c.confidence, 2)})
    # start-to-start: the moving part plus any pause before the next rep (what a member really spends per rep)
    for a, b in zip(out, out[1:]):
        a["start_to_next_start"] = round(b["start"] - a["start"], 2)
    return out

def still_times(cycles, dur):
    """Stills on the first cycles (start, a third, two thirds, end); with no cycles, evenly over the clip."""
    end = max(0.0, float(dur) - 0.3)
    times = []
    for c in cycles[:4]:
        a, b = c["start"], c["end"]
        times += [a, a + (b - a) / 3, a + 2 * (b - a) / 3, b]
    if not times:
        times = [end * (k + 0.5) / STILLS_MAX for k in range(STILLS_MAX)]
    seen, out = set(), []
    for t in sorted(min(max(0.0, t), end) for t in times):
        k = round(t, 1)
        if k not in seen:
            seen.add(k); out.append(k)
    return out[:STILLS_MAX]

def _stills(path, times):
    out = []
    for t in times:
        jpg = subprocess.run([ss.FFMPEG, "-nostdin", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                              "-vf", f"scale={STILL_WIDTH}:-2", "-q:v", "6", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                             capture_output=True, timeout=30).stdout
        if jpg:
            out.append({"t": t, "jpeg_base64": base64.b64encode(jpg).decode()})
    return out

def rep_timing(job, get=None):
    url = _private(job)
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "source"
        (get or ss.fetch)(url, src)
        dur = ss.duration(src)
        if not 1.0 <= dur <= MAX_SECONDS:
            raise ValueError(f"Video must be 1-{MAX_SECONDS} seconds")
        w, h = ss.video_size(src)
        frames = _grey(src, dur)
        cycles = cycles_of(frames)
        stills = _stills(src, still_times(cycles, dur)) if job.get("stills") is not False else []
        return {"status": "REP_TIMING_MEASURED", "publishing_enabled": False, "width": w, "height": h,
                "duration": round(dur, 2), "fps": FPS, "movement_every_half_second": movement_line(frames),
                "cycles": cycles, "frames": stills}
