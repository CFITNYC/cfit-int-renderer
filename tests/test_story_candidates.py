from story_boundary_candidates import propose_story_candidates,guard_story_proposal
try:
 propose_story_candidates([])
 raise AssertionError("Accepted empty story assignment")
except ValueError:
 pass
assert guard_story_proposal({"may_render_story":False})
try:
 guard_story_proposal({"may_render_story":True})
 raise AssertionError("Accepted unverified story evidence")
except ValueError:
 pass
print("Story candidate safeguards passed")
