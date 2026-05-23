import os
import clickhouse_connect

db = clickhouse_connect.get_client(
    host=os.getenv("CLICKHOUSE_HOST", "db.georgytadjiev.ink"),
    port=int(os.getenv("CLICKHOUSE_PORT", "443")),
    username=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass"),
    secure=os.getenv("CLICKHOUSE_SECURE", "True").lower() in ("true", "1", "yes")
)

print("--- interactions table schema ---")
print(db.query_df("DESCRIBE interactions"))
print("\n--- agent_registry table schema ---")
print(db.query_df("DESCRIBE agent_registry"))
print("\n--- agent_states table schema ---")
print(db.query_df("DESCRIBE agent_states"))

print("\n--- finding a truly heterogeneous run_id ---")
df = db.query_df("""
    SELECT r.run_id, r.scenario_name, r.run_name, count(DISTINCT a.archetype) as archetypes
    FROM simulation_runs r
    JOIN agent_registry a ON r.run_id = a.run_id
    GROUP BY r.run_id, r.scenario_name, r.run_name
    ORDER BY archetypes DESC
    LIMIT 5
""")
print(df)
