# Alembic migrations

The async Alembic environment reads `DATABASE_URL` through the application
settings. From the repository root:

```powershell
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
```

The initial revision enables the `vector` extension supplied by the
`pgvector/pgvector` PostgreSQL image. Domain tables are added in later tasks.
