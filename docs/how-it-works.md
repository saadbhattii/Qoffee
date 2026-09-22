# How Qoffee works

Qoffee has no database. There is no state file, no jobs.yaml, no spreadsheet, and no server holding a list of what you are watching. IBM's own job tags are the entire tracking mechanism, from discovery through to cleanup.

## The whole loop

1. You submit a job carrying the tag `qoffee`.
2. A GitHub Action runs, on a schedule or manually.
3. Qoffee asks IBM for every job tagged `qoffee`.
4. It compares each job's status against the status recorded in its second tag, and sends a message if anything differs.
5. After the message is confirmed delivered, finished jobs have their tags rewritten to `qoffeed`, which removes them from the next query.

## The second tag

Qoffee adds one extra tag, and it's temporary. You add one tag; Qoffee adds a second, rewrites it as the job moves through its life, and removes both at the end. This matters because IBM allows only **five tags per job**, so you should know how many Qoffee is using.

**What the job actually carries over its lifetime:**

| Moment | Tags on the job | Count |
|---|---|---|
| You submit it | `qoffee` | 1 |
| Qoffee sees it queued | `qoffee`, `qoffee@Q` | 2 |
| It starts running | `qoffee`, `qoffee@R` | 2 |
| It fails, and you're told | `qoffee`, `qoffee@F:1755835200` | 2 |
| Tracking ends | `qoffeed` | 1 |

### Why the second tag exists

Qoffee has no database, so "I already told you this job was queued" has to be written down somewhere. It gets written on the job itself.

- `qoffee@Q`: queued, and you've been told
- `qoffee@R`: running, and you've been told
- `qoffee@F:1755835200`: failed, and you've been told. The number is a Unix timestamp, used only by the `FAILURE_AUTOCLEAR_HOURS` safety net.

On every run Qoffee compares the job's real status against the letter in that tag. Same, and it stays silent. Different, and it notifies you, then rewrites the tag. That comparison is the entire reason you aren't pinged every fifteen minutes about the same status.

## When a job resolves

| Status | Tag renamed to `qoffeed`? |
|---|---|
| `INITIALIZING` / `QUEUED` / `RUNNING` | No |
| `DONE` | Yes, immediately after notifying you |
| `ERROR` / `CANCELLED` | Only if nothing else tagged `qoffee` is still active or finished in the batch |

Why failures behave differently is covered in [Design decisions](design-decisions.md#your-failed-jobs-matter).

## When Qoffee gives up

IBM allows five tags per job. If a job already carries five of your own, Qoffee cannot add its tracking tag, and there is no database in which to record that it tried. Rather than retry forever in silence, the run exits with code **4**, goes red in the Actions tab, and names the job in the log. Remove one of that job's tags, or remove `qoffee` from it, and the next run proceeds normally.

This is distinct from a transient failure. A network blip is retried quietly on the next run and the run still passes; only a rejection that can never succeed turns the run red.

See also: [exit codes](development.md#exit-codes).