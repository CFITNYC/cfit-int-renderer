# CFIT Scout framing (2026-10-31). Private, admin-only; publishing stays off.
#
# Nick's rules:
#   * Shorts are full-screen 9:16: the clip fills the whole 720x1280 frame. Never crop around part of the movement.
#   * Portrait clips are shown whole. A landscape clip may be used only if a 9:16 crop keeps the WHOLE movement
#     (every used second); otherwise Scout must not make the video and the exercise "needs reshoot in portrait".
#   * The title band and the spoken-caption box are small and see-through, and never cover the body or the movement.
#     If a band would cover it, the band shrinks first, then moves. The footage is never cropped to make room.
#   * No blurred bars or square version unless Nick chooses that.
#
# scout_framing_check : looks at the exact seconds a storyboard would use (low resolution, nothing kept) and returns,
#                       per clip, the 9:16 box, where the person moves, where the bands go, and 3 small stills of the
#                       Short as it would look. Free: no AI, no voice, nothing saved.
import base64, pathlib, subprocess, tempfile

import scout_story as ss   # shared helpers (looked up at call time, so tests can swap them)

W, H = 720, 1280
LEVEL = 0.10                        # movement counts at 10% of the clip's strongest movement (same as Reframe)
MIN_MOTION = 1.0                    # below this nothing clearly moves (grey)
HEAD_ROOM, FEET_ROOM, SIDE_ROOM = 0.06, 0.04, 0.05    # room kept around where the person moves (fractions of the source)
BODY_PAD = 14                       # px kept between a band and the person, on the 720x1280 Short
YT_BOTTOM = 0.13                    # YouTube's own title text covers the bottom of every Short
YT_RIGHT = (0.86, 0.45, 0.87)       # and its buttons the right edge: x from, y from, y to (fractions of the Short)
TITLE_HEIGHTS = (64, 52, 40)        # title band: thin, shrinks before it moves
CAPTION_SIZES = ((300, 120, 40, 12), (260, 104, 34, 11), (220, 96, 30, 10), (190, 110, 28, 8), (150, 120, 26, 7))   # box w, h, font px, characters per line
CAPTION_TOP_PREF = 0.22             # captions sit as high as they can (away from YouTube's bottom area)
BAND_ALPHA = 0.55                   # see-through navy
STILL_W, STILL_H = 180, 320
GRID_PORTRAIT, GRID_LANDSCAPE = (36, 64), (64, 36)

def _private(job):
    if job.get("mode") != "scout_framing_check" or job.get("publishing_enabled") is not False:
        raise ValueError("Private framing check required")
    segs = job.get("segments")
    if not isinstance(segs, list) or not 1 <= len(segs) <= 6:
        raise ValueError("1-6 clips required")
    for s in segs:
        a, z = float(s.get("start", -1)), float(s.get("end", -1))
        if not (0 <= a < z <= a + 30):
            raise ValueError("Each clip part must be 0-30 seconds")
        if "/storage/v1/object/sign/cfit-exercise-videos/" not in str(s.get("signed_url") or ""):
            raise ValueError("Private library or phone video required")
    return segs

def motion_grid(frames, w, h):
    """Per frame pair: column and row energy (average change), so both the whole span and each second can be measured."""
    out = []
    for p, q in zip(frames, frames[1:]):
        cols, rows = [0.0] * w, [0.0] * h
        for r in range(h):
            base = r * w
            for c in range(w):
                d = abs(p[base + c] - q[base + c])
                cols[c] += d
                rows[r] += d
        out.append(([v / h for v in cols], [v / w for v in rows]))
    return out

def _extent(energy, peak):
    idx = [i for i, e in enumerate(energy) if e >= max(peak * LEVEL, MIN_MOTION)]
    return (idx[0] / len(energy), (idx[-1] + 1) / len(energy)) if idx else None

