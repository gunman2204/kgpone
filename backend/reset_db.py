import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")
print(f"Connecting to {url}...")
engine = create_engine(url)

with engine.begin() as conn:
    print("Dropping public schema...")
    conn.execute(text("DROP SCHEMA public CASCADE;"))
    print("Recreating public schema...")
    conn.execute(text("CREATE SCHEMA public;"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))

print("Schema reset successfully. Running Alembic migrations...")
os.system("uv run alembic upgrade head")
print("Done! Database is fully initialized.")
