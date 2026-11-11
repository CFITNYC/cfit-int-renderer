"""Library rep timing: safety tests (no network) and, when ffmpeg is available (CFIT_TEST_FFMPEG), a real timing test on
made-up clips with a known rep length (3.0 s simple rep; 12.0 s drill of four 3-second movements)."""
import os, shutil, subprocess, tempfile, pathlib
import library_timing as lt
import scout_story as ss

def refused(job, words):
    try:
        lt.rep_timing(job, get=lambda u, d: None)
    except ValueError as e:
        assert words in str(e), (words, str(e)); return
    raise AssertionError("accepted: " + words)

url = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/CFM-EX-0097/a.mp4?token=t"
refused({"mode": "library_rep_timing", "publishing_enabled": True, "signed_url": url}, "Private timing required")
refused({"mode": "scout_story_short", "publishing_enabled": False, "signed_url": url}, "Private timing required")
refused({"mode": "library_rep_timing", "publishing_enabled": False, "signed_url": url.replace("cfit-exercise-videos", "cfit-social-exports")}, "Private library video required")
assert lt.still_times([], 10)[:2] == [0.3, 0.9] and len(lt.still_times([], 10)) == 16
assert lt.still_times([{"start": 1, "end": 4}], 30) == [1.0, 2.0, 3.0, 4.0]
print("safety ok")

import math
W, H = lt.GRID_W, lt.GRID_H
def frame(x):
    # grey frame with a bright 10x10 square whose left edge is at column x
    px = bytearray([90] * (W * H))
    for r in range(40, 50):
        for c in range(int(x), min(W, int(x) + 10)):
            px[r * W + c] = 230
    return bytes(px)
def frames(pos, seconds):
    return [frame(pos(k / lt.FPS)) for k in range(int(seconds * lt.FPS))]
# simple rep: out and back in 2 s, then 1 s still -> one rep every 3.0 s
simple = frames(lambda t: 2 + 30 * math.sin(math.pi * (t % 3) / 2) if t % 3 < 2 else 2, 30)
secs = [c["seconds"] for c in lt.cycles_of(simple)]
print("simple cycles", secs)
assert len(secs) >= 6 and all(1.6 <= s <= 3.2 for s in secs), secs
gaps = [c["start_to_next_start"] for c in lt.cycles_of(simple) if "start_to_next_start" in c]
print("simple start-to-start", gaps)
assert gaps and all(abs(g - 3.0) <= 0.4 for g in gaps), gaps
line = lt.movement_line(simple)
assert len(line) >= 50 and max(line) == 9 and min(line) == 0, line
# drill: four movements of 3 s (big, small, medium, tiny) then 1 s still = one 13 s sequence; the finder sees the
# separate movements (the AI groups them into one rep using the exercise's sequence)
amps = [30, 12, 20, 8]
def drill(t):
    m, k = t % 13, int((t % 13) // 3)
    return 2 + amps[k] * math.sin(math.pi * (m - 3 * k) / 3) if m < 12 else 2
d = lt.cycles_of(frames(drill, 39))
print("drill cycles", [(c["start"], c["seconds"]) for c in d])
assert d, "no cycles found in the drill"
# a hold: nothing moves -> no cycles, stills spread over the clip
hold = frames(lambda t: 2, 20)
assert lt.cycles_of(hold) == [] and len(lt.still_times([], 20)) == 16
print("timing ok")
