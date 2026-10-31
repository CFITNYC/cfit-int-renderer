"""Full-screen Short render (layout "full"): the exact ffmpeg instructions, captured without running ffmpeg."""
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
job = {"mode": "scout_story_short", "publishing_enabled": False, "layout": "full", "version": "short", "frame": "9:16",
       "branding": {"opening_role": "opening", "closing_role": "closing", "opening_signed_url": "o", "closing_signed_url": "c"},
       "segments": [seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)], "title": "Bodyweight Squat Floor Touch",
       "series": "STAY GROUNDED", "hook": "Own the squat", "payoff": "Strength you use all day"}

# 1) portrait clip, person on the left: whole clip fills the Short, bands clear of the person
SIZES["src0"] = (1080, 1920); MOTION["src0"] = (0.08, 0.6, 0.14, 0.86)
calls.clear()
assert ss.render_story(job, get) == b"VIDEO"
graph = next(c[c.index("-filter_complex") + 1] for c in calls if "-filter_complex" in c and "subtitles=" in c[c.index("-filter_complex") + 1])
assert "crop=1080:1920:0:0,scale=720:1280" in graph, graph[:400]
assert "pad=720:1280:0:150" not in graph and "h=96:color=black@0.85" not in graph      # no window, no bottom bar
assert "color=0x0F1133@0.55:t=fill" in graph                                          # see-through title band
assert "gblur" not in graph                                                            # no blurred bars
ass = [c for c in calls]  # captions file is written to the temp dir; check the module made it with a box
# 2) landscape clip that a 9:16 crop can't hold: refused before rendering, nothing cropped
SIZES["src0"] = (1920, 1080); MOTION["src0"] = (0.1, 0.9, 0.4, 0.9)
calls.clear()
try:
    ss.render_story(job, get); raise AssertionError("accepted a cut-off crop")
except ValueError as e:
    assert str(e).startswith("Framing: A 9:16 crop cuts off part of the movement"), e
assert not any("libx264" in " ".join(c) for c in calls), "rendered anyway"
# 3) landscape clip whose movement fits a 9:16 box: exactly that box, full-screen
SIZES["src0"] = (1920, 1080); MOTION["src0"] = (0.42, 0.56, 0.3, 0.9)   # floor drill: room above for the bands
calls.clear()
assert ss.render_story(job, get) == b"VIDEO"
graph = next(c[c.index("-filter_complex") + 1] for c in calls if "-filter_complex" in c and "subtitles=" in c[c.index("-filter_complex") + 1])
assert "crop=608:1080:" in graph and ",scale=720:1280," in graph, graph[:300]
# 4) the Long (4:5) can't use the full-screen layout
try:
    ss.render_story({**job, "version": "long", "frame": "4:5"}, get); raise AssertionError("long accepted")
except ValueError as e:
    assert "9:16 Short only" in str(e), e

# captions: the see-through box style and the chosen place
import tempfile
with tempfile.TemporaryDirectory() as td:
    g = ss.frame_geometry("9:16")
    p = pathlib.Path(td) / "c.ass"
    ss.captions_ass_v3(p, g, [(0.0, 0.4, "Own"), (0.4, 0.8, "the"), (0.8, 1.2, "squat.")], 2.0, video_len=10.0,
                       cap={"rect": (480, 100, 710, 196), "font": 30, "chars": 10})
    a = p.read_text()
    assert ",30,&H00FFFFFF,&H00FFFFFF,&H73331110&,&H73331110&," in a and ",3,8,0,5," in a, a[:900]
    assert "\\an5\\pos(595,148)" in a
    ss.captions_ass_v3(p, g, [(0.0, 0.4, "Own")], 2.0, video_len=10.0)          # without cap: exactly as before
    b = p.read_text()
    assert f"\\pos(360,{g['ZONE_Y'] + g['ZONE'] // 2})" in b and ",1,3,0,5," in b
print("test_scout_full_render: all passed")
