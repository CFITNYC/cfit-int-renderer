# CFIT Scout STAY GROUNDED stories (2026-10-26). Private previews only; publishing stays off.
#
# scout_source_check : looks at one source video (low resolution, nothing kept) and returns its length, how much
#                      is moving every half second (for picking setup / challenge / win), and whether it looks like a
#                      FINISHED EDIT rather than raw footage (your opening/closing inside it, or several hard cuts).
# scout_story_short  : opening -> SETUP (hook line) -> CHALLENGE -> WIN (payoff line) -> closing, one continuous video:
#                      720x1280, 30 fps, BT.709, one silent stereo track; series tag + title band, CFIT bar.
import math, pathlib, re, subprocess, tempfile, urllib.parse, urllib.request

FFMPEG = "ffmpeg"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HOST = "hszormivkbqvpfgfhktm.supabase.co"
SOURCE_BUCKETS = {"cfit-exercise-videos", "cfit-social-exports"}
MAX_SOURCE_BYTES = 200_000_000
SIZE, FPS = "720:1280", 30
ROLES = ("setup", "challenge", "win")
LIMITS = {"setup": (1.0, 4.0), "challenge": (2.0, 7.0), "win": (1.5, 5.0)}
MAX_STORY_SECONDS = 13.0
HOOK_SECONDS, PAYOFF_SECONDS = 2.2, 1.8
BRAND_MATCH = 0.55   # thumbnail correlation with your opening/closing (calibrated on your own clips)
CUTS_FLAG = 3        # hard cuts inside a clip that suggest it was already edited
THUMB_W, THUMB_H = 32, 56

def fetch(url, dest):
    p = urllib.parse.urlsplit(url or "")
    if p.scheme != "https" or p.hostname != HOST or not p.path.startswith("/storage/v1/object/sign/"):
        raise ValueError("Unsigned or unsupported video link")
    bucket = p.path.split("/storage/v1/object/sign/", 1)[1].split("/", 1)[0]
    if bucket not in SOURCE_BUCKETS or pathlib.PurePosixPath(urllib.parse.unquote(p.path)).suffix.lower() not in (".mp4", ".mov", ".m4v"):
        raise ValueError("Invalid video source")
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        n = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_SOURCE_BYTES:
                raise ValueError("Video over 200 MB")
            f.write(chunk)

def duration(path):
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        raise ValueError("Could not read the video length")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

