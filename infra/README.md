# Infra

## Local database

```bash
docker compose -f infra/docker-compose.yml up -d     # PostgreSQL 16 on localhost:5432
export DATABASE_URL=postgresql+psycopg://cognipath:cognipath@localhost:5432/cognipath
```

Tables are created automatically the first time the Planner API starts
(`planner_profiles`, `planner_proposals`, `planner_plans`, `planner_decisions`).
Without `DATABASE_URL`, the Planner uses a local SQLite file `cognipath_dev.db`.

Look inside the database:

```bash
docker exec -it cognipath-db psql -U cognipath -d cognipath -c '\dt'
```

The password `cognipath` is for local development only.
