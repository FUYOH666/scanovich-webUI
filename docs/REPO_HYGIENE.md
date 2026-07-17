# Repository hygiene (public)

Rules for what may be committed to this **public** repository.

## Never commit

- Real `.env`, `.env.mws.local`, `bootstrap.env`, API keys, tunnel tokens
- Private keys (`*.pem`, `credentials.*`, `secrets/`)
- Absolute personal paths, internal hostnames, Tailscale / private IPs
- Vendored full Open WebUI source tree (`/open-webui/` is gitignored — use `OPEN_WEBUI_IMAGE`)
- Team-only strategy and ops journals (live under **`.local/`**, gitignored)

## Safe to commit

- Code under `apps/`, `infra/`, `scripts/`
- `*.example` env templates with placeholders only
- Public docs: architecture, feature matrix, local run, business one-pager
- Social assets under `docs/assets/`

## Before every push

```bash
git status
git diff --cached
# spot-check staged files for secrets / IPs
```

Team-internal playbooks (commercial roadmap, OSS layer assembly, smoke journals)
stay in **`.local/`** on developer machines — not on GitHub.
