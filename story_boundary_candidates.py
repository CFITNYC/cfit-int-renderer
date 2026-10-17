"""CFIT story boundary candidate generator.

This module proposes review timestamps from source footage; it does NOT label
BOSU entry, hip extension or balance as verified from pixel motion alone.
"""
from rep_cycles_staging import analyze_video
from dataclasses import asdict

def propose_story_candidates(video_paths):
    """Returns independent source-specific candidate repetitions and review needs.

    Never synthesize or attest story_evidence verified_by=founder.
    """
    if not 1 <= len(video_paths) <= 6:
        raise ValueError("Expected 1-6 original videos")
    result=[]
    for source_id,path in video_paths:
        cycles=analyze_video(str(path),fps=5)
        candidates=[asdict(c) for c in cycles if c.end-c.start>=1.5 and c.confidence>=0.55]
        result.append({
            "source_id":str(source_id),
            "repetition_candidates":candidates[:12],
            "movement_phase_detection_verified":False,
            "requires_semantic_review":["setup_entry","hip_extension_transition","upright_single_leg_finish"],
        })
    return {"status":"CANDIDATES_ONLY_NOT_STORY_VERIFIED","sources":result,"may_render_story":False}

def guard_story_proposal(proposal):
    if proposal.get("may_render_story") is not False:
        raise ValueError("Unverified video analysis cannot authorize a story render")
    return True
