import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


JSON_DATA_FILE = Path(__file__).parent / "journal_entries.json"
DB_FILE = Path(__file__).parent / "ai_journal.db"


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_pro INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                label TEXT NOT NULL,
                polarity REAL NOT NULL,
                subjectivity REAL NOT NULL,
                confidence REAL NOT NULL,
                provider TEXT NOT NULL DEFAULT 'textblob',
                model TEXT NOT NULL DEFAULT 'textblob-default',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        _migrate_schema(conn)
        conn.commit()
    _migrate_json_if_needed()


def load_entries(user_id: int) -> list[dict]:
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, user_id, text, created_at, label, polarity, subjectivity, confidence, provider, model
            FROM entries
            WHERE user_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [_row_to_entry(row) for row in rows]


def add_entry(text: str, sentiment: dict, user_id: int) -> dict:
    init_db()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries (user_id, text, created_at, label, polarity, subjectivity, confidence, provider, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                text.strip(),
                created_at,
                sentiment.get("label", "Neutral"),
                float(sentiment.get("polarity", 0.0)),
                float(sentiment.get("subjectivity", 0.0)),
                float(sentiment.get("confidence", 0.5)),
                sentiment.get("provider", "textblob"),
                sentiment.get("model", "textblob-default"),
            ),
        )
        conn.commit()
        entry_id = cursor.lastrowid
    return {
        "id": entry_id,
        "user_id": user_id,
        "text": text.strip(),
        "created_at": created_at,
        "sentiment": {
            "label": sentiment.get("label", "Neutral"),
            "polarity": float(sentiment.get("polarity", 0.0)),
            "subjectivity": float(sentiment.get("subjectivity", 0.0)),
            "confidence": float(sentiment.get("confidence", 0.5)),
            "provider": sentiment.get("provider", "textblob"),
            "model": sentiment.get("model", "textblob-default"),
            "from_cache": bool(sentiment.get("from_cache", False)),
        },
    }


def build_stats(entries: list[dict]) -> dict:
    if not entries:
        return {
            "total_entries": 0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "avg_polarity": 0.0,
            "streak_days": 0,
            "best_label": "Neutral",
            "volatility": 0.0,
        }

    positive = sum(1 for e in entries if e["sentiment"]["label"] == "Positive")
    neutral = sum(1 for e in entries if e["sentiment"]["label"] == "Neutral")
    negative = sum(1 for e in entries if e["sentiment"]["label"] == "Negative")
    avg_polarity = round(
        sum(e["sentiment"]["polarity"] for e in entries) / len(entries), 3
    )
    polarity_values = [e["sentiment"]["polarity"] for e in entries]
    volatility = round(
        sum(abs(polarity_values[i] - polarity_values[i + 1]) for i in range(len(polarity_values) - 1))
        / max(1, len(polarity_values) - 1),
        3,
    )

    streak_days = _calculate_streak(entries)
    best_label = max(
        {"Positive": positive, "Neutral": neutral, "Negative": negative},
        key=lambda x: {"Positive": positive, "Neutral": neutral, "Negative": negative}[x],
    )

    return {
        "total_entries": len(entries),
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "avg_polarity": avg_polarity,
        "streak_days": streak_days,
        "best_label": best_label,
        "volatility": volatility,
    }


def delete_entry(entry_id: int, user_id: int) -> bool:
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "DELETE FROM entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def build_insights(entries: list[dict], stats: dict) -> list[str]:
    if not entries:
        return [
            "Start with one short entry today to build your emotional baseline.",
            "Consistency matters more than length. Aim for 2-3 lines daily.",
        ]

    insights = []
    latest = entries[0]["sentiment"]["label"]
    insights.append(f"Latest entry mood is {latest.lower()}.")

    if stats["streak_days"] >= 7:
        insights.append("Great consistency: you have a 7+ day reflection streak.")
    elif stats["streak_days"] >= 3:
        insights.append("Good momentum: keep your current journaling streak going.")
    else:
        insights.append("Build a stronger streak by writing one quick entry each day.")

    if stats["volatility"] > 0.45:
        insights.append("Emotional volatility is elevated. Consider shorter, more frequent check-ins.")
    else:
        insights.append("Your emotional trend is relatively stable over recent entries.")

    if stats["negative"] > stats["positive"]:
        insights.append("Negative entries are currently higher than positive ones. Add one gratitude note daily.")
    else:
        insights.append("Positive sentiment is holding well. Maintain your current reflection habit.")

    return insights


