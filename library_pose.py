"""Library pose timing (Nov 11 2026): seconds per rep from body points instead of pixels. Private, read-only, free (no AI).

library_pose_timing : reads one private library video, finds 33 body points per frame with Google MediaPipe Pose
                      (on this server), and returns seconds per rep, rep type, side pattern, setup time, a confidence
                      and the reason. Nothing is kept, saved or published.

How a rep is found (no guessing):
 1. Each frame becomes a posture: 12 body points (shoulders, elbows, wrists, hips, knees, ankles) relative to the hips,
    scaled by torso length. Standing and plank look completely different; a raised arm looks different from a lowered one.
 2. Return to start: the start posture is chosen among the still moments; a movement = leave it, move far, come back.
 3. Self-similarity: the time after which the WHOLE posture sequence repeats (a 4-raise drill repeats every full
    sequence, not every raise). The library's movements-per-rep (when known) says roughly where to look.
 4. Both must agree (within 15%) for "high" confidence; otherwise the result is flagged with the reason.
The analysis below is plain Python (testable without the tracker); only extract_points() needs MediaPipe.
"""
import math, subprocess, tempfile, pathlib

import scout_story as ss

MODE = "library_pose_timing"
MAX_SECONDS = 180
FPS = 10
WIDTH = 384
MODEL = "/app/models/pose_landmarker_full.task"
# MediaPipe indices: shoulders 11/12, elbows 13/14, wrists 15/16, hips 23/24, knees 25/26, ankles 27/28
POINTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
LEFT, RIGHT = [11, 13, 15, 23, 25, 27], [12, 14, 16, 24, 26, 28]
MIN_VIS = 0.5

# ---------------------------------------------------------------- posture features (plain Python)
def posture(lm):
    """lm: list of 33 (x, y, visibility) or None. Returns a flat vector or None when the body is not clear."""
    if not lm:
        return None
    vis = [lm[i][2] for i in POINTS]
    if sum(v >= MIN_VIS for v in vis) < 9:
        return None
    hx = (lm[23][0] + lm[24][0]) / 2; hy = (lm[23][1] + lm[24][1]) / 2
    sx = (lm[11][0] + lm[12][0]) / 2; sy = (lm[11][1] + lm[12][1]) / 2
    torso = math.hypot(sx - hx, sy - hy)
    if torso < 1e-3:
        return None
    v = []
    for i in POINTS:
        v += [(lm[i][0] - hx) / torso, (lm[i][1] - hy) / torso]
    return v

def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))

def fill(vectors, max_gap=5):
    """Fill short gaps (body briefly unclear) by holding the last posture; long gaps stay None."""
    out, last, gap = list(vectors), None, 0
    for i, v in enumerate(out):
        if v is None:
            gap += 1
            if last is not None and gap <= max_gap:
                out[i] = last
        else:
            last, gap = v, 0
    return out

def smooth(vectors, k=2):
    out = []
    for i in range(len(vectors)):
        win = [v for v in vectors[max(0, i - k):i + k + 1] if v is not None]
        out.append([sum(c) / len(win) for c in zip(*win)] if win and vectors[i] is not None else None)
    return out

def speed(vectors):
    s = [0.0]
    for a, b in zip(vectors, vectors[1:]):
        s.append(dist(a, b) if a is not None and b is not None else 0.0)
    return s

# ---------------------------------------------------------------- return-to-start movements
def movements_from(ref, vectors, fps=FPS):
    """Leave the reference posture, go far, come back. Returns [(start_s, end_s, peak_distance)]."""
    d = [dist(ref, v) if v is not None else None for v in vectors]
    known = sorted(x for x in d if x is not None)
    if len(known) < fps * 2:
        return []
    top = known[int(len(known) * 0.9)]
    if top < 0.15:                      # nothing moves enough (a hold)
        return []
    lo, hi = 0.3 * top, 0.6 * top
    out, state, start, peak = [], "near", None, 0.0
    for i, x in enumerate(d):
        if x is None:
            continue
        if state == "near" and x > lo:
            state, start, peak = "out", i, x
        elif state == "out":
            peak = max(peak, x)
            if x <= lo:
                if peak >= hi:
                    out.append((round(start / fps, 2), round(i / fps, 2), round(peak, 3)))
                state = "near"
    return out

