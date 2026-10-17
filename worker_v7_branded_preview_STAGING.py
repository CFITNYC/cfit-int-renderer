# CFIT INT branded preview staging. Not wired to live /render.
# Preserves athlete-logo intro/outro. Middle remains experimental motion edit.
import io, pathlib, subprocess, tempfile, urllib.parse, urllib.request
from worker_v6_repetition_detection_STAGING import HOST, render as render_middle
ALLOWED_BUCKETS={"cfit-social-exports","cfit-exercise-videos"}
def download_signed(url,dest):
 p=urllib.parse.urlsplit(url)
 if p.scheme!="https" or p.hostname!=HOST or not p.path.startswith("/storage/v1/object/sign/"): raise ValueError("Unsigned or unsupported asset")
 remainder=p.path.split("/storage/v1/object/sign/",1)[1]
 if remainder.split("/",1)[0] not in ALLOWED_BUCKETS or pathlib.PurePosixPath(p.path).suffix.lower()!=".mp4": raise ValueError("Invalid asset source")
 with urllib.request.urlopen(url,timeout=45) as response,open(dest,"wb") as f:
  n=0
  while True:
   chunk=response.read(65536)
   if not chunk: break
   n+=len(chunk)
   if n>55000000:raise ValueError("Asset too large")
   f.write(chunk)
def normalize(src,dst):
 # Same letterboxed composition for any 9:16 visual. Do not draw over brand animations.
 vf="scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,fps=24,format=yuv420p"
 subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-y","-i",str(src),"-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart",str(dst)],check=True,timeout=140)
def duration_seconds(path):
 import json
 data=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(path)],capture_output=True,text=True,check=True,timeout=15)
 return float(json.loads(data.stdout)["format"]["duration"])

def check_platform_duration(opening,middle,closing,contract):
 if not contract or not contract.get("platform") or contract.get("minimum_complete_repetitions_per_exercise")!=1:
  raise ValueError("Founder platform editing contract required")
 maximum=float(contract.get("maximum_seconds",0))
 total=sum((opening,middle,closing))
 if maximum<=0 or total>maximum:
  raise ValueError("Complete exercises plus approved branding exceed platform duration; reduce exercises or request longer post")
 return round(total,2)

def branded_preview(job):
 if job.get("mode")!="cfit_branded_preview_staging" or job.get("publishing_enabled") is not False: raise ValueError("Private-only job required")
 if job.get("founder_review_required") is not True:raise ValueError("Founder review required")
 assets=job.get("branding") or {}
 if assets.get("opening_role")!="opening" or assets.get("closing_role")!="closing":raise ValueError("Opening and closing roles required")
 middle_sources=job.get("middle_sources")
 if not isinstance(middle_sources,list) or not middle_sources:raise ValueError("Original exercise sources required")
 if not all(source.get("auto_select_complete_cycle") is True and source.get("auto_select_motion") is not True for source in middle_sources):raise ValueError("Complete-cycle selection required for every exercise")
 # CFIT V17 story regression gate: do not use optical-cycle cuts in story mode.
 # Story evidence must identify original-source movement boundaries; a motion
 # score can never attest to a BOSU entry, hip extension, or final balance.
 required=("setup_entry","hip_extension_transition","upright_single_leg_finish")
 evidence=job.get("story_evidence")
 if not isinstance(evidence,dict) or evidence.get("verified_by")!="founder" or not all(isinstance(evidence.get(k),dict) and isinstance(evidence[k].get("source_id"),str) and isinstance(evidence[k].get("start"),(int,float)) and isinstance(evidence[k].get("end"),(int,float)) and 0<=evidence[k]["start"]<evidence[k]["end"] for k in required):
  raise ValueError("CFIT STORY_GATE: setup, hip-extension transition and upright single-leg finish need verified source boundaries; motion-only montage prohibited")
 # The original montage renderer cannot yet place or preserve verified story
 # windows. Refuse rendering rather than silently discarding the evidence.
 raise ValueError("CFIT STORY_GATE: story-aware sequence assembler pending; no incomplete montage will be delivered")

 with tempfile.TemporaryDirectory() as td:
  t=pathlib.Path(td);parts=[]
  first=t/"opening-source.mp4";last=t/"closing-source.mp4"
  download_signed(assets.get("opening_signed_url",""),first)
  download_signed(assets.get("closing_signed_url",""),last)
  middle_job={"mode":"source_to_preview","publishing_enabled":False,"title":job.get("title","CFIT METHOD"),"sources":middle_sources}
  # Current render worker still uses motion scoring, NOT phase/rep understanding.
  mid=t/"middle-source.mp4";mid.write_bytes(render_middle(middle_job))
  check_platform_duration(duration_seconds(first),duration_seconds(mid),duration_seconds(last),job.get("editing_contract"))
  for i,src in enumerate((first,mid,last)):
   out=t/f"normalized-{i}.mp4";normalize(src,out);parts.append(out)
  list_file=t/"concat.txt";list_file.write_text("".join("file '"+str(p)+"'\n" for p in parts))
  final=t/"private-branded-review.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(list_file),"-c","copy","-movflags","+faststart",str(final)],check=True,timeout=60)
  return final.read_bytes()