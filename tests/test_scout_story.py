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

# ---- captions never touch the edges: 3 words only when they fit, else 2 or 1 ----
gw = lambda txt: [(i, i + 0.5, w) for i, w in enumerate(txt.split())]
assert [len(x) for x in ss.caption_groups(gw("from the ground."), 16)] == [3]
assert [" ".join(w for _, _, w in x) for x in ss.caption_groups(gw("Method brings mobility, stability, and functional"), 16)] == ["Method brings", "mobility,", "stability, and", "functional"]
assert all(len(" ".join(w for _, _, w in x)) <= 16 or len(x) == 1 for x in ss.caption_groups(gw("The CFIT Method brings mobility, stability, and functional strength together for athletes"), 16))
assert ss.frame_geometry("9:16")["cap_chars"] == 16 and ss.frame_geometry("4:5")["cap_chars"] == 20
print("Scout caption width: PASS")

# ---- end tagline: full-width panel-navy bar with a thin gold line slides in, then the tagline fades in ----
TAG = "Move Freely | Stay Grounded | Age Powerfully, my friends"
OLD = "Move Freely. Stay Grounded. Age Powerfully, my friends."
assert ss.tagline_lines(TAG) == ["Move Freely | Stay Grounded", "Age Powerfully, my friends"]      # break at the middle pipe, not shown
assert ss.tagline_lines(OLD) == ["Move Freely. Stay Grounded.", "Age Powerfully, my friends."]   # the old text still works
assert ss.tagline_lines(None) is None and ss.tagline_lines("") is None and ss.tagline_lines("Stay grounded") == ["Stay grounded"]
for bad, words in [("x" * 61, "1-60 plain"), ("Move {\\b1} freely", "1-60 plain"), ("Supercalifragilisticexpialidocious-and-even-longer words", "too long for two lines"),
                   ("Supercalifragilisticexpialidocious-even | longer", "too long for two lines")]:
    try:
        ss.tagline_lines(bad); raise AssertionError("accepted tagline " + bad)
    except ValueError as e:
        assert words in str(e), (words, str(e))
import re as _re
sec = lambda x: int(x.split(":")[0]) * 3600 + int(x.split(":")[1]) * 60 + float(x.split(":")[2])
def events(a):
    return [dict(zip(["layer", "start", "end", "style", "text"], [int(f[0][10:]), sec(f[1]), sec(f[2]), f[3], f[9]]))
            for f in (line.split(",", 9) for line in a.splitlines() if line.startswith("Dialogue:"))]
