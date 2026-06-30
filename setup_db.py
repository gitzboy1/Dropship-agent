"""
setup_db.py — Run this ONCE to create the dropship_db database on AlloyDB.
Usage:  python setup_db.py
        (requires ALLOYDB_HOST and ALLOYDB_PASSWORD env vars)
"""

import os
from dotenv import load_dotenv
load_dotenv()

import sys
import pg8000.native

HOST     = os.environ.get("ALLOYDB_HOST", input("AlloyDB Primary IP: ").strip())
PASSWORD = os.environ.get("ALLOYDB_PASSWORD", input("postgres password: ").strip())
PORT     = int(os.environ.get("ALLOYDB_PORT", 5432))

print(f"\nConnecting to {HOST}:{PORT} as postgres...")

try:
    # Connect to default 'postgres' database to create ours
    conn = pg8000.native.Connection(
        host=HOST,
        port=PORT,
        user="postgres",
        password=PASSWORD,
        database="postgres",
        ssl_context=None,
    )

    # Check if database already exists
    rows = conn.run("SELECT datname FROM pg_database WHERE datname='dropship_db'")
    if rows:
        print("Database 'dropship_db' already exists — skipping creation.")
    else:
        conn.run("CREATE DATABASE dropship_db")
        print("Created database: dropship_db")

    conn.close()

    # Now connect to dropship_db and enable extensions
    conn2 = pg8000.native.Connection(
        host=HOST,
        port=PORT,
        user="postgres",
        password=PASSWORD,
        database="dropship_db",
        ssl_context=None,
    )
    conn2.run("CREATE EXTENSION IF NOT EXISTS vector")
    conn2.run("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    print("Extensions enabled: pgvector, uuid-ossp")
    conn2.close()

    print("\nSetup complete! Now set these environment variables:")
    print(f"  ALLOYDB_HOST={HOST}")
    print(f"  ALLOYDB_PORT={PORT}")
    print(f"  ALLOYDB_DATABASE=dropship_db")
    print(f"  ALLOYDB_USER=postgres")
    print(f"  ALLOYDB_PASSWORD=<your password>")

except Exception as e:
    print(f"\nError: {e}")
    print("\nTroubleshooting:")
    print("  1. Make sure the AlloyDB instance is fully provisioned")
    print("  2. Check that your IP is allowlisted (Connectivity > Authorized Networks)")
    print("  3. For PSC networks, you may need to run this from a GCP VM in the same VPC")
    sys.exit(1)
