# Database Environments

Mind Palace App uses one active database connection at runtime:

```text
DATABASE_URL
```

The code does not know about Neon branch names directly. Each environment points `DATABASE_URL` at the correct Neon branch.

## Neon Branch Mapping

```text
production   -> production Neon branch
staging      -> staging Neon branch
development  -> development Neon branch
local        -> development Neon branch or a local Postgres database
```

## Local Development

For normal local work, use the Neon `development` branch.

```bash
cp .env.development.example .env
```

Then replace the placeholder `DATABASE_URL` with the connection string copied from Neon.

Check the connection:

```bash
.venv/bin/python scripts/check_neon_connection.py
```

## Staging

Staging deploys should set:

```text
APP_ENV=staging
DATABASE_URL=<staging branch connection string>
```

Do not use staging credentials locally unless you are intentionally debugging staging data or migrations.

## Production

Production deploys should set:

```text
APP_ENV=production
DATABASE_URL=<production branch connection string>
```

Production credentials should live only in the production deployment environment.

## Migration Rule

Alembic runs against whichever `DATABASE_URL` is active.

Before running migrations, confirm the target environment:

```bash
grep APP_ENV .env
```

Then run:

```bash
.venv/bin/alembic upgrade head
```

## Safety Rules

- Never commit real Neon connection strings.
- Use `development` for local feature work.
- Use `staging` for release validation.
- Use `production` only for live deploys.
- Keep branch separation in environment variables, not application code.
- Treat migrations as production-impacting once they reach staging.

