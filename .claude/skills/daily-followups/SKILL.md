---
name: daily-followups
description: Run and review the personalised follow-up queue. Use when asked to run the follow-ups, check what is waiting for approval, approve or reject a queued follow-up, or explain why someone was skipped.
---

# Daily follow-ups

Drives the follow-up pipeline conversationally. The CLI does the work; this
skill decides what to run and how to report it.

## Setup

Always set the data directory first, so nothing is written into the repository:

```bash
export FOLLOWUPS_HOME=./out
```

## Running the daily pass

```bash
followups run
```

Report the counts as prose, not a table dump. The two numbers that matter are
`queued`, which is what needs the user's attention, and `skipped`, which is
what the system decided to leave alone. If anything `failed`, say which vendor
and what the error was.

Never pass `--live-send` unless the user asked for it in this conversation.

## Reviewing the queue

```bash
followups review
```

For each pending item, give the user the company, what the person actually
said, which resource was produced, and the link. Group by track so the user can
approve a batch rather than one at a time.

## Approving

Only after the user has said yes to specific items:

```bash
followups approve <id>
followups reject <id>
```

Approval is per item. "Looks good" about one deck is not approval of the queue.

## Explaining a skip

Skips carry their reason. Read them from the dashboard or the database rather
than guessing:

```bash
followups dashboard && open out/dashboard.html
```

The common reasons are: the category routed to no resource, the prospect went
dormant after three silent days, the 48 hour gap was not met, or they already
received that kind of resource.

## What not to do

- Do not send anything the user has not approved in this conversation.
- Do not edit `config/routing.yaml` without saying what the change does to
  which category.
- Do not implement the real adapters. They are deliberately stubbed.
