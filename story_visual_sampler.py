"""Sample real frames from original footage for semantic storyboard inspection.

This is preparation for vision-based BOSU phase recognition, not an optical
motion score. Frames retain source timestamps and are never treated as proof
of a particular movement until a vision reviewer classifies them.
"""
import base64, json, subprocess

def frame_samples(path, interval=1.5, max_seconds=75, max_frames=48):
    if not (0.5 <= interval <= 5 and 1 <= max_frames <= 60):
        raise ValueError("Invalid sampling settings")
    probe=subprocess.run(
      ["ffprobe","-v","error","-show_entries","format=duration",
       "-of","json",str(path)],capture_output=True,text=True,check=True,timeout=12)
    duration=float(json.loads(probe.stdout)["format"]["duration"])
    if duration <= 0:raise ValueError("Source video empty")
    samples=[]
    n=min(max_frames,int(min(max_seconds,duration)/interval)+1)
    for i in range(n):
        at=round(i*interval,3)
        if at>=duration:break
        shot=subprocess.run(
          ["ffmpeg","-nostdin","-hide_banner","-v","error","-ss",str(at),
           "-i",str(path),"-frames:v","1","-vf",
           "scale=288:512:force_original_aspect_ratio=decrease",
           "-q:v","5","-f","image2pipe","-vcodec","mjpeg","pipe:1"],
           capture_output=True,check=True,timeout=15).stdout
        if shot:
            samples.append({"at_seconds":at,"jpeg_base64":base64.b64encode(shot).decode("ascii")})
    return {"duration_seconds":round(duration,3),"frames":samples,
            "semantic_phase_verified":False}

def validate_phase_timeline(timeline, allowed_ids):
    """Validate model output structurally, not biomechanically."""
    if not isinstance(timeline,dict) or timeline.get("inspection_method")!="vision_frames":
        raise ValueError("Video-frame inspection evidence required")
    required=["setup_entry","hip_extension_transition","upright_single_leg_finish"]
    phases=[timeline.get(k) for k in required]
    if not all(isinstance(v,dict) and v.get("source_id") in allowed_ids
               and isinstance(v.get("start"),(int,float))
               and isinstance(v.get("end"),(int,float))
               and 0<=v["start"]<v["end"] for v in phases):
        raise ValueError("Missing or invalid story phases")
    reps=timeline.get("complete_repetitions",[])
    if not isinstance(reps,list) or {v.get("source_id") for v in reps if isinstance(v,dict)}!=set(allowed_ids):
        raise ValueError("Missing exercise repetition candidates")
    return True
