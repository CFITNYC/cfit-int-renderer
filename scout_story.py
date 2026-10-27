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
AUDIO_BUCKETS = {"cfit-int-private-audio", "cfit-social-exports"}   # music tracks; Scout's saved voice reads
MAX_SOURCE_BYTES = 200_000_000
SIZE, FPS = "720:1280", 30
ROLES = ("setup", "challenge", "win")
LIMITS = {"setup": (1.0, 4.0), "challenge": (2.0, 7.0), "win": (1.5, 5.0)}
MAX_STORY_SECONDS = 13.0
HOOK_SECONDS, PAYOFF_SECONDS = 2.2, 1.8
BRAND_MATCH = 0.55   # thumbnail correlation with your opening/closing (calibrated on your own clips)
CUTS_FLAG = 3        # hard cuts inside a clip that suggest it was already edited
THUMB_W, THUMB_H = 32, 56

def fetch(url, dest, audio=False):
    p = urllib.parse.urlsplit(url or "")
    if p.scheme != "https" or p.hostname != HOST or not p.path.startswith("/storage/v1/object/sign/"):
        raise ValueError("Unsigned or unsupported video link")
    bucket = p.path.split("/storage/v1/object/sign/", 1)[1].split("/", 1)[0]
    suffix = pathlib.PurePosixPath(urllib.parse.unquote(p.path)).suffix.lower()
    if audio:
        if bucket not in AUDIO_BUCKETS or suffix not in (".mp3", ".wav", ".mp4"):
            raise ValueError("Invalid audio source")
    elif bucket not in SOURCE_BUCKETS or suffix not in (".mp4", ".mov", ".m4v"):
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
    if job.get("layout") == "v3":
        return render_story_v3(job, get)
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


# ================= layout v3 (Stage 3, 2026-10-27): platform versions, Nick voice, music =================
# Short version (TikTok, Reels, Shorts): 9:16, the challenge as fast cuts, the voice starts over the opening logo.
# Long version (LinkedIn, Facebook): 4:5, three calm parts, the voice starts when the story starts.
# Captions follow the voice word by word (current word gold) in the caption area, never over the footage.
# Music sits low under the voice and dips while the voice speaks; loudness levelled for social media.
FRAMES = {
    "9:16": {"W": 720, "H": 1280, "TOP": 150, "BAR": 96, "ZONE": 230, "series": 22, "title": 30, "bar": 21, "cap": 62, "line": 52, "cap_chars": 16, "tag": 46, "tagbar_top": 1140},
    "4:5":  {"W": 720, "H": 900,  "TOP": 110, "BAR": 70, "ZONE": 170, "series": 18, "title": 24, "bar": 17, "cap": 50, "line": 42, "cap_chars": 20, "tag": 46, "tagbar_top": 778},
}
# End tagline (from the series settings), from TAG_SECONDS before the closing clip to the last frame: a full-width bar in
# the caption-panel navy with a thin gold top line slides in from the left (BAR_SLIDE s), then the tagline fades in
# (TAG_RISE s): the first word of each phrase in gold, the rest white. Below the spoken captions; the footage window is untouched.
TAG_SECONDS, TAG_MAX, TAG_LINE_MAX = 3.0, 60, 30
BAR_SLIDE, TAG_RISE, TAGBAR_SIDE, TAGBAR_BOTTOM = 0.6, 0.5, 0, 0      # full width, to the bottom (like the caption panel)
NAVY_ASS = "&H00391210&"                       # #101239 in ASS colour order
PANEL_ASS = "&H00260D0B&"                      # #0B0D26, the caption panel navy
# Upright footage is widened (thin soft blurred edges) only when the whole body still fits: the Long window is wide and
# short, so it gets a moderate zoom. Each clip is checked; a clip framed too tightly keeps today's width.
SIDE_EDGE, LONG_SIDE_EDGE = 18, 140            # Short: about 684 px wide; Long (4:5): about 440 px wide
BODY_HEAD_MARGIN, BODY_FEET_MARGIN = 0.03, 0.15   # room kept above the highest and below the lowest movement (planted feet don't move)
BODY_MIN_MOTION = 1.5                          # too little movement to tell where the body is: keep today's width
GOLD_LINE = 2                                  # the thin gold line (main post and tagline bar)

