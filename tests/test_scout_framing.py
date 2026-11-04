"""Scout framing check, banded only (2026-11-04): safety, the refusal and the banded stills. Needs ffmpeg on PATH."""
import pathlib, shutil, subprocess, tempfile
import scout_story as ss, scout_framing as sf

def refused(fn, job, words):
    try:
        fn(job)
    except ValueError as e:
        assert words in str(e), (words, str(e))
        return
    raise AssertionError("accepted: " + words)

url = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/a.mp4?token=t"
job = {"mode": "scout_framing_check", "publishing_enabled": False, "segments": [{"signed_url": url, "start": 0, "end": 2}]}
refused(sf._private, {**job, "publishing_enabled": True}, "Private framing check required")
refused(sf._private, {**job, "mode": "scout_story_short"}, "Private framing check required")
refused(sf._private, {**job, "segments": []}, "1-6 clips required")
refused(sf._private, {**job, "segments": [{"signed_url": url, "start": 3, "end": 2}]}, "0-30 seconds")
refused(sf._private, {**job, "segments": [{"signed_url": url.replace("cfit-exercise-videos", "cfit-billing"), "start": 0, "end": 2}]}, "Private library")
refused(sf._private, {**job, "layout": "full"}, "Only the banded layout is allowed")
refused(sf._private, {**job, "challenge_cuts": 9}, "1-4")
assert not hasattr(sf, "crop_box") and not hasattr(sf, "place_bands")            # the full-screen 9:16 box and see-through bands are gone
# the check uses the same seconds as the render: the challenge as fast cuts
segs = [{"role": "setup", "start": 0, "end": 2}, {"role": "challenge", "start": 3, "end": 8}, {"role": "win", "start": 9, "end": 12}]
assert [(a, z) for _, a, z in sf.pieces_of(segs, 3)] == [(0, 2)] + ss.challenge_cuts(3, 8, 3) + [(9, 12)]

def clip(path, w, h, moving=True, seconds=6):
    bw, bh = int(w * 0.25), int(h * 0.6)
    x = "(W-w)/2+W*0.15*sin(t*4)" if moving else "(W-w)/2"
    fc = (f"color=c=0x202020:s={w}x{h}:d={seconds}:r=15[bg];color=c=white:s={bw}x{bh}:d={seconds}:r=15[fg];"
          f"[bg][fg]overlay=x='{x}':y=H*0.2:shortest=1")
    subprocess.run([ss.FFMPEG, "-v", "error", "-y", "-filter_complex", fc, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)

with tempfile.TemporaryDirectory() as td:
    t = pathlib.Path(td)
    files = {"move": t / "move.mp4", "still": t / "still.mp4", "wide": t / "wide.mp4"}
    clip(files["move"], 360, 640); clip(files["still"], 360, 640, moving=False); clip(files["wide"], 640, 360)
    U = lambda k: url.replace("a.mp4", k + ".mp4")
    get = lambda u, p: shutil.copy(files[u.split("/")[-1].split(".mp4")[0]], p)
    story = lambda k: {"mode": "scout_framing_check", "publishing_enabled": False, "stills": True, "challenge_cuts": 3,
                       "segments": [{"role": r, "signed_url": U(k), "start": a, "end": z} for r, a, z in (("setup", 0, 1.5), ("challenge", 1.5, 4.5), ("win", 4.5, 5.8))]}
    r = sf.framing_check(story("move"), get)                       # a portrait clip: framed in the banded window, 3 stills
    assert r["ok"] and r["layout"] == "banded" and len(r["stills"]) == 3 and r["credits_spent"] == 0, r.get("message")
    assert all(s.startswith("data:image/jpeg;base64,") for s in r["stills"])
    r = sf.framing_check(story("wide"), get)                       # a wide clip: also banded (navy above and below if needed)
    assert r["ok"] and r["sources"][0]["portrait"] is False
    r = sf.framing_check(story("still"), get)                      # nothing moves: refused, no fallback picture
    assert not r["ok"] and r["reason"] == "unclear" and "banded layout" in r["message"] and "stills" not in r, r
    assert r["needs_reshoot"] is False
print("test_scout_framing: all passed")
