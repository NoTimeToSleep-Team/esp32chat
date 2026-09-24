"""Auto-moderation for chat messages.

Flow:
  1. text is normalised in two variants (cyrillic-oriented and latin-oriented)
     with leet digits, latin homoglyphs and ё/е folded in;
  2. the variants are matched against two word groups:
       * PROFANITY -> report reason "profanity" (mat + english swearing)
       * ABUSE     -> report reason "abuse" (insults + threats)
  3. on a hit a report is filed into the regular queue (``user_reports``) with
     ``source='auto'``, the matched words and a context excerpt: the flagged
     message plus 3 messages before and 3 after it.

Matching is intentionally tolerant: separators ("с-у-к-а"), letter masks
("л**х"), stretched vowels ("сссууккаа"), homoglyphs and leet ("$yka", "CYKA",
"sh1t") are all caught, while strict letter boundaries keep false positives low
("лохматый", "бляха", "нас укачало" must not match).

The detector never blocks or deletes a message: it only files a report, and a
moderator decides what happens next.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

from app.services.user_reports import UserReportsError, UserReportsService

LOGGER = logging.getLogger("lc.auto_moderation")

AUTO_REPORTER_LOGIN = "Авто-модерация"
AUTO_REPORTER_ID = 0
CONTEXT_BEFORE = 3
CONTEXT_AFTER = 3
MAX_EXCERPT_CHARS = 160
MAX_COMMENT_CHARS = 950
MIN_REAL_LETTERS = 2

_ZERO_WIDTH = "\u200c\u200d\u2060\ufeff"

# --- normalisation -----------------------------------------------------------

_ZERO_WIDTH = "\u200c\u200d\u2060\ufeff"

# Latin letters that visually replace cyrillic ones ($yka, CYKA, xyu).
_HOMOGLYPHS = {
    "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "i": "и", "k": "к",
    "m": "м", "o": "о", "p": "р", "t": "т", "x": "х", "y": "у", "q": "к",
    "j": "й", "u": "у", "d": "д", "g": "г", "r": "г", "s": "с", "v": "в",
    "w": "ш", "z": "з",
}

# --- dictionary --------------------------------------------------------------

PROFANITY_WORDS: tuple[str, ...] = (
    # ху- family
    "хуй", "хуя", "хуе", "хую", "хуи", "хуйня", "хуйню", "хуйло", "хули", "хуля",
    "нахуй", "нахуя", "нихуя", "охуел", "охуела", "охуело", "охуели",
    "захуя", "похуй", "похую", "похуел", "хуесос", "хуебень", "хуёвый",
    # пизд- family
    "пизд", "пизда", "пизду", "пизды", "пизде", "пиздец", "пиздеть",
    "пиздюля", "пиздюк", "спиздить", "спиздел", "пропиздеть",
    # бляд- family
    "бля", "блядь", "бляди", "блядям", "блядями", "блядьми", "блябуду",
    # еб- family
    "ебать", "ебал", "ебала", "ебало", "ебаный", "ебаная", "ебаное", "ебаные",
    "ебанутый", "ебанутая", "ебанат", "ебёт", "ебли", "ебись",
    "заебал", "заебала", "заебали", "уебал", "уебала", "наебать", "наебал",
    "наебалово", "доебать", "доебался", "выебал", "проебал", "поебать",
    "отъебись", "долбоеб", "долбоёб", "ебарь", "ебло",
    # сук- family
    "сук", "сука", "суки", "суке", "суку", "сукой", "сучка", "сучки", "сучку",
    "сучара", "сучило",
    # прочий мат
    "гандон", "гондон", "манда", "манду", "манде", "манды",
    "мудак", "мудака", "мудилы", "мудила",
    "пидор", "пидора", "пидоры", "пидорка", "пидарас",
    "залупа", "залуп",
    "шлюха", "шлюхи", "шлюхе", "шлюху", "шлюшонок",
    "ублюдок", "ублюдки",
    "дроч", "дрочу", "дрочить", "дрочила",
    # english swearing
    "fuck", "fucked", "fucker", "fucking", "motherfucker", "fucker",
    "shit", "shitty", "bullshit", "bitch", "asshole", "arsehole", "bastard",
    "cunt", "dick", "dickhead", "wanker", "slut", "whore",
    "nigger", "nigga", "faggot", "cocksucker",
)

ABUSE_WORDS: tuple[str, ...] = (
    # insults
    "дурак", "дураки", "дурачок", "дура",
    "идиот", "идиоты", "идиотка", "идиотский",
    "дебил", "дебилы", "дебильный", "дебильность",
    "кретин", "кретины", "кретинский",
    "даун", "дауны",
    "дегенерат", "дегенераты",
    "тупой", "тупая", "тупые", "тупица", "тупицы",
    "урод", "уроды", "уродливый", "уродина",
    "лох", "лохи", "лоха", "лошара", "лошок",
    "мразь", "мразота", "мрази",
    "тварь", "твари", "тварюга",
    "сволочь", "сволочи",
    "гнида", "гниды", "гнидой",
    "чмо", "чмошник", "чмырь",
    "быдло", "шваль", "швальня",
    "козёл", "козла", "козлы", "козлина",
    "подлец", "подонок", "подонки",
    "убогий", "ничтожество", "недоумок", "недоумки",
    "бездарь", "бездарность", "выродок", "выродки",
    "рак мозга", "ракмозга", "дебилоид",
    "трус", "крыса", "крысы",
    "казёл", "казлы",
    # threats
    "сдохни", "сдохните", "умри", "зарежу", "прирежу",
    "прикончу", "убью", "убей", "убейте", "прибью",
    "застрелю", "расстреляю",
    "kill yourself", "kill your self", "kys", "go die",
    # english insults
    "idiot", "idiots", "moron", "morons", "dumbass", "stupid", "dumb",
    "jerk", "jackass", "loser", "scum", "trash", "prick", "retard",
)

DEFAULT_WHITELIST: tuple[str, ...] = (
    "бляха", "бляшка", "блямба", "бляхин", "бляк", "бляшка",
)

# --- normalisation -----------------------------------------------------------


def normalize(text: str, *, cyrillic: bool = True) -> str:
    """Lower-case, fold ё/е and zero-width characters.

    ``cyrillic=True`` additionally maps latin homoglyphs to cyrillic
    ("$yka"/"CYKA" letters become cyrillic). Leet digits and symbols are NOT
    mapped here: they are treated as letter masks by the pattern builder, so
    "су4ка" matches "сучка" and "нах@й" matches "нахуй".
    """
    if not text:
        return ""
    out: list[str] = []
    for ch in text.lower():
        if ch in _ZERO_WIDTH:
            continue
        if cyrillic and "a" <= ch <= "z":
            out.append(_HOMOGLYPHS.get(ch, ch))
        else:
            out.append(ch)
    return "".join(out)


def _plain(text: str) -> str:
    """Lower-case text with only ё/е folded (no homoglyph mapping)."""
    return (text or "").lower().replace("ё", "е")


# --- matching ----------------------------------------------------------------

_LETTER_CLASS = r"0-9a-zа-яёіїєґ"
# Digits and symbol-leet ($4 @ ...) act as letter masks: "су4ка" ~ "сучка",
# "нах@й" ~ "нахуй", "sh1t" ~ "shit". The post-filter requires real letters.
_MASK = r"[*\-_.\d@$€°]"
_SEPARATORS = r"[\s\-_*.'’`·‒–—…]{0,2}"
_VOWELS = "аеиоуыэюя"


def _word_pattern(word: str) -> str:
    """Build a tolerant regex for one dictionary word.

    Letters can be separated by punctuation/spaces ("с-у-к-а"), replaced by a
    mask ("л**х", "нах@й", "sh1t") and stretched ("сссууккаа"). Strict letter
    boundaries on both sides keep matches inside real words out.
    """
    parts: list[str] = []
    for index, ch in enumerate(word):
        if ch == " ":
            parts.append(r"[\s\-_*.'’`·]{0,3}")
            continue
        letter = f"(?:{re.escape(ch)}|{_MASK}){{1,3}}"
        parts.append(letter)
        if index + 1 < len(word):
            parts.append(_SEPARATORS)
    body = "".join(parts)
    return f"(?<![{_LETTER_CLASS}]){body}(?![{_LETTER_CLASS}])"


def _compile(words: Iterable[str]) -> list[tuple[str, re.Pattern[str], str]]:
    """Compile entries as (word, pattern, target) with target in {cyr, lat}."""
    compiled: list[tuple[str, re.Pattern[str], str]] = []
    seen: set[str] = set()
    for word in words:
        clean = " ".join(str(word).split()).strip().lower()
        if len(clean) < 2 or clean in seen:
            continue
        seen.add(clean)
        has_cyr = bool(re.search(r"[а-яё]", clean))
        target = "cyr" if has_cyr else "lat"
        try:
            pattern = re.compile(_word_pattern(clean))
        except re.error:  # pragma: no cover - defensive
            LOGGER.warning("automod: bad pattern for %r", word)
            continue
        compiled.append((clean, pattern, target))
    return compiled


def _split_words(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[\s,;]+", value)
    return [p.strip() for p in parts if p.strip()]


def _mask_text(text: str, whitelist: Sequence[str]) -> str:
    """Replace whitelisted words with spaces (length preserving)."""
    if not whitelist:
        return text
    out = text
    for word in whitelist:
        clean = " ".join(str(word).split()).strip().lower()
        if len(clean) < 3:
            continue
        try:
            pattern = re.compile(_word_pattern(clean), re.IGNORECASE)
        except re.error:  # pragma: no cover - defensive
            continue
        out = pattern.sub(lambda m: " " * len(m.group(0)), out)
    return out


def _now_ms() -> int:
    return int(time.time() * 1000)


class AutoModerationService:
    """Word-list auto-moderation that files reports into the normal queue."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._reports = UserReportsService(db_path=self._db_path)
        self._cache: tuple[float, dict] | None = None
        self._groups_cache: tuple[tuple, list[tuple[str, re.Pattern[str], str]]] | None = None

    # ----- persistence -----

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def settings(self, *, fresh: bool = False) -> dict:
        if not fresh and self._cache is not None and time.time() - self._cache[0] < 5:
            return self._cache[1]
        row = self._read_settings()
        self._cache = (time.time(), row)
        return row

    def _read_settings(self) -> dict:
        connection = self._connect()
        try:
            try:
                row = connection.execute(
                    "SELECT enabled, extra_words, whitelist FROM auto_moderation_settings WHERE id = 1"
                ).fetchone()
            except sqlite3.OperationalError:
                LOGGER.warning("automod: settings table missing, defaulting to disabled")
                return {"enabled": False, "extra_words": "", "whitelist": ""}
        finally:
            connection.close()
        if row is None:
            return {"enabled": True, "extra_words": "", "whitelist": ""}
        return {
            "enabled": bool(row["enabled"]),
            "extra_words": str(row["extra_words"] or ""),
            "whitelist": str(row["whitelist"] or ""),
        }

    def update_settings(
        self,
        *,
        enabled: bool | None = None,
        extra_words: str | Sequence[str] | None = None,
        whitelist: str | Sequence[str] | None = None,
    ) -> dict:
        current = self.settings(fresh=True)

        def as_text(value: str | Sequence[str] | None, fallback: str) -> str:
            if value is None:
                return fallback
            if isinstance(value, str):
                return value.strip()
            return ", ".join(_split_words(" ".join(str(v) for v in value)))

        new_enabled = current["enabled"] if enabled is None else bool(enabled)
        new_extra = as_text(extra_words, current["extra_words"])
        new_white = as_text(whitelist, current["whitelist"])
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO auto_moderation_settings(id, enabled, extra_words, whitelist, updated_at_ms)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled = excluded.enabled,
                    extra_words = excluded.extra_words,
                    whitelist = excluded.whitelist,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (1 if new_enabled else 0, new_extra, new_white, _now_ms()),
            )
            connection.commit()
        finally:
            connection.close()
        return self.settings(fresh=True)

    # ----- dictionary -----

    @staticmethod
    def base_words() -> dict:
        return {"profanity": list(PROFANITY_WORDS), "abuse": list(ABUSE_WORDS)}

    def _entries(
        self,
        extra_words: Sequence[str],
    ) -> list[tuple[str, re.Pattern[str], str]]:
        signature = tuple(sorted(extra_words))
        if self._groups_cache is not None and self._groups_cache[0] == signature:
            return self._groups_cache[1]
        extra = [
            " ".join(str(word).split()).strip().lower()
            for word in extra_words
            if len(" ".join(str(word).split()).strip()) >= 2
        ]
        entries = _compile(PROFANITY_WORDS + tuple(extra) + ABUSE_WORDS)
        self._groups_cache = (signature, entries)
        return entries

    def _reason_for(self, matches: Sequence[dict]) -> str:
        return "abuse" if any(m["group"] == "abuse" for m in matches) else "profanity"

    # ----- scanning -----

    def scan(
        self,
        text: str,
        *,
        extra_words: Sequence[str] = (),
        whitelist: Sequence[str] = (),
    ) -> list[dict]:
        """Return the matched dictionary words with their group."""
        if not text or not text.strip():
            return []
        variants = {
            "cyr": normalize(text, cyrillic=True),
            "lat": _plain(normalize(text, cyrillic=False)),
        }
        white = list(whitelist) or list(DEFAULT_WHITELIST)
        variants = {key: _mask_text(value, white) for key, value in variants.items()}
        found: list[dict] = []
        seen: set[str] = set()
        for word, pattern, target in self._entries(extra_words):
            match = pattern.search(variants[target])
            if match is None:
                continue
            snippet = match.group(0)
            if sum(1 for ch in snippet if ch.isalpha()) < MIN_REAL_LETTERS:
                continue
            if word in seen:
                continue
            seen.add(word)
            found.append({"word": word, "group": self._group_of(word)})
        return found

    def _group_of(self, word: str) -> str:
        return "abuse" if word in ABUSE_SET else "profanity"

    # ----- report filing -----

    def _has_pending_auto_report(self, message_id: int) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM user_reports WHERE message_id = ? AND source = 'auto' AND status = 'pending' LIMIT 1",
                (int(message_id),),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        finally:
            connection.close()
        return row is not None

    def _context_lines(self, message) -> list[str]:
        connection = self._connect()
        try:
            try:
                before = connection.execute(
                    """
                    SELECT m.id, u.login, m.body_text
                    FROM chat_messages m
                    LEFT JOIN users u ON u.id = m.author_user_id
                    WHERE m.chat_id = ? AND m.id <= ?
                    ORDER BY m.id DESC
                    LIMIT ?
                    """,
                    (int(message.chat_id), int(message.message_id), CONTEXT_BEFORE + 1),
                ).fetchall()
                after = connection.execute(
                    """
                    SELECT m.id, u.login, m.body_text
                    FROM chat_messages m
                    LEFT JOIN users u ON u.id = m.author_user_id
                    WHERE m.chat_id = ? AND m.id > ?
                    ORDER BY m.id ASC
                    LIMIT ?
                    """,
                    (int(message.chat_id), int(message.message_id), CONTEXT_AFTER),
                ).fetchall()
            except sqlite3.OperationalError:
                LOGGER.warning("automod: cannot read message context")
                return []
        finally:
            connection.close()

        before = list(reversed(before))[-(CONTEXT_BEFORE + 1):]
        lines: list[str] = []
        for row in before:
            marker = ">> " if int(row["id"]) == int(message.message_id) else "   "
            text = " ".join(str(row["body_text"] or "").split())[:MAX_EXCERPT_CHARS]
            lines.append(f"{marker}{row['login'] or '?'}: {text}")
        for row in after:
            text = " ".join(str(row["body_text"] or "").split())[:MAX_EXCERPT_CHARS]
            lines.append(f"   {row['login'] or '?'}: {text}")
        return lines

    def _context_comment(self, message, matches: Sequence[dict]) -> str:
        words = ", ".join(m["word"] for m in matches)
        kind = "оскорбление/угроза" if any(m["group"] == "abuse" for m in matches) else "мат"
        header = f"Авто-модерация: {kind}\nСработавшие слова: {words}"
        lines = self._context_lines(message)
        if not lines:
            return header[:MAX_COMMENT_CHARS]
        body = f"Контекст ({CONTEXT_BEFORE} до / {CONTEXT_AFTER} после):\n" + "\n".join(lines)
        comment = f"{header}\n\n{body}"
        if len(comment) > MAX_COMMENT_CHARS:
            comment = comment[: MAX_COMMENT_CHARS - 1].rstrip() + "…"
        return comment

    def check_message(self, message) -> dict | None:
        """Scan one message and file a report when something is found."""
        settings = self.settings()
        if not settings.get("enabled"):
            return None
        extra = _split_words(settings.get("extra_words"))
        whitelist = _split_words(settings.get("whitelist")) or list(DEFAULT_WHITELIST)
        matches = self.scan(message.body_text or "", extra_words=extra, whitelist=whitelist)
        if not matches:
            return None
        if self._has_pending_auto_report(message.message_id):
            return None
        reason = self._reason_for(matches)
        try:
            report = self._reports.create_auto(
                target_user_id=int(message.author_user_id),
                target_login=message.author_login,
                reason=reason,
                matched_words=", ".join(m["word"] for m in matches),
                message_id=int(message.message_id),
                chat_id=int(message.chat_id),
                comment=self._context_comment(message, matches),
            )
        except UserReportsError as exc:
            LOGGER.warning("automod: cannot file report: %s", exc)
            return None
        LOGGER.info(
            "automod: report %s for message %s (%s)",
            report.get("id"),
            message.message_id,
            reason,
        )
        return report


ABUSE_SET = frozenset(" ".join(w.split()).lower() for w in ABUSE_WORDS)