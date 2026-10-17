"""CFIT experimental complete-cycle candidate detector (preview-only, no publishing).

Heuristic: observe low-res frame similarity to a resting/start pose and motion
between samples. Candidate cycle requires departure, meaningful motion, and
return close to that reference. This DOES NOT verify biomechanics or full ROM.
"""
from __future__ import annotations
import subprocess, math
from dataclasses import dataclass

@dataclass(frozen=True)
class Cycle:
    start: float
    end: float
    movement: float
    confidence: float


def _dist(a: bytes,b: bytes)->float:
    return sum(abs(x-y) for x,y in zip(a[::6],b[::6])) / max(1,len(a[::6]))


def find_cycles(frames:list[bytes], fps:float=3.0,min_seconds:float=1.5,max_seconds:float=12.0)->list[Cycle]:
    if len(frames)<8 or fps<=0:return []
    movement=[0.0]+[_dist(frames[i-1],frames[i]) for i in range(1,len(frames))]
    sorted_mov=sorted(movement[1:]); baseline=sorted_mov[len(sorted_mov)//2]
    threshold=max(1.8,baseline*0.8)
    active=[m>threshold for m in movement]
    # Candidate start poses: snapshots just before meaningful motion begins.
    starts=[i-1 for i in range(1,len(frames)) if active[i] and not active[i-1] and i>2]
    cycles=[];last_end=-1
    for st in starts:
        if st<=last_end:continue
        lo=st+max(1,round(min_seconds*fps));hi=min(len(frames)-1,st+round(max_seconds*fps))
        if lo>hi:continue
        scores=[]
        for j in range(lo,hi+1):
            distances=[_dist(frames[st],frames[k]) for k in range(st+1,j+1)]
            departure=max(distances,default=0)
            return_distance=_dist(frames[st],frames[j])
            movement_total=sum(movement[st+1:j+1])
            # Accept only a departure-and-return pattern with substantive movement.
            if departure<max(4.0,threshold*1.8):continue
            if return_distance>max(3.0,departure*0.42):continue
            if movement_total<max(12.0,threshold*4):continue
            score=min(1.0,(departure-return_distance)/max(departure,1)) * min(1.,movement_total/35)
            scores.append((score,j,movement_total))
        if scores:
            # Favor earliest acceptable return rather than amalgamating multiple reps.
            viable=[x for x in scores if x[0]>=0.45]
            if viable:
                score,j,total=viable[0]
                cycles.append(Cycle(round(st/fps,2),round(j/fps,2),round(total,2),round(score,2)))
                last_end=j
    return cycles


def analyze_video(path:str,fps:int=3,max_seconds:int=90)->list[Cycle]:
    w,h=48,84
    command=['ffmpeg','-nostdin','-v','error','-t',str(max_seconds),'-i',path,
             '-vf',f'fps={fps},scale={w}:{h},format=gray','-an','-f','rawvideo','-pix_fmt','gray','pipe:1']
    output=subprocess.run(command,capture_output=True,check=True,timeout=90).stdout
    size=w*h
    frames=[output[i:i+size] for i in range(0,len(output)-size+1,size)]
    return find_cycles(frames,float(fps))

if __name__=='__main__':
    import sys,json
    if len(sys.argv)!=2:raise SystemExit('Usage: python rep_cycles.py local-original.mp4')
    print(json.dumps([vars(c) for c in analyze_video(sys.argv[1])],indent=2))