assert ss.TAG_SECONDS == 3.0 and ss.BAR_SLIDE == 0.6 and ss.TAG_RISE == 0.5 and ss.GOLD_LINE == 2 and ss.PANEL_ASS == "&H00260D0B&"
GOLD = "{\\c&H0050BEF2&}"; WHITE = "{\\c&H00FFFFFF&}"
for frame in ["9:16", "4:5"]:
    g = ss.frame_geometry(frame)
    assert g["tag"] == 46
    x0, y0, x1, y1 = ss.tagbar_box(g)
    assert (x0, x1, y1) == (0, g["W"], g["H"])                                                       # full width, to the bottom
    assert y0 > g["ZONE_Y"] + g["ZONE"] // 2 + g["cap"] // 2                                         # below the spoken captions
    assert y0 > g["TOP"] + g["WIN"]                                                                   # never over the footage window
    with tempfile.TemporaryDirectory() as td:
        p, q = pathlib.Path(td) / "t.ass", pathlib.Path(td) / "n.ass"
        words = [(i * 0.4, i * 0.4 + 0.35, w) for i, w in enumerate("Strong rotation starts from the ground. Ready? Train it with control.".split())]
        ss.captions_ass_v3(p, g, words, 6.5, video_len=15.0, story_len=12.8, tagline=ss.tagline_lines(TAG), tag_start=10.5)
        ss.captions_ass_v3(q, g, words, 6.5, video_len=15.0, story_len=12.8)
        a, n = p.read_text(), q.read_text(); ev, ev0 = events(a), events(n)
        caps = [e for e in ev if e["style"] == "Cap"]
        assert caps == [e for e in ev0 if e["style"] == "Cap"] and "TagBar" not in n and "Style: Tag," not in n   # captions identical; no tagline = no bar
        bar = [e for e in ev if e["style"] == "TagBar"]; tag = [e for e in ev if e["style"] == "Tag"]
        assert len(bar) == 3 and len(tag) == 1 and all(e["start"] == 10.5 and e["end"] == 15.0 for e in bar + tag)
        w, h = x1 - x0, y1 - y0
        shadow, panel, line = sorted(bar, key=lambda e: e["layer"])
        assert panel["text"] == f"{{\\an7\\move({x0 - w},{y0},{x0},{y0},0,600)\\p1}}m 0 0 l {w} 0 {w} {h} 0 {h}{{\\p0}}"      # slides in from the left in 0.6 s
        assert "\\1c&H0050BEF2&" in line["text"] and f"l {w} 0 {w} 2 0 2" in line["text"] and f"move({x0 - w},{y0}," in line["text"]   # thin gold top line, moves with it
        assert "\\1a&H70&" in shadow["text"] and "\\blur" in shadow["text"] and shadow["layer"] < panel["layer"] < line["layer"] < tag[0]["layer"]
        assert f"Style: TagBar,DejaVu Sans,20,&H00260D0B&," in a and f"Style: Tag,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,&H00260D0B&," in a        # panel navy; white text by default
        t = tag[0]["text"]
        assert f"\\pos({g['W'] // 2},{(y0 + 2 + y1) // 2})" in t and "\\alpha&HFF&\\t(600,1100,\\alpha&H00&)" in t           # centred, fades in after the slide
        assert t.endswith(f"{GOLD}Move{WHITE} Freely | {GOLD}Stay{WHITE} Grounded\\N{GOLD}Age{WHITE} Powerfully, my friends"), t   # Move, Stay, Age gold; rest white
        # no final period on screen: "ground." and "control." lose it, "Ready?" keeps its mark; timing unchanged
        shown = " ".join(_re.sub(r"\{[^}]*\}", "", e["text"]) for e in caps)
        assert "ground. Ready?" in shown and "control." not in shown and shown.endswith("control")   # mid-caption period stays; final one goes; "?" stays
        assert [(e["start"], e["end"]) for e in caps] == [(e["start"], e["end"]) for e in ev0 if e["style"] == "Cap"]
        ss.captions_ass_v3(p, g, [], 0.7, "Can you stay grounded?", "Grounded first. Rise with control.", 4.0, 8.3, 12.8, 15.0)
        lines_ = [_re.sub(r"\{[^}]*\}", "", e["text"]) for e in events(p.read_text()) if e["style"] == "Line"]
        assert lines_ == ["Can you stay grounded?", "Grounded first. Rise with control"], lines_
assert ss.no_final_period("Stay grounded...") == "Stay grounded" and ss.no_final_period("Why?") == "Why?" and ss.no_final_period("") == ""
print("Scout end tagline (design polish): PASS")

# ---- wider footage only when the whole body still fits; otherwise today's width ----
real = (0.219, 0.656)    # where things move in your hip-thrust clip (measured)
assert ss.widen_fits(real, 1080, 1920, 720, 804, ss.SIDE_EDGE) is True            # Short: 684 px wide, whole body
assert ss.widen_fits(real, 1080, 1920, 720, 550, ss.LONG_SIDE_EDGE) is True       # Long: about 440 px wide, whole body
assert ss.widen_fits(real, 1080, 1920, 720, 550, ss.SIDE_EDGE) is False           # the old thin edge on the Long would cut the body: refused
assert ss.widen_fits((0.05, 0.95), 1080, 1920, 720, 804, ss.SIDE_EDGE) is False   # framed too tightly: keep today's width
assert ss.widen_fits((0.20, 0.75), 1080, 1920, 720, 804, ss.SIDE_EDGE) is False   # feet too close to the bottom: keep today's width
assert ss.widen_fits(None, 1080, 1920, 720, 804, ss.SIDE_EDGE) is False           # unclear: keep today's width
src = open("scout_story.py").read()
assert '"-an", "-c:v", "libx264"' in src and 'mix += ["-filter_complex", f, "-map", "0:v", "-map", "[a]"' in src   # sound: picture built silent; only voice + music mixed
print("Scout whole-body fit + sound lock: PASS")

