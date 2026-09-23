<p align="center">
  <img src="assets/qoffee-logo.svg" alt="Qoffee logo" width="170">
</p>

<p align="center">
  <em>Qoffee monitors your quantum jobs, so you don't have to.</em>
</p>

<p align="center">
  <a href="https://github.com/saadbhattii/Qoffee/actions/workflows/tests.yml"><img src="https://github.com/saadbhattii/Qoffee/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/saadbhattii/Qoffee/blob/main/LICENSE"><img src="https://img.shields.io/github/license/saadbhattii/Qoffee" alt="License"></a>
  <a href="https://deepwiki.com/saadbhattii/Qoffee"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</p>

<p align="center">
  <img src="https://qisk.it/e-8f32b728" alt="Qiskit Ecosystem">
  <a href="https://github.com"><img src="https://img.shields.io/badge/bot-github_actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions Bot"></a>
</p>

# Qoffee

Qoffee is a free and open-source IBM quantum job monitoring and notification tool that runs as a GitHub Action in your own repository, on a schedule, under your own GitHub account. You submit a job, tag it, and forget about it. Qoffee
notifies you when it's done, or when the job fails, without you ever needing to open a laptop, refresh a dashboard, or check a queue.

Unlike a traditional SaaS, Qoffee is designed to give you complete control over your data and infrastructure. It keeps information private to your own storage, requires no paid service, and fits naturally into existing workflows. The result is minimal setup, maximum ownership, and the freedom to decide where data lives.

## How to Setup Qoffee

1. **Fork this repo.**
2. In your fork's **Settings → Secrets and variables → Actions**, add:

   | Secret | What it is |
   |---|---|
   | `IBM_TOKEN` | Your IBM Quantum API token |
   | `IBM_CRN` | Your IBM Quantum instance CRN |
   | `DISCORD_WEBHOOK` | A webhook URL from your own Discord server (default channel) [A guide to getting it.](https://www.svix.com/resources/guides/how-to-make-webhook-discord/)|

Add `SLACK_WEBHOOK` and/or `NTFY_URL` too if you want more than one channel. Check [Configuration](docs/configuration.md).

> **Note:** Nobody can view a secret's value once it's set; not you, not a collaborator, not anyone browsing a public repo. This isn't fork-specific: it's true for every GitHub repository. Forking doesn't migrate secrets, each fork's secrets are created independently by whoever owns that fork, and stay scoped to it alone.

3. Open the `Actions` tab on your fork and press the button confirming you want workflows to run. After that, manually enable and trigger the `Qoffee Watcher` workflow once to confirm everything connects.

**That's it.**

## Usage: Tagging a job with `qoffee`

Add a line to whatever script you already use when submitting jobs:

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

To **stop tracking a job manually**, just remove or rename the `qoffee` tag yourself and Qoffee will simply stop
seeing it on the next run. No other cleanup needed.

```python
# For removing the tag
job = service.job("your_job_id_here")
job.update_tags([t for t in (job.tags or []) if t != "qoffee"])

#For renaming the tag
job = service.job("your_job_id_here")
job.update_tags(["qoffeed" if t == "qoffee" else t for t in (job.tags or [])])
```

## Documentation

| Document | What's in it |
|---|---|
| [How Qoffee works](docs/how-it-works.md) | The run cycle, the tracking tags, the state machine |
| [Design decisions](docs/design-decisions.md) | Why there's no database, why failures linger, why tags are the state |
| [Configuration](docs/configuration.md) | Notification channels, `settings.py` settings, log redaction |
| [Scheduling](docs/scheduling.md) | Triggers, and the optional Cloudflare Worker for high-frequency runs |
| [Development](docs/development.md) | Tests, local debugging, exit codes |

## Roadmap

- **More channels**: Telegram, email, Teams, generic webhooks.
- **More providers**: AWS Braket and Azure Quantum.

## FAQ

- **Do I need to keep my laptop on?** No. It runs on GitHub's infrastructure.

- **Does this cost anything?** No. GitHub Actions is free for public repos; Discord webhooks are free. The optional Cloudflare Worker is also free-tier.

- **Can you see my quantum jobs?** No. There is no server to send them to. Read the code, it's fully public.

- **Can you see my secret keys?** No. They are saved in your forked repository settings that belongs to your Github Account.

- **What if I already have jobs tagged from an older version?** They migrate automatically.

- **How do I stop tracking a job?** Remove the `qoffee` tag. Qoffee stops seeing it on the next run.

- **What if my notification service is down?** Nothing gets untagged, the run goes red, and everything is reported again next run. By design.

## License

Apache License 2.0.

<p align="center">
<em>Submit. Tag. Forget.</em>
</p>