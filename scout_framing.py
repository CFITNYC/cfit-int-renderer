# CFIT Scout framing (2026-10-31; banded only since 2026-11-04). Private, admin-only; publishing stays off.
#
# Nick's standing rule (2026-11-04): the banded design is the ONLY layout for every video: a navy title bar at the top,
# the clip framed in the middle window with a soft blurred copy at the sides (the original design, EP10/EP18), big spoken captions in a navy band, and the CFIT METHOD footer.
# No full-screen or other layout, not even as a fallback. If a clip can't be framed in the banded layout, Scout refuses
# and says why, and spends nothing.
#
# scout_framing_check : looks at the exact seconds a storyboard would use (low resolution, nothing kept) and returns
#                       3 small stills of the banded video as it would look, or why it can't be framed. It uses the
#                       render's own banded fit (scout_story.banded_fits) on the same seconds, so the free check and
#                       the render can't disagree. Free: no AI, no voice, nothing saved.
import base64, pathlib, tempfile

import scout_story as ss   # shared helpers (looked up at call time, so tests can swap them)

STILL_W = 180
HEADER_NAVY, PANEL_NAVY, GOLD = "0x101239", "0x0B0D26", "0xF2BE50"

def _private(job):
    if job.get("mode") != "scout_framing_check" or job.get("publishing_enabled") is not False:
        raise ValueError("Private framing check required")
    if job.get("layout", "v3") != "v3":
        raise ValueError(ss.BANDED_ONLY)
    segs = job.get("segments")
    if not isinstance(segs, list) or not 1 <= len(segs) <= 6:
        raise ValueError("1-6 clips required")
    for s in segs:
        a, z = float(s.get("start", -1)), float(s.get("end", -1))
        if not (0 <= a < z <= a + 30):
            raise ValueError("Each clip part must be 0-30 seconds")
        if "/storage/v1/object/sign/cfit-exercise-videos/" not in str(s.get("signed_url") or ""):
            raise ValueError("Private library or phone video required")
    cuts = int(job.get("challenge_cuts") or 1)
    if not 1 <= cuts <= 4:
        raise ValueError("Challenge cuts must be 1-4")
    return segs, cuts, ss.frame_geometry(job.get("frame") or "9:16")

def pieces_of(segs, cuts):
    """The exact seconds the render uses: the challenge as fast cuts (Short), every other part whole."""
    out = []
    for s in segs:
        a, z = float(s["start"]), float(s["end"])
        out += [(s, x, y) for x, y in (ss.challenge_cuts(a, z, cuts) if s.get("role") == "challenge" else [(a, z)])]
    return out

def still(path, t, fit, g, out):
    """One small still of the banded video: title bar, the clip in its window (blurred copy at the sides), caption band, CFIT footer."""
    vw, vh, cx, cy, dw, dh = fit
    W, H, TOP, WIN, BAR, ZONE_Y = g["W"], g["H"], g["TOP"], g["WIN"], g["BAR"], g["ZONE_Y"]
    fc = (f"[0:v]split[a][b];[a]scale={W}:{WIN}:force_original_aspect_ratio=increase,crop={W}:{WIN},{ss.BLUR_SIDES}[bg];"
          f"[b]scale={vw}:{vh},crop={dw}:{dh}:{cx}:{cy}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
          f"pad={W}:{H}:0:{TOP}:color={PANEL_NAVY},"
          f"drawbox=x=0:y=0:w=iw:h={TOP}:color={HEADER_NAVY}@1:t=fill,drawbox=x=0:y={ZONE_Y}:w=iw:h={ss.GOLD_LINE}:color={GOLD}@1:t=fill,"
          f"drawbox=x=0:y=ih-{BAR}:w=iw:h={BAR}:color=black@0.85:t=fill,scale={STILL_W}:-2")
    ss.subprocess.run([ss.FFMPEG, "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                       "-filter_complex", fc, "-q:v", "5", str(out)], check=True, timeout=60, capture_output=True)
    return "data:image/jpeg;base64," + base64.b64encode(pathlib.Path(out).read_bytes()).decode()

def framing_check(job, get=None):
    segs, cuts, g = _private(job)
    get = get or ss.fetch
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        srcs = {}
        for s in segs:
            u = s["signed_url"]
            if u not in srcs:
                srcs[u] = t / f"src{len(srcs)}"; get(u, srcs[u])
        base = {"status": "FRAMING_CHECKED", "layout": "banded", "publishing_enabled": False, "credits_spent": 0}
        try:
            fits = ss.banded_fits(srcs, pieces_of(segs, cuts), g)
        except ValueError as e:   # no fallback picture: refuse and say why
            return {**base, "ok": False, "needs_reshoot": False, "reason": "unclear", "red_seconds": [],
                    "message": str(e).replace(" Nothing was made.", "")}
        sources = []
        for i, (u, p) in enumerate(srcs.items()):
            sw, sh = ss.video_size(p)
            sources.append({"index": i, "width": sw, "height": sh, "portrait": sh > sw})
        result = {**base, "ok": True, "sources": sources, "warnings": []}
        if job.get("stills", True):
            first, mid, last = segs[0], segs[len(segs) // 2], segs[-1]
            shots = []
            for n, (s, at) in enumerate(((first, float(first["start"]) + 0.3), (mid, (float(mid["start"]) + float(mid["end"])) / 2),
                                         (last, float(last["end"]) - 0.3))):
                shots.append(still(srcs[s["signed_url"]], at, fits[s["signed_url"]], g, t / f"s{n}.jpg"))
            result["stills"] = shots
        return result