# ---- as large as the whole movement allows (body_fit), Shorts and Longs ----
def old_width(rows, sw, sh, W, WIN, edge):       # what the renderer showed before body_fit
    return W - 2 * edge if ss.widen_fits(rows, sw, sh, W, WIN, edge) else round(WIN * sw / sh)
for WIN, edge in ((804, ss.SIDE_EDGE), (550, ss.LONG_SIDE_EDGE), (804, ss.LONG_SIDE_EDGE)):
    for top in (0.02, 0.05, 0.1, 0.2, 0.3):
        for bottom in (0.5, 0.6, 0.7, 0.8, 0.9):
            for cols in (None, (0.2, 0.8), (0.0, 1.0)):
                vw, vh, cx, cy, dw, dh = ss.body_fit((top, bottom), cols, 1080, 1920, 720, WIN)
                assert dw >= old_width((top, bottom), 1080, 1920, 720, WIN, edge) - 2, (top, bottom, WIN)   # upright clips never smaller than before
                assert dw <= 720 and dh <= WIN and dw % 2 == 0 and dh % 2 == 0
                y0, y1 = max(0, top - ss.BODY_HEAD_MARGIN) * vh, min(1, bottom + ss.BODY_FEET_MARGIN) * vh
                if y1 - y0 <= WIN:                                                                        # the whole movement (with margins) is in view
                    assert cy <= y0 + 1 and cy + dh >= y1 - 1, (top, bottom, WIN)
# wide clip (your Bench Bird Dog, measured): background may go, the movement never does
for WIN in (804, 550):
    rows, cols = (0.0625, 0.6875), (0.0, 0.75)
    vw, vh, cx, cy, dw, dh = ss.body_fit(rows, cols, 1920, 1080, 720, WIN)
    x0, x1 = 0, (cols[1] + ss.SIDE_MARGIN) * vw
    y0, y1 = (rows[0] - ss.BODY_HEAD_MARGIN) * vh, min(1, rows[1] + ss.BODY_FEET_MARGIN) * vh
    assert cx <= x0 + 1 and cx + dw >= x1 - 1 and cy <= y0 + 1 and cy + dh >= y1 - 1
    assert dh > round(720 * 1080 / 1920)                     # larger than simply fitting the whole wide picture
# a still clip (movement unclear): the whole picture with blurred edges, never a guess
assert "if f is None:" in src and "fits[url] = body_fit(rows, movement_cols(path, spans), sw0, sh0, W, WIN) if rows else None" in src
# the free video check also reports the clip's size (so Scout can prefer upright clips)
stub = {"duration": lambda p: 10.0, "gray_frames": lambda *a, **k: [], "best_match": lambda a, b: 0.0, "hard_cuts": lambda p, d: [],
        "motion_profile": lambda p, d: ([1.0], [0.5]), "video_size": lambda p: (1080, 1920)}
saved = {k: getattr(ss, k) for k in stub}
for k, v in stub.items(): setattr(ss, k, v)
try:
    r = ss.source_check(check, get=lambda u, d, audio=False: None)
finally:
    for k, v in saved.items(): setattr(ss, k, v)
assert r["width"] == 1080 and r["height"] == 1920 and r["publishing_enabled"] is False
print("Scout as large as the movement allows + clip size: PASS")

# ---- auto-fit endings from Scout: hold the last frame, end the voice at a word ----
assert ss.check_ending({}) == (0.0, None)
assert ss.check_ending({"end_hold": 0.4, "voice_cut_at": 12.35}) == (0.4, 12.35)
for bad, words in [({"end_hold": 1.5}, "0-1 s"), ({"end_hold": -0.1}, "0-1 s"), ({"voice_cut_at": 0.2}, "after 0.5 s")]:
    try:
        ss.check_ending(bad); raise AssertionError("accepted " + str(bad))
    except ValueError as e:
        assert words in str(e), (words, str(e))
