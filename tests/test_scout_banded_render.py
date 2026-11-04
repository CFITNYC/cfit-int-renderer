"""Banded-only render (2026-11-04, Nick's standing rule): the exact ffmpeg instructions, captured without running ffmpeg.
The banded layout (v3) is the only layout, as in the original EP10/EP18 (soft blurred copy beside the clip); anything else is refused before anything is made."""
import pathlib, subprocess, types
import scout_story as ss, scout_framing as sf

calls = []
def fake_run(args, **kw):
    calls.append(list(map(str, args)))
    out = pathlib.Path(str(args[-1]))
    if out.suffix in (".mp4",) or out.name in ("story.mp4", "silent.mp4"):
        out.write_bytes(b"VIDEO")
    return types.SimpleNamespace(stdout=b"", stderr="", returncode=0)
ss.subprocess = types.SimpleNamespace(run=fake_run)
ss.duration = lambda p: 2.0 if "opening" in str(p) or "closing" in str(p) else 15.0
SIZES = {}
ss.video_size = lambda p: SIZES.get(pathlib.Path(p).name, (1080, 1920))

def person(w, h, x0, x1, y0, y1, n=12):
    """Frames where a block moves inside (x0..x1, y0..y1) of the picture (fractions)."""
    frames = []
    for k in range(n):
        f = bytearray(w * h)
        for r in range(int(y0 * h), int(y1 * h)):
            for c in range(int(x0 * w), int(x1 * w)):
                f[r * w + c] = (40 + 90 * ((k + r + c) % 2))
        frames.append(bytes(f))
    return frames
MOTION = {}
ss.gray_frames = lambda path, a=0, sec=None, fps=3, w=36, h=64: person(w, h, *MOTION[pathlib.Path(path).name])
def get(url, dest, audio=False):
    pathlib.Path(dest).write_bytes(b"x")

u = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/a.mp4?token=t"
seg = lambda role, a, z: {"role": role, "signed_url": u, "start": a, "end": z}
job = {"mode": "scout_story_short", "publishing_enabled": False, "layout": "v3", "version": "short", "frame": "9:16", "challenge_cuts": 3,
       "branding": {"opening_role": "opening", "closing_role": "closing", "opening_signed_url": "o", "closing_signed_url": "c"},
       "segments": [seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)], "title": "Bodyweight Squat Floor Touch",
       "series": "STAY GROUNDED", "hook": "Own the squat", "payoff": "Strength you use all day"}
def graph_of():
    return next(c[c.index("-filter_complex") + 1] for c in calls if "-filter_complex" in c and "subtitles=" in c[c.index("-filter_complex") + 1])

# 1) full-screen, older and missing layouts: refused before anything is downloaded or made
got = []
for lay in ("full", "v2", "v1", "", None):
    calls.clear()
    j = {**job, "layout": lay} if lay is not None else {k: v for k, v in job.items() if k != "layout"}
    try:
        ss.render_story(j, lambda *a: got.append(a)); raise AssertionError(f"layout {lay!r} accepted")
    except ValueError as e:
        assert str(e) == "Only the banded layout is allowed. Nothing was made.", e
    assert not calls and not got, "something ran"
# 2) portrait clip: banded (title bar, clip window, caption band, footer), blurred copy beside the clip
SIZES["src0"] = (1080, 1920); MOTION["src0"] = (0.3, 0.7, 0.1, 0.9)
calls.clear()
assert ss.render_story(job, get) == b"VIDEO"
graph = graph_of()
assert "crop=720:804,gblur=sigma=28" in graph, graph[:400]                             # the original design: soft blurred copy at the sides
assert "pad=720:1280:0:150" in graph and "h=96:color=black@0.85" in graph             # top bar and CFIT METHOD footer
assert "0x0F1133@0.55" not in graph                                                  # no see-through full-screen band
# 3) landscape clip: shown as large as the whole movement allows, still banded
SIZES["src0"] = (1920, 1080); MOTION["src0"] = (0.1, 0.9, 0.2, 0.9)
calls.clear()
assert ss.render_story(job, get) == b"VIDEO"
graph = graph_of()
assert "crop=720:804,gblur=sigma=28" in graph and "pad=720:1280:0:150" in graph
# 4) the Long (4:5) is banded too
calls.clear()
lj = {**job, "version": "long", "frame": "4:5", "challenge_cuts": 1, "segments": [seg("setup", 0, 4), seg("challenge", 4.5, 13), seg("win", 13.5, 18)]}
SIZES["src0"] = (1080, 1920); MOTION["src0"] = (0.3, 0.7, 0.1, 0.9)
assert ss.render_story(lj, get) == b"VIDEO"
assert "crop=720:550,gblur=sigma=28" in graph_of() and "pad=720:900:0:110" in graph_of()
# 5) Scout can't tell where the person moves: refused, nothing made (no blurred "whole picture" fallback)
MOTION["src0"] = (0.0, 0.0, 0.0, 0.0)
calls.clear()
try:
    ss.render_story(job, get); raise AssertionError("unclear clip accepted")
except ValueError as e:
    assert "can't tell where you move" in str(e) and "banded layout" in str(e) and "Nothing was made" in str(e), e
assert not any("libx264" in " ".join(c) for c in calls), "rendered anyway"
print("test_scout_banded_render: all passed")
