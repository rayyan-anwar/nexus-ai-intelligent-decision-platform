# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private vulnerability reporting for this repository (Security tab > Report a vulnerability). Include what you found, how to reproduce it, and the potential impact. You can expect an acknowledgement and a plan for a fix or mitigation; this is a volunteer-maintained project, so no response-time guarantee is made.

## Supported versions

Only the latest release on `main` receives fixes.

## Scope and known limits

Read [docs/security.md](docs/security.md): it lists the implemented controls and the limitations (for example, there is no per-user data isolation, rate limiting is per process, and model files are pickles verified by checksum).

## If you deploy this

* Never commit `.env` files, tokens, database dumps or datasets.
* Serve over HTTPS and keep the API token hashes, not tokens, in configuration.
* Keep dependencies updated (Dependabot is configured) and review CI's vulnerability scan results.
