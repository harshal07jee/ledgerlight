"""
Pytest configuration for Ledgerlight Test Suite.
Defaults to local SQLite for isolated test execution when DATABASE_URL is unset.
When DATABASE_URL is explicitly set (e.g., in CI with a PostgreSQL service container),
that database is used.
"""
import os

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./ledgerlight.db"
