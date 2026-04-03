# SQL Migrations

This directory contains ordered SQL migrations for the server SQLite schema.

Rules:

- file names are ordered lexicographically (`0001_*.sql`, `0002_*.sql`, ...);
- each migration is applied once and tracked in `schema_migrations`;
- migrations must be idempotent and safe for clean bootstrap.
