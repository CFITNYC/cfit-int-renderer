"""2026-11-17 (Nick): an APP clip (fit_whole) is a screen recording: no person is looked for; the whole screen is shown inside the
same banded window. Posts without an APP clip must be made exactly as before. Run: python3 tests/test_scout_app_whole.py [record FILE]
'record' writes the ffmpeg instructions for the non-APP posts to FILE (run on the old and the new code, then compare)."""
import json, pathlib, re, sys, types
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import scout_story as ss, scout_framing as sf
calls = []
def fake_run(args, **kw):
    calls.append(list(map(str, args)))
    out = pathlib.Path(str(args[-1]))
    if out.suffix == ".mp4" or out.name in ("story.mp4", "silent.mp4"): out.write_bytes(b"VIDEO")
    return types.SimpleNamespace(stdout=b"", stderr="", returncode=0)
ss.subprocess = types.SimpleNamespace(run=fake_run)
ss.duration = lambda p: 2.0 if "opening" in str(p) or "closing" in str(p) else 15.0
SIZES = {}; ss.video_size = lambda p: SIZES.get(pathlib.Path(p).name, (1080, 1920))
def person(w, h, x0, x1, y0, y1, n=12):
    frames = []
    for k in range(n):
        f = bytearray(w * h)
        for r in range(int(y0 * h), int(y1 * h)):
            for c in range(int(x0 * w), int(x1 * w)): f[r * w + c] = (40 + 90 * ((k + r + c) % 2))
        frames.append(bytes(f))
    return frames
MOTION = {}
ss.gray_frames = lambda path, a=0, sec=None, fps=3, w=36, h=64: person(w, h, *MOTION.get(pathlib.Path(path).name, (0.3, 0.7, 0.1, 0.9)))
get = lambda url, dest, audio=False: pathlib.Path(dest).write_bytes(b"x")
U = lambda n: f"https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/scout-phone/2026/11/{n}.mov?token=t"
seg = lambda role, a, z, n="a", **k: {"role": role, "signed_url": U(n), "start": a, "end": z, **k}
base = {"mode": "scout_story_short", "publishing_enabled": False, "layout": "v3", "version": "short", "frame": "9:16", "challenge_cuts": 3,
        "branding": {"opening_role": "opening", "closing_role": "closing", "opening_signed_url": "o", "closing_signed_url": "c"},
        "title": "Made-up", "series": "STAY GROUNDED", "hook": "Own the squat", "payoff": "Strength you use all day"}
norm = lambda s: re.sub(r"/(private/)?(var|tmp)/[^ :'\"]*?/(tmp[^/ ]*)", "/TMP", s)
def run(job):
    calls.clear(); ss.render_story(job, get); return [[norm(a) for a in c] for c in calls]
# the non-APP posts: one portrait clip, a landscape clip, the Long, three clips with the hook clip
SCEN = {
  "portrait": {**base, "segments": [seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)]},
  "long": {**base, "version": "long", "frame": "4:5", "challenge_cuts": 1, "segments": [seg("setup", 0, 4), seg("challenge", 4.5, 13), seg("win", 13.5, 18)]},
  "multi_hook": {**base, "hook_clip": True, "segments": [seg("setup", 0, 2, "a", multi=True), seg("challenge", 2, 4, "b", multi=True), seg("challenge", 4, 6, "c", multi=True), seg("win", 6, 8, "a", multi=True)]},
}
if len(sys.argv) > 2 and sys.argv[1] == "record":
    out = {}
    for name, job in SCEN.items():
        SIZES.clear(); out[name] = run(job)
    SIZES["src0"] = (1920, 1080); MOTION["src0"] = (0.1, 0.9, 0.2, 0.9); out["landscape"] = run(SCEN["portrait"]); SIZES.clear(); MOTION.clear()
    pathlib.Path(sys.argv[2]).write_text(json.dumps(out, indent=0)); print("recorded", {k: len(v) for k, v in out.items()}); sys.exit(0)
# APP clip: nothing moves (a still screen) -> today refused; with fit_whole -> the whole screen in the banded window
MOTION["src0"] = (0, 0, 0, 0)
app = {**base, "segments": [seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)]}
try: run(app); raise AssertionError("a still clip without fit_whole was accepted")
except ValueError as e: assert "can't tell where you move" in str(e)
SIZES["src0"] = (884, 1920)
c = run({**app, "segments": [{**s, "fit_whole": True} for s in app["segments"]]})
graph = next(x[x.index("-filter_complex") + 1] for x in c if "-filter_complex" in x and "subtitles=" in x[x.index("-filter_complex") + 1])
assert "crop=720:804,gblur=sigma=28" in graph and "pad=720:1280:0:150" in graph, "not the banded design"
fit = ss.body_fit((ss.BODY_HEAD_MARGIN, 1 - ss.BODY_FEET_MARGIN), (ss.SIDE_MARGIN, 1 - ss.SIDE_MARGIN), 884, 1920, 720, 804)
assert fit[0] <= 720 and fit[1] <= 804 and fit[2] == 0 and fit[3] == 0 and (fit[0], fit[1]) == (fit[4], fit[5]), ("whole screen, never cropped", fit)
print("APP clip: still screen refused without fit_whole; shown whole in the banded window with it", fit)
print("test_scout_app_whole: all passed")
