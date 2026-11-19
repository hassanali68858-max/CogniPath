from alembic import context

context.configure(
    connection=context.config.attributes["connection"],
    version_table="event_alembic_version",
)
with context.begin_transaction():
    context.run_migrations()
