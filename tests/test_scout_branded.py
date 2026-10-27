"""Scout branded short: request safety checks (no network, no ffmpeg)."""
import scout_branded as sb

def refused(job, words):
    try:
        sb.scout_branded(job)
    except ValueError as e:
        assert words in str(e), (words, str(e))
        return
    raise AssertionError("accepted: " + words)

good_brand = {"opening_role": "opening", "closing_role": "closing", "opening_signed_url": "x", "closing_signed_url": "y"}
base = {"mode": "scout_branded_short", "publishing_enabled": False, "title": "T", "branding": good_brand, "source": {"duration": 13}}

refused({**base, "mode": "source_to_preview"}, "Private Scout preview required")
refused({**base, "publishing_enabled": True}, "Private Scout preview required")
refused({**base, "publishing_enabled": None}, "Private Scout preview required")
refused({**base, "branding": {**good_brand, "opening_role": "intro"}}, "Opening and closing roles required")
refused({**base, "branding": {}}, "Opening and closing roles required")
refused({**base, "source": {"duration": 14}}, "3 to 13 seconds")
refused({**base, "source": {"duration": 2}}, "3 to 13 seconds")
# A good request gets past every check and fails only at the download, which refuses unsigned links.
refused(base, "Unsigned or unsupported asset")
assert sb.MAX_MIDDLE_SECONDS == 13 and sb.SIZE == "720:1280" and sb.FPS == 30
print("Scout branded short: PASS")
