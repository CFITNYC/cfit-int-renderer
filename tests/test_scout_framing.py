"""Scout framing check: safety and placement tests (no network, no ffmpeg)."""
import scout_framing as sf

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

def env(x, y, per=None):
    return {"x": x, "y": y, "seconds": per or {0: x}}

# portrait 9:16: always the whole clip; nothing cropped
c = sf.crop_box(1080, 1920, env((0.1, 0.65), (0.07, 0.9)))
assert c["ok"] and c["box"] == (0.0, 0.0, 1.0, 1.0), c
# landscape: the movement fits a 9:16 box (box is 0.316 of the width)
c = sf.crop_box(1920, 1080, env((0.40, 0.58), (0.1, 0.95), {0: (0.40, 0.58), 1: (0.42, 0.57)}))
assert c["ok"] and abs((c["box"][2] - c["box"][0]) - 9 / 16 / (1920 / 1080)) < 1e-9, c
assert c["box"][0] <= 0.40 - sf.SIDE_ROOM and c["box"][2] >= 0.58 + sf.SIDE_ROOM, c
# landscape: a long, low drill (quadruped) does not fit: refused with the cut seconds, never a tighter crop
c = sf.crop_box(1920, 1080, env((0.15, 0.85), (0.4, 0.9), {1: (0.40, 0.55), 2: (0.15, 0.85), 3: (0.15, 0.8), 7: (0.42, 0.56)}))
assert not c["ok"] and c["reason"] == "too_wide" and c["red_seconds"] == [2, 3], c
assert "2–3 s" in c["message"], c["message"]
assert c["box"][0] <= 0.40 - sf.SIDE_ROOM and c["box"][2] >= 0.56 + sf.SIDE_ROOM   # the box that cuts the fewest seconds
# nothing moving: refused as unclear (no guessing)
assert sf.crop_box(1920, 1080, None)["reason"] == "unclear"

# decide: a refusal names reshoot only for the 9:16 problems
d = sf.decide([(1920, 1080, env((0.15, 0.85), (0.4, 0.9), {2: (0.15, 0.85)}))])
assert not d["ok"] and d["needs_reshoot"] and d["red_seconds"] == [2]
d = sf.decide([(1920, 1080, None)])
assert not d["ok"] and not d["needs_reshoot"] and d["reason"] == "unclear"

# bands: never on the body; the title strip shrinks before it moves; captions avoid YouTube's areas
def clear(d):
    b = d["body"]
    for r in (d["bands"]["title"]["rect"], d["bands"]["caption"]["rect"]):
        assert not sf._overlap(r, b, sf.BODY_PAD - 1), (r, b)
    for z in sf._youtube_zones():
        assert not sf._overlap(d["bands"]["caption"]["rect"], z), d["bands"]["caption"]
d = sf.decide([(1080, 1920, env((0.05, 0.62), (0.14, 0.9)))])        # person on the left, wall on the right
assert d["ok"]; clear(d)
assert d["bands"]["title"]["kind"] == "strip" and d["bands"]["title"]["rect"][3] == 64
assert d["bands"]["caption"]["rect"][0] > 720 * 0.62, d["bands"]["caption"]   # on the free side
d = sf.decide([(1080, 1920, env((0.3, 0.7), (0.08, 0.9)))])          # head close to the top: the strip shrinks
assert d["ok"]; clear(d); assert d["bands"]["title"]["rect"][3] < 64, d["bands"]["title"]
d = sf.decide([(1080, 1920, env((0.3, 0.7), (0.0, 0.9)))])           # head at the very top, centred: a corner tag instead
assert d["ok"]; clear(d); assert d["bands"]["title"]["kind"] == "tag", d["bands"]["title"]
d = sf.decide([(1080, 1920, env((0.0, 1.0), (0.0, 1.0)))])           # movement everywhere: no room, refused, nothing cropped
assert not d["ok"] and d["reason"] == "no_room" and not d["needs_reshoot"]
d = sf.decide([(1080, 1920, env((0.05, 0.62), (0.12, 0.97)))])       # feet in YouTube's bottom area: a warning only
assert d["ok"] and d["warnings"], d

# per-second envelope from motion pairs
pairs = [([0, 0, 50, 50, 0, 0, 0, 0], [0, 40, 40, 0]) for _ in range(6)]
e = sf.envelope(pairs, fps=3, start=10)
assert e["x"] == (0.25, 0.5) and e["y"] == (0.25, 0.75) and set(e["seconds"]) == {10, 11, 12}, e
assert sf.envelope([([0.1] * 8, [0.1] * 4)]) is None
m = sf.merge([env((0.2, 0.4), (0.1, 0.5), {1: (0.2, 0.4)}), env((0.3, 0.6), (0.2, 0.9), {1: (0.35, 0.6), 2: (0.3, 0.5)})])
assert m["x"] == (0.2, 0.6) and m["y"] == (0.1, 0.9) and m["seconds"] == {1: (0.2, 0.6), 2: (0.3, 0.5)}
print("test_scout_framing: all passed")
