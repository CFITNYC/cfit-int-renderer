"""Rotated phone clips (2026-11-04): an iPhone portrait clip is stored sideways with a 90° rotation note.
The renderer must read it as portrait everywhere it reads a clip's size. Needs ffmpeg on PATH (small made-up clips)."""
import pathlib, subprocess, tempfile

import scout_story as ss
import scout_framing as sf
import scout_reframe as sr

# 1. the size text, both ways ffmpeg prints a rotation (newer: displaymatrix; older: rotate tag)
NEW = """  Stream #0:0[0x1](und): Audio: aac (LC), 48000 Hz, stereo
  Stream #0:2[0x3](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 1278x718, 10333 kb/s, 30.01 fps
      Side data:
        displaymatrix: rotation of -90.00 degrees
  Stream #0:3[0x4](und): Data: none (mebx / 0x7862656D)"""
OLD = """    Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 1920x1080, 15000 kb/s, 30 fps
    Metadata:
      rotate          : 90
      handler_name    : Core Media Video"""
assert ss.size_from_probe(NEW) == (718, 1278)
assert ss.size_from_probe(OLD) == (1080, 1920)
assert ss.size_from_probe(NEW.replace("-90.00", "90.00")) == (718, 1278)
assert ss.size_from_probe(NEW.replace("-90.00", "-270.00")) == (718, 1278)
assert ss.size_from_probe(NEW.replace("-90.00", "180.00")) == (1278, 718)          # upside down: same shape
assert ss.size_from_probe(NEW.replace("rotation of -90.00 degrees", "")) == (1278, 718)   # no note: unchanged
assert ss.size_from_probe("  Stream #0:0: Video: h264, yuv420p, 1920x1080, 30 fps") == (1920, 1080)
# a rotation note on ANOTHER stream after the video doesn't count
assert ss.size_from_probe("  Stream #0:0: Video: h264, yuv420p, 1920x1080, 30 fps\n  Stream #0:1: Video: mjpeg, 320x240\n      displaymatrix: rotation of -90.00 degrees") == (1920, 1080)
assert ss.size_from_probe("no video here") == (720, 1280)                           # same fallback as before

# 2. real small clips through ffmpeg: a person-sized moving block, portrait picture stored sideways with a note
def clip(path, w, h, rotate=None, x_expr="(W-w)/2", seconds=4):
    bw, bh = int(w * 0.18), int(h * 0.7)
    fc = (f"color=c=0x202020:s={w}x{h}:d={seconds}:r=15[bg];color=c=white:s={bw}x{bh}:d={seconds}:r=15[fg];"
          f"[bg][fg]overlay=x='{x_expr.replace('iw', 'W').replace('(W-w)/2', '(W-w)/2+W*0.1*sin(t*4)')}':y=H*0.15:shortest=1")
    subprocess.run([ss.FFMPEG, "-v", "error", "-y", "-filter_complex", fc, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    if rotate is not None:   # re-mux the encoded file with the rotation note (the picture stays stored sideways)
        tmp = path.with_name("r_" + path.name)
        subprocess.run([ss.FFMPEG, "-v", "error", "-y", "-display_rotation", str(rotate), "-i", str(path), "-c", "copy", str(tmp)], check=True)
        tmp.replace(path)

with tempfile.TemporaryDirectory() as td:
    t = pathlib.Path(td)
    rot = t / "rot.mp4"; clip(rot, 640, 360, rotate=-90, x_expr="iw*0.3+iw*0.2*sin(t*3)")   # stored 640x360, shown 360x640
    assert ss.video_size(rot) == (360, 640), ss.video_size(rot)
    # frames come out upright, so they match the size now read
    fr = ss.gray_frames(rot, 0, 1, fps=2, w=36, h=64)
    assert fr and len(fr[0]) == 36 * 64
    # framing: a rotated portrait clip is shown whole and passes (before the fix: judged landscape)
    r = sf.measure({"u": rot}, ["u"], [{"signed_url": "u", "start": 0.5, "end": 3.5}])
    c = r["clips"][0]   # the crop itself (band placement depends on the made-up picture, not on this fix)
    assert c["ok"] and c["portrait"] and c["box"][0] == 0.0 and c["box"][2] == 1.0, r
    assert r.get("reason") != "too_wide", r
    assert r["sources"][0]["portrait"] is True, r["sources"]
    # reframe: it's already tall
    try:
        w, h = ss.video_size(rot); assert sr.box_width(w, h) >= w
    except AttributeError:
        pass
    # a real landscape clip (no note) is still landscape and still refused when the movement is wider than 9:16
    wide = t / "wide.mp4"; clip(wide, 640, 360, x_expr="iw*0.05+iw*0.7*(0.5+0.5*sin(t*3))")
    assert ss.video_size(wide) == (640, 360)
    r = sf.measure({"u": wide}, ["u"], [{"signed_url": "u", "start": 0.5, "end": 3.5}])
    assert not r["ok"] and r["reason"] == "too_wide", r
    # upside-down (180°) keeps its shape
    flip = t / "flip.mp4"; clip(flip, 640, 360, rotate=180)
    assert ss.video_size(flip) == (640, 360)

print("rotated phone clips: all checks pass")
