"""Intake drafting frames (Nov 4 2026): 10 sharper still frames from the moving part of the video. No network, no ffmpeg."""
import scout_reframe as rf
import scout_story as ss

# the moving part: first to last second that moves; whole clip when too little moves
assert rf.moving_span([None, None, [0.2, 0.4], [0.2, 0.5], None, [0.3, 0.5], None, None], 8.0) == (2.0, 6.0)
assert rf.moving_span([None, [0.1, 0.2], None], 3.0) == (0.0, 3.0)          # 1 moving second: whole clip
assert rf.moving_span([], 5.0) == (0.0, 5.0) and rf.moving_span(None, 5.0) == (0.0, 5.0)
assert rf.moving_span([[0, 1]] * 3, 2.5) == (0.0, 2.5)                     # last second capped at the clip's end

# stand-ins: no video download, no ffmpeg; every still-frame call is recorded
calls = []
class R:
    def __init__(self): self.stdout = b"jpg"
def fake_run(args, **kw):
    calls.append(args); return R()
rf.subprocess.run = fake_run
ss.fetch = lambda url, dst: None
ss.duration = lambda p: 40.0
ss.video_size = lambda p: (1620, 912)
moving = [None] * 10 + [[0.3, 0.6]] * 20 + [None] * 10                      # still 0-10 s, moving 10-30 s, still 30-40 s
rf._gray = lambda p, d: []
rf.movement_by_second = lambda frames: moving
url = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/intake/b/x.mov?token=t"
job = {"mode": "scout_reframe_measure", "publishing_enabled": False, "signed_url": url}

# old callers (6 frames, nothing else asked): exactly as before — whole clip, 384 px, quality 6
calls.clear(); out = rf.reframe_measure({**job, "ai_frames": 6})
times = [f["t"] for f in out["frames"]]
assert times == [round(40.0 * (k + 0.5) / 6, 2) for k in range(6)], times
assert all("scale=384:-2" in a and a[a.index("-q:v") + 1] == "6" for a in calls)
assert out["frames_span"] == [0.0, 40.0]

# Intake drafting: 10 frames, 768 px, sharper, only inside the moving part (10-30 s)
calls.clear(); out = rf.reframe_measure({**job, "ai_frames": 10, "ai_frame_width": 768, "ai_frames_from": "movement"})
times = [f["t"] for f in out["frames"]]
assert len(times) == 10 and all(10.0 <= t <= 30.0 for t in times) and times[0] == 11.0 and times[-1] == 29.0, times
assert all("scale=768:-2" in a and a[a.index("-q:v") + 1] == "3" for a in calls)
assert out["frames_span"] == [10.0, 30.0]

# never more than 10 frames; only 384 or 768 wide
calls.clear(); assert len(rf.reframe_measure({**job, "ai_frames": 50})["frames"]) == 10
try:
    rf.reframe_measure({**job, "ai_frames": 6, "ai_frame_width": 1920}); raise AssertionError("accepted 1920")
except ValueError as e:
    assert "384 or 768" in str(e)
# no frames asked: no frames, no span (the Reframe page's measure call is unchanged)
assert "frames" not in rf.reframe_measure(job) and "frames_span" not in rf.reframe_measure(job)
# the AI look: dense at the start, spread to the end, at most 30 frames, no movement reading
ts = rf.look_times(60.0)
assert ts[:14] == [float(i) for i in range(14)] and len(ts) == 30 and ts[-1] <= 59.5 and ts == sorted(ts), ts
assert rf.look_times(10.0) == [float(i) for i in range(10)]
calls.clear(); out = rf.reframe_measure({**job, "ai_look": True})
assert len(out["frames"]) == 30 and "seconds" not in out and out["duration"] == 40.0 and out["frames"][14]["t"] > 14
print("intake frames: all checks pass")