def envelope(pairs, fps=3, start=0.0):
    """Where the person moves across these frames: ((x0, x1), (y0, y1)) as fractions of the source, plus the same per
    second ({second: (x0, x1)}) for the red-second report. None when nothing clearly moves."""
    if not pairs:
        return None
    w, h = len(pairs[0][0]), len(pairs[0][1])
    cols = [sum(p[0][c] for p in pairs) / len(pairs) for c in range(w)]
    rows = [sum(p[1][r] for p in pairs) / len(pairs) for r in range(h)]
    peak = max(max(cols), max(rows))
    if peak < MIN_MOTION:
        return None
    x, y = _extent(cols, peak), _extent(rows, peak)
    if not x or not y:
        return None
    per = {}
    for i, (c, _) in enumerate(pairs):
        sec = int(start + (i + 1) / fps)
        per.setdefault(sec, []).append(c)
    seconds = {}
    for sec, cs in per.items():
        avg = [sum(v[k] for v in cs) / len(cs) for k in range(w)]
        e = _extent(avg, peak)
        if e:
            seconds[sec] = e
    return {"x": x, "y": y, "seconds": seconds}

def merge(envs):
    envs = [e for e in envs if e]
    if not envs:
        return None
    sec = {}
    for e in envs:
        for k, (a, z) in e["seconds"].items():
            o = sec.get(k)
            sec[k] = (min(a, o[0]), max(z, o[1])) if o else (a, z)
    return {"x": (min(e["x"][0] for e in envs), max(e["x"][1] for e in envs)),
            "y": (min(e["y"][0] for e in envs), max(e["y"][1] for e in envs)), "seconds": sec}

def crop_box(sw, sh, env):
    """The 9:16 part of the source the Short shows, as fractions (x0, y0, x1, y1), or a refusal with the cut seconds.
    Portrait: the whole clip (a clip that isn't exactly 9:16 loses a sliver, and only if the movement isn't in it).
    Landscape: one fixed 9:16 box at full height, only if the whole movement fits inside it in every used second."""
    target = 9 / 16
    aspect = sw / sh
    if env is None:
        return {"ok": False, "reason": "unclear", "message": "Scout can't tell where the person moves in this clip."}
    (ex0, ex1), (ey0, ey1) = env["x"], env["y"]
    need_x0, need_x1 = max(0.0, ex0 - SIDE_ROOM), min(1.0, ex1 + SIDE_ROOM)
    need_y0, need_y1 = max(0.0, ey0 - HEAD_ROOM), min(1.0, ey1 + FEET_ROOM)
    if aspect <= target + 0.001:                     # taller than (or exactly) 9:16: keep full width, trim height evenly
        keep = aspect / target                       # fraction of the height that fits
        y0 = min(max((need_y0 + need_y1) / 2 - keep / 2, 0.0), 1.0 - keep)
        box = (0.0, y0, 1.0, y0 + keep)
        if need_y0 < box[1] - 1e-6 or need_y1 > box[3] + 1e-6:
            return {"ok": False, "reason": "too_tall", "message": "The movement doesn't fit the 9:16 frame top to bottom."}
        return {"ok": True, "box": box, "portrait": True}
    bw = target / aspect                             # wider than 9:16: a full-height box this wide
    if aspect < 1.0:                                 # portrait, but wider than 9:16 (e.g. 3:4): keep the full height
        pass
    def cut_at(x0):
        return sorted(s for s, (a, z) in env["seconds"].items() if a - SIDE_ROOM < x0 - 1e-6 or z + SIDE_ROOM > x0 + bw + 1e-6)
    centre = min(max((need_x0 + need_x1) / 2 - bw / 2, 0.0), 1.0 - bw)
    if need_x1 - need_x0 <= bw + 1e-6:
        x0 = centre
    else:                                            # it can't fit: report the fewest cut seconds a fixed box could manage
        steps = [min(i / 100, 1.0 - bw) for i in range(0, 101)]
        x0 = min(steps, key=lambda v: (len(cut_at(v)), abs(v - centre)))
    box = (x0, 0.0, x0 + bw, 1.0)
    cut = cut_at(x0)
    if need_x1 - need_x0 > bw + 1e-6 or cut:
        return {"ok": False, "reason": "too_wide", "red_seconds": cut, "box": box,
                "message": "A 9:16 crop cuts off part of the movement" + (" at " + _ranges(cut) if cut else "") + "."}
    return {"ok": True, "box": box, "portrait": aspect < 1.0}