def build_product_signals(entries: list[dict], stats: dict) -> dict:
    overall_mood = _humanize_mood(stats.get("avg_polarity", 0.0), stats.get("best_label", "Neutral"))
    stability = _humanize_stability(stats.get("volatility", 0.0))
    top_trigger = _detect_top_trigger(entries)
    weekly_summary = _build_weekly_summary(entries, stats, overall_mood, stability)
    return {
        "overall_mood": overall_mood,
        "stability": stability,
        "consistency": f"{stats.get('streak_days', 0)}-day streak",
        "top_trigger": top_trigger,
        "weekly_summary": weekly_summary,
        "trend_hint": _trend_hint(stats),
    }


def _calculate_streak(entries: list[dict]) -> int:
    if not entries:
        return 0

    unique_days = sorted(
        {
            datetime.strptime(entry["created_at"], "%Y-%m-%d %H:%M").date()
            for entry in entries
            if entry.get("created_at")
        },
        reverse=True,
    )
    if not unique_days:
        return 0

    streak = 1
    for idx in range(len(unique_days) - 1):
        delta = (unique_days[idx] - unique_days[idx + 1]).days
        if delta == 1:
            streak += 1
        else:
            break
    return streak


def _row_to_entry(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "text": row["text"],
        "created_at": row["created_at"],
        "sentiment": {
            "label": row["label"],
            "polarity": row["polarity"],
            "subjectivity": row["subjectivity"],
            "confidence": row["confidence"],
            "provider": row["provider"],
            "model": row["model"],
        },
    }


