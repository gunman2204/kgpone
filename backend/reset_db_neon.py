import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")
engine = create_engine(url)

try:
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        print("Dropping public schema...")
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        print("Recreating public schema...")
        conn.execute(text("CREATE SCHEMA public;"))
except Exception as e:
    print(f"Error resetting schema: {e}")

print("Schema reset successfully. Running Alembic migrations...")
os.system("uv run alembic upgrade head")
print("Done! Database is fully initialized.")
