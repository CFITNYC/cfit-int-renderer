"""CFIT INT private integrated renderer staging entrypoint.
Do not deploy as production until exercise-cycle quality is visually accepted.
"""
import os, json, hmac, pathlib, tempfile
from http.server import ThreadingHTTPServer
from worker import Handler as BaseHandler, render as render_existing
from worker_v7_branded_preview_STAGING import branded_preview, download_signed
from story_visual_sampler import frame_samples
from worker_autonomous_private_STAGING import render_autonomous

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
            if mode == "inspect_original_frames_private":
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
            if mode == "cfit_autonomous_preview_staging":
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
            self.answer(500, {"error": "Private video rendering failed"})

if __name__ == "__main__":
    if not os.environ.get("CFIT_RENDER_TOKEN"):
        raise RuntimeError("Missing render token")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8765"))), Handler).serve_forever()