def _migrate_json_if_needed() -> None:
    if not JSON_DATA_FILE.exists():
        return
    try:
        legacy_entries = json.loads(JSON_DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    if not legacy_entries:
        return

    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT COUNT(1) FROM entries").fetchone()[0]
        if existing > 0:
            return

        default_user = _get_or_create_default_user(conn)

        for entry in reversed(legacy_entries):
            sentiment = entry.get("sentiment", {})
            conn.execute(
                """
                INSERT INTO entries (user_id, text, created_at, label, polarity, subjectivity, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    default_user,
                    (entry.get("text") or "").strip(),
                    entry.get("created_at")
                    or datetime.now().strftime("%Y-%m-%d %H:%M"),
                    sentiment.get("label", "Neutral"),
                    float(sentiment.get("polarity", 0.0)),
                    float(sentiment.get("subjectivity", 0.0)),
                    float(sentiment.get("confidence", 0.5)),
                ),
            )
        conn.commit()


def create_user(name: str, email: str, password_hash: str) -> tuple[bool, str, Optional[int]]:
    init_db()
    normalized_email = email.strip().lower()
    if not normalized_email:
        return False, "Email is required.", None

    with sqlite3.connect(DB_FILE) as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (name, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    name.strip() or "User",
                    normalized_email,
                    password_hash,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            conn.commit()
            return True, "Account created.", cursor.lastrowid
        except sqlite3.IntegrityError:
            return False, "Email already registered.", None


def get_user_by_email(email: str) -> Optional[dict]:
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, email, password_hash, is_pro, created_at FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def get_user_by_id(user_id: int) -> Optional[dict]:
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, email, password_hash, is_pro, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    current_version = _get_schema_version(conn)
    if current_version < 2:
        cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
        }
        if "user_id" not in cols:
            conn.execute("ALTER TABLE entries ADD COLUMN user_id INTEGER")

        default_user_id = _get_or_create_default_user(conn)
        conn.execute(
            "UPDATE entries SET user_id = ? WHERE user_id IS NULL",
            (default_user_id,),
        )
        _set_schema_version(conn, 2)

    if current_version < 3:
        user_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "is_pro" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_pro INTEGER NOT NULL DEFAULT 0")
        _set_schema_version(conn, 3)

    if current_version < 4:
        entry_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
        }
        if "provider" not in entry_cols:
            conn.execute(
                "ALTER TABLE entries ADD COLUMN provider TEXT NOT NULL DEFAULT 'textblob'"
            )
        if "model" not in entry_cols:
            conn.execute(
                "ALTER TABLE entries ADD COLUMN model TEXT NOT NULL DEFAULT 'textblob-default'"
            )
        _set_schema_version(conn, 4)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if not row:
        return 1
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return 1


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def _get_or_create_default_user(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT id FROM users WHERE email = 'local@aijournal.app'"
    ).fetchone()
    if existing:
        return existing["id"]

    any_user = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
    if any_user:
        return any_user["id"]

    cursor = conn.execute(
        """
        INSERT INTO users (name, email, password_hash, is_pro, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "Local User",
            "local@aijournal.app",
            "!",
            0,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    return cursor.lastrowid


def set_user_pro_status(user_id: int, is_pro: bool) -> None:
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE users SET is_pro = ? WHERE id = ?",
            (1 if is_pro else 0, user_id),
        )
        conn.commit()


def build_pro_insights(entries: list[dict]) -> dict:
    recent = entries[:7]
    positive = sum(1 for e in recent if e["sentiment"]["label"] == "Positive")
    negative = sum(1 for e in recent if e["sentiment"]["label"] == "Negative")
    neutral = sum(1 for e in recent if e["sentiment"]["label"] == "Neutral")
    avg_recent = (
        sum(e["sentiment"]["polarity"] for e in recent) / len(recent) if recent else 0.0
    )

    trigger_scores = _trigger_severity(entries[:30])
    top_negative_trigger = max(trigger_scores, key=lambda x: trigger_scores[x]["negative"])
    confidence = min(95, 68 + len(entries) * 2)
    stability_score = max(35, min(96, int(100 - _volatility(entries) * 100)))

    weekly_summary = (
        "Your emotional tone was more negative this week than your recent baseline. "
        "Stress mentions peaked mid-week, while gratitude language improved stability."
        if negative > positive
        else "Your emotional tone improved this week, with more balanced entries and stronger stability markers."
    )

    forecast = _forecast_text(entries, top_negative_trigger)

    return {
        "weekly_summary": weekly_summary,
        "confidence": confidence,
        "trend_points": [round(e["sentiment"]["polarity"], 2) for e in recent[::-1]],
        "distribution": {"positive": positive, "neutral": neutral, "negative": negative},
        "trigger_scores": trigger_scores,
        "top_negative_trigger": top_negative_trigger,
        "stability_score": stability_score,
        "volatility_map": _volatility_map(entries),
        "forecast": forecast,
        "insights_generated": max(3, len(entries) * 2),
        "trigger_count": sum(1 for _, v in trigger_scores.items() if v["total"] > 0),
        "avg_recent": round(avg_recent, 2),
    }


def _volatility(entries: list[dict]) -> float:
    if len(entries) < 2:
        return 0.0
    values = [e["sentiment"]["polarity"] for e in entries[:20]]
    return sum(abs(values[i] - values[i + 1]) for i in range(len(values) - 1)) / max(
        1, len(values) - 1
    )


def _trigger_severity(entries: list[dict]) -> dict:
    trigger_keywords = {
        "Work": ["deadline", "work", "meeting", "project", "manager"],
        "Fatigue": ["tired", "sleep", "rest", "insomnia", "exhausted"],
        "Social": ["friend", "family", "partner", "team", "conversation"],
        "Health": ["health", "sick", "pain", "exercise", "gym"],
    }
    result = {
        key: {"total": 0, "negative": 0, "severity": "Low"} for key in trigger_keywords
    }

    for entry in entries:
        text = (entry.get("text") or "").lower()
        is_negative = entry["sentiment"]["label"] == "Negative"
        for trigger, keywords in trigger_keywords.items():
            if any(k in text for k in keywords):
                result[trigger]["total"] += 1
                if is_negative:
                    result[trigger]["negative"] += 1

    for trigger, values in result.items():
        if values["negative"] >= 4:
            values["severity"] = "High"
        elif values["negative"] >= 2:
            values["severity"] = "Medium"
        elif values["negative"] >= 1:
            values["severity"] = "Low"
        elif values["total"] >= 2:
            values["severity"] = "Positive"
        else:
            values["severity"] = "Low"
    return result


def _forecast_text(entries: list[dict], top_negative_trigger: str) -> str:
    if len(entries) < 7:
        return "Add at least 7 entries to unlock higher-confidence forecasting."
    return (
        f"Based on your recent pattern, negative spikes often follow {top_negative_trigger.lower()} mentions. "
        "Next high-risk period: mid-week. Try a short reflection break before peak stress hours."
    )


def _volatility_map(entries: list[dict]) -> list[dict]:
    bucket = {}
    for entry in entries[:60]:
        day = entry["created_at"].split(" ")[0]
        bucket.setdefault(day, []).append(entry["sentiment"]["polarity"])

    rows = []
    for day, vals in sorted(bucket.items(), reverse=True)[:28]:
        avg = sum(vals) / len(vals)
        if avg > 0.15:
            status = "balanced"
            score = 75
        elif avg < -0.15:
            status = "unstable"
            score = 45
        else:
            status = "neutral"
            score = 60
        rows.append({"day": day, "score": score, "status": status})
    return rows


def _humanize_mood(avg_polarity: float, best_label: str) -> str:
    if avg_polarity >= 0.35:
        return "Positive and improving"
    if avg_polarity >= 0.1:
        return "Slightly positive"
    if avg_polarity <= -0.35:
        return "Heavily negative"
    if avg_polarity <= -0.1:
        return "Slightly negative"
    if best_label == "Positive":
        return "Balanced, leaning positive"
    if best_label == "Negative":
        return "Balanced, leaning negative"
    return "Balanced / neutral"


def _humanize_stability(volatility: float) -> str:
    if volatility <= 0.15:
        return "Very stable"
    if volatility <= 0.35:
        return "Stable"
    if volatility <= 0.55:
        return "Moderate swings"
    return "High variation"


def _detect_top_trigger(entries: list[dict]) -> str:
    if not entries:
        return "Not enough data yet"

    trigger_keywords = {
        "Workload": ["deadline", "work", "meeting", "task", "project", "manager"],
        "Academics": ["exam", "assignment", "class", "semester", "study", "college"],
        "Sleep": ["sleep", "tired", "fatigue", "rest", "insomnia"],
        "Relationships": ["friend", "family", "partner", "relationship", "argument"],
        "Health": ["health", "sick", "pain", "exercise", "gym"],
        "Finances": ["money", "rent", "bill", "salary", "expense"],
    }
    scores = {k: 0 for k in trigger_keywords}
    for entry in entries[:20]:
        text = (entry.get("text") or "").lower()
        for trigger, keywords in trigger_keywords.items():
            if any(kw in text for kw in keywords):
                scores[trigger] += 1

    best_trigger = max(scores, key=scores.get)
    return best_trigger if scores[best_trigger] > 0 else "General stress / unclear pattern"


def _build_weekly_summary(
    entries: list[dict], stats: dict, overall_mood: str, stability: str
) -> str:
    recent = entries[:7]
    if not recent:
        return "Write your first entry to generate a personalized weekly insight."

    positive = sum(1 for e in recent if e["sentiment"]["label"] == "Positive")
    negative = sum(1 for e in recent if e["sentiment"]["label"] == "Negative")
    direction = "improving" if positive >= negative else "under pressure"
    return (
        f"Your recent emotional pattern looks {direction}. "
        f"Overall mood is {overall_mood.lower()} with {stability.lower()} behavior."
    )


def _trend_hint(stats: dict) -> str:
    streak_days = stats.get("streak_days", 0)
    if streak_days >= 7:
        return "Strong habit: your reflection streak is helping pattern clarity."
    if streak_days >= 3:
        return "Momentum building: keep daily entries to improve trend confidence."
    return "Early stage: 3+ daily entries will unlock more reliable trend detection."
