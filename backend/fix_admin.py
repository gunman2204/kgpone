import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pwdlib import PasswordHash

load_dotenv()
url = os.getenv("DATABASE_URL")
engine = create_engine(url)

password_hash = PasswordHash.recommended()
hashed = password_hash.hash("admin123")

with engine.begin() as conn:
    conn.execute(text("UPDATE users SET hashed_password = :hash WHERE email = 'admin@kgpone.edu'"), {"hash": hashed})
    
print("Admin password updated to 'admin123'")
