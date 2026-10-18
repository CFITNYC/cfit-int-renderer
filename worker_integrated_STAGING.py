"""CFIT INT private integrated renderer staging entrypoint.
Do not deploy as production until exercise-cycle quality is visually accepted.
"""
import os, json, hmac, pathlib, tempfile, traceback, subprocess
from http.server import ThreadingHTTPServer
from worker import Handler as BaseHandler, render as render_existing
from worker_v7_branded_preview_STAGING import branded_preview, download_signed
from story_visual_sampler import frame_samples
from worker_autonomous_private_STAGING import render_autonomous

def private_audio_mix(job):
    """Finish a previously rendered private video; preserve existing images and branding."""
    if job.get("founder_review_required") is not True or job.get("publishing_enabled") is not False:
        raise ValueError("Founder review and disabled publishing required")
    from worker_v7_branded_preview_STAGING import duration_seconds
    with tempfile.TemporaryDirectory() as tmp:
        root=pathlib.Path(tmp)
        video=root/"picture.mp4"; audio=root/"nick.mp3"; result=root/"narrated.mp4"
        download_signed(job.get("video_signed_url",""),video)
        import urllib.parse,urllib.request
        u=urllib.parse.urlsplit(job.get("voice_signed_url",""))
        if u.scheme!="https" or u.hostname!=os.environ.get("CFIT_STORAGE_HOST","hszormivkbqvpfgfhktm.supabase.co") or not u.path.startswith("/storage/v1/object/sign/cfit-int-private-audio/") or not u.path.endswith(".mp3"):
            raise ValueError("Signed Nick audio required")
        with urllib.request.urlopen(job["voice_signed_url"],timeout=35) as inp,open(audio,"wb") as out:
            out.write(inp.read(10000001))
        if audio.stat().st_size>10000000 or duration_seconds(audio)>duration_seconds(video):
            raise ValueError("Narration cannot exceed locked video duration")
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-i",str(video),"-i",str(audio),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","128k","-t",str(duration_seconds(video)),"-movflags","+faststart",str(result)],check=True,timeout=80)
        return result.read_bytes()

class Handler(BaseHandler):
    def do_POST(self):
        if self.path != "/render":
            return self.answer(404, {"error": "Not found"})
        key = os.environ.get("CFIT_RENDER_TOKEN", "")
        if not key or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key):
            return self.answer(401, {"error": "Not authorized"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 16000:
                return self.answer(413, {"error": "Invalid body length"})
            job = json.loads(self.rfile.read(size))
            mode = job.get("mode")
            if job.get("publishing_enabled") is not False:
                raise ValueError("Publishing must be disabled")
            if mode == "private_nick_voice_mix":
                video=private_audio_mix(job)
            elif mode == "inspect_original_frames_private":
                sources=job.get("sources")
                if not isinstance(sources,list) or not 1<=len(sources)<=3:
                    raise ValueError("1-3 original sources required")
                with tempfile.TemporaryDirectory() as td:
                    result=[]
                    for i,source in enumerate(sources):
                        if not isinstance(source,dict) or not source.get("source_id") or source.get("original_source") is not True:
                            raise ValueError("Original source and ID required")
                        path=pathlib.Path(td)/("inspection-"+str(i)+".mp4")
                        download_signed(source.get("signed_url",""),path)
                        sample=frame_samples(path,interval=3,max_seconds=54,max_frames=18)
                        result.append({"source_id":source["source_id"],**sample})
                return self.answer(200,{"status":"ORIGINAL_FRAMES_UNVERIFIED","publishing_enabled":False,"sources":result})
            if mode == "private_nick_voice_mix":
                pass
            elif mode == "cfit_autonomous_preview_staging":
                video = render_autonomous(job)
            elif mode == "cfit_branded_preview_staging":
                video = branded_preview(job)
            elif mode == "source_to_preview" and not job.get("editing_contract"):
                video = render_existing(job)
            else:
                raise ValueError("Unsupported or incomplete editing contract")
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(video)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(video)
        except (ValueError, json.JSONDecodeError) as exc:
            self.answer(422, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self.answer(500, {"error": "Private video rendering failed"})

if __name__ == "__main__":
    if not os.environ.get("CFIT_RENDER_TOKEN"):
        raise RuntimeError("Missing render token")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8765"))), Handler).serve_forever()