src_ = open("scout_story.py").read()
assert "tpad=stop_mode=clone:stop_duration=" in src_ and "afade=t=out:st=" in src_ and "atrim=0:{cut:.3f}" in src_
assert "win_start = story_len - hold -" in src_                       # the hold comes after the win footage
print("Scout auto-fit endings: PASS")

# ---- three-line end tagline: line 1 above, the tagline on one line, line 3 pops on and holds still ----
assert ss.tagline_extra(None) is None and ss.tagline_extra("  ") is None
assert ss.tagline_extra("Train with Purpose") == "Train with Purpose" and ss.tagline_extra("- THAT'S CFIT METHOD -") == "- THAT'S CFIT METHOD -"
for bad in ["x" * 31, "Train {\\b1}"]:
    try:
        ss.tagline_extra(bad); raise AssertionError("accepted " + bad)
    except ValueError as e:
        assert "1-30 plain" in str(e)
MID = "Move Freely | Stay Grounded | Age Powerfully"
assert ss.tagline_single(MID) == MID
try:
    ss.tagline_single("Move Freely | Stay Grounded | Age Powerfully, my friends"); raise AssertionError("accepted a too-long one-line tagline")
except ValueError as e:
    assert "fit one line" in str(e)
for frame in ["9:16", "4:5"]:
    g = ss.frame_geometry(frame); t3 = g["t3"]
    assert t3["l2"] == 28 and t3["top"] > g["ZONE_Y"] + g["ZONE"] // 2 + g["cap"] // 2 + 3   # line 2 at 28 px; bar below the spoken captions
    with tempfile.TemporaryDirectory() as td:
        p, q = pathlib.Path(td) / "a.ass", pathlib.Path(td) / "b.ass"
        words = [(i * 0.4, i * 0.4 + 0.35, w) for i, w in enumerate("Strong hips start from the ground and finish with control".split())]
        ss.captions_ass_v3(p, g, words, 0.0, video_len=15.0, story_len=12.8, tagline=[MID], tag_start=10.5, tag_top="Train with Purpose", tag_bottom="- THAT'S CFIT METHOD -")
        ss.captions_ass_v3(q, g, words, 0.0, video_len=15.0, story_len=12.8)
        ev, ev0 = events(p.read_text()), events(q.read_text())
        assert [e for e in ev if e["style"] == "Cap"] == [e for e in ev0 if e["style"] == "Cap"]          # spoken captions untouched
        tags = [e for e in ev if e["style"] == "Tag"]
        assert len(tags) == 3 and all(e["start"] == 10.5 and e["end"] == 15.0 for e in tags)               # one copy each, to the last frame
        l1, l2, l3 = tags
        assert f"\\pos({g['W'] // 2},{t3['y'][0]})\\fs{t3['l1']}\\fsp3" in l1["text"] and l1["text"].endswith("Train with Purpose")
        assert f"\\fs{t3['l2']}" in l2["text"] and l2["text"].endswith(f"{GOLD}Move{WHITE} Freely | {GOLD}Stay{WHITE} Grounded | {GOLD}Age{WHITE} Powerfully")
        assert f"\\pos({g['W'] // 2},{t3['y'][2]})" in l3["text"] and "\\move" not in l3["text"] and "\\c&H0050BEF2&" in l3["text"]   # still, gold
        assert "\\fscx70\\fscy70\\alpha&HFF&\\t(1100,1350,\\fscx100\\fscy100\\alpha&H00&)" in l3["text"]   # pops on after lines 1-2 fade in
        assert l3["text"].endswith("- THAT'S CFIT METHOD -")
        bar = [e for e in ev if e["style"] == "TagBar"]
        assert len(bar) == 3 and all(f",{t3['top']},0," in b_["text"] or f",{t3['top'] - 7}," in b_["text"] or f",{t3['top'] - 3}," in b_["text"] for b_ in bar)
        # no lines 1 and 3: today's two-line look exactly
        ss.captions_ass_v3(p, g, words, 0.0, video_len=15.0, story_len=12.8, tagline=ss.tagline_lines(MID), tag_start=10.5)
        two = [e for e in events(p.read_text()) if e["style"] == "Tag"]
        assert len(two) == 1 and "\\N" in two[0]["text"]
print("Scout three-line tagline: PASS")
