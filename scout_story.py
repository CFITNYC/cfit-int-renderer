# CFIT Scout STAY GROUNDED stories (2026-10-26). Private previews only; publishing stays off.
#
# scout_source_check : looks at one source video (low resolution, nothing kept) and returns its length, how much
#                      is moving every half second (for picking setup / challenge / win), and whether it looks like a
#                      FINISHED EDIT rather than raw footage (your opening/closing inside it, or several hard cuts).
# scout_story_short  : opening -> SETUP (hook line) -> CHALLENGE -> WIN (payoff line) -> closing, one continuous video:
#                      720x1280, 30 fps, BT.709, one silent stereo track; series tag + title band, CFIT bar.
#                      layout "v2" (2026-10-27): nothing is ever drawn on the footage. The footage sits in its own window;
#                      the hook, payoff and (once the voiceover exists) word-by-word captions go in a caption area below it.
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
    """Movement and brightness every half second (brightness 0-255; under ~25 is a black or nearly black picture)."""
    frames = gray_frames(path, 0, min(seconds, 120), fps=2, w=48, h=84)
    motion = [0.0]
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        motion.append(round(sum(abs(x - y) for x, y in zip(a[::5], b[::5])) / len(a[::5]), 2))
    luma = [round(sum(f) / len(f), 1) for f in frames]
    return motion, luma

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
        motion, luma = motion_profile(src, dur)
        return {"status": "SOURCE_CHECKED", "publishing_enabled": False, "duration": round(dur, 2), "fps": 2,
                "motion": motion, "luma": luma, "opening_match": opening_match, "closing_match": closing_match,
                "cuts": cuts, "finished_edit": bool(reasons), "reasons": reasons}

# ---- layout v2: footage window + caption area ----
V2_TOP, V2_BAR, V2_ZONE = 150, 96, 230
V2_WIN = 1280 - V2_TOP - V2_BAR - V2_ZONE      # 804 px of footage
V2_ZONE_Y = V2_TOP + V2_WIN                    # 954
FONT_NAME = "DejaVu Sans"
GOLD_ASS = "&H0050BEF2&"                       # #F2BE50 in ASS colour order
MAX_WORDS = 140

def video_size(path):
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    return (int(m[1]), int(m[2])) if m else (720, 1280)

def window_filter(idx, src_w, src_h, label, tag):
    """Wide clips fill the window (centre crop). Tall clips are shown whole, with a soft blurred copy behind."""
    if src_w / src_h >= 0.9:
        return f"[{idx}:v]scale=720:{V2_WIN}:force_original_aspect_ratio=increase,crop=720:{V2_WIN},{tag}[{label}]"
    return (f"[{idx}:v]split[{label}a][{label}b];"
            f"[{label}a]scale=720:{V2_WIN}:force_original_aspect_ratio=increase,crop=720:{V2_WIN},gblur=sigma=28,eq=brightness=-0.12[{label}bg];"
            f"[{label}b]scale=720:{V2_WIN}:force_original_aspect_ratio=decrease[{label}fg];"
            f"[{label}bg][{label}fg]overlay=(W-w)/2:(H-h)/2,{tag}[{label}]")

def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

def ass_escape(text):
    return str(text).replace("\\", "").replace("{", "(").replace("}", ")")

def check_words(words, story_len):
    """Spoken words with exact times on the story timeline (from the voice service): [{start, end, text}]."""
    if not words:
        return []
    if not isinstance(words, list) or len(words) > MAX_WORDS:
        raise ValueError("Caption words must be a list of at most 140 words")
    out = []
    for w in words:
        a, z, txt = float(w.get("start", -1)), float(w.get("end", -1)), clean(w.get("text"), 24)
        if not txt:
            continue
        if not (0 <= a <= z <= story_len + 0.05):
            raise ValueError("A caption word is timed outside the story")
        out.append((a, z, txt))
    return out

