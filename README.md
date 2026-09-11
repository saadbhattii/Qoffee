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

## Perk: Qoffee has no database. 

The repo itself never stores anything about you, not your job IDs, not your history, not
who's using it. That means the repo can be **completely public**, and
anyone can fork it and run their own copy just by adding their own
secrets. No cloning, no re-uploading, no private repo required. Moreover, all public repositories get unlimited Actions minutes. Two people running identical forks produce completely separate, mutually invisible systems, purely because their secrets differ.

Learn more about [how Qoffee redacts from the public log]("https://qoffee-docs.pages.dev/redaction").

## How Qoffee works

**IBM's own job metadata: `tags`, is the entire tracking mechanism**. A quantum job is tracked because it carries a tag that you gave it. There is no database. No `jobs.yaml`. No local state file.

### The loop:

1. You submit jobs to IBM with the tag `qoffee` in it's metadata.
2. GitHub Action runs, on a schedule via cron.
3. Qoffee asks your IBM account for every job tagged `qoffee`.
4. It compares each job's status against the status recorded in its second tag, and sends a message if anything differs.
5. After the message is confirmed delivered, finished jobs have their tags rewritten to `qoffeed`, which removes them from the next query.

Learn more about [the rules behind Qoffee]("https://qoffee-docs.pages.dev/notifications"). 

## How to Setup Qoffee
 
1. **Fork this repo.**
2. In your fork's **Settings → Secrets and variables → Actions**, add:

   | Secret | What it is |
   |---|---|
   | `IBM_TOKEN` | Your IBM Quantum API token |
   | `IBM_CRN` | Your IBM Quantum instance CRN |
   | `DISCORD_WEBHOOK` | A webhook URL from your own Discord server (default channel) [A guide to getting it.](https://www.svix.com/resources/guides/how-to-make-webhook-discord/)|
  
3. **Actions tab → allow workflows on your fork.** GitHub disables Actions entirely on a freshly forked repo until you enable them once. After that, open `Qoffee Watcher` in the Actions tab and enable the workflow itself. Optionally trigger the workflow once manually now to confirm everything connects. 

That's it. If you have any queries, visit [Qoffee's documentation]("https://qoffee-docs.pages.dev/setup").

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

## Testing for Developers

```bash
pip install -e ".[dev]"
pytest -m "not live"
```
 
## Debugging

```bash
python -m qoffee --check-config   # validate everything, contact nothing
python -m qoffee --dry-run        # fetch, decide, report: change nothing
```

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