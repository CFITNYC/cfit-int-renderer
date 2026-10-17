"""CFIT story-editor regression contract: never silently fall back to a montage."""
from worker_v7_branded_preview_STAGING import branded_preview

base={
 "mode":"cfit_branded_preview_staging","publishing_enabled":False,"founder_review_required":True,
 "branding":{"opening_role":"opening","closing_role":"closing"},
 "middle_sources":[{"source_id":"CFM-EX-0103","auto_select_complete_cycle":True,"auto_select_motion":False}],
 "editing_contract":{"platform":"youtube_shorts","maximum_seconds":30,"minimum_complete_repetitions_per_exercise":1}
}
try:
 branded_preview(base)
 raise AssertionError("Allowed an unverified movement story")
except ValueError as error:
 assert "CFIT STORY_GATE" in str(error),str(error)

print("Missing story evidence correctly rejected")
