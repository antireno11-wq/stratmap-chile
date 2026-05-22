# stratmap-chile

## Setup

### Required environment variables

- `SECRET_KEY` — used to sign JWT access tokens. **Required.** Must be at least 32 characters long. The app will refuse to start without it.

  Generate one with:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

  Set it locally with `export SECRET_KEY="<paste-generated-value>"`, or on Railway via the **Variables** tab.

- `ADMIN_EMAILS` — comma-separated list of emails allowed to call `/admin/*` endpoints and `POST /ingest`. Example: `ADMIN_EMAILS=alice@acme.cl,bob@acme.cl`. Anyone logged in with an email **not** in this list gets `403` from admin endpoints.

- `ALLOW_SETUP` — bootstrap flag for `POST /setup/first-user`. Set to `true` only while creating the very first user, then unset.

  The endpoint is **double-gated**: it requires both `ALLOW_SETUP=true` **and** an empty `users` table. So even if you forget to unset it, setup only runs once.

### Bootstrap on a fresh deployment

1. Set `SECRET_KEY` and (temporarily) `ALLOW_SETUP=true` in Railway.
2. Deploy.
3. Call `POST /setup/first-user` with the email/password of your first admin user (`curl` or any tool).
4. Add that same email to `ADMIN_EMAILS` (e.g. `ADMIN_EMAILS=you@yourdomain.cl`).
5. Unset `ALLOW_SETUP` (or set it to anything other than `true`).
6. Log in through `/login.html` — you'll get a JWT and full access.

> Other env vars (`DATABASE_URL`, `ANTHROPIC_API_KEY`, etc.) will be documented as the rest of the configuration is hardened.
