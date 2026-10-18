"""Private autonomous-edit renderer. Executes source-backed AI editorial shot list, no fixed exercise choreography."""
import pathlib, tempfile, subprocess, json, math
from worker_v7_branded_preview_STAGING import download_signed, duration_seconds, normalize

def render_autonomous(job):
 if job.get("mode")!="cfit_autonomous_preview_staging" or job.get("publishing_enabled") is not False or job.get("founder_review_required") is not True:
  raise ValueError("Private founder-review mode required")
 sources=job.get("middle_sources")
 brand=job.get("branding") or {}
 shots=job.get("editorial_shots")
 if not isinstance(sources,list) or not 1<=len(sources)<=6 or not isinstance(shots,list) or not len(sources)<=len(shots)<=18:
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
  # Optional AI-authored editorial captions. These are overlays, not claimed speech transcripts.
  captions=job.get("editorial_captions") or []
  if not isinstance(captions,list) or len(captions)>18:
   raise ValueError("Invalid editorial captions")
  label_by_shot={}
  for caption in captions:
   if not isinstance(caption,dict) or type(caption.get("shot_index")) is not int or not 0<=caption["shot_index"]<len(shots):
    raise ValueError("Caption references invalid shot")
   line=caption.get("text")
   if not isinstance(line,str) or not 1<=len(line.strip())<=64 or any(ord(c)<32 for c in line):
    raise ValueError("Invalid editorial caption text")
   if caption["shot_index"] in label_by_shot:
    raise ValueError("Duplicate editorial caption")
   label_by_shot[caption["shot_index"]]=line.strip()
  segments=[]
  for i,shot in enumerate(shots):
   src=downloaded[shot["source_id"]]
   if shot["end"]>duration_seconds(src):
    raise ValueError("Editorial shot exceeds source footage")
   dest=t/f"shot-{i}.mp4"
   filters=["-vf","scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,setpts=PTS-STARTPTS"]
   if i in label_by_shot:
    caption_file=t/f"caption-{i}.txt"
    caption_file.write_text(label_by_shot[i],encoding="utf-8")
    filters=["-vf","scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,setpts=PTS-STARTPTS,drawtext=textfile="+str(caption_file)+":fontsize=38:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h*0.79"]
   subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-filter_threads","1","-y","-ss",str(shot["start"]),"-t",str(shot["end"]-shot["start"]),"-i",str(src),*filters,"-an","-c:v","libx264","-threads","1","-preset","veryfast","-crf","21","-pix_fmt","yuv420p",str(dest)],check=True,timeout=100)
   segments.append(dest)
  midlist=t/"midlist.txt"
  midlist.write_text("".join("file '"+str(v)+"'\n" for v in segments))
  middle=t/"middle.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(midlist),"-c","copy",str(middle)],check=True,timeout=90)
  # Reject long static intervals in exercise-only footage; successful encoding is not proof of motion.
  freeze=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",str(middle),"-vf","freezedetect=n=-50dB:d=2.5","-an","-f","null","-"],capture_output=True,text=True,timeout=90)
  if freeze.returncode!=0:
   raise ValueError("Exercise motion validation unavailable; private preview rejected")
  if "freeze_start:" in freeze.stderr:
   raise ValueError("Exercise footage contains a prolonged frozen segment; director must revise original source cuts")
  contract=job.get("editing_contract") or {}
  max_seconds=float(contract.get("maximum_seconds",0))
  total=duration_seconds(first)+duration_seconds(middle)+duration_seconds(last)
  min_seconds=float(contract.get('minimum_seconds',0))
  if not 0<min_seconds<=max_seconds<=90 or total>max_seconds:
   raise ValueError(f"Director edit exceeds platform budget: {total:.2f}s > {max_seconds:.2f}s. AI must revise source cuts.")
  normalized=[]
  for i,part in enumerate((first,middle,last)):
   dest=t/f"normalized-{i}.mp4";normalize(part,dest);normalized.append(dest)
  manifest=t/"manifest.txt"
  manifest.write_text("".join("file '"+str(v)+"'\n" for v in normalized))
  final=t/"autonomous-preview.mp4"
  subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(final)],check=True,timeout=90)
  inspection=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(final)],capture_output=True,text=True,check=True,timeout=20)
  probed=json.loads(inspection.stdout)
  finished=float(probed.get('format',{}).get('duration',0))
  video_streams=[v for v in probed.get('streams',[]) if v.get('codec_type')=='video']
  if not math.isfinite(finished) or finished<min_seconds or finished>max_seconds:
   raise ValueError('Finished preview duration fails platform requirements')
  if len(video_streams)!=1 or video_streams[0].get('width')!=720 or video_streams[0].get('height')!=1280:
   raise ValueError('Finished preview fails vertical-video requirements')
  if not final.is_file() or final.stat().st_size<10240:
   raise ValueError('Finished preview file incomplete')
  return final.read_bytes()
