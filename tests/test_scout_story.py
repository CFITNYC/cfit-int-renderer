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

# ---- layout v2 (2026-10-27): footage window + caption area, nothing drawn on the footage ----
import tempfile, pathlib
assert ss.V2_TOP + ss.V2_WIN + ss.V2_ZONE + ss.V2_BAR == 1280 and ss.V2_WIN == 804 and ss.V2_ZONE_Y == 954
tag = "fps=30"
wide, tall = ss.window_filter(1, 1920, 1080, "w0", tag), ss.window_filter(1, 540, 960, "w0", tag)
assert "crop=720:804" in wide and "gblur" not in wide                          # wide: fill the window
assert "force_original_aspect_ratio=decrease" in tall and "gblur" in tall       # tall: whole clip shown, blurred sides
assert ss.check_words([], 10) == []
assert ss.check_words([{"start": 0.2, "end": 0.5, "text": "Watch"}], 10) == [(0.2, 0.5, "Watch")]
for bad, words in [([{"start": 9.5, "end": 11, "text": "late"}], "outside the story"), ([{"start": 0, "end": 0.1, "text": "x"}] * 141, "at most 140")]:
    try:
        ss.check_words(bad, 10); raise AssertionError("accepted bad words")
    except ValueError as e:
        assert words in str(e)
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "c.ass"
    ss.captions_ass(p, 10.0, "Watch the\nbase first.", "Grounded first.", 2.0, 7.0)
    a = p.read_text()
    assert "\\pos(360,1069)" in a and "Watch the\\Nbase first." in a and ss.GOLD_ASS + "}Grounded first." in a
    assert a.count("Dialogue:") == 2 and "0:00:00.00,0:00:02.00" in a and "0:00:07.00,0:00:10.00" in a
    ss.captions_ass(p, 10.0, "", "", 2.0, 7.0, [(0.2, 0.5, "Watch"), (0.6, 0.9, "the"), (1.0, 1.3, "base"), (1.8, 2.1, "first.")])
    a = p.read_text()
    assert a.count("Dialogue:") == 4 and "Grounded" not in a                    # with a voice: words only, no hook/payoff
    assert "{\\c" + ss.GOLD_ASS + "}Watch{\\c&H00FFFFFF&} the base" in a          # the word being spoken is gold
    assert "0:00:01.00,0:00:01.80" in a                                          # "base" holds through the short pause until "first."
calls = []
ss.render_story_v2 = lambda job, get=None: calls.append(job["layout"]) or b"v2"
assert ss.render_story({**story, "layout": "v2"}) == b"v2" and calls == ["v2"]
print("Scout layout v2: PASS")

# ---- layout v3 (Stage 3): versions, 4:5 frame, fast cuts, voice + music ----
for fr in ("9:16", "4:5"):
    g = ss.frame_geometry(fr)
    assert g["TOP"] + g["WIN"] + g["ZONE"] + g["BAR"] == g["H"] and g["WIN"] > 0
assert ss.frame_geometry("4:5")["H"] == 900 and ss.frame_geometry("9:16")["H"] == 1280
try:
    ss.frame_geometry("1:1"); raise AssertionError("accepted 1:1")
except ValueError:
    pass
cuts = ss.challenge_cuts(2.5, 9.5, 3)
assert len(cuts) == 3 and cuts[0] == (2.5, 4.1) and cuts[-1] == (7.9, 9.5) and all(abs((z - a) - 1.6) < 1e-9 for a, z in cuts)
assert ss.challenge_cuts(3, 8, 1) == [(3, 8)]
v3 = {"mode": "scout_story_short", "publishing_enabled": False, "version": "short", "frame": "9:16", "challenge_cuts": 3, "branding": brand,
      "segments": [seg("setup", 0, 4), seg("challenge", 2.5, 9.5), seg("win", 8.5, 12.5)]}
version, segs3, ncuts, g3 = ss.check_story_v3(v3)                      # 4 + 3 cuts of 1.6 + 4 = 12.8 s seen: allowed
assert version == "short" and ncuts == 3
try:
    ss.check_story_v3({**v3, "segments": [seg("setup", 0, 4), seg("challenge", 2.5, 9.5), seg("win", 8, 13)]}); raise AssertionError("13.8 s short accepted")
except ValueError as e:
    assert "Story is 13.8 s; the most is 13" in str(e)                  # the limit counts the length after the fast cuts
for bad, words in [({**v3, "version": "medium"}, "short or long"), ({**v3, "publishing_enabled": True}, "Private Scout story"),
                   ({**v3, "challenge_cuts": 6}, "1-4"), ({**v3, "frame": "16:9"}, "9:16 or 4:5")]:
    try:
        ss.check_story_v3(bad); raise AssertionError("accepted " + words)
    except ValueError as e:
        assert words in str(e), (words, str(e))
long_job = {**v3, "version": "long", "frame": "4:5", "challenge_cuts": 1, "segments": [seg("setup", 0, 4), seg("challenge", 5, 23), seg("win", 24, 31)]}
assert ss.check_story_v3(long_job)[0] == "long"
try:
    ss.check_story_v3({**long_job, "segments": [seg("setup", 0, 4), seg("challenge", 5, 25), seg("win", 26, 35)]}); raise AssertionError("long over 32 s accepted")
except ValueError as e:
    assert "the most is 32" in str(e)
au = "https://hszormivkbqvpfgfhktm.supabase.co/storage/v1/object/sign/cfit-int-private-audio/u/private-soundtracks/a.mp3?t"
for url, audio, words in [(au, False, "Invalid video source"), (au.replace(".mp3", ".exe"), True, "Invalid audio source"),
                          (au.replace("cfit-int-private-audio", "cfit-billing"), True, "Invalid audio source")]:
    try:
        ss.fetch(url, "/dev/null", audio); raise AssertionError("accepted " + url)
    except ValueError as e:
        assert words in str(e)
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "v3.ass"
    ss.captions_ass_v3(p, ss.frame_geometry("4:5"), [(0.1, 0.4, "Most"), (0.5, 0.9, "training")], 0.7, video_len=10)
    a = p.read_text()
    assert "PlayResY: 900" in a and "0:00:00.80" in a and "\\pos(360,745)" in a     # voice clock + 0.7 s offset; 4:5 caption area centre (110 + 550 + 85)
print("Scout layout v3: PASS")
