# Design decisions

Qoffee makes a few choices. This page explains why.

## No database

The tracking state lives entirely on IBM's servers. The repo itself never stores anything about you, not your job IDs, not your history, not who's using it. That means the repo can be **completely public**, and anyone can fork it and run their own copy just by adding their own secrets. No cloning, no re-uploading, no private repo required. All public repositories also get unlimited Actions minutes.

Two people running identical forks produce completely separate, mutually invisible systems, purely because their secrets differ.

Public run logs are handled too. GitHub Actions logs on a public repo are world-readable, so Qoffee redacts job IDs and instance CRNs to stable short hashes (`job#3beed3`) before anything reaches the log, including inside exception tracebacks, which is where the IBM SDK would otherwise leak your CRN in a request URL. Redaction is **on by default**.The full IDs are still in your notification, where only you can see them.

## Qoffee doesn't spam

Every run sends one batched message, not one per job. As jobs resolve, they drop out of the batch, so the message naturally shrinks over time.

Qoffee also doesn't repeat a status it has already reported. It tracks the last state it reported by encoding it in the tag, which costs no storage, and stays silent when nothing has changed. A job that sits in the queue for six hours produces **one** message.

If nothing is currently tagged `qoffee`, Qoffee sends no message at all.

## Your failed jobs matter

This is the another design decision behind Qoffee's notification logic:

| Status | Will Qoffee stop tracking? |
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
 
Nothing is ever untagged without a **confirmed** Discord send. The sequence is always: check status → build message → send → *only on a successful send* → rename terminal jobs. If the Discord call fails for any reason, every tag is left exactly as it was, and everything gets re-reported on the next run instead of silently disappearing from tracking.