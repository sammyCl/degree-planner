from fastapi import FastAPI

from degree_planner_backend.db import get_connection

app = FastAPI(title="Degree Planner API")


@app.get("/health")
def health() -> dict[str, str]:
    connection = get_connection()
    try:
        connection.execute("SELECT 1")
        database_status = "ok"
    finally:
        connection.close()
    return {"status": "ok", "database": database_status}
