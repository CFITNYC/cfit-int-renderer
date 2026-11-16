"""Scout hook clip (2026-11-16): the pick and its rules. No ffmpeg, no network."""
import scout_story as ss

U = "u"
def pieces(*spans):
    return [({"role": "x", "signed_url": U}, a, z) for a, z in spans]

# motion every half second for a 10 s video: a burst at 6.0-7.5 s, a smaller one at 2.0-3.5 s
motion = [0.0] * 21
for k in (13, 14, 15): motion[k] = 6.0
for k in (5, 6, 7): motion[k] = 3.0

# 1) the most movement, mid-movement
h = ss.pick_hook({U: U}, pieces((0, 10)), {U: (motion, 10.0)})
assert (h["start"], h["end"]) == (6.0, 7.5), h

# 2) never the first or last second of the video
edge = [0.0] * 21; edge[1] = edge[2] = edge[3] = 9.0; edge[4] = 1.0
h = ss.pick_hook({U: U}, pieces((0, 10)), {U: (edge, 10.0)})
assert h["start"] >= 1.0, h

# 3) only inside the seconds Scout's look says the exercise is performed
h = ss.pick_hook({U: U}, pieces((0, 10)), {U: (motion, 10.0)}, {U: [1.5, 5.0]})
assert (h["start"], h["end"]) == (2.0, 3.5), h

# 4) a later piece that is just those seconds on its own: the next best moment is used instead
h = ss.pick_hook({U: U}, pieces((1, 5), (6, 7.5)), {U: (motion, 10.0)})
assert not (h["start"] == 6.0), h
# ... but a longer piece that contains them is fine
h = ss.pick_hook({U: U}, pieces((5, 9)), {U: (motion, 10.0)})
assert (h["start"], h["end"]) == (6.0, 7.5), h

# 5) several videos: the most dynamic one gives the hook
calm = [0.0] + [0.5] * 20
h = ss.pick_hook({"a": "a", "b": U}, [({"signed_url": "a"}, 0, 10)] + pieces((0, 10)), {"a": (calm, 10.0), U: (motion, 10.0)})
assert h["signed_url"] == U, h

# 6) the hook fits inside the same length: a 29 s story is fine without a hook, and too long with one (29 + 1.5 > 30)
job = {"mode": "scout_story_short", "publishing_enabled": False, "version": "short", "hook": "Watch the base first",
       "branding": {"opening_role": "opening", "closing_role": "closing"},
       "segments": [{"role": "setup", "start": 0, "end": 4}, {"role": "challenge", "start": 4, "end": 19}, {"role": "win", "start": 19, "end": 29}]}
ss.check_story_v3(job)                                   # the text "hook" line alone changes nothing
try:
    ss.check_story_v3({**job, "hook_clip": True}); raise AssertionError("30.5 s accepted")
except ValueError as e:
    assert "most is 30" in str(e), e
print("scout hook: all checks passed")