def _ranges(secs):
    out, run = [], []
    for s in secs:
        if run and s != run[-1] + 1:
            out.append(run); run = []
        run.append(s)
    if run:
        out.append(run)
    return ", ".join(f"{r[0]} s" if len(r) == 1 else f"{r[0]}–{r[-1]} s" for r in out)

def body_on_short(env, box):
    """Where the person moves, on the 720x1280 Short (px), with the same room kept around them."""
    bx0, by0, bx1, by1 = box
    fx = lambda v: (v - bx0) / (bx1 - bx0) * W
    fy = lambda v: (v - by0) / (by1 - by0) * H
    x0 = fx(max(0.0, env["x"][0] - SIDE_ROOM)); x1 = fx(min(1.0, env["x"][1] + SIDE_ROOM))
    y0 = fy(max(0.0, env["y"][0] - HEAD_ROOM)); y1 = fy(min(1.0, env["y"][1] + FEET_ROOM))
    return (max(0, int(x0)), max(0, int(y0)), min(W, int(round(x1))), min(H, int(round(y1))))

def _overlap(a, b, pad=0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])

def _youtube_zones():
    rx, ry0, ry1 = YT_RIGHT
    return [(0, int(H * (1 - YT_BOTTOM)), W, H), (int(W * rx), int(H * ry0), W, int(H * ry1))]

