"""Longer stories from 2-5 parts (2026-11-04): checks before anything is made. No network, no ffmpeg."""
import scout_story as ss
u = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/a.mp4?token=t"
seg = lambda role, a, z, url=u: {"role": role, "signed_url": url, "start": a, "end": z}
base = {"mode": "scout_story_short", "publishing_enabled": False, "version": "short", "frame": "9:16", "challenge_cuts": 1,
        "branding": {"opening_role": "opening", "closing_role": "closing"}}
ok = lambda **k: ss.check_story_v3({**base, **k})
def refused(words, **k):
    try:
        ok(**k)
    except ValueError as e:
        assert words in str(e), (words, str(e)); return
    raise AssertionError("accepted: " + words)
# the old 3-part stories still pass, with the fast cuts
assert len(ok(segments=[seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)], challenge_cuts=3)[1]) == 3
# 2, 3, 4 and 5 parts, different clips
two = [seg("setup", 0, 8), seg("win", 0, 10, u + "b")]
assert len(ok(segments=two)[1]) == 2
four = [seg("setup", 0, 5), seg("challenge", 0, 6, u + "b"), seg("challenge", 0, 6, u + "c"), seg("win", 0, 6, u + "d")]
assert len(ok(segments=four)[1]) == 4
five = [seg("setup", 0, 4), seg("challenge", 0, 6, u + "b"), seg("challenge", 0, 6, u + "c"), seg("challenge", 0, 6, u + "d"), seg("win", 0, 6, u + "e")]
assert len(ok(segments=five)[1]) == 5
# 1 or 6 parts, wrong order
refused("2-5 parts", segments=[seg("setup", 0, 4)])
refused("2-5 parts", segments=[seg("setup", 0, 4)] + [seg("challenge", 0, 3)] * 4 + [seg("win", 0, 3)])
refused("2-5 parts", segments=[seg("win", 0, 3), seg("setup", 0, 3)])
# lengths: Short up to 30 s, Long up to 45 s, each part within its limits
refused("the most is 30", segments=[seg("setup", 0, 8), seg("challenge", 0, 15), seg("win", 0, 10)])
assert ok(segments=[seg("setup", 0, 8), seg("challenge", 0, 12), seg("win", 0, 10)])
refused("setup must be 1-8", segments=[seg("setup", 0, 9), seg("win", 0, 5)])
lng = {"version": "long", "frame": "4:5"}
assert ok(segments=[seg("setup", 0, 10), seg("challenge", 0, 20), seg("win", 0, 15)], **lng)
refused("the most is 45", segments=[seg("setup", 0, 10), seg("challenge", 0, 22), seg("win", 0, 15)], **lng)
print("multi clip: all checks pass")
