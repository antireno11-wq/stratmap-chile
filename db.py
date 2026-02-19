import os
from psycopg.rows import dict_row
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:

            # USERS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # USER PREFERENCES
            cur.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                industries TEXT[],
                regions TEXT[],
                companies TEXT[],
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

            # OPPORTUNITIES
            cur.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id SERIAL PRIMARY KEY,
                source TEXT,
                title TEXT,
                url TEXT UNIQUE,
                company TEXT,
                contractor TEXT,
                industry TEXT,
                region TEXT,
                phase TEXT,
                score INTEGER DEFAULT 0,
                entry TEXT,
                raw JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            """)

        conn.commit()
