# Deployment

Use Docker Compose locally and Railway for production. The app service must run migrations before startup:

```bash
alembic upgrade head
python -m app.main
```

Keep PostgreSQL as a separate service. Never drop the database on deploy. Use one app replica for MVP. Advisory locks are included for scheduler safety.
