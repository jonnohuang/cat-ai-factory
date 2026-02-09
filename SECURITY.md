# Security Policy

## Reporting a vulnerability

If you discover a security issue, please report it responsibly.

Preferred:
- Use GitHub Security Advisories for this repository.

Alternative:
- Contact the maintainers via email (placeholder): security@example.com

## Public repo posture (no secrets)

This repository is PUBLIC by design (portfolio posture). Therefore:
- Secrets and credentials must never be committed to the repo.
- This includes API keys, OAuth secrets, refresh tokens, cookies, authorization headers, webhook URLs with embedded secrets, service account JSON files, and private keys.

See:
- docs/briefs/GUARDRAILS.md

## If a secret is accidentally committed

If credential material is accidentally exposed:
1. Revoke / rotate the secret immediately.
2. Treat it as compromised.
3. Remove it from the repository history if needed (do not rely on deleting a file in a later commit).
