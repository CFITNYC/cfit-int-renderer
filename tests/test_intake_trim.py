"""Intake trim: safety tests with no network; a real short clip when ffmpeg is available (FFMPEG=path, as on this Mac)."""
import http.server, os, pathlib, subprocess, tempfile, threading
import intake_trim as it
import scout_story as ss

def refused(fn, job, words):
    try:
        fn(job)
    except ValueError as e:
        assert words in str(e), (words, str(e))
        return
    raise AssertionError("accepted: " + words)

H = "https://hszormivkbqvpfgfhktm.supabase.co"
src = H + "/storage/v1/object/sign/cfit-exercise-videos/intake/b/a%20b.mov?token=t"
dst = H + "/storage/v1/object/upload/sign/cfit-exercise-videos/intake/trims/i/n.mp4?token=t"
job = {"mode": "intake_trim_save", "publishing_enabled": False, "signed_url": src, "upload_url": dst, "start": 2, "end": 12}
assert it.check_job(job) == (2.0, 12.0)
refused(it.check_job, {**job, "publishing_enabled": None}, "Private trim required")
refused(it.check_job, {**job, "mode": "scout_reframe_save"}, "Private trim required")
refused(it.check_job, {**job, "signed_url": src.replace("https", "http")}, "Private upload link")
refused(it.check_job, {**job, "signed_url": src.replace("supabase.co", "evil.example")}, "Private upload link")
refused(it.check_job, {**job, "signed_url": src.replace("/intake/", "/exercises/")}, "Private upload link")      # never a Library file
refused(it.check_job, {**job, "signed_url": src.replace("cfit-exercise-videos", "cfit-social-exports")}, "Private upload link")
refused(it.check_job, {**job, "upload_url": dst.replace("/intake/", "/exercises/")}, "Private storage link")
refused(it.check_job, {**job, "upload_url": dst.replace("upload/sign", "sign")}, "Private storage link")
refused(it.check_job, {**job, "upload_url": dst.replace("n.mp4", "n.mov")}, "Private storage link")
refused(it.check_job, {**job, "start": 5, "end": 2}, "Choose a part")
refused(it.check_job, {**job, "start": 1, "end": 2.5}, "Choose a part")
refused(it.check_job, {**job, "start": 0, "end": 121}, "Choose a part")
refused(it.check_job, {**job, "start": -1, "end": 5}, "Choose a part")
assert it.check_job({**job, "start": 1, "end": 3}) == (1.0, 3.0) and it.check_job({**job, "start": 0, "end": 120}) == (0.0, 120.0)
a = it.cut_args("s", "o", 1.5, 10)
assert a[a.index("-ss") + 1] == "1.500" and a.index("-ss") < a.index("-i") and a[a.index("-crf") + 1] == "20"
assert a[a.index("-fps_mode") + 1] == "vfr"                                 # never duplicates frames
assert "copy" not in a and "-an" not in a and "-vf" not in a                # exact cut, sound kept, no colour change
s = open("intake_trim.py").read()
assert "unlink" not in s and "remove(" not in s and "DELETE" not in s       # this module never deletes anything
if os.environ.get("FFMPEG"):
    ss.FFMPEG = it.ss.FFMPEG = os.environ["FFMPEG"]
    td = pathlib.Path(tempfile.mkdtemp())
    clip = td / "c.mov"
    subprocess.run([ss.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=720x1280:rate=30:duration=12", "-f", "lavfi", "-i", "sine=duration=12",
                    "-g", "30", "-c:v", "libx264", "-c:a", "aac", "-metadata:s:v:0", "rotate=90", str(clip)], check=True)
    got = {}
    class S(http.server.BaseHTTPRequestHandler):
        def do_PUT(self):
            n = int(self.headers["Content-Length"]); got["b"] = self.rfile.read(n); got["ct"] = self.headers["Content-Type"]; got["up"] = self.headers["x-upsert"]
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), S); threading.Thread(target=srv.serve_forever, daemon=True).start()
    orig = open(clip, "rb").read()
    get = lambda u, d: pathlib.Path(d).write_bytes(orig)
    put = lambda u, p: it.upload(f"http://127.0.0.1:{srv.server_port}/x", p)
    r = it.intake_trim({**job, "start": 2.4, "end": 7.9}, get=get, put=put)
    assert r["status"] == "TRIM_SAVED" and abs(r["seconds"] - 5.5) < 0.1 and r["source_seconds"] == 12 and r["bytes"] == len(got["b"]), r
    assert got["ct"] == "video/mp4" and got["up"] == "false"
    out = td / "o.mp4"; out.write_bytes(got["b"])
    info = subprocess.run([ss.FFMPEG, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    assert "h264" in info and "aac" in info, info
    assert open(clip, "rb").read() == orig                                   # the source is only read
    # the first frame of the result is the frame at the start time, not the keyframe before it
    gray = lambda p, ss_: subprocess.run([ss.FFMPEG, "-v", "error", "-ss", ss_, "-i", str(p), "-frames:v", "1", "-vf", "scale=64:64,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    a0, b0 = gray(clip, "2.4"), gray(out, "0")
    assert sum(abs(x - y) for x, y in zip(a0, b0)) / len(a0) < 6, "start not exact"
    refused(lambda j: it.intake_trim(j, get=get, put=put), {**job, "start": 9, "end": 20}, "ends after the video")
    print("real clip:", r)
print("Intake trim: PASS")