def place_bands(body):
    """Title band and caption box that never touch the body: shrink first, then move. None when there's no room."""
    zones = _youtube_zones()
    title = None
    for th in TITLE_HEIGHTS:                                      # 1) the thin strip across the top, shrinking
        r = (0, 0, W, th)
        if not _overlap(r, body, BODY_PAD):
            title = {"kind": "strip", "rect": r, "font": max(16, int(th * 0.36))}
            break
    if title is None:                                             # 2) then a small corner tag at the top
        for tw, th in ((300, 52), (240, 44), (160, 44), (140, 40)):
            for x in (10, W - tw - 10):
                r = (x, 10, x + tw, 10 + th)
                if not _overlap(r, body, BODY_PAD):
                    title = {"kind": "tag", "rect": r, "font": max(16, int(th * 0.36))}
                    break
            if title:
                break
    if title is None:
        return None
    top_free = title["rect"][3] + 12
    for bw, bh, font, chars in CAPTION_SIZES:                     # captions: shrink first, then move
        spots = []
        for y in range(top_free, int(H * (1 - YT_BOTTOM)) - bh, 8):
            for x in (W - bw - 10, 10, (W - bw) // 2):
                r = (x, y, x + bw, y + bh)
                if _overlap(r, body, BODY_PAD) or any(_overlap(r, z) for z in zones) or _overlap(r, title["rect"], 6):
                    continue
                spots.append((abs(y / H - CAPTION_TOP_PREF), x != W - bw - 10, r))
        if spots:
            spots.sort(key=lambda s: (s[0], s[1]))
            return {"title": title, "caption": {"rect": spots[0][2], "font": font, "chars": chars}}
    return None

def decide(sizes_envs):
    """sizes_envs: [(sw, sh, env)] per source used. All clips must pass; the bands are placed once, clear of every clip."""
    crops, bodies = [], []
    for sw, sh, env in sizes_envs:
        c = crop_box(sw, sh, env)
        crops.append(c)
        if c["ok"]:
            bodies.append(body_on_short(env, c["box"]))
    if not all(c["ok"] for c in crops):
        bad = next(c for c in crops if not c["ok"])
        return {"ok": False, "needs_reshoot": bad["reason"] in ("too_wide", "too_tall"), "reason": bad["reason"],
                "red_seconds": bad.get("red_seconds", []), "message": bad["message"], "clips": crops}
    body = (min(b[0] for b in bodies), min(b[1] for b in bodies), max(b[2] for b in bodies), max(b[3] for b in bodies))
    bands = place_bands(body)
    if bands is None:
        return {"ok": False, "needs_reshoot": False, "reason": "no_room",
                "message": "There's no free space beside the person for the title and captions, even with the bands shrunk.",
                "clips": crops, "body": body}
    warn = []
    if body[3] > H * (1 - YT_BOTTOM):
        warn.append("The feet sit where YouTube shows its own title text; leave more floor below the feet next time.")
    return {"ok": True, "clips": crops, "body": body, "bands": bands, "warnings": warn}

def still(path, t, box, sw, sh, bands, body, out):
    """One small still of the Short as it would look: the 9:16 crop, the see-through bands, the person's area (gold)."""
    x0, y0, x1, y1 = box
    cw, ch = int(round((x1 - x0) * sw / 2) * 2), int(round((y1 - y0) * sh / 2) * 2)
    cx, cy = int(x0 * sw), int(y0 * sh)
    k = STILL_W / W
    sc = lambda r: (int(r[0] * k), int(r[1] * k), max(2, int((r[2] - r[0]) * k)), max(2, int((r[3] - r[1]) * k)))
    draws = []
    for r in (bands["title"]["rect"], bands["caption"]["rect"]):
        x, y, w, h = sc(r)
        draws.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x0F1133@{BAND_ALPHA}:t=fill")
    x, y, w, h = sc(body)
    draws.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0xF2BE50@0.9:t=1")
    vf = f"crop={cw}:{ch}:{cx}:{cy},scale={STILL_W}:{STILL_H}," + ",".join(draws)
    subprocess.run([ss.FFMPEG, "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                    "-vf", vf, "-q:v", "5", str(out)], check=True, timeout=60, capture_output=True)
    return "data:image/jpeg;base64," + base64.b64encode(pathlib.Path(out).read_bytes()).decode()

def measure(srcs, order, segs):
    """srcs: {signed_url: local path}. The framing decision for exactly these seconds (also used by the render itself)."""
    sizes, envs = {}, {}
    for u in order:
        sw, sh = ss.video_size(srcs[u])
        gw, gh = GRID_PORTRAIT if sh > sw else GRID_LANDSCAPE
        parts = []
        for s in segs:
            if s["signed_url"] != u:
                continue
            a, z = float(s["start"]), float(s["end"])
            frames = ss.gray_frames(srcs[u], a, z - a, fps=3, w=gw, h=gh)
            parts.append(envelope(motion_grid(frames, gw, gh), fps=3, start=a))
        sizes[u], envs[u] = (sw, sh), merge(parts)
    result = decide([(*sizes[u], envs[u]) for u in order])
    result["sources"] = [{"index": i, "width": sizes[u][0], "height": sizes[u][1], "portrait": sizes[u][1] > sizes[u][0]}
                         for i, u in enumerate(order)]
    result["_sizes"] = sizes
    return result

def framing_check(job, get=None):
    segs = _private(job)
    get = get or ss.fetch
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        srcs, order = {}, []
        for s in segs:
            u = s["signed_url"]
            if u not in srcs:
                srcs[u] = t / f"src{len(srcs)}"; get(u, srcs[u]); order.append(u)
        result = measure(srcs, order, segs)
        sizes = result.pop("_sizes")
        result.update({"status": "FRAMING_CHECKED", "publishing_enabled": False, "credits_spent": 0})
        if result["ok"] and job.get("stills", True):
            first = segs[0]; mid = segs[len(segs) // 2]; last = segs[-1]
            shots = []
            for n, (s, at) in enumerate(((first, float(first["start"]) + 0.3), (mid, (float(mid["start"]) + float(mid["end"])) / 2),
                                         (last, float(last["end"]) - 0.3))):
                u = s["signed_url"]; i = order.index(u)
                shots.append(still(srcs[u], at, result["clips"][i]["box"], *sizes[u], result["bands"], result["body"], t / f"s{n}.jpg"))
            result["stills"] = shots
        return result
