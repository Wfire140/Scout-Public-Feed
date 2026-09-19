# Scout Public Feed Mirror

```text
Scout
  ↓
Cloudflare Project Hub (authoritative sanitized feed)
  ↓
GitHub Action
  ↓
scout-current.json
  ↓
Chat weekly audit
```

This repository contains public sanitized Scout data only. GitHub does not control Scout, does not publish back to Cloudflare, and contains no credentials. The source is the read-only public endpoint `https://project-hub-view.pages.dev/api/scout/current`.

The action checks every two hours at minute 17 UTC and can also run manually. It uses the repository-provided `GITHUB_TOKEN` with only `contents: write` permission. It validates HTTP status, JSON, the reviewed schema-v1 field set, values, result URL hosts, and sensitive data patterns before atomically replacing `scout-current.json`. Failures preserve the last good file and fail the run. A changed valid file is committed; an identical file makes no commit. New fields or source hosts require review and a validator change.

Run offline tests with `python -m unittest discover -s tests -v`. Run a local fetch with `python mirror.py`.

`scout-current.json` is the only file Chat needs to read. It retains the source payload's meaning and does not add fetch-time metadata, so unchanged source data produces no commit.
