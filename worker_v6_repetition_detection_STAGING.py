import os,json,hmac,tempfile,urllib.parse,urllib.request,subprocess,pathlib,re
from rep_cycles_staging import analyze_video
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
HOST=os.environ.get("CFIT_STORAGE_HOST","hszormivkbqvpfgfhktm.supabase.co")
def best_motion_start(src, seconds):
 # Analyze low-resolution frames from the original source without retaining video frames.
 # This is movement scoring, not understanding exercise technique.
 sample_rate=2
 frame_size=48*84
 args=["ffmpeg","-nostdin","-v","error","-t","55","-i",str(src),"-vf","fps=2,scale=48:84,format=gray","-an","-f","rawvideo","-pix_fmt","gray","pipe:1"]
 try:
  out=subprocess.run(args,capture_output=True,timeout=35,check=True).stdout
  n=len(out)//frame_size
  if n<sample_rate*(seconds+2):return 0.0
  samples=[out[i*frame_size:(i+1)*frame_size] for i in range(n)]
  motion=[0]
  for i in range(1,n):
   a,b=samples[i-1],samples[i]
   motion.append(sum(abs(x-y) for x,y in zip(a[::5],b[::5]))/len(a[::5]))
  width=max(2,int(seconds*sample_rate))
  latest=n-width-1
  earliest=min(6,max(0,latest))
  if latest<earliest:return 0.0
  # Favor sustained, evenly distributed movement instead of one brief motion spike.
  # Reject windows with extended idle frames when stronger windows exist.
  scored=[]
  for k in range(earliest,latest+1):
   frames=motion[k+1:k+width]
   if not frames:continue
   halves=[frames[:len(frames)//2],frames[len(frames)//2:]]
   half_means=[sum(v)/len(v) for v in halves if v]
   sorted_m=sorted(frames)
   lower_half=sum(sorted_m[:max(1,len(sorted_m)//2)])/max(1,len(sorted_m)//2)
   high=max(sorted_m)
   sustained=min(half_means) if half_means else 0
   spike_penalty=max(0,high-3*max(1,sustained))
   # Prioritize a usable exercise segment: sustained movement across the window,
   # not a burst followed by stillness. This is not exercise-repetition recognition.
   floor=max(1.2,0.32*max(sorted_m))
   active_fraction=sum(v>=floor for v in frames)/len(frames)
   thirds=[frames[z::3] for z in range(3)]
   consistency=min(sum(g)/len(g) for g in thirds if g)
   quiet_fraction=sum(v<floor for v in frames)/len(frames)
   score=(2.1*sustained+1.3*lower_half+0.8*consistency
          +0.7*sum(frames)/len(frames)+3.5*active_fraction
          -2.0*quiet_fraction-0.32*spike_penalty)
   scored.append((score,k))
  if not scored:return 0.0
  best=max(scored,key=lambda item:item[0])[1]
  return round(best/sample_rate,1)
 except (subprocess.CalledProcessError,subprocess.TimeoutExpired,ValueError):
  return 0.0

def render(j):
 if j.get("mode")!="source_to_preview" or j.get("publishing_enabled") is not False: raise ValueError("Preview-only request required")
 clips=j.get("sources")
 if not isinstance(clips,list) or not 1<=len(clips)<=6:raise ValueError("1-6 original clips required")
 title=str(j.get('title','MOVE FREELY. STAY GROUNDED.'))[:65]
 title=re.sub(r'[^a-zA-Z0-9 .,!?-]','',title) or 'CFIT METHOD'
 duration_total=sum(float(c.get('duration',5)) for c in clips)
 if duration_total>36:raise ValueError('Preview exceeds 36 seconds')
 with tempfile.TemporaryDirectory() as t:
  t=pathlib.Path(t);segments=[]
  for i,c in enumerate(clips):
   if not all(c.get(x) is True for x in ("original_source","usage_rights_confirmed","subject_consent_confirmed")) or c.get("rejected") is not False:raise ValueError("Unapproved or rejected source")
   u=urllib.parse.urlsplit(c.get("signed_url",""))
   if u.scheme!="https" or u.hostname!=HOST or not u.path.startswith("/storage/v1/object/sign/") or pathlib.PurePosixPath(u.path).suffix.lower() not in (".mp4",".mov",".m4v"):raise ValueError("Invalid signed source")
   if any(x in u.path.lower() for x in ("_review","polished","finished_post","_v4","_v5","_v6","_v7")):raise ValueError("Edited media not permitted")
   src=t/("original"+str(i)+pathlib.PurePosixPath(u.path).suffix.lower())
   with urllib.request.urlopen(c["signed_url"],timeout=40) as f,open(src,"wb") as out:
    total=0
    while True:
     chunk=f.read(65536)
     if not chunk:break
     total+=len(chunk)
     if total>200000000:raise ValueError("Source over 200 MB")
     out.write(chunk)
   seconds=float(c.get("duration",5))
   if c.get("auto_select_complete_cycle") is True:
    cycles=analyze_video(str(src),fps=5)
    # Short near-identical poses can be transitions, not complete repetitions.
    viable=[cycle for cycle in cycles if (cycle.end-cycle.start)>=3.0 and cycle.confidence>=0.55]
    if not viable:raise ValueError("No sufficiently long full-cycle candidate found; founder review required")
    # First credible cycle avoids accidentally selecting a short later transition.
    cycle=min(viable,key=lambda v:v.start)
    # Include modest margins, preserving the full return-to-start movement.
    start=max(0.0,cycle.start-0.4)
    seconds=min(18.0,round(cycle.end+0.4-start,2))
   else:
    start=best_motion_start(src,seconds) if c.get("auto_select_motion") is True else float(c.get("start",0))
   if not 1<=seconds<=18 or not 0<=start<=3600:raise ValueError("Invalid segment timing")
   seg=t/("segment"+str(i)+".mp4")
   overlay=t/("title"+str(i)+".txt");overlay.write_text(title if i==0 else re.sub(r"[^a-zA-Z0-9 .,!?-]","",str(c.get("label","CFIT METHOD")))[:33])
   brand=t/("brand"+str(i)+".txt");brand.write_text("CFIT METHOD  |  CREATIVE FITNESS NYC")
   vf="scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,drawbox=x=0:y=0:w=iw:h=165:color=black@0.48:t=fill,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile="+str(overlay)+":fontsize=29:fontcolor=white:x=(w-text_w)/2:y=70,drawbox=x=0:y=1180:w=iw:h=100:color=black@0.58:t=fill,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile="+str(brand)+":fontsize=21:fontcolor=white:x=(w-text_w)/2:y=1214"
   args=["ffmpeg","-nostdin","-v","error","-y","-ss",str(start),"-t",str(seconds),"-i",str(src),"-vf",vf,"-an","-c:v","libx264","-preset","ultrafast","-crf","24","-pix_fmt","yuv420p",str(seg)]
   subprocess.run(args,check=True,timeout=100,capture_output=True);segments.append(seg)
  txt=t/"list.txt";txt.write_text("".join("file '"+str(s)+"'\\n" for s in segments).replace("\\n","\n"))
  final=t/"preview.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(txt),"-c","copy","-movflags","+faststart",str(final)],check=True,timeout=60,capture_output=True)
  return final.read_bytes()
class Handler(BaseHTTPRequestHandler):
 def answer(self,status,data):
  b=json.dumps(data).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  return self.answer(200,{"ok":True,"service":"CFIT_INT_RENDER_WORKER","publishing_enabled":False}) if self.path=="/health" else self.answer(404,{"error":"Not found"})
 def do_POST(self):
  if self.path!="/render":return self.answer(404,{"error":"Not found"})
  key=os.environ.get("CFIT_RENDER_TOKEN","")
  if not key or not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+key):return self.answer(401,{"error":"Not authorized"})
  try:
   n=int(self.headers.get("Content-Length","0"))
   if n<1 or n>16000:return self.answer(413,{"error":"Invalid body length"})
   data=render(json.loads(self.rfile.read(n)))
   self.send_response(200);self.send_header("Content-Type","video/mp4");self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
  except ValueError as e:self.answer(422,{"error":str(e)})
  except Exception:self.answer(500,{"error":"Render failed"})
if __name__=="__main__":
 if not os.environ.get("CFIT_RENDER_TOKEN"):raise RuntimeError("Missing render token")
 ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","8765"))),Handler).serve_forever()