def still_moments(vectors, fps=FPS):
    sp = speed(vectors)
    known = sorted(x for x, v in zip(sp, vectors) if v is not None)
    if not known:
        return []
    calm = known[int(len(known) * 0.3)]
    idx = [i for i, v in enumerate(vectors) if v is not None and sp[i] <= calm]
    step = max(1, len(idx) // 12)       # about 12 candidate start postures across the video
    return idx[::step]

def best_movements(vectors, fps=FPS):
    """Try still moments as the start posture; keep the one giving the most regular movements."""
    best = (None, [], 1e9)
    for i in still_moments(vectors, fps):
        mv = movements_from(vectors[i], vectors, fps)
        if len(mv) < 2:
            continue
        starts = [m[0] for m in mv]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        mean = sum(gaps) / len(gaps)
        cv = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5 / mean if mean > 0 else 9
        score = cv - 0.02 * len(mv)    # regular first, then more complete movements
        if score < best[2]:
            best = (i, mv, score)
    return best[0], best[1]

# ---------------------------------------------------------------- self-similarity (when does the whole sequence repeat)
def repeat_curve(vectors, fps=FPS, max_lag_s=30.0):
    idx = [i for i, v in enumerate(vectors) if v is not None]
    if len(idx) < fps * 3:
        return {}
    step = 2                                            # every other frame is plenty
    base_pairs = [(idx[k], idx[(k * 7919) % len(idx)]) for k in range(0, len(idx), 3)]
    base = sum(dist(vectors[a], vectors[b]) for a, b in base_pairs) / len(base_pairs) or 1e-9
    curve = {}
    for lag in range(int(fps * 0.8), int(min(max_lag_s, len(vectors) / fps / 2) * fps) + 1):
        ds = [dist(vectors[t], vectors[t + lag]) for t in range(0, len(vectors) - lag, step)
              if vectors[t] is not None and vectors[t + lag] is not None]
        if len(ds) >= fps:
            curve[lag] = (sum(ds) / len(ds)) / base     # 0 = identical, 1 = like random moments
    return curve

def repeat_period(curve, fps=FPS, near_s=None):
    """The lag (s) where the sequence best repeats: a clear dip; when near_s is given, the dip closest to it."""
    if not curve:
        return None, None
    lags = sorted(curve)
    dips = [l for l in lags[1:-1] if curve[l] <= curve.get(l - 1, 9) and curve[l] <= curve.get(l + 1, 9) and curve[l] < 0.6]
    if not dips:
        return None, None
    if near_s:
        window = [l for l in dips if 0.7 * near_s * fps <= l <= 1.4 * near_s * fps]
        if window:
            l = min(window, key=lambda x: curve[x])
            return round(l / fps, 2), round(curve[l], 3)
    deepest = min(curve[l] for l in dips)
    l = min(l for l in dips if curve[l] <= deepest + 0.08)    # the first near-deepest dip (not its multiples)
    return round(l / fps, 2), round(curve[l], 3)

# ---------------------------------------------------------------- sides
def side_pattern(raw_vectors, movements, fps=FPS):
    """Which side moves in each movement: L, R or both (from left vs right point travel)."""
    li = [k for k, p in enumerate(POINTS) if p in LEFT]; ri = [k for k, p in enumerate(POINTS) if p in RIGHT]
    def travel(a, b, side):
        tot = 0.0
        for i in range(int(a * fps), min(len(raw_vectors) - 1, int(b * fps))):
            u, v = raw_vectors[i], raw_vectors[i + 1]
            if u is None or v is None:
                continue
            tot += sum(math.hypot(v[2 * k] - u[2 * k], v[2 * k + 1] - u[2 * k + 1]) for k in side)
        return tot
    marks = []
    for a, b, _ in movements:
        l, r = travel(a, b, li), travel(a, b, ri)
        marks.append("L" if l > 1.6 * r else "R" if r > 1.6 * l else "B")
    if not marks or all(m == "B" for m in marks):
        return "both_at_once", marks
    one = [m for m in marks if m != "B"]
    switches = sum(1 for a, b in zip(one, one[1:]) if a != b)
    if switches == 1:
        return "one_side_then_switch", marks
    if switches >= max(2, len(one) // 2):
        return "alternating", marks
    return "mixed", marks

# ---------------------------------------------------------------- the answer
def analyse(landmarks, duration, movements_per_rep=None, fps=FPS):
    raw = [posture(lm) for lm in landmarks]
    seen = sum(v is not None for v in raw) / max(1, len(raw))
    vec = smooth(fill(raw))
    ref_i, mv = best_movements(vec, fps)
    m = int(movements_per_rep) if movements_per_rep and int(movements_per_rep) > 0 else None
    starts = [x[0] for x in mv]
    gaps = sorted(b - a for a, b in zip(starts, starts[1:]))
    move_s = gaps[len(gaps) // 2] if gaps else None
    curve = repeat_curve(vec, fps)
    period, depth = repeat_period(curve, fps, near_s=(move_s * (m or 1)) if move_s else None)
    # a longer repeat that is clearly closer (for example a 4-raise drill repeating every 4 raises): the video says drill
    found_m = None
    if move_s and period and curve:
        for k in range(2, 9):
            lags = [l for l in curve if abs(l - k * move_s * fps) <= 0.1 * k * move_s * fps]
            if lags:
                l = min(lags, key=lambda x: curve[x])
                if curve[l] < 0.6 * (depth or 1) and curve[l] < 0.5:
                    found_m = k
                    break
    if found_m and (m or 1) != found_m:
        if not m:
            m = found_m
            near = move_s * m
            period, depth = repeat_period(curve, fps, near_s=near)
    sides, marks = side_pattern(raw, mv, fps)
    reasons = []
    if seen < 0.8:
        reasons.append(f"body clearly visible only {round(seen * 100)}% of the time")
    sp = speed(vec); known = [x for x, v in zip(sp, vec) if v is not None]
    still = bool(known) and sorted(known)[int(len(known) * 0.9)] < 0.02 and not mv
    if still or (not mv and period is None):
        rep_type = "hold" if seen >= 0.6 else "unclear"
        return {"rep_type": rep_type, "seconds_per_rep": None, "per_rep_seconds": [], "movements_seen": 0,
                "movements_per_rep": 0, "side_pattern": "not_sided", "setup_seconds": None,
                "confidence": "high" if rep_type == "hold" and not reasons else "low",
                "reason": "; ".join(reasons) or ("posture stays still: a hold" if rep_type == "hold" else "no repeating movement found"),
                "visible": round(seen, 2)}
    by_moves = round(move_s * (m or 1), 2) if move_s else None
    group = m or 1
    reps = [mv[k:k + group] for k in range(0, len(mv) - group + 1, group)]
    per_rep = [round(reps[k + 1][0][0] - r[0][0], 2) for k, r in enumerate(reps[:-1])]
    seconds = period or by_moves
    agree = bool(period and by_moves and abs(period - by_moves) <= 0.15 * max(period, by_moves))
    if len(reps) < 2:
        reasons.append(f"only {len(reps)} full rep seen")
    if period and by_moves and not agree:
        reasons.append(f"repeat time {period}s and movement count ({by_moves}s) disagree")
    if not period:
        reasons.append("the whole sequence does not clearly repeat")
    if found_m and not movements_per_rep:
        reasons.append(f"the video repeats every {found_m} movements: looks like a drill; confirm movements per rep")
    if found_m and movements_per_rep and int(movements_per_rep) != found_m:
        reasons.append(f"library says {movements_per_rep} movements per rep, the video repeats every {found_m}")
    if gaps and len(gaps) >= 2:
        mean = sum(gaps) / len(gaps)
        cv = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5 / mean
        if cv > 0.35 and group == 1:
            reasons.append("movement lengths vary a lot")
    first, last = (mv[0][0], mv[-1][1]) if mv else (0.0, duration)
    conf = "high" if not reasons and agree else ("medium" if len(reasons) <= 1 and seconds else "low")
    return {"rep_type": "drill" if group > 1 else "simple", "seconds_per_rep": seconds, "per_rep_seconds": per_rep,
            "movements_seen": len(mv), "movements_per_rep": group, "movement_seconds": move_s,
            "repeat_seconds": period, "repeat_strength": depth, "side_pattern": sides, "sides_by_movement": "".join(marks),
            "setup_seconds": round(first + max(0.0, duration - last), 1), "confidence": conf,
            "reason": "; ".join(reasons) or "movement count and whole-sequence repeat agree", "visible": round(seen, 2)}

# ---------------------------------------------------------------- server side (needs MediaPipe + ffmpeg)
def extract_points(path, seconds):
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    w = WIDTH
    probe = ss.video_size(path)
    h = int(round(probe[1] * w / probe[0] / 2)) * 2
    raw = subprocess.run([ss.FFMPEG, "-nostdin", "-v", "error", "-t", f"{seconds:.2f}", "-i", str(path),
                          "-vf", f"fps={FPS},scale={w}:{h}", "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                         capture_output=True, check=True, timeout=170).stdout
    n = w * h * 3
    opts = vision.PoseLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=MODEL),
                                        running_mode=vision.RunningMode.VIDEO, num_poses=1)
    out = []
    with vision.PoseLandmarker.create_from_options(opts) as lm:
        for k in range(len(raw) // n):
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.frombuffer(raw[k * n:(k + 1) * n], np.uint8).reshape(h, w, 3).copy())
            r = lm.detect_for_video(img, int(k * 1000 / FPS))
            out.append([(p.x, p.y, p.visibility) for p in r.pose_landmarks[0]] if r.pose_landmarks else None)
    return out

def pose_timing(job, get=None, points=None):
    if job.get("mode") != MODE or job.get("publishing_enabled") is not False:
        raise ValueError("Private timing required")
    url = str(job.get("signed_url") or "")
    if "/storage/v1/object/sign/cfit-exercise-videos/" not in url:
        raise ValueError("Private library video required")
    mpr = job.get("movements_per_rep")
    if mpr is not None and not (isinstance(mpr, int) and 1 <= mpr <= 12):
        raise ValueError("movements_per_rep must be 1-12")
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "source"
        (get or ss.fetch)(url, src)
        dur = ss.duration(src)
        if not 1.0 <= dur <= MAX_SECONDS:
            raise ValueError(f"Video must be 1-{MAX_SECONDS} seconds")
        lms = (points or extract_points)(src, dur)
        res = analyse(lms, dur, mpr)
        return {"status": "POSE_TIMING_MEASURED", "publishing_enabled": False, "duration": round(dur, 2), "fps": FPS, **res}
