"""Auto-Moderator: scans chat for bad words, creates reports."""
import re, sqlite3, time, threading
from pathlib import Path

BAD_WORDS = [
    r'\b(fuck|shit|bitch|asshole|damn|dick|bastard|crap|piss|stupid|idiot|moron|dumb)\b',
    r'\b(дурак|идиот|дебил|урод|тварь|сука|бл[яѣ]|нах[уй]|пош[ёе]л|лох|мудак|коз[ёе]л|ублюдок|сволочь|г[ао]ндон)\b',
    r'\b(nigga|nigger|faggot|retard|slut|whore|cunt)\b',
    r'\b(убей|убью|сдохни|умри|kill yourself|kys)\b',
]

def scan_message(text):
    if not text: return []
    found = []
    for p in BAD_WORDS:
        found.extend(re.findall(p, text.lower(), re.IGNORECASE))
    return list(set(found))

class AutoModerator:
    def __init__(self, db_path):
        self.db_path = db_path
        self._running = False
        self._last_id = 0
        self._ensure_table()
        self._last_id = self._load_last_id()

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def _ensure_table(self):
        c = self._conn()
        c.execute("""CREATE TABLE IF NOT EXISTS moderation_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER, chat_id INTEGER, user_id INTEGER,
            user_login TEXT, message_text TEXT, found_words TEXT,
            status TEXT DEFAULT 'pending', created_at_ms INTEGER,
            resolved_by TEXT, resolved_at_ms INTEGER, action TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS moderation_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_message_id INTEGER NOT NULL DEFAULT 0)""")
        c.execute("INSERT OR IGNORE INTO moderation_state (id, last_message_id) VALUES (1, 0)")
        c.commit(); c.close()

    def _load_last_id(self):
        c = self._conn()
        row = c.execute("SELECT last_message_id FROM moderation_state WHERE id = 1").fetchone()
        c.close()
        return int(row["last_message_id"]) if row else 0

    def get_reports(self, status=None, limit=100):
        c = self._conn()
        q = "SELECT * FROM moderation_reports"
        if status: q += " WHERE status = ?"
        q += " ORDER BY created_at_ms DESC LIMIT ?"
        rows = c.execute(q, (status, limit) if status else (limit,)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def get_report(self, report_id):
        c = self._conn()
        row = c.execute("SELECT * FROM moderation_reports WHERE id = ?", (int(report_id),)).fetchone()
        c.close()
        return dict(row) if row else None

    def resolve(self, rid, action, admin_login):
        c = self._conn()
        c.execute("UPDATE moderation_reports SET status='resolved',resolved_by=?,resolved_at_ms=?,action=? WHERE id=?",
                  (admin_login, int(time.time()*1000), action, rid))
        c.commit(); c.close()

    def scan_new(self):
        c = self._conn()
        rows = c.execute(
            "SELECT m.id,m.chat_id,m.author_user_id,u.login,m.body_text FROM chat_messages m "
            "LEFT JOIN users u ON m.author_user_id=u.id WHERE m.id>? ORDER BY m.id LIMIT 100",
            (self._last_id,)).fetchall()
        for r in rows:
            words = scan_message(r['body_text'] or '')
            if words:
                ex = c.execute("SELECT id FROM moderation_reports WHERE message_id=?", (r['id'],)).fetchone()
                if not ex:
                    c.execute("INSERT INTO moderation_reports (message_id,chat_id,user_id,user_login,message_text,found_words,created_at_ms) VALUES (?,?,?,?,?,?,?)",
                              (r['id'],r['chat_id'],r['author_user_id'],r['login'],(r['body_text'] or '')[:200],','.join(words),int(time.time()*1000)))
            self._last_id = max(self._last_id, r['id'])
        c.execute("UPDATE moderation_state SET last_message_id = ? WHERE id = 1", (self._last_id,))
        c.commit(); c.close()

    def start(self, interval=10):
        if self._running: return
        self._running = True
        def loop():
            import logging
            logger = logging.getLogger("lc.auto_moderator")
            while self._running:
                try:
                    self.scan_new()
                except Exception as exc:
                    logger.warning("auto-moderator scan failed: %s", exc)
                time.sleep(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