def gray_frames(path, start=0.0, seconds=None, fps=2, w=THUMB_W, h=THUMB_H):
    args = [FFMPEG, "-nostdin", "-v", "error"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    if seconds:
        args += ["-t", f"{seconds:.3f}"]
    args += ["-i", str(path), "-vf", f"fps={fps},scale={w}:{h},format=gray", "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    out = subprocess.run(args, capture_output=True, timeout=90, check=True).stdout
    size = w * h
    return [out[i * size:(i + 1) * size] for i in range(len(out) // size)]

def correlation(a, b):
    n = min(len(a), len(b))
    if not n:
        return 0.0
    ma, mb = sum(a[:n]) / n, sum(b[:n]) / n
    sab = saa = sbb = 0.0
    for x, y in zip(a[:n], b[:n]):
        dx, dy = x - ma, y - mb
        sab += dx * dy; saa += dx * dx; sbb += dy * dy
    return sab / math.sqrt(saa * sbb) if saa and sbb else 0.0

def best_match(frames, brand):
    return round(max((correlation(f, g) for f in frames for g in brand), default=0.0), 3)

def motion_profile(path, seconds):
    frames = gray_frames(path, 0, min(seconds, 120), fps=2, w=48, h=84)
    motion = [0.0]
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        motion.append(round(sum(abs(x - y) for x, y in zip(a[::5], b[::5])) / len(a[::5]), 2))
    return motion

def hard_cuts(path, seconds):
    err = subprocess.run([FFMPEG, "-hide_banner", "-t", f"{min(seconds, 120):.1f}", "-i", str(path), "-vf", "scale=160:-2,select='gt(scene,0.35)',showinfo", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=90).stderr
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", err)]

def source_check(job, get=fetch):
    if job.get("mode") != "scout_source_check" or job.get("publishing_enabled") is not False:
        raise ValueError("Private Scout check required")
    b = job.get("branding") or {}
    if b.get("opening_role") != "opening" or b.get("closing_role") != "closing":
        raise ValueError("Opening and closing roles required")
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        src, first, last = t / "source", t / "opening.mp4", t / "closing.mp4"
        get(job.get("signed_url"), src); get(b.get("opening_signed_url"), first); get(b.get("closing_signed_url"), last)
        dur = duration(src)
        opening_match = best_match(gray_frames(src, 0, min(2.0, dur), fps=6), gray_frames(first, 0, 1.0, fps=6))
        closing_match = best_match(gray_frames(src, max(0.0, dur - 2.5), 2.5, fps=6), gray_frames(last, 0, 2.0, fps=6))
        cuts = [c for c in hard_cuts(src, dur) if 0.8 < c < dur - 0.8]  # cuts at the very start/end don't count
        reasons = []
        if opening_match >= BRAND_MATCH:
            reasons.append(f"starts with your opening clip (match {opening_match:.2f})")
        if closing_match >= BRAND_MATCH:
            reasons.append(f"ends with your closing clip (match {closing_match:.2f})")
        if len(cuts) >= CUTS_FLAG:
            reasons.append(f"{len(cuts)} hard cuts, so it was already edited")
        return {"status": "SOURCE_CHECKED", "publishing_enabled": False, "duration": round(dur, 2), "fps": 2,
                "motion": motion_profile(src, dur), "opening_match": opening_match, "closing_match": closing_match,
                "cuts": cuts, "finished_edit": bool(reasons), "reasons": reasons}

def clean(s, n):
    return re.sub(r"[^A-Za-z0-9 .,!?'&#|-]", "", str(s or "")).strip()[:n]

def wrap(text, width=20):
    """Break an on-screen line into at most two balanced lines so it never touches the edges."""
    if len(text) <= width:
        return text
    words = text.split(); best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if best is None or max(len(a), len(b)) < best[0]:
            best = (max(len(a), len(b)), a + "\n" + b)
    return best[1] if best else text

def check_story(job):
    if job.get("mode") != "scout_story_short" or job.get("publishing_enabled") is not False:
        raise ValueError("Private Scout story required")
    b = job.get("branding") or {}
    if b.get("opening_role") != "opening" or b.get("closing_role") != "closing":
        raise ValueError("Opening and closing roles required")
    segs = job.get("segments")
    if not isinstance(segs, list) or [s.get("role") for s in segs] != list(ROLES):
        raise ValueError("Story needs exactly setup, challenge, win, in that order")
    total = 0.0
    for s in segs:
        a, z = float(s.get("start", -1)), float(s.get("end", -1))
        lo, hi = LIMITS[s["role"]]
        if not (0 <= a < z) or not (lo - 0.001 <= z - a <= hi + 0.001):
            raise ValueError(f"{s['role']} must be {lo:g}-{hi:g} seconds")
        total += z - a
    if total > MAX_STORY_SECONDS + 0.001:
        raise ValueError(f"Story is {total:.1f} s; the most is {MAX_STORY_SECONDS:g} s")
    hook, payoff = clean(job.get("hook"), 40), clean(job.get("payoff"), 48)
    if not hook or not payoff:
        raise ValueError("Hook and payoff lines are required")
    return segs, hook, payoff, total

def text_filter(textfile, size, color, start, end):
    return (f"drawtext=fontfile='{FONT}':textfile='{textfile}':fontsize={size}:fontcolor={color}:"
            f"x=(w-text_w)/2:y=h*0.30:line_spacing=10:box=1:boxcolor=black@0.55:boxborderw=18:enable='between(t,{start:.2f},{end:.2f})'")

def render_story(job, get=fetch):
    segs, hook, payoff, story_len = check_story(job)
    b = job["branding"]
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        first, last, out = t / "opening.mp4", t / "closing.mp4", t / "story.mp4"
        get(b["opening_signed_url"], first); get(b["closing_signed_url"], last)
        srcs = {}
        for s in segs:
            if s["signed_url"] not in srcs:
                srcs[s["signed_url"]] = t / f"src{len(srcs)}"; get(s["signed_url"], srcs[s["signed_url"]])
        for name, value in {"title": clean(job.get("title"), 40) or "CFIT METHOD", "series": clean(job.get("series"), 30) or "STAY GROUNDED",
                            "hook": wrap(hook), "payoff": wrap(payoff), "bar": "CFIT METHOD  |  CREATIVE FITNESS NYC"}.items():
            (t / f"{name}.txt").write_text(value)
        args = [FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(first)]
        for s in segs:
            args += ["-ss", f"{float(s['start']):.3f}", "-t", f"{float(s['end']) - float(s['start']):.3f}", "-i", str(srcs[s["signed_url"]])]
        args += ["-i", str(last), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        tag = f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv,setsar=1,fps={FPS},format=yuv420p"
        fit = f"scale={SIZE}:force_original_aspect_ratio=decrease,pad={SIZE}:(ow-iw)/2:(oh-ih)/2:color=black,{tag}"
        fill = f"scale={SIZE}:force_original_aspect_ratio=increase,crop={SIZE},{tag}"
        story = (f"[1:v]{fill}[s1];[2:v]{fill}[s2];[3:v]{fill}[s3];[s1][s2][s3]concat=n=3:v=1:a=0,"
                 f"drawbox=x=0:y=0:w=iw:h=150:color=0x101239@0.82:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'series.txt'}':fontsize=22:fontcolor=0xF2BE50:x=(w-text_w)/2:y=34,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'title.txt'}':fontsize=30:fontcolor=white:x=(w-text_w)/2:y=76,"
                 f"{text_filter(t / 'hook.txt', 48, 'white', 0.15, HOOK_SECONDS)},"
                 f"{text_filter(t / 'payoff.txt', 48, '0xF2BE50', story_len - PAYOFF_SECONDS, story_len)},"
                 f"drawbox=x=0:y=ih-96:w=iw:h=96:color=black@0.58:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'bar.txt'}':fontsize=21:fontcolor=white:x=(w-text_w)/2:y=h-62[mid]")
        graph = f"[0:v]{fit}[a];{story};[4:v]{fit}[c];[a][mid][c]concat=n=3:v=1:a=0[v]"
        args += ["-filter_complex", graph, "-map", "[v]", "-map", "5:a", "-shortest",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                 "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
        subprocess.run(args, check=True, timeout=150, capture_output=True)
        return out.read_bytes()
