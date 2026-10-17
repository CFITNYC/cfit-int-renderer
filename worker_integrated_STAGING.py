"""CFIT INT private integrated renderer staging entrypoint.
Do not deploy as production until exercise-cycle quality is visually accepted.
"""
import os, json, hmac
from http.server import ThreadingHTTPServer
from worker import Handler as BaseHandler, render as render_existing
from worker_v7_branded_preview_STAGING import branded_preview

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
            if mode == "cfit_branded_preview_staging":
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
