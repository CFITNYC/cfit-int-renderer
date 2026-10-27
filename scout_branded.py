# CFIT Scout branded short (2026-10-26). Private preview only; publishing stays off.
# Your opening clip + Scout's titled exercise clip + your closing clip, as ONE continuous video:
# every part is scaled to 720x1280 (same 9:16 shape, no bars), set to 30 fps, and joined in a single
# encode so there are no jumps or gaps. A silent stereo sound track runs the full length, so every
# part has the same (silent) sound and music can be added later. Brand clips are never drawn over.
import pathlib, subprocess, tempfile
from worker import render as render_middle
from worker_v7_branded_preview_STAGING import download_signed

FFMPEG = "ffmpeg"
MAX_MIDDLE_SECONDS = 13  # keeps the whole video about 15 seconds with the 0.7 s opening and 1.5 s closing
SIZE = "720:1280"
FPS = 30

def scout_branded(job):
    if job.get("mode") != "scout_branded_short" or job.get("publishing_enabled") is not False:
        raise ValueError("Private Scout preview required")
    brand = job.get("branding") or {}
    if brand.get("opening_role") != "opening" or brand.get("closing_role") != "closing":
        raise ValueError("Opening and closing roles required")
    source = job.get("source") or {}
    seconds = float(source.get("duration", MAX_MIDDLE_SECONDS))
    if not 3 <= seconds <= MAX_MIDDLE_SECONDS:
        raise ValueError("Middle clip must be 3 to 13 seconds")
    middle_job = {"mode": "source_to_preview", "publishing_enabled": False, "title": job.get("title", "CFIT METHOD"), "sources": [source]}
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        first, mid, last, out = t / "opening.mp4", t / "middle.mp4", t / "closing.mp4", t / "scout-branded.mp4"
        download_signed(brand.get("opening_signed_url", ""), first)
        download_signed(brand.get("closing_signed_url", ""), last)
        mid.write_bytes(render_middle(middle_job))  # existing renderer: best motion window, title band, brand bar
        # One colour standard for the whole video: the iPhone-made brand clips are tagged HDR (HLG) while the
        # exercise part is standard; tagging everything standard (BT.709) keeps how they look now and stops
        # phones from switching modes mid-video.
        norm = (f"scale={SIZE}:force_original_aspect_ratio=decrease,pad={SIZE}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS},setsar=1,"
                "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv,format=yuv420p")
        graph = f"[0:v]{norm}[a];[1:v]{norm}[b];[2:v]{norm}[c];[a][b][c]concat=n=3:v=1:a=0[v]"
        subprocess.run([FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-y",
                        "-i", str(first), "-i", str(mid), "-i", str(last),
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                        "-filter_complex", graph, "-map", "[v]", "-map", "3:a", "-shortest",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)],
                       check=True, timeout=150, capture_output=True)
        return out.read_bytes()
