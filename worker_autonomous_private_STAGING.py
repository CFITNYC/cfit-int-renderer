"""Private autonomous-edit renderer. Executes source-backed AI editorial shot list, no fixed exercise choreography."""
import pathlib, tempfile, subprocess, json
from worker_v7_branded_preview_STAGING import download_signed, duration_seconds, normalize

def render_autonomous(job):
 if job.get("mode")!="cfit_autonomous_preview_staging" or job.get("publishing_enabled") is not False or job.get("founder_review_required") is not True:
  raise ValueError("Private founder-review mode required")
 sources=job.get("middle_sources")
 brand=job.get("branding") or {}
 shots=job.get("editorial_shots")
 if not isinstance(sources,list) or not 1<=len(sources)<=3 or not isinstance(shots,list) or not 3<=len(shots)<=12:
  raise ValueError("Original sources and director shots required")
 if brand.get("opening_role")!="opening" or brand.get("closing_role")!="closing":
  raise ValueError("Approved branding required")
 source_ids={str(v.get("source_id")) for v in sources}
 if len(source_ids)!=len(sources):
  raise ValueError("Duplicate source IDs")
 for shot in shots:
  if not isinstance(shot,dict) or shot.get("source_id") not in source_ids or type(shot.get("start")) not in (int,float) or type(shot.get("end")) not in (int,float) or not 0<=shot["start"]<shot["end"] or shot["end"]-shot["start"]>18 or not isinstance(shot.get("purpose"),str) or not shot["purpose"].strip():
   raise ValueError("Invalid source-backed director decision")
 if {x["source_id"] for x in shots}!=source_ids:
  raise ValueError("Every chosen original exercise requires footage")
 with tempfile.TemporaryDirectory() as tmp:
  t=pathlib.Path(tmp)
  first=t/"opening.mp4";last=t/"closing.mp4"
  download_signed(brand.get("opening_signed_url",""),first)
  download_signed(brand.get("closing_signed_url",""),last)
  downloaded={}
  for i,src in enumerate(sources):
   dst=t/f"source-{i}.mp4"
   download_signed(src.get("signed_url",""),dst)
   downloaded[src["source_id"]]=dst
  segments=[]
  for i,shot in enumerate(shots):
   src=downloaded[shot["source_id"]]
   if shot["end"]>duration_seconds(src):
    raise ValueError("Editorial shot exceeds source footage")
   dest=t/f"shot-{i}.mp4"
   subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-y","-ss",str(shot["start"]),"-t",str(shot["end"]-shot["start"]),"-i",str(src),"-an","-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p",str(dest)],check=True,timeout=100)
   segments.append(dest)
  midlist=t/"midlist.txt"
  midlist.write_text("".join("file '"+str(v)+"'\n" for v in segments))
  middle=t/"middle.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(midlist),"-c","copy",str(middle)],check=True,timeout=90)
  contract=job.get("editing_contract") or {}
  max_seconds=float(contract.get("maximum_seconds",0))
  total=duration_seconds(first)+duration_seconds(middle)+duration_seconds(last)
  if not 0<max_seconds<=90 or total>max_seconds:
   raise ValueError(f"Director edit exceeds platform budget: {total:.2f}s > {max_seconds:.2f}s. AI must revise source cuts.")
  normalized=[]
  for i,part in enumerate((first,middle,last)):
   dest=t/f"normalized-{i}.mp4";normalize(part,dest);normalized.append(dest)
  manifest=t/"manifest.txt"
  manifest.write_text("".join("file '"+str(v)+"'\n" for v in normalized))
  final=t/"autonomous-preview.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(final)],check=True,timeout=90)
  return final.read_bytes()
