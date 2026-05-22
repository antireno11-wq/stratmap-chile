# stratmap-chile

## Setup

### Required environment variables

- `SECRET_KEY` — used to sign JWT access tokens. **Required.** Must be at least 32 characters long. The app will refuse to start without it.

Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set it locally:

```bash
export SECRET_KEY="<paste-generated-value>"
```

On Railway: open the project → **Variables** tab → add `SECRET_KEY` with the generated value, then redeploy.

> Other required env vars (`DATABASE_URL`, `ANTHROPIC_API_KEY`, etc.) will be documented as the rest of the configuration is hardened.
