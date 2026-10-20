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
        if audio.stat().st_size>10000000:
            raise ValueError("Nick audio exceeds private file limit")
        picture_duration=duration_seconds(video)
        speech_duration=duration_seconds(audio)
        extension=max(0.0,speech_duration-picture_duration+0.25)
        if extension>18.0:
            raise ValueError("Natural narration needs a new longer visual edit; more than 18s of frozen picture is not acceptable")
        words=job.get("timed_words") or []
        video_filters=[]
        if words:
            if job.get("alignment_source")!="elevenlabs" or not isinstance(words,list) or len(words)>140:
                raise ValueError("Actual ElevenLabs word timing required")
            import math
            entries=[]
            video_duration=picture_duration+extension
            for item in words:
                start=item.get("start");end=item.get("end");value=item.get("text")
                if not isinstance(value,str) or not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not (math.isfinite(start) and math.isfinite(end)):
                    raise ValueError("Caption alignment contains invalid word data")
                # ElevenLabs can return zero-length timestamps for punctuation or pauses.
                # They are not visible words and must not invalidate a valid voice mix.
                if end <= start:
                    continue
                if start < 0 or end > video_duration + 0.20:
                    raise ValueError(f"Caption alignment exceeds video: word ends at {end:.2f}s; video is {video_duration:.2f}s")
                start=max(0.0,float(start))
                end=min(float(end),video_duration)
                if end <= start:
                    continue
                clean=value.replace("{","").replace("}","").replace("\\","").replace("\n"," ").strip()
                if not clean:
                    continue
                if len(clean)>48: raise ValueError("Invalid caption text")
                entries.append((start,end,clean,item.get("gold") is True))
            if not entries:
                raise ValueError("Narration has no valid timed caption words")
            entries.sort(key=lambda x:x[0])
            def ass_time(n):
                c=round(n*100)
                return f"{c//360000}:{(c//6000)%60:02}:{(c//100)%60:02}.{c%100:02}"
            lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 720","PlayResY: 1280","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding","Style: Nick,DejaVu Sans,68,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,84,84,325,1","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
            for i in range(0,len(entries),2):
                group=entries[i:i+2]
                phrase=" ".join(("{\\c&H0037AFD4&}"+x[2].upper()+"{\\c&H00FFFFFF&}") if x[3] else x[2].upper() for x in group)
                lines.append(f"Dialogue: 0,{ass_time(group[0][0])},{ass_time(group[-1][1])},Nick,,0,0,0,,{phrase}")
            ass=root/"narration.ass"
            ass.write_text("\n".join(lines)+"\n",encoding="utf-8")
            video_filters=["-vf","tpad=stop_mode=clone:stop_duration="+str(round(extension,3))+",subtitles="+str(ass)] if extension>0 else ["-vf","subtitles="+str(ass)]
        if extension>0 and not words:
            video_filters=["-vf","tpad=stop_mode=clone:stop_duration="+str(round(extension,3))]
        codec=["-c:v","libx264","-preset","veryfast","-crf","21"] if words or extension>0 else ["-c:v","copy"]
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-i",str(video),"-i",str(audio),"-map","0:v:0","-map","1:a:0",*video_filters,*codec,"-c:a","aac","-b:a","128k","-t",str(picture_duration+extension),"-movflags","+faststart",str(result)],check=True,timeout=120)
        return result.read_bytes()

def private_music_mix(job):
    """Create a new private music-backed review copy; never overwrite the source."""
    if job.get("founder_review_required") is not True or job.get("publishing_enabled") is not False:
        raise ValueError("Private music review only")
    from worker_v7_branded_preview_STAGING import duration_seconds
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        picture=root/"narrated.mp4"; music=root/"instrumental.mp3"; final=root/"music-review.mp4"
        download_signed(job.get("video_signed_url",""),picture)
        download_signed(job.get("music_signed_url",""),music)
        picture_seconds=duration_seconds(picture)
        music_seconds=duration_seconds(music)
        if not 5 <= picture_seconds <= 180 or not 5 <= music_seconds <= 180:
            raise ValueError("Invalid picture or soundtrack duration")
        volume=float(job.get("music_volume",0.10))
        if not 0.05 <= volume <= 0.16:
            raise ValueError("Background music volume must be between 0.05 and 0.16")
        # No post-processing on Nick speech; preserve original picture stream and vocals.
        fade_start=max(0,picture_seconds-1.5)
        filterstr=f"[1:a]volume={volume},afade=t=out:st={fade_start:.3f}:d=1.5[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-i",str(picture),
          "-stream_loop","-1","-i",str(music),"-filter_complex",filterstr,
          "-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k",
          "-t",f"{picture_seconds:.3f}","-movflags","+faststart",str(final)],check=True,timeout=120)
        if not final.exists() or final.stat().st_size<10000:
            raise ValueError("Music render produced no video")
        return final.read_bytes()

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
            elif mode == "private_music_mix":
                video=private_music_mix(job)
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
            if mode in ("private_nick_voice_mix","private_music_mix"):
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
