"""Private renderer safety tests. No media or credentials."""
from worker_v7_branded_preview_STAGING import check_platform_duration
for platform in ('youtube_shorts','tiktok'):
    contract={'platform':platform,'maximum_seconds':20,'minimum_complete_repetitions_per_exercise':1}
    assert check_platform_duration(2,14,2,contract)==18
    try:
        check_platform_duration(3,19,3,contract)
        raise AssertionError('Overlong edit accepted')
    except ValueError:
        pass
print('Platform duration safety checks passed')