def tagline_lines(text):
    """None when there is no tagline; else 1-2 balanced lines, split after a sentence when possible. Refuses what won't fit."""
    if text is None or str(text).strip() == "":
        return None
    t = re.sub(r"\s+", " ", str(text)).strip()
    if len(t) > TAG_MAX or not re.fullmatch(r"[A-Za-z0-9 .,!?'&|-]+", t):
        raise ValueError(f"End tagline must be 1-{TAG_MAX} plain characters")
    if len(t) <= TAG_LINE_MAX:
        return [t]
    if "|" in t:
        parts = [x.strip() for x in t.split("|")]
        best = min(range(1, len(parts)), key=lambda i: max(len(" | ".join(parts[:i])), len(" | ".join(parts[i:]))))
        lines = [" | ".join(parts[:best]), " | ".join(parts[best:])]
        if max(len(x) for x in lines) > TAG_LINE_MAX:
            raise ValueError("End tagline is too long for two lines")
        return lines
    words = t.split(); best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = (max(len(a), len(b)) - (4 if a.endswith((".", "!", "?")) else 0), max(len(a), len(b)))
        if best is None or score < best[0]:
            best = (score, [a, b])
    if max(len(x) for x in best[1]) > TAG_LINE_MAX:
        raise ValueError("End tagline is too long for two lines")
    return best[1]
VERSION_LIMITS = {
    "short": ({"setup": (1.0, 4.0), "challenge": (2.0, 7.0), "win": (1.5, 5.0)}, 13.0),
    "long":  ({"setup": (2.0, 6.0), "challenge": (8.0, 20.0), "win": (4.0, 9.0)}, 32.0),
}
CUT_SECONDS = 1.6

def frame_geometry(frame):
    if frame not in FRAMES:
        raise ValueError("Frame must be 9:16 or 4:5")
    g = dict(FRAMES[frame])
    g["WIN"] = g["H"] - g["TOP"] - g["BAR"] - g["ZONE"]
    g["ZONE_Y"] = g["TOP"] + g["WIN"]
    return g

def challenge_cuts(start, end, cuts):
    """Fast cuts: `cuts` short pieces spread evenly across the challenge (Scout uses the same formula)."""
    length = end - start
    if cuts <= 1:
        return [(start, end)]
    piece = min(CUT_SECONDS, length / cuts)
    step = (length - piece) / (cuts - 1)
    return [(round(start + i * step, 3), round(start + i * step + piece, 3)) for i in range(cuts)]

def story_pieces(segs, cuts):
    pieces = []
    for s in segs:
        a, z = float(s["start"]), float(s["end"])
        if s["role"] == "challenge":
            pieces += [(s, x, y) for x, y in challenge_cuts(a, z, cuts)]
        else:
            pieces.append((s, a, z))
    return pieces

def check_story_v3(job):
    if job.get("mode") != "scout_story_short" or job.get("publishing_enabled") is not False:
        raise ValueError("Private Scout story required")
    version = job.get("version")
    if version not in VERSION_LIMITS:
        raise ValueError("Version must be short or long")
    b = job.get("branding") or {}
    if b.get("opening_role") != "opening" or b.get("closing_role") != "closing":
        raise ValueError("Opening and closing roles required")
    segs = job.get("segments")
    if not isinstance(segs, list) or [s.get("role") for s in segs] != list(ROLES):
        raise ValueError("Story needs exactly setup, challenge, win, in that order")
    limits, most = VERSION_LIMITS[version]
    cuts = int(job.get("challenge_cuts", 1))
    if not 1 <= cuts <= 4:
        raise ValueError("Challenge cuts must be 1-4")
    for s in segs:
        a, z = float(s.get("start", -1)), float(s.get("end", -1))
        lo, hi = limits[s["role"]]
        if not (0 <= a < z) or not (lo - 0.001 <= z - a <= hi + 0.001):
            raise ValueError(f"{s['role']} must be {lo:g}-{hi:g} seconds")
    total = sum(z - a for _, a, z in story_pieces(segs, cuts))   # the length viewers see, after the fast cuts
    if total > most + 0.001:
        raise ValueError(f"Story is {total:.1f} s; the most is {most:g} s")
    return version, segs, cuts, frame_geometry(job.get("frame") or "9:16")

