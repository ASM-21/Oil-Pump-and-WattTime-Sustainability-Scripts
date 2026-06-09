# Security and Sharing Checklist

Use this checklist before pushing the repository to a public GitHub repo, sharing it with a collaborator, or attaching it to a portfolio/application. The current cleanup removes plain-text WattTime credentials and local OpenLCA host details from the working tree, but **anything committed in old Git history should still be treated as exposed and rotated**.

## Completed in this cleanup pass

- WattTime scripts now read `WATTTIME_USERNAME` and `WATTTIME_PASSWORD` from environment variables instead of hardcoded values.
- OpenLCA automation scripts now default to local placeholders or environment variables instead of a private lab IP/process UUID.
- `.env.example` documents the local variables expected by WattTime, OpenLCA, and OpenNX workflows.
- `.gitignore` excludes local `.env` files, generated token files, logs, Python caches, and large local data caches.
- Tracked `__pycache__` files, `agent.log`, and `Background watttime scripts/WattTime_token.txt` were removed from the repo.

## Still required before public release

- [ ] Rotate any WattTime password/token that appeared in previous commits.
- [ ] Decide whether old Git history must be rewritten before public release.
- [ ] Confirm WattTime data redistribution rights before committing any downloaded API data.
- [ ] Confirm whether OpenLCA UUIDs are sensitive for the database you plan to share.
- [ ] Replace any remaining local absolute paths with environment variables or documented placeholders.
- [ ] Review generated figures/tables for proprietary machine names, student names, lab paths, or timestamps.
- [ ] Keep raw machine logs, OpenLCA databases, and WattTime caches out of Git unless they are explicitly approved for release.

## Local setup pattern

```bash
cp .env.example .env
# edit .env locally with real credentials and local paths
```

Never commit `.env`. If a script needs a new secret or local path, add a placeholder to `.env.example` and document it here.
