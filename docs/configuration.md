# Configuration

Everything you'd want to change lives in one file: `qoffee/settings.py`.

## Settings

| Setting | Default | What it controls |
|---|---|---|
| `RESOLVED_TAG` | `"qoffeed"` | Applied once tracking stops (set `""` to delete the tag outright instead) |
| `CHANNELS` | `"discord"` | Which notification channels are active |
| `REQUIRED_CHANNELS` | *(first channel)* | Which channels must confirm delivery before tags change |
| `FAILURE_AUTOCLEAR_HOURS` | `0` (disabled) | Safety net: force-clear a stuck failure after N hours if the batch never goes quiet |
| `REDACT_LOGS` | `True` | Replace job IDs and instance CRNs with short hashes in the public Actions log |

> The tracking tag itself is deliberately **not** configurable. Qoffee encodes a
reported failure as `qoffee@F:<epoch>`, which needs 13 characters on top of the
tag, and IBM caps tags at 24. A longer tag cannot be encoded, so the failure
state silently fails to persist and the job is re-reported on every run. Use
`name:` labels to distinguish your jobs instead.


## Notification channels

Set `CHANNELS` in `qoffee/settings.py`, comma-separated, in priority order:

```python
CHANNELS = "discord,slack,ntfy"
```

| Channel | Secret needed |
|---|---|
| Discord | `DISCORD_WEBHOOK` |
| Slack | `SLACK_WEBHOOK` |
| ntfy | `NTFY_URL` (e.g. `https://ntfy.sh/your-topic`) |

By default, the **first** channel listed must confirm delivery before a job's tag is updated. That way a single broken webhook can never cause a job to silently drop out of tracking without you having actually been told. If every configured channel fails on a given run, nothing changes and the same news is reported again next run.

## Log redaction

`REDACT_LOGS` defaults **on** deliberately. This repo can be public, which means its Actions run logs are readable by anyone, and the full IDs are already sitting safely in your private notification either way. There's no cost to leaving it on.

Qoffee redacts job IDs and instance CRNs to stable short hashes (`job#3beed3`) before anything reaches the log including inside exception tracebacks, which is where the IBM SDK would otherwise leak your CRN in a request URL.