def caption_groups(words, max_chars):
    """Up to 3 words on screen at a time, but only as many as fit the width (long words: 2 or 1)."""
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) == 3 or len(" ".join(x[2] for x in cur + [w])) > max_chars):
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups

def movement_rows(path, spans, w=36, h=64, fps=3):
    """(top, bottom) of where things move across the used parts of a clip, as fractions of its height; None if unclear."""
    energy, pairs = [0.0] * h, 0
    for a, z in spans:
        frames = gray_frames(path, a, z - a, fps=fps, w=w, h=h)
        for p, q in zip(frames, frames[1:]):
            pairs += 1
            for r in range(h):
                energy[r] += sum(abs(x - y) for x, y in zip(p[r * w:(r + 1) * w], q[r * w:(r + 1) * w]))
    if not pairs:
        return None
    energy = [e / pairs / w for e in energy]
    peak = max(energy)
    rows = [r for r, e in enumerate(energy) if e >= max(peak * 0.2, 1.0)]
    if peak < BODY_MIN_MOTION or not rows:
        return None
    return rows[0] / h, (rows[-1] + 1) / h

def widen_fits(rows, sw, sh, W, WIN, edge):
    """True when widening upright footage to W - 2*edge keeps the moving body, with margins, inside the window."""
    if rows is None:
        return False
    scaled_h = (W - 2 * edge) * sh / sw
    if scaled_h <= WIN:
        return True
    keep = WIN / scaled_h
    return rows[0] - BODY_HEAD_MARGIN >= (1 - keep) / 2 and rows[1] + BODY_FEET_MARGIN <= (1 + keep) / 2

def no_final_period(text):
    """On-screen text only: drop the final period(s); question and exclamation marks stay."""
    return re.sub(r"\.+$", "", text) if text else text

def tagbar_box(g):
    """(left, top, right, bottom) of the end-tagline bar: inside the edges, below the spoken captions."""
    return TAGBAR_SIDE, g["tagbar_top"], g["W"] - TAGBAR_SIDE, g["H"] - TAGBAR_BOTTOM

