"""
==============================================================================
  EDIT THIS BLOCK. DO NOT EDIT ANYTHING BELOW THE LINE, OR ANY OTHER FILE.
==============================================================================

Keeping your changes confined to this block means you can pull upstream fixes
without merge conflicts. Every value here can also be overridden by an
environment variable of the same name (see the parsing in config.py), which is
what the GitHub Actions workflow uses.
"""

# --- Tracking -----------------------------------------------------------

# The tag a job must carry to be tracked. Change this to run two independent
# Qoffee instances against one IBM account, or to avoid colliding with someone
# else sharing your instance.
TRACKING_TAG = "qoffee"

# Tag applied once a job stops being tracked. Set to "" to delete the tracking
# tags outright instead of leaving an audit trail.
RESOLVED_TAG = "qoffeed"

# --- Notification -------------------------------------------------------

# Comma-separated, in priority order. Supported: discord, slack, ntfy.
# Each needs its credential in GitHub Secrets:
#   discord -> DISCORD_WEBHOOK
#   slack   -> SLACK_WEBHOOK
#   ntfy    -> NTFY_URL   (full topic URL, e.g. https://ntfy.sh/my-topic)
CHANNELS = "discord"

# Channels that MUST confirm delivery before any tag is mutated. Blank means
# "the first entry in CHANNELS". A job is never untagged unless every required
# channel confirmed, so a failure is never lost to a broken webhook.
REQUIRED_CHANNELS = ""

# --- Policy -------------------------------------------------------------

# SAFETY NET ONLY. Failures normally clear themselves: they are held and shown
# in every notification until nothing else in the batch is moving, then
# reported one final time and released. This setting only matters if you submit
# work continuously so the batch never goes quiet — then a failure would be
# held forever. Hours until such a failure is released anyway; 0 disables it.
# A release by this route is silent: it is cleanup, not news.
FAILURE_AUTOCLEAR_HOURS = 0

# --- Logging ------------------------------------------------------------

# Replace job IDs and instance CRNs in the Actions run log with stable short
# hashes. Public repos have public run logs; the full IDs are still in your
# notification. Set False only if you are debugging in a private fork.
REDACT_LOGS = True

# ==============================================================================
#   NOTHING BELOW THIS LINE IS A USER SETTING.
# ==============================================================================

# IBM caps job tags at 5 per job and 24 characters each. Qoffee uses two of
# them (tracking + state); a "name:" label uses a third.
MAX_TAGS_PER_JOB = 5
MAX_TAG_LENGTH = 24

# Prefix for the human-readable label tag, e.g. "name:Bell Test 1".
NAME_TAG_PREFIX = "name:"

# Separator between the tracking tag and its encoded state, e.g. "qoffee@R".
STATE_SEPARATOR = "@"
