"""Seed test device users into the LC server database.
Run after server code is deployed, before first start.
"""
import os
import sys
import hashlib
import hmac
import secrets

# Add server root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 (matching server auth)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210000).hex()
    return f"pbkdf2_sha256$210000${salt}${digest}"

def seed():
    """Main seed function."""
    # Import server modules
    try:
        from app.db.bootstrap import DataBootstrap
        from app.db.migrate import apply_migrations
    except ImportError as e:
        print(f"ERROR: Cannot import server modules: {e}")
        print("Make sure you're running from the server directory with dependencies installed.")
        sys.exit(1)

    # Initialize database
    print("Initializing database...")
    db = DataBootstrap()
    apply_migrations(db)

    # Get connection from db
    conn = db.acquire() if hasattr(db, 'acquire') else db.conn
    cursor = conn.cursor() if hasattr(conn, 'cursor') else db

    # Create device user
    device_login = "device"
    device_password = "devicepass"
    hashed = hash_password(device_password)
    
    now_ms = 1700000000000
    cursor.execute(
        """INSERT OR IGNORE INTO users
           (login, password_hash, role, status, phone, registration_device_id, created_at_ms, updated_at_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_login, hashed, "user", "active", "+70000000001", "lc-device-01", now_ms, now_ms)
    )
    print(f"  User '{device_login}' created/verified (password: {device_password})")

    # Set access mode to open
    try:
        cursor.execute(
            "UPDATE mode_state SET access_mode = 'open', updated_at_ms = ? WHERE id = 1",
            (now_ms,)
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO mode_state (id, access_mode, updated_at_ms) VALUES (1, 'open', ?)",
                (now_ms,)
            )
        print("  Access mode set to 'open'")
    except Exception as e:
        print(f"  Warning: could not set access mode: {e}")

    # Commit
    try:
        conn.commit()
    except AttributeError:
        pass  # Auto-commit mode

    print("\nSeed complete!")
    print(f"  Login:    {device_login}")
    print(f"  Password: {device_password}")
    print(f"  Role:     user (active)")
    print(f"  Mode:     open")


if __name__ == "__main__":
    seed()
