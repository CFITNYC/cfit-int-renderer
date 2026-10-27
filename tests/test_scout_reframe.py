"""Library Reframe (portrait copy of a wide library video): safety tests (no network, no ffmpeg)."""
import scout_reframe as rf
import scout_story as ss

def refused(fn, job, words):
    try:
        fn(job)
    except ValueError as e:
        assert words in str(e), (words, str(e))
        return
    raise AssertionError("accepted: " + words)

url = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/exercises/CFM-EX-0054/a.mp4?token=t"
base = {"publishing_enabled": False, "signed_url": url, "start": 2, "end": 12, "path": [[2, 0.45], [12, 0.47]]}
# private only, library videos only
refused(rf.reframe_measure, {"mode": "scout_reframe_measure", "publishing_enabled": True, "signed_url": url}, "Private reframe required")
refused(rf.reframe_measure, {"mode": "scout_story_short", "publishing_enabled": False, "signed_url": url}, "Private reframe required")
refused(rf.reframe_measure, {"mode": "scout_reframe_measure", "publishing_enabled": False, "signed_url": url.replace("cfit-exercise-videos", "cfit-social-exports")}, "Private library video required")
refused(rf.reframe_render, {**base, "mode": "scout_reframe_save", "publishing_enabled": None}, "Private reframe required")
# the part and the box path are checked before any video is read
refused(rf.check_crop, {**base, "start": 5, "end": 2}, "Choose a part")
refused(rf.check_crop, {**base, "start": 0, "end": 121}, "Choose a part")
refused(rf.check_crop, {**base, "start": 1, "end": 1.2}, "Choose a part")
refused(rf.check_crop, {**base, "path": []}, "A box path is required")
refused(rf.check_crop, {**base, "path": [[2, 1.4]]}, "Box point out of range")
refused(rf.check_crop, {**base, "path": [[2, 0.5, 1]]}, "Each box point")
assert rf.check_crop(base) == (2.0, 12.0, [(2.0, 0.45), (12.0, 0.47)])
# the tall box: 9:16 of the full height, even, never wider than the picture
assert rf.box_width(1920, 1080) == 608 and rf.box_width(1280, 720) == 404 and rf.box_width(1080, 1920) == 1080
# the crop position follows the path in straight lines and never leaves the picture
x = rf.crop_x_expr([[2, 0.5], [12, 0.6]], 2, 1920, 608)
assert x.startswith("if(lt(t,0.000),656.00,") and "+(192.00)*(t-0.000)/10.000" in x   # 0.5*1920-304 = 656 → 0.6*1920-304 = 848
edge = rf.crop_x_expr([[0, 0.0], [5, 1.0]], 0, 1920, 608)
assert "0.00" in edge and "1312.00" in edge and "-" not in edge.split("*")[0]            # clamped to 0 … 1920-608
# movement by second: a block moving right registers where it moves, a still picture registers nothing
W, H = rf.MEASURE_W, rf.MEASURE_H
def frame(x0):
    return bytes(200 if x0 <= c < x0 + 10 and 10 <= r < 40 else 20 for r in range(H) for c in range(W))
frames = [frame(20 + i) for i in range(12)]                    # 3 s at 4 fps, moving slowly right
secs = rf.movement_by_second(frames)
assert len(secs) == 3 and all(s and 0.15 < s[0] < 0.3 and 0.3 < s[1] < 0.5 for s in secs), secs
assert all(s is None for s in rf.movement_by_second([frame(30)] * 8))            # nothing moves: nothing to keep (the page shows it grey)
cut = [frame(20)] * 4 + [bytes(255 - b for b in frame(20))] * 4  # the whole picture changes at once (a cut)
assert any(s and s[1] - s[0] >= 0.9 for s in rf.movement_by_second(cut))
# only ever reads the original: no upload, rename or delete code in this module
src = open("scout_reframe.py").read()
assert "upload" not in src.replace("cfit-exercise-videos", "") and "unlink" not in src and "remove(" not in src and "requests.put" not in src
assert '"-an"' in src                                            # no sound in the copy (Scout's rule)
print("Scout library reframe: PASS")
