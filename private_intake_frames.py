import base64
import pathlib
import subprocess
import tempfile
import urllib.parse
import urllib.request


def inspect_private_frames(payload, storage_host):
    if payload.get("publishing_enabled") is not False:
        raise ValueError("Inspection requires publishing disabled")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("Exactly one source required")
    source = sources[0]
    if source.get("original_source") is not True:
        raise ValueError("An original source is required")
    url = urllib.parse.urlsplit(source.get("signed_url", ""))
    suffix = pathlib.PurePosixPath(url.path).suffix.lower()
    if (url.scheme != "https" or url.hostname != storage_host or
            not url.path.startswith("/storage/v1/object/sign/") or
            suffix not in (".mp4", ".mov", ".m4v")):
        raise ValueError("Invalid private signed video URL")
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / ("original" + suffix)
        with urllib.request.urlopen(source["signed_url"], timeout=40) as response, open(path, "wb") as output:
            total = 0
            while True:
                block = response.read(65536)
                if not block:
                    break
                total += len(block)
                if total > 200000000:
                    raise ValueError("Video exceeds size limit")
                output.write(block)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=20)
        duration = float(probe.stdout.strip())
        if not 0.3 <= duration <= 3600:
            raise ValueError("Unsupported video duration")
        frames = []
        for position in (0.08, 0.25, 0.42, 0.58, 0.75, 0.92):
            second = round(duration * position, 2)
            jpeg = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(second),
                 "-i", str(path), "-frames:v", "1", "-vf", "scale=360:-2",
                 "-q:v", "8", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                check=True, capture_output=True, timeout=30).stdout
            if not jpeg or len(jpeg) > 400000:
                raise ValueError("Unable to sample video frame")
            frames.append({"at_seconds": second,
                           "jpeg_base64": base64.b64encode(jpeg).decode("ascii")})
        return {"sources": [{"source_id": source.get("source_id"), "frames": frames}]}
