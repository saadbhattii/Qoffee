<p align="center">
  <img src="assets/qoffee-logo.svg" alt="Qoffee logo" width="170">
</p>

<p align="center">
<em>Qoffee monitors your quantum jobs, so you don't have to.</em>
</p>

# Qoffee

Qoffee is a free and open-source IBM quantum job monitoring and notification tool that runs as a GitHub Action in your own repository, on a schedule, under your own GitHub account. You submit a job, tag it, and forget about it. Qoffee
notifies you when it's done, or when the job fails, without you ever needing to open a laptop, refresh a dashboard, or check a queue.

## Contents

- [Perk: Qoffee has no database.](#perk-qoffee-has-no-database)
- [How Qoffee works](#how-qoffee-works)
- [Setup](#setup)
- [Usage: Tagging a job with `qoffee`](#usage-tagging-a-job-with-qoffee)
- [Qoffee doesn't spam.](#qoffee-doesnt-spam)
- [For Qoffee, your failed jobs matter.](#for-qoffee-your-failed-jobs-matter)
- [Qoffee makes sure the notification was delivered.](#qoffee-makes-sure-the-notification-was-delivered)
- [Notification channels](#notification-channels)
- [Optional Configuration](#optional-configuration)
- [Triggers](#triggers)
- [Setting up a Cloudflare Worker as a High Frequency Scheduler (Optional)](#setting-up-a-cloudflare-worker-as-a-high-frequency-scheduler-optional)
  - [1. Create a Cloudflare Worker](#1-create-a-cloudflare-worker)
  - [2. Add Worker Secrets](#2-add-worker-secrets)
  - [3. Worker Code](#3-worker-code)
  - [4. Configure the Cron Trigger](#4-configure-the-cron-trigger)
  - [5. Generate a GitHub Token](#5-generate-a-github-token)
  - [6. Test the Scheduler](#6-test-the-scheduler)
  - [7. Verify the Workflow](#7-verify-the-workflow)
- [Where Qoffee could go](#where-qoffee-could-go)
- [Other Vendors looked into](#other-vendors-looked-into)
- [Test Locally](#test-locally)
- [Debugging](#debugging)
- [FAQ](#faq)
- [License](#license)

## Perk: Qoffee has no database.

The tracking state lives entirely on IBM's servers, the repo itself
never stores anything about you, not your job IDs, not your history, not
who's using it. That means the repo can be **completely public**, and
anyone can fork it and run their own copy just by adding their own
secrets. No cloning, no re-uploading, no private repo required. Moreover, all public repositories get unlimited Actions minutes.

> **Public run logs also handled.** GitHub Actions logs on a public repo are world-readable. Qoffee redacts job IDs and instance CRNs to stable short hashes (`job#3beed3`) before anything reaches the log, including inside exception tracebacks, which is where the IBM SDK would otherwise leak your CRN in a request URL. Redaction is **on by default**, because a safe default is worth more than a configurable one. The full IDs are still in your notification, where only you can see them.

Two people running identical forks produce completely separate, mutually invisible systems, purely because their secrets differ.

## How Qoffee works

A quantum job is tracked because it carries a tag that you gave it. Nothing else remembers
anything.

There is no database. No spreadsheet. No `jobs.yaml`. No local state file.
**IBM's own job metadata: `tags`, is the entire tracking mechanism**, from
discovery through to cleanup.

```
Submit job with tag "qoffee"
            │
            ▼
   GitHub Actions runs (schedule or manual trigger)
            │
            ▼
   Qoffee queries IBM for every job tagged "qoffee"
            │
            ▼
   Notify Discord: one batched message per run with filters to avoid spamming and redundancy.
            │
            ▼
   Terminal jobs (DONE / ERROR / CANCELLED) get
   renamed "qoffee" → "qoffeed", but only AFTER
   the notification is confirmed sent.
```

## Setup
 
1. **Fork this repo.**
2. In your fork's **Settings → Secrets and variables → Actions**, add:
   | Secret | What it is |
   |---|---|
   | `IBM_TOKEN` | Your IBM Quantum API token |
   | `IBM_CRN` | Your IBM Quantum instance CRN |
   | `DISCORD_WEBHOOK` | A webhook URL from your own Discord server (default channel) [A guide to getting it.](https://www.svix.com/resources/guides/how-to-make-webhook-discord/)|

Add `SLACK_WEBHOOK` and/or `NTFY_URL` too if you want more than one channel. See [Notification channels](#notification-channels) below.

> **Note:** Nobody can view a secret's value once it's set; not you, not a collaborator, not anyone browsing a public repo. This isn't fork-specific: it's true for every GitHub repository, always. Forking doesn't migrate secrets, each fork's secrets are created independently by whoever owns that fork, and stay scoped to it alone.
  
3. **Actions tab → enable workflows on your fork.** GitHub disables
   Actions entirely on a freshly forked repo until you enable them once. Optionally trigger the workflow once manually now to confirm everything connects.

That's it. 

> **GitHub disables scheduled workflows after 60 days with no repo
> activity**, silently, and it also disables manual dispatch until
> re-enabled. To prevent that, Qoffee pushes an empty "keepalive" commit
> every 45 days if the repo has been otherwise quiet. If you see an
> unexplained `chore: keepalive` commit in your history, that's why, 
> it's expected, not a bug.

## Usage: Tagging a job with `qoffee`

Add one line to whatever script you already use to submit jobs:

```python
sampler = Sampler(backend)
sampler.options.environment.job_tags = ["qoffee"] #tagged

job = sampler.run([isa_circuit])
```

You can also tag a job **after** submission, or tag one you didn't even
submit in this session, as long as you can retrieve it:

```python
job = service.job("your_job_id_here")
job.update_tags(list(job.tags or []) + ["qoffee"]) #tagged
```

Optionally, you can give it a name so notifications are readable instead of showing a raw job ID, add a second tag using the `name:` prefix:

```python
sampler.options.environment.job_tags = ["qoffee", "name:Bell Test 1"] #tagged and named
```

IBM caps each tag at **24 characters** and allows **5 tags per job**
the `name:` prefix uses 5 of those characters, leaving 19 for the label
itself.

To **`stop tracking a job manually`**, just remove or rename the `qoffee` tag yourself and Qoffee will simply stop
seeing it on the next run. No other cleanup needed.

```python
# For removing the tag
job = service.job("your_job_id_here")
job.update_tags([t for t in (job.tags or []) if t != "qoffee"])

#For renaming the tag
job = service.job("your_job_id_here")
job.update_tags(["qoffeed" if t == "qoffee" else t for t in (job.tags or [])])
```



## Qoffee doesn't spam.
 
Every run sends **one batched message**, not one per job. As jobs
resolve, they drop out of the batch, so the message naturally shrinks
over time.

Qoffee doesn't spam the same status notification as well. Qoffee tracks the last state it reported, which it encodes in the tag itself, so this costs no storage, and stays silent when nothing has changed.

A job that sits in the queue for six hours produces **one** message. Only when the status changes, you are notified.

Also, if nothing is currently tagged `qoffee`, Qoffee sends **no message at
all**.
 

## For Qoffee, your failed jobs matter.

This is the another design decision behind Qoffee's notification logic:

| Status | Tag renamed to `qoffeed`? |
|---|---|
| `INITIALIZING` / `QUEUED` / `RUNNING` | No |
| `DONE` | Yes, immediately after notifying you  |
| `ERROR` / `CANCELLED` | Only if nothing else tagged `qoffee` is still active or finished in the batch |

A `DONE` job clears out of the batch the moment it's reported. An
`ERROR`/`CANCELLED` job deliberately does **not**, it stays visible in
every batch notification for as long as anything else in the batch is still
moving. It only resolves once the whole batch has gone quiet.

The result: if you walk away for a day, the last message you see are the failures if any. An empty batch means
everything succeeded. A batch that's shrunk down to just failures means
those are exactly the jobs that need resubmitting.
 
## Qoffee makes sure the notification was delivered.
 
Nothing is ever untagged without a **confirmed** Discord send. The
sequence is always: check status → build message → send → *only on a
successful send* → rename terminal jobs. If the Discord call fails for
any reason, every tag is left exactly as it was, and everything gets
re-reported on the next run instead of silently disappearing from
tracking.

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
 
By default, the **first** channel listed must confirm delivery before a job's tag is updated, that way a single broken webhook can never cause a job to silently drop out of tracking without you having actually been told. If every configured channel fails on a given run, nothing changes and the same news is reported again next run.

## Optional Configurations
 
Everything you'd want to change lives in one file: `qoffee/settings.py`. It's a plain block of commented constants, no YAML, no JSON, no hidden config service.
 
| Setting | Default | What it controls |
|---|---|---|
| `TRACKING_TAG` | `"qoffee"` | The tag a job needs to be tracked |
| `RESOLVED_TAG` | `"qoffeed"` | Applied once tracking stops (set `""` to delete the tag outright instead) |
| `CHANNELS` | `"discord"` | Which notification channels are active |
| `REQUIRED_CHANNELS` | *(first channel)* | Which channels must confirm delivery before tags change |
| `FAILURE_AUTOCLEAR_HOURS` | `0` (disabled) | Safety net: force-clear a stuck failure after N hours if the batch never goes quiet |
| `REDACT_LOGS` | `True` | Replace job IDs and instance CRNs with short hashes in the public Actions log |
 
`REDACT_LOGS` defaults **on** deliberately, this repo can be public, which means its Actions run logs are readable by anyone, and the full IDs are already sitting safely in your private notification either way. There's no cost to leaving it on.

## Triggers

The workflow runs on:
- **`schedule`**: every 15 minutes by default, automatically. (Not consistent, and has delays, solution discussed below, see the Cloudflare section.)
- **`workflow_dispatch`**: manually, including from the GitHub Mobile
  app, so you can check on demand without opening a laptop. Manual triggering spins up with no delays.

## Setting up a Cloudflare Worker as a High Frequency Scheduler (Optional)

GitHub's cron scheduler is known to occasionally delay scheduled runs during periods of heavy load. Even if you set up `cron` for 15 minutes, it will spin up in the range of every 30 to 40 minutes or even more depending on the time of the day, which is acceptable to some people, however, if you demand a more consistent high-frequency scheduler, you can let Cloudflare Worker wake up your GitHub workflow instead. It is easy to set up and will cost you nothing as well.

> Cloudflare Worker's sole responsibility is to wake the GitHub workflow on a schedule; all Qoffee logic continues to execute entirely within GitHub Actions, keeping scheduling cleanly separated from monitoring and notification logic. This separation also allows the scheduler to be replaced or removed at any time without requiring any changes to Qoffee itself.

### 1. Create a Cloudflare Worker

1. Sign in to Cloudflare.
2. Navigate to **Workers & Pages**.
3. Create a new Worker.
4. Replace the default code with the Worker below.
5. Deploy the Worker.

### 2. Add Worker Secrets

Under **Settings → Variables and Secrets**, create the following secrets.

| Secret         | Value                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `GITHUB_REPO`  | `your-username/your-repository`                                                                                   |
| `GITHUB_TOKEN` | A GitHub Fine-Grained Personal Access Token with **Actions: Read & Write** permission for your Qoffee repository. |

### 3. Worker Code

```javascript
export default {
  async scheduled(event, env, ctx) {
    console.log("☕ Qoffee scheduler triggered");

    ctx.waitUntil(triggerWorkflow(env));
  },

  async fetch(request, env, ctx) {
    return new Response("☕ Qoffee scheduler alive");
  }
};

async function triggerWorkflow(env) {
  const url =
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/watch.yml/dispatches`;

  console.log("Dispatch URL:", url);

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "qoffee-cloudflare-scheduler"
    },
    body: JSON.stringify({
      ref: "main"
    })
  });

  const text = await response.text();

  console.log("GitHub status:", response.status);
  console.log("GitHub response:", text);

  if (!response.ok) {
    console.log("✗ GitHub workflow dispatch failed");
  } else {
    console.log("✓ GitHub workflow dispatched");
  }
}
```

### 4. Configure the Cron Trigger

From the Worker dashboard:

> **Settings → Triggers → Cron Triggers**

Create a cron schedule such as:

```text
*/5 * * * *
```

This runs the scheduler every five minutes.

Cloudflare cron expressions use UTC time and changes may take several minutes to propagate globally after being saved.

### 5. Generate a GitHub Token

Create a **Fine-Grained Personal Access Token** with access only to your selected Qoffee repository.

Required repository permissions:

* **Actions:** Read and Write
* **Metadata:** Read (automatically included)

Copy the token into the Cloudflare `GITHUB_TOKEN` secret.

### 6. Test the Scheduler

After deployment, you should see logs similar to:

```text
☕ Qoffee scheduler triggered
Dispatch URL: https://api.github.com/repos/your-name/your-repo/actions/workflows/watch.yml/dispatches
GitHub status: 204
GitHub response:
✓ GitHub workflow dispatched
```

An HTTP **204 No Content** response is the expected success response from GitHub when a workflow dispatch request is accepted.

### 7. Verify the Workflow

Open your repository's **Actions** tab.

Every time the Cloudflare cron fires, a new **Qoffee Watcher** workflow run should appear.

And that's it. You are done.


## Where Qoffee could go
 
- **More channels**: Telegram, email, Teams, generic webhooks. One file each; the core doesn't change.
- **More providers**: the seam is built and contract-tested. A future adapter inherits the whole test suite.

## Other Vendors looked into
 
- AWS Braket was investigated: Braket cannot filter tasks by tag server-side, *and* AWS already ships first-party push notifications via EventBridge and SNS. Duplicating a native feature didn't seem like it would be worth the maintenance for now. If you want Braket notifications today, [use EventBridge](https://docs.aws.amazon.com/braket/latest/developerguide/braket-monitor-eventbridge.html).

## Testing for Developers

```bash
pip install -e ".[dev]"
pytest -m "not live"
```
 
## Debugging Locally
 
```bash
python -m qoffee --check-config   # validate everything, contact nothing
python -m qoffee --dry-run        # fetch, decide, report — change nothing
```


## FAQ
 
- **Do I need to keep my laptop on?** No. It runs on GitHub's infrastructure.
 
- **Does this cost anything?** No. GitHub Actions is free for public repos; IBM's Open Plan is free; Discord webhooks are free. The optional Cloudflare Worker is also free-tier.
 
- **Can you see my quantum jobs?** No. There is no server to send them to. Read the code, it's fully public.

- **Can you see my secret keys?** No. They are saved in your forked repository settings that belongs to your Github Account.
 
- **What if I already have jobs tagged from an older version?** They migrate automatically.
 
- **How do I stop tracking a job?** Remove the `qoffee` tag. Qoffee stops seeing it on the next run.
 
- **What if my notification service is down?** Nothing gets untagged, the run goes red, and everything is reported again next run. By design.
 
 
## License
 
MIT.
 

 
<p align="center">
<em>Submit. Tag. Forget.</em>
</p>














 



