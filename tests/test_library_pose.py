"""Library pose timing: safety tests and timing tests on made-up body-point sequences (no MediaPipe, no ffmpeg, no network).
Each made-up exercise has a known seconds per rep; the analysis must find it within 15%."""
import math, random
import library_pose as lp

random.seed(7)
FPS = lp.FPS

def refused(job, words):
    try:
        lp.pose_timing(job, get=lambda u, d: None, points=lambda p, s: [])
    except ValueError as e:
        assert words in str(e), (words, str(e)); return
    raise AssertionError("accepted: " + words)

url = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/CFM-EX-0004/a.mp4?token=t"
refused({"mode": "library_pose_timing", "publishing_enabled": True, "signed_url": url}, "Private timing required")
refused({"mode": "library_rep_timing", "publishing_enabled": False, "signed_url": url}, "Private timing required")
refused({"mode": "library_pose_timing", "publishing_enabled": False, "signed_url": url.replace("cfit-exercise-videos", "x")}, "Private library video required")
refused({"mode": "library_pose_timing", "publishing_enabled": False, "signed_url": url, "movements_per_rep": 40}, "movements_per_rep")
print("safety ok")

def body(torso=0.0, squat=0.0, lw=(0.0, 0.0), rw=(0.0, 0.0), lleg=0.0, rleg=0.0, reach=0.0, noise=0.004):
    """33 points (x, y, vis). torso: 0 standing .. 1 horizontal plank. squat: 0..1 hips down. lw/rw: wrist offsets
    (out, up) in torso lengths from hanging. lleg/rleg: knee lift 0..1. reach: hands walking forward (plank)."""
    pts = [(0.5, 0.5, 0.2)] * 33
    hx, hy = 0.5, 0.62 + 0.12 * squat
    a = torso * math.pi / 2
    T = 0.2
    sx, sy = hx + T * math.sin(a), hy - T * math.cos(a)
    def put(i, x, y):
        pts[i] = (x + random.uniform(-noise, noise), y + random.uniform(-noise, noise), 0.95)
    put(11, sx - 0.05 * math.cos(a), sy - 0.05 * math.sin(a)); put(12, sx + 0.05 * math.cos(a), sy + 0.05 * math.sin(a))
    put(23, hx - 0.04, hy); put(24, hx + 0.04, hy)
    for (si, ei, wi, off, sgn) in ((11, 13, 15, lw, -1), (12, 14, 16, rw, 1)):
        bx, by = pts[si][0], pts[si][1]
        dx = sgn * off[0] * T + reach * T * math.sin(a) * 1.5
        dy = T * (1 - off[1]) * (math.cos(a) if torso < 0.5 else 1)
        put(ei, bx + dx / 2, by + dy / 2); put(wi, bx + dx, by + dy)
    for (hi, ki, ai, lift) in ((23, 25, 27, lleg), (24, 26, 28, rleg)):
        bx, by = pts[hi][0], pts[hi][1]
        k = 0.18 * (1 - 0.6 * squat) * (1 - lift)
        put(ki, bx + 0.05 * squat, by + k + 0.0); put(ai, bx, by + 2 * k + 0.02 * lift)
    return pts

def run(fn, seconds, mpr=None):
    lms = [fn(k / FPS) for k in range(int(seconds * FPS))]
    return lp.analyse(lms, seconds, mpr)

def near(x, want, tol=0.15):
    return x is not None and abs(x - want) <= tol * want

ease = lambda u: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, u)))

# 1. squat: 4.2 s per rep (down 1.8 s, up 1.8 s, 0.6 s pause), 3 s setup standing
def squat(t):
    if t < 3: return body()
    u = (t - 3) % 4.2
    return body(squat=ease(u / 1.8) if u < 1.8 else ease((3.6 - u) / 1.8) if u < 3.6 else 0)
r = run(squat, 3 + 4.2 * 8)
print("squat", r["seconds_per_rep"], r["confidence"], r["reason"])
assert near(r["seconds_per_rep"], 4.2) and r["rep_type"] == "simple", r

# 2. walkout: 12.6 s per rep. Hinge 2 s, hands walk out 4 s (with small hand shuffles that look like returns in pixels),
#    plank 2 s, walk back 3.6 s, stand 1 s.
def walkout(t):
    u = t % 12.6
    if u < 2: return body(torso=0.5 * ease(u / 2))
    if u < 6:
        v = (u - 2) / 4
        return body(torso=0.5 + 0.5 * ease(v), reach=ease(v) + 0.08 * math.sin(2 * math.pi * 4 * v))
    if u < 8: return body(torso=1.0, reach=1.0)
    if u < 11.6:
        v = (u - 8) / 3.6
        return body(torso=1.0 - ease(v), reach=1.0 - ease(v) + 0.08 * math.sin(2 * math.pi * 3 * v))
    return body()
r = run(walkout, 12.6 * 6)
print("walkout", r["seconds_per_rep"], r["movements_seen"], r["confidence"], r["reason"])
assert near(r["seconds_per_rep"], 12.6), r

# 3. drill of 4 different arm raises (lateral, front, left-front/right-side, switched), each 1.6 s up+down + 0.5 s,
#    = 8.4 s per rep; movements_per_rep = 4 from the library
moves = [((1, 1), (1, 1)), ((0.2, 1), (0.2, 1)), ((0.2, 1), (1, 1)), ((1, 1), (0.2, 1))]
def combo(t):
    u = t % 8.4; k = int(u // 2.1); v = (u - 2.1 * k)
    h = ease(v / 0.8) if v < 0.8 else ease((1.6 - v) / 0.8) if v < 1.6 else 0
    l, rr = moves[min(k, 3)]
    return body(lw=(l[0] * h, l[1] * h), rw=(rr[0] * h, rr[1] * h))
r = run(combo, 8.4 * 5, mpr=4)
print("combo", r["seconds_per_rep"], r["movements_seen"], r["movement_seconds"], r["repeat_seconds"], r["confidence"], r["reason"])
assert near(r["seconds_per_rep"], 8.4) and r["rep_type"] == "drill", r

# 4. hold: plank, nothing moves
r = run(lambda t: body(torso=1.0, reach=1.0, noise=0.002), 25)
print("hold", r["rep_type"], r["confidence"], r["reason"])
assert r["rep_type"] == "hold" and r["seconds_per_rep"] is None, r

# 5. one side then switch: right knee lifts 6 times (3 s each), then left 6 times
def knees(t):
    u = t % 3; h = ease(u / 1.2) if u < 1.2 else ease((2.4 - u) / 1.2) if u < 2.4 else 0
    return body(rleg=h) if t < 18 else body(lleg=h)
r = run(knees, 36)
print("knees", r["seconds_per_rep"], r["side_pattern"], r["sides_by_movement"], r["confidence"])
assert near(r["seconds_per_rep"], 3.0) and r["side_pattern"] == "one_side_then_switch", r

# 6. body hidden half the time -> flagged, never "high"
def hidden(t):
    return None if int(t) % 2 else squat(t + 3)
r = run(hidden, 30)
print("hidden", r["confidence"], r["reason"])
assert r["confidence"] != "high" and "visible" in r["reason"], r
print("pose timing ok")

# 7. the same drill WITHOUT movements-per-rep: must not report one raise (2.1 s) as a rep with high confidence
r = run(combo, 8.4 * 5)
print("combo, no structure", r["seconds_per_rep"], r["repeat_seconds"], r["movement_seconds"], r["confidence"], r["reason"])
assert near(r["seconds_per_rep"], 8.4) or r["confidence"] != "high", r
print("no-structure ok")
