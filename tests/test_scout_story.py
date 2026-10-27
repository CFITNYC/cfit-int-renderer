"""Scout STAY GROUNDED story + source check: safety tests (no network, no ffmpeg)."""
import scout_story as ss

def refused(fn, job, words):
    try:
        fn(job)
    except ValueError as e:
        assert words in str(e), (words, str(e))
        return
    raise AssertionError("accepted: " + words)

brand = {"opening_role": "opening", "closing_role": "closing", "opening_signed_url": "o", "closing_signed_url": "c"}
seg = lambda role, a, z: {"role": role, "signed_url": "s", "start": a, "end": z}
story = {"mode": "scout_story_short", "publishing_enabled": False, "hook": "Watch the base first.", "payoff": "Grounded first. Then you rise.",
         "branding": brand, "segments": [seg("setup", 0, 2), seg("challenge", 3, 8), seg("win", 9, 12)]}
cs = ss.check_story
refused(cs, {**story, "publishing_enabled": True}, "Private Scout story required")
refused(cs, {**story, "mode": "scout_branded_short"}, "Private Scout story required")
refused(cs, {**story, "branding": {}}, "Opening and closing roles required")
refused(cs, {**story, "segments": story["segments"][::-1]}, "setup, challenge, win")
refused(cs, {**story, "segments": story["segments"][:2]}, "setup, challenge, win")
refused(cs, {**story, "segments": [seg("setup", 0, 5), *story["segments"][1:]]}, "setup must be 1-4 seconds")
refused(cs, {**story, "segments": [seg("setup", 3, 2), *story["segments"][1:]]}, "setup must be")
refused(cs, {**story, "segments": [seg("setup", 0, 4), seg("challenge", 0, 7), seg("win", 0, 5)]}, "the most is 13 s")
refused(cs, {**story, "hook": ""}, "Hook and payoff lines are required")
refused(cs, {**story, "payoff": "<<>>"}, "Hook and payoff lines are required")
segs, hook, payoff, total = cs(story)
assert total == 10 and hook == "Watch the base first."

check = {"mode": "scout_source_check", "publishing_enabled": False, "signed_url": "x", "branding": brand}
refused(ss.source_check, {**check, "publishing_enabled": None}, "Private Scout check required")
refused(ss.source_check, {**check, "branding": {"opening_role": "opening"}}, "Opening and closing roles required")
good = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/scout-phone/2026/10/a.mov?token=t"
for bad, words in [("https://evil.example/storage/v1/object/sign/cfit-exercise-videos/a.mp4", "Unsigned"),
                   ("https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/public/cfit-exercise-videos/a.mp4", "Unsigned"),
                   ("https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-billing/a.mp4?t", "Invalid video source"),
                   ("https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-exercise-videos/a.exe?t", "Invalid video source")]:
    refused(lambda u: ss.fetch(u, "/dev/null"), bad, words)
assert abs(ss.correlation(bytes(range(200)), bytes(range(200))) - 1) < 1e-9
assert ss.correlation(bytes(range(200)), bytes(range(199, -1, -1))) < -0.99
assert ss.wrap("Grounded first. Then you rise.") == "Grounded first.\nThen you rise."
assert ss.wrap("Short line") == "Short line"
assert ss.BRAND_MATCH == 0.55 and ss.CUTS_FLAG == 3 and ss.MAX_STORY_SECONDS == 13.0
print("Scout story + source check: PASS")