def captions_ass(path, story_len, hook="", payoff="", setup_end=0.0, win_start=0.0, words=()):
    """Caption area text: hook (white) over the setup, payoff (gold) over the win, or, with a voiceover,
    the spoken words up to 3 at a time with the word being spoken in gold. Always below the footage."""
    cy = V2_ZONE_Y + V2_ZONE // 2
    lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280", "WrapStyle: 2", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{FONT_NAME},62,&H00FFFFFF,&H00FFFFFF,&H00391210,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,40,40,0,1",
             f"Style: Line,{FONT_NAME},52,&H00FFFFFF,&H00FFFFFF,&H00391210,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1",
             "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    pos = f"{{\\pos(360,{cy})}}"
    if words:
        groups = [list(words[i:i + 3]) for i in range(0, len(words), 3)]
        for gi, g in enumerate(groups):
            hold = groups[gi + 1][0][0] if gi + 1 < len(groups) else story_len
            for k, (a, z, _) in enumerate(g):
                end = g[k + 1][0] if k + 1 < len(g) else (hold if hold - z < 1.0 else z + 0.3)   # stay through short pauses
                text = " ".join((f"{{\\c{GOLD_ASS}}}{ass_escape(w)}{{\\c&H00FFFFFF&}}" if j == k else ass_escape(w)) for j, (_, _, w) in enumerate(g))
                lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(min(end, story_len))},Cap,,0,0,0,,{pos}{text}")
    else:
        if hook:
            lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(setup_end)},Line,,0,0,0,,{pos}{ass_escape(hook).replace(chr(10), chr(92) + 'N')}")
        if payoff:
            lines.append(f"Dialogue: 1,{ass_time(win_start)},{ass_time(story_len)},Line,,0,0,0,,{pos}{{\\c{GOLD_ASS}}}{ass_escape(payoff).replace(chr(10), chr(92) + 'N')}")
    pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

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
    if job.get("layout") == "v2":
        return render_story_v2(job, get)
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


def render_story_v2(job, get=fetch):
    """Layout v2: navy band (series + title), footage window (nothing drawn on it), caption area, CFIT bar."""
    words_in = job.get("words") or []
    if words_in:   # with a voiceover the spoken captions tell the story; hook and payoff are not shown
        job = {**job, "hook": job.get("hook") or "-", "payoff": job.get("payoff") or "-"}
    segs, hook, payoff, story_len = check_story(job)
    words = check_words(words_in, story_len)
    lens = [float(s["end"]) - float(s["start"]) for s in segs]
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
                            "bar": "CFIT METHOD  |  CREATIVE FITNESS NYC"}.items():
            (t / f"{name}.txt").write_text(value)
        captions_ass(t / "captions.ass", story_len, "" if words else wrap(hook), "" if words else wrap(payoff), lens[0], lens[0] + lens[1], words)
        args = [FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(first)]
        for s in segs:
            args += ["-ss", f"{float(s['start']):.3f}", "-t", f"{float(s['end']) - float(s['start']):.3f}", "-i", str(srcs[s["signed_url"]])]
        args += ["-i", str(last), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        colour = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
        tag = f"{colour},setsar=1,fps={FPS},format=yuv420p"
        fit = f"scale={SIZE}:force_original_aspect_ratio=decrease,pad={SIZE}:(ow-iw)/2:(oh-ih)/2:color=black,{tag}"
        windows = ";".join(window_filter(i + 1, *video_size(srcs[s["signed_url"]]), f"w{i}", tag) for i, s in enumerate(segs))
        story = (f"{windows};[w0][w1][w2]concat=n=3:v=1:a=0,pad=720:1280:0:{V2_TOP}:color=0x0B0D26,{tag},"
                 f"drawbox=x=0:y=0:w=iw:h={V2_TOP}:color=0x101239@1:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'series.txt'}':fontsize=22:fontcolor=0xF2BE50:x=(w-text_w)/2:y=34,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'title.txt'}':fontsize=30:fontcolor=white:x=(w-text_w)/2:y=76,"
                 f"drawbox=x=0:y={V2_ZONE_Y}:w=iw:h=3:color=0xF2BE50@0.85:t=fill,"
                 f"subtitles='{t / 'captions.ass'}',"
                 f"drawbox=x=0:y=ih-{V2_BAR}:w=iw:h={V2_BAR}:color=black@0.85:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'bar.txt'}':fontsize=21:fontcolor=white:x=(w-text_w)/2:y=h-62[mid]")
        graph = f"[0:v]{fit}[a];{story};[4:v]{fit}[c];[a][mid][c]concat=n=3:v=1:a=0[v]"
        args += ["-filter_complex", graph, "-map", "[v]", "-map", "5:a", "-shortest",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                 "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)]
        subprocess.run(args, check=True, timeout=150, capture_output=True)
        return out.read_bytes()
