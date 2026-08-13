"""Database configuration for the SRA V2 production domain."""

import os

import psycopg2


DB_CONFIG = {
    "host": os.getenv("SRA_V2_DB_HOST", "localhost"),
    "dbname": os.getenv("SRA_V2_DB_NAME", "sra_v2_db"),
    "user": os.getenv("SRA_V2_DB_USER", "sra_user"),
    "password": os.getenv("SRA_V2_DB_PASSWORD", ""),
    "port": int(os.getenv("SRA_V2_DB_PORT", "5432")),
}


def connect_database():
    """Create a transactional PostgreSQL connection to the SRA V2 database."""
    connection = psycopg2.connect(**DB_CONFIG)
    connection.autocommit = False
    return connection