def captions_ass_v3(path, g, words, offset, hook="", payoff="", setup_end=0.0, win_start=0.0, story_len=0.0, video_len=0.0, tagline=None, tag_start=None):
    """words: [(start, end, text)] on the voice's own clock; shown on the video clock (offset added).
    Without a voice: hook over the setup, payoff over the win (story clock).
    tagline (1-2 lines): from tag_start (video clock) to the end, the navy bar slides in, then the tagline rises onto it.
    The spoken captions are written exactly as without a tagline."""
    cy = g["ZONE_Y"] + g["ZONE"] // 2
    hook, payoff = no_final_period(hook), no_final_period(payoff)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {g['W']}", f"PlayResY: {g['H']}", "WrapStyle: 2", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{FONT_NAME},{g['cap']},&H00FFFFFF,&H00FFFFFF,&H00391210,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,30,30,0,1",
             f"Style: Line,{FONT_NAME},{g['line']},&H00FFFFFF,&H00FFFFFF,&H00391210,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,30,30,0,1"]
    if tagline:
        lines += [f"Style: TagBar,{FONT_NAME},20,{PANEL_ASS},{PANEL_ASS},{PANEL_ASS},&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
                  f"Style: Tag,{FONT_NAME},{g['tag']},&H00FFFFFF,&H00FFFFFF,{PANEL_ASS},&H80000000,-1,0,0,0,100,100,0,0,1,1,2,5,0,0,0,1"]
    lines += ["[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    pos = f"{{\\pos({g['W'] // 2},{cy})}}"
    if words:
        timed = [(a + offset, z + offset, w) for a, z, w in words]
        groups = caption_groups(timed, g.get("cap_chars", 16))
        for gi, grp in enumerate(groups):
            hold = groups[gi + 1][0][0] if gi + 1 < len(groups) else video_len
            for k, (a, z, _) in enumerate(grp):
                end = grp[k + 1][0] if k + 1 < len(grp) else (hold if hold - z < 1.0 else z + 0.3)
                shown = [w if j < len(grp) - 1 else no_final_period(w) for j, (_, _, w) in enumerate(grp)]
                text = " ".join((f"{{\\c{GOLD_ASS}}}{ass_escape(w)}{{\\c&H00FFFFFF&}}" if j == k else ass_escape(w)) for j, w in enumerate(shown))
                lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(min(end, video_len))},Cap,,0,0,0,,{pos}{text}")
    else:
        if hook:
            lines.append(f"Dialogue: 1,{ass_time(offset)},{ass_time(offset + setup_end)},Line,,0,0,0,,{pos}{ass_escape(hook).replace(chr(10), chr(92) + 'N')}")
        if payoff:
            lines.append(f"Dialogue: 1,{ass_time(offset + win_start)},{ass_time(offset + story_len)},Line,,0,0,0,,{pos}{{\\c{GOLD_ASS}}}{ass_escape(payoff).replace(chr(10), chr(92) + 'N')}")
    if tagline:
        x0, y0, x1, y1 = tagbar_box(g)
        w, h = x1 - x0, y1 - y0
        slide, fade_end = int(BAR_SLIDE * 1000), int((BAR_SLIDE + TAG_RISE) * 1000)
        mv = lambda y: f"\\an7\\move({x0 - w},{y},{x0},{y},0,{slide})"
        sh = 14 if g["H"] > 1000 else 6                                   # soft shadow above the bar, so it lifts off the footage
        lines.append(f"Dialogue: 2,{ass_time(tag_start)},{ass_time(video_len)},TagBar,,0,0,0,,{{{mv(y0 - sh // 2)}\\1c&H000000&\\1a&H70&\\blur{sh // 2}\\p1}}m 0 0 l {w} 0 {w} {sh} 0 {sh}{{\\p0}}")
        lines.append(f"Dialogue: 3,{ass_time(tag_start)},{ass_time(video_len)},TagBar,,0,0,0,,{{{mv(y0)}\\p1}}m 0 0 l {w} 0 {w} {h} 0 {h}{{\\p0}}")
        lines.append(f"Dialogue: 4,{ass_time(tag_start)},{ass_time(video_len)},TagBar,,0,0,0,,{{{mv(y0)}\\1c{GOLD_ASS}\\p1}}m 0 0 l {w} 0 {w} {GOLD_LINE} 0 {GOLD_LINE}{{\\p0}}")
        def paint(line):   # the first word of each phrase in gold, everything else (pipes too) white
            out, first = [], True
            for w in line.split(" "):
                out.append(f"{{\\c{GOLD_ASS}}}{ass_escape(w)}{{\\c&H00FFFFFF&}}" if first and w != "|" else ass_escape(w))
                first = (w == "|")
            return " ".join(out)
        tag_text = "\\N".join(paint(x) for x in tagline)
        lines.append(f"Dialogue: 5,{ass_time(tag_start)},{ass_time(video_len)},Tag,,0,0,0,,"
                     f"{{\\an5\\pos({g['W'] // 2},{(y0 + GOLD_LINE + y1) // 2})\\alpha&HFF&\\t({slide},{fade_end},\\alpha&H00&)}}{tag_text}")
    pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

def render_story_v3(job, get=fetch):
    version, segs, cuts, g = check_story_v3(job)
    tagline = tagline_lines(job.get("end_tagline"))
    audio = job.get("audio") or {}
    b = job["branding"]
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        first, last, silent, out = t / "opening.mp4", t / "closing.mp4", t / "silent.mp4", t / "story.mp4"
        get(b["opening_signed_url"], first); get(b["closing_signed_url"], last)
        srcs = {}
        for s in segs:
            if s["signed_url"] not in srcs:
                srcs[s["signed_url"]] = t / f"src{len(srcs)}"; get(s["signed_url"], srcs[s["signed_url"]])
        pieces = story_pieces(segs, cuts)
        story_len = sum(z - a for _, a, z in pieces)
        setup_end = float(segs[0]["end"]) - float(segs[0]["start"])
        win_start = story_len - (float(segs[2]["end"]) - float(segs[2]["start"]))
        opening_len, closing_len = duration(first), duration(last)
        video_len = opening_len + story_len + closing_len
        words = []
        if audio.get("voice_signed_url"):
            offset = float(audio.get("voice_offset", 0))
            if not 0 <= offset <= opening_len + 0.25:
                raise ValueError("The voice must start during the opening or when the story starts")
            words = check_words(job.get("words") or [], video_len - offset)
        else:
            offset = opening_len
        for name, value in {"title": clean(job.get("title"), 40) or "CFIT METHOD", "series": clean(job.get("series"), 30) or "STAY GROUNDED",
                            "bar": "CFIT METHOD  |  CREATIVE FITNESS NYC"}.items():
            (t / f"{name}.txt").write_text(value)
        captions_ass_v3(t / "captions.ass", g, words, offset, "" if words else wrap(clean(job.get("hook"), 40)), "" if words else wrap(clean(job.get("payoff"), 48)),
                        setup_end, win_start, story_len, video_len, tagline, opening_len + story_len - TAG_SECONDS)
        W, H, WIN, TOP, BAR, ZONE_Y = g["W"], g["H"], g["WIN"], g["TOP"], g["BAR"], g["ZONE_Y"]
        args = [FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(first)]
        for s, a, z in pieces:
            args += ["-ss", f"{a:.3f}", "-t", f"{z - a:.3f}", "-i", str(srcs[s["signed_url"]])]
        n = len(pieces)
        args += ["-i", str(last)]
        colour = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
        tag = f"{colour},setsar=1,fps={FPS},format=yuv420p"
        fit = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0B0D26,{tag}"
        edge = SIDE_EDGE if H > 1000 else LONG_SIDE_EDGE   # the Long window is wide and short: a moderate zoom keeps the whole body
        wide = {}                                          # per clip: widen only when the whole body still fits, else today's width
        for url, path in srcs.items():
            sw0, sh0 = video_size(path)
            wide[url] = sw0 / sh0 >= 0.9 or widen_fits(movement_rows(path, [(a, z) for s, a, z in pieces if s["signed_url"] == url]), sw0, sh0, W, WIN, edge)
        def win(idx, sw, sh, label, url=None):
            if sw / sh < 0.9 and not wide.get(url, False):   # today's fit: the whole picture, wider blurred sides
                return (f"[{idx}:v]split[{label}a][{label}b];[{label}a]scale={W}:{WIN}:force_original_aspect_ratio=increase,crop={W}:{WIN},gblur=sigma=28,eq=brightness=-0.12[{label}bg];"
                        f"[{label}b]scale={W}:{WIN}:force_original_aspect_ratio=decrease[{label}fg];[{label}bg][{label}fg]overlay=(W-w)/2:(H-h)/2,{tag}[{label}]")
            if sw / sh >= 0.9:
                return f"[{idx}:v]scale={W}:{WIN}:force_original_aspect_ratio=increase,crop={W}:{WIN},{tag}[{label}]"
            return (f"[{idx}:v]split[{label}a][{label}b];[{label}a]scale={W}:{WIN}:force_original_aspect_ratio=increase,crop={W}:{WIN},gblur=sigma=28,eq=brightness=-0.12[{label}bg];"
                    f"[{label}b]scale={W - 2 * edge}:{WIN}:force_original_aspect_ratio=increase,crop={W - 2 * edge}:{WIN}[{label}fg];[{label}bg][{label}fg]overlay=(W-w)/2:(H-h)/2,{tag}[{label}]")
        windows = ";".join(win(i + 1, *video_size(srcs[s["signed_url"]]), f"w{i}", s["signed_url"]) for i, (s, _, _) in enumerate(pieces))
        story = (f"{windows};{''.join(f'[w{i}]' for i in range(n))}concat=n={n}:v=1:a=0,pad={W}:{H}:0:{TOP}:color=0x0B0D26,{tag},"
                 f"drawbox=x=0:y=0:w=iw:h={TOP}:color=0x101239@1:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'series.txt'}':fontsize={g['series']}:fontcolor=0xF2BE50:x=(w-text_w)/2:y={int(TOP * 0.22)},"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'title.txt'}':fontsize={g['title']}:fontcolor=white:x=(w-text_w)/2:y={int(TOP * 0.52)},"
                 + "".join(f"drawbox=x=0:y={TOP + 2 * i}:w=iw:h=2:color=black@{0.42 - 0.07 * i:.2f}:t=fill," for i in range(6)) +   # soft shadow under the header
                 f"drawbox=x=0:y={ZONE_Y - 1}:w=iw:h=1:color=0xF2BE50@0.35:t=fill,drawbox=x=0:y={ZONE_Y}:w=iw:h={GOLD_LINE}:color=0xF2BE50@1:t=fill,"
                 f"drawbox=x=0:y=ih-{BAR}:w=iw:h={BAR}:color=black@0.85:t=fill,"
                 f"drawtext=fontfile='{FONT}':textfile='{t / 'bar.txt'}':fontsize={g['bar']}:fontcolor=white:x=(w-text_w)/2:y=h-{int(BAR * 0.65)}[mid]")
        graph = f"[0:v]{fit}[a];{story};[{n + 1}:v]{fit}[c];[a][mid][c]concat=n=3:v=1:a=0,subtitles='{t / 'captions.ass'}'[v]"
        args += ["-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", "-movflags", "+faststart", str(silent)]
        subprocess.run(args, check=True, timeout=180, capture_output=True)
        vlen = duration(silent)
        # sound: Nick voice at its offset, music low under it (dipping while he speaks), levelled for social media
        voice, music = t / "voice", t / "music"
        mix = [FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(silent)]
        if audio.get("voice_signed_url"):
            get(audio["voice_signed_url"], voice, True); mix += ["-i", str(voice)]
        if audio.get("music_signed_url"):
            get(audio["music_signed_url"], music, True); mix += ["-stream_loop", "-1", "-i", str(music)]
        has_v, has_m = bool(audio.get("voice_signed_url")), bool(audio.get("music_signed_url"))
        ms = int(offset * 1000)
        fade = f"afade=t=in:d=0.8,afade=t=out:st={max(0.0, vlen - 1.5):.2f}:d=1.5"
        if has_v and has_m:
            f = (f"[1:a]aformat=channel_layouts=stereo,adelay={ms}|{ms},apad[vo];[vo]asplit=2[v1][vsc];"
                 f"[2:a]aformat=channel_layouts=stereo,atrim=0:{vlen:.2f},volume=0.22,{fade}[m];[m][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md];"
                 f"[v1][md]amix=inputs=2:normalize=0:duration=first,atrim=0:{vlen:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        elif has_v:
            f = f"[1:a]aformat=channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{vlen:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        elif has_m:
            f = f"[1:a]aformat=channel_layouts=stereo,atrim=0:{vlen:.2f},volume=0.5,{fade},loudnorm=I=-16:TP=-1.5:LRA=11[a]"
        else:
            f = f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=0:{vlen:.2f}[a]"
        mix += ["-filter_complex", f, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out)]
        subprocess.run(mix, check=True, timeout=120, capture_output=True)
        return out.read_bytes()
