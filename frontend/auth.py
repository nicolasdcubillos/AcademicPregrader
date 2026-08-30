"""
Autenticación y auditoría basada en sesiones.

- Usuarios con rol admin (is_admin); contraseñas hasheadas (PBKDF2).
- Persistencia: PostgreSQL si existe PREGRADER_DB_URL (Azure); SQLite en local.
- Registro de eventos: accesos, IP, calificaciones y descargas para el dashboard.
- Primer ingreso: el usuario nuevo debe elegir su clave (must_change_password).
"""

import os
import sqlite3
import secrets
import string
import json
import datetime
import time
from functools import wraps
from pathlib import Path

from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

CONFIG_DIR = Path(os.environ.get("PREGRADER_CONFIG_DIR", str(Path(__file__).parent.parent / "backend")))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = CONFIG_DIR / "users.db"
SECRET_KEY_FILE = CONFIG_DIR / ".secret_key"

# Backend: PostgreSQL cuando hay PREGRADER_DB_URL (Azure), SQLite en local.
_DB_URL = os.environ.get("PREGRADER_DB_URL", "").strip()
_BACKEND = "postgres" if _DB_URL else "sqlite"
_NOW = "NOW()" if _BACKEND == "postgres" else "datetime('now')"
_DB_READY = False

if _BACKEND == "postgres":
    import psycopg2
    import psycopg2.extras


def _connect():
    if _BACKEND == "postgres":
        return psycopg2.connect(_DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    # Timeout evita errores de "database is locked" sobre disco local.
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _q(sql: str) -> str:
    """El código usa marcadores %s; se traducen a ? para SQLite."""
    return sql if _BACKEND == "postgres" else sql.replace("%s", "?")


def _rowdict(row):
    """Normaliza una fila a dict con timestamps como texto 'YYYY-MM-DD HH:MM:SS'."""
    if row is None:
        return None
    d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d


def _execute(sql: str, params=(), fetch=None):
    """Ejecuta una sentencia y hace commit. fetch: None|'one'|'all'|'rowcount'."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        if fetch == "one":
            result = _rowdict(cur.fetchone())
        elif fetch == "all":
            result = [_rowdict(r) for r in cur.fetchall()]
        elif fetch == "rowcount":
            result = cur.rowcount
        else:
            result = None
        conn.commit()
        return result
    finally:
        conn.close()


_DDL = {
    "sqlite": [
        """CREATE TABLE IF NOT EXISTS users (
                username             TEXT PRIMARY KEY,
                password_hash        TEXT NOT NULL,
                is_admin             INTEGER NOT NULL DEFAULT 0,
                is_blocked           INTEGER NOT NULL DEFAULT 0,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                course_id            INTEGER,
                created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                last_login           TEXT,
                last_seen            TEXT
            )""",
        """CREATE TABLE IF NOT EXISTS courses (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""",
        """CREATE TABLE IF NOT EXISTS course_students (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id       INTEGER NOT NULL,
                org_id          TEXT,
                campus_username TEXT,
                full_name       TEXT NOT NULL
            )""",
        """CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL DEFAULT (datetime('now')),
                username   TEXT,
                ip         TEXT,
                event_type TEXT NOT NULL,
                detail     TEXT
            )""",
        """CREATE TABLE IF NOT EXISTS user_config (
                username TEXT PRIMARY KEY,
                data     TEXT NOT NULL
            )""",
        """CREATE TABLE IF NOT EXISTS grading_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL,
                job_id        TEXT NOT NULL,
                label         TEXT,
                student_count INTEGER NOT NULL DEFAULT 0,
                results       TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(username, job_id)
            )""",
    ],
    "postgres": [
        """CREATE TABLE IF NOT EXISTS users (
                username             TEXT PRIMARY KEY,
                password_hash        TEXT NOT NULL,
                is_admin             INTEGER NOT NULL DEFAULT 0,
                is_blocked           INTEGER NOT NULL DEFAULT 0,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                course_id            INTEGER,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_login           TIMESTAMPTZ,
                last_seen            TIMESTAMPTZ
            )""",
        """CREATE TABLE IF NOT EXISTS courses (
                id         BIGSERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",
        """CREATE TABLE IF NOT EXISTS course_students (
                id              BIGSERIAL PRIMARY KEY,
                course_id       BIGINT NOT NULL,
                org_id          TEXT,
                campus_username TEXT,
                full_name       TEXT NOT NULL
            )""",
        """CREATE TABLE IF NOT EXISTS events (
                id         BIGSERIAL PRIMARY KEY,
                ts         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                username   TEXT,
                ip         TEXT,
                event_type TEXT NOT NULL,
                detail     TEXT
            )""",
        """CREATE TABLE IF NOT EXISTS user_config (
                username TEXT PRIMARY KEY,
                data     TEXT NOT NULL
            )""",
        """CREATE TABLE IF NOT EXISTS grading_history (
                id            BIGSERIAL PRIMARY KEY,
                username      TEXT NOT NULL,
                job_id        TEXT NOT NULL,
                label         TEXT,
                student_count INTEGER NOT NULL DEFAULT 0,
                results       TEXT NOT NULL,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(username, job_id)
            )""",
    ],
}


def init_db() -> None:
    global _DB_READY
    if _DB_READY:
        return
    conn = _connect()
    try:
        cur = conn.cursor()
        for stmt in _DDL[_BACKEND]:
            cur.execute(stmt)
        # Migración SQLite: agrega columnas nuevas si la tabla ya existía sin ellas.
        if _BACKEND == "sqlite":
            existing = {r["name"] for r in cur.execute("PRAGMA table_info(users)")}
            for col, ddl in (
                ("is_admin", "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"),
                ("is_blocked", "ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"),
                ("must_change_password", "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"),
                ("last_login", "ALTER TABLE users ADD COLUMN last_login TEXT"),
                ("last_seen", "ALTER TABLE users ADD COLUMN last_seen TEXT"),
                ("course_id", "ALTER TABLE users ADD COLUMN course_id INTEGER"),
            ):
                if col not in existing:
                    cur.execute(ddl)
        else:
            # Migración PostgreSQL: agrega la columna si el despliegue es previo a cursos.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS course_id INTEGER")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ")
        conn.commit()
        _DB_READY = True
    finally:
        conn.close()


def get_secret_key() -> str:
    """Clave de firma de sesión estable entre reinicios (env var o archivo persistido)."""
    env_key = os.environ.get("PREGRADER_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        os.chmod(SECRET_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


# ── Gestión de usuarios ──────────────────────────────────────────────────────

def generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def seed_admin_from_env() -> None:
    """Crea el admin inicial desde env vars si aún no existe (idempotente)."""
    user = os.environ.get("PREGRADER_ADMIN_USER", "").strip()
    pwd = os.environ.get("PREGRADER_ADMIN_PASSWORD", "").strip()
    if user and pwd and not get_user(user):
        create_user(user, pwd, is_admin=True, must_change=False)


def create_user(username: str, password: str, is_admin: bool = False, must_change: bool = False) -> None:
    username = username.strip().lower()
    if not username or not password:
        raise ValueError("Usuario y contraseña son obligatorios.")
    init_db()
    _execute(
        "INSERT INTO users (username, password_hash, is_admin, must_change_password) VALUES (%s, %s, %s, %s)",
        (username, generate_password_hash(password), 1 if is_admin else 0, 1 if must_change else 0),
    )


def set_password(username: str, password: str, clear_must_change: bool = True) -> bool:
    username = username.strip().lower()
    init_db()
    return _execute(
        "UPDATE users SET password_hash = %s, must_change_password = %s WHERE username = %s",
        (generate_password_hash(password), 0 if clear_must_change else 1, username),
        fetch="rowcount",
    ) > 0


def reset_password(username: str) -> str | None:
    """Asigna una clave temporal y fuerza el cambio en el próximo ingreso."""
    temp = generate_temp_password()
    if set_password(username, temp, clear_must_change=False):
        _execute(
            "UPDATE users SET must_change_password = 1 WHERE username = %s",
            (username.strip().lower(),),
        )
        return temp
    return None


def delete_user(username: str) -> bool:
    return _execute("DELETE FROM users WHERE username = %s", (username.strip().lower(),), fetch="rowcount") > 0


def set_blocked(username: str, blocked: bool) -> bool:
    return _execute(
        "UPDATE users SET is_blocked = %s WHERE username = %s",
        (1 if blocked else 0, username.strip().lower()),
        fetch="rowcount",
    ) > 0


def set_admin(username: str, is_admin: bool) -> bool:
    return _execute(
        "UPDATE users SET is_admin = %s WHERE username = %s",
        (1 if is_admin else 0, username.strip().lower()),
        fetch="rowcount",
    ) > 0


def get_user(username: str) -> dict | None:
    init_db()
    return _execute("SELECT * FROM users WHERE username = %s", (username.strip().lower(),), fetch="one")


def list_users() -> list[str]:
    init_db()
    rows = _execute("SELECT username FROM users ORDER BY username", fetch="all")
    return [r["username"] for r in rows]


def count_admins() -> int:
    init_db()
    row = _execute("SELECT COUNT(*) AS n FROM users WHERE is_admin = 1", fetch="one")
    return int(row["n"])


def authenticate(username: str, password: str) -> dict:
    """Devuelve {status: ok|bad|blocked, user: dict|None}."""
    user = get_user(username or "")
    if not user or not check_password_hash(user["password_hash"], password or ""):
        return {"status": "bad", "user": None}
    if user["is_blocked"]:
        return {"status": "blocked", "user": user}
    return {"status": "ok", "user": user}


def record_login(username: str) -> None:
    _execute(
        f"UPDATE users SET last_login = {_NOW} WHERE username = %s",
        (username.strip().lower(),),
    )


# Última vez (epoch, en memoria) que se guardó last_seen por usuario, para no
# escribir en la BD en cada request — con sesiones que no vuelven a autenticarse
# (cookie persistente) el login queda viejo aunque la persona siga usando la app.
_LAST_SEEN_WRITE: dict[str, float] = {}
_LAST_SEEN_THROTTLE_SECONDS = 60


def touch_last_seen(username: str | None) -> None:
    """Marca al usuario como visto ahora mismo (cualquier request autenticado cuenta
    como actividad), sin martillar la BD: como mucho una escritura por minuto/usuario."""
    if not username:
        return
    username = username.strip().lower()
    now = time.monotonic()
    last_write = _LAST_SEEN_WRITE.get(username, 0.0)
    if now - last_write < _LAST_SEEN_THROTTLE_SECONDS:
        return
    _LAST_SEEN_WRITE[username] = now
    _execute(
        f"UPDATE users SET last_seen = {_NOW} WHERE username = %s",
        (username,),
    )


# ── Configuración por usuario ────────────────────────────────────────────────

def get_user_config(username: str) -> dict:
    """Config personal del usuario (proveedor, modelo, pasos…). {} si no tiene."""
    init_db()
    row = _execute("SELECT data FROM user_config WHERE username = %s", (username.strip().lower(),), fetch="one")
    if not row:
        return {}
    try:
        return json.loads(row["data"])
    except (ValueError, TypeError):
        return {}


def save_user_config(username: str, data: dict) -> None:
    init_db()
    _execute(
        "INSERT INTO user_config (username, data) VALUES (%s, %s) "
        "ON CONFLICT(username) DO UPDATE SET data = excluded.data",
        (username.strip().lower(), json.dumps(data)),
    )


# ── Historial de calificaciones ───────────────────────────────────────────────
# Guarda, por calificador, el estado completo (tal cual quedó) de sus últimas
# corridas de calificación, para poder retomarlas desde cualquier navegador o PC.

MAX_HISTORY_PER_USER = 10


def _prune_grading_history(username: str) -> None:
    """Conserva solo las MAX_HISTORY_PER_USER entradas más recientes del usuario."""
    _execute(
        f"DELETE FROM grading_history WHERE username = %s AND id NOT IN ("
        f"  SELECT id FROM grading_history WHERE username = %s "
        f"  ORDER BY updated_at DESC, id DESC LIMIT {MAX_HISTORY_PER_USER}"
        f")",
        (username, username),
    )


def save_grading_history(username: str, job_id: str, label: str, results: list) -> None:
    """Crea o actualiza (upsert) el snapshot completo de una corrida de calificación."""
    init_db()
    username = username.strip().lower()
    payload = json.dumps(results, ensure_ascii=False)
    _execute(
        f"INSERT INTO grading_history (username, job_id, label, student_count, results, created_at, updated_at) "
        f"VALUES (%s, %s, %s, %s, %s, {_NOW}, {_NOW}) "
        f"ON CONFLICT(username, job_id) DO UPDATE SET "
        f"label = excluded.label, student_count = excluded.student_count, "
        f"results = excluded.results, updated_at = {_NOW}",
        (username, job_id, label, len(results), payload),
    )
    _prune_grading_history(username)


def update_grading_history_results(username: str, job_id: str, results: list) -> bool:
    """Actualiza solo los resultados (p.ej. notas/comentarios editados) de una
    entrada ya existente. No crea una nueva si no existía. Devuelve True si actualizó."""
    init_db()
    username = username.strip().lower()
    payload = json.dumps(results, ensure_ascii=False)
    rowcount = _execute(
        f"UPDATE grading_history SET results = %s, student_count = %s, updated_at = {_NOW} "
        f"WHERE username = %s AND job_id = %s",
        (payload, len(results), username, job_id),
        fetch="rowcount",
    )
    return bool(rowcount)


def get_grading_history(username: str) -> list[dict]:
    """Lista (metadatos, sin el contenido pesado) del historial del usuario, más reciente primero."""
    init_db()
    username = username.strip().lower()
    rows = _execute(
        "SELECT job_id, label, student_count, created_at, updated_at "
        "FROM grading_history WHERE username = %s ORDER BY updated_at DESC, id DESC "
        f"LIMIT {MAX_HISTORY_PER_USER}",
        (username,),
        fetch="all",
    )
    return rows or []


def get_grading_history_item(username: str, job_id: str) -> dict | None:
    """Snapshot completo (con resultados) de una entrada del historial del usuario."""
    init_db()
    username = username.strip().lower()
    row = _execute(
        "SELECT job_id, label, student_count, created_at, updated_at, results "
        "FROM grading_history WHERE username = %s AND job_id = %s",
        (username, job_id),
        fetch="one",
    )
    if not row:
        return None
    try:
        row["results"] = json.loads(row["results"])
    except (ValueError, TypeError):
        row["results"] = []
    return row


# ── Auditoría ────────────────────────────────────────────────────────────────

def log_event(username, ip, event_type: str, detail: str | None = None) -> None:
    init_db()
    _execute(
        "INSERT INTO events (username, ip, event_type, detail) VALUES (%s, %s, %s, %s)",
        (username, ip, event_type, detail),
    )


def get_events(limit: int = 200, username: str | None = None) -> list[dict]:
    init_db()
    if username:
        return _execute(
            "SELECT * FROM events WHERE username = %s ORDER BY id DESC LIMIT %s",
            (username.strip().lower(), limit),
            fetch="all",
        )
    return _execute("SELECT * FROM events ORDER BY id DESC LIMIT %s", (limit,), fetch="all")


def delete_events(event_types: list[str]) -> int:
    """Elimina los eventos de los tipos indicados. Devuelve cuántos borró."""
    init_db()
    if not event_types:
        return 0
    placeholders = ",".join(["%s"] * len(event_types))
    return _execute(
        f"DELETE FROM events WHERE event_type IN ({placeholders})",
        tuple(event_types),
        fetch="rowcount",
    )


def get_users_overview() -> list[dict]:
    """Usuarios con métricas agregadas para el dashboard."""
    init_db()
    users = _execute("SELECT * FROM users ORDER BY username", fetch="all")
    stats = _execute(
        "SELECT username, event_type, COUNT(*) AS n "
        "FROM events GROUP BY username, event_type",
        fetch="all",
    )
    # Última actividad real (cualquier evento: login, calificar, descargar…), no solo el
    # último login — una sesión puede seguir activa mucho después de haberse autenticado.
    last_activity_rows = _execute(
        "SELECT username, MAX(ts) AS last_activity FROM events "
        "WHERE username IS NOT NULL AND username != '' GROUP BY username",
        fetch="all",
    )
    activity_map = {r["username"]: r["last_activity"] for r in last_activity_rows}
    courses = {c["id"]: c["name"] for c in _execute("SELECT id, name FROM courses", fetch="all")}
    agg: dict[str, dict] = {}
    for s in stats:
        agg.setdefault(s["username"] or "", {})[s["event_type"]] = s["n"]
    result = []
    for row in users:
        u = dict(row)
        counts = agg.get(u["username"], {})
        u["login_count"] = counts.get("login", 0)
        u["grade_count"] = counts.get("grade_run", 0)
        u["download_count"] = counts.get("download_csv", 0) + counts.get("download_excel", 0)
        u["course_name"] = courses.get(u.get("course_id"))
        last_login = u.get("last_login") or ""
        last_seen = u.get("last_seen") or ""
        last_event = activity_map.get(u["username"]) or ""
        u["last_activity"] = max(last_login, last_seen, last_event) or None
        result.append(u)
    return result


# ── Cursos / clases ──────────────────────────────────────────────────────────

def create_course(name: str, created_by: str, students: list[dict]) -> int:
    """Crea un curso con su roster (lista de {name, username, org_id}). Devuelve el id."""
    init_db()
    conn = _connect()
    try:
        cur = conn.cursor()
        if _BACKEND == "postgres":
            cur.execute("INSERT INTO courses (name, created_by) VALUES (%s, %s) RETURNING id", (name, created_by))
            course_id = cur.fetchone()["id"]
        else:
            cur.execute("INSERT INTO courses (name, created_by) VALUES (?, ?)", (name, created_by))
            course_id = cur.lastrowid
        _insert_students(cur, course_id, students)
        conn.commit()
        return course_id
    finally:
        conn.close()


def _insert_students(cur, course_id: int, students: list[dict]) -> None:
    sql = _q(
        "INSERT INTO course_students (course_id, org_id, campus_username, full_name) "
        "VALUES (%s, %s, %s, %s)"
    )
    for s in students:
        name = (s.get("name") or "").strip()
        if not name:
            continue
        cur.execute(sql, (
            course_id,
            (s.get("org_id") or "").strip(),
            (s.get("username") or "").strip(),
            name,
        ))


def set_course_students(course_id: int, students: list[dict]) -> None:
    """Reemplaza por completo el roster de un curso."""
    init_db()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_q("DELETE FROM course_students WHERE course_id = %s"), (course_id,))
        _insert_students(cur, course_id, students)
        conn.commit()
    finally:
        conn.close()


def list_courses() -> list[dict]:
    """Cursos con número de estudiantes y calificadores asignados."""
    init_db()
    courses = _execute("SELECT * FROM courses ORDER BY name", fetch="all")
    counts = _execute(
        "SELECT course_id, COUNT(*) AS n FROM course_students GROUP BY course_id",
        fetch="all",
    )
    graders = _execute(
        "SELECT username, course_id FROM users WHERE course_id IS NOT NULL ORDER BY username",
        fetch="all",
    )
    cmap = {c["course_id"]: c["n"] for c in counts}
    gmap: dict[int, list[str]] = {}
    for g in graders:
        gmap.setdefault(g["course_id"], []).append(g["username"])
    for c in courses:
        c["student_count"] = cmap.get(c["id"], 0)
        c["graders"] = gmap.get(c["id"], [])
    return courses


def get_course(course_id: int) -> dict | None:
    init_db()
    return _execute("SELECT * FROM courses WHERE id = %s", (course_id,), fetch="one")


def get_course_students(course_id: int) -> list[dict]:
    init_db()
    return _execute(
        "SELECT * FROM course_students WHERE course_id = %s ORDER BY full_name",
        (course_id,),
        fetch="all",
    )


def delete_course(course_id: int) -> bool:
    init_db()
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_q("UPDATE users SET course_id = NULL WHERE course_id = %s"), (course_id,))
        cur.execute(_q("DELETE FROM course_students WHERE course_id = %s"), (course_id,))
        cur.execute(_q("DELETE FROM courses WHERE id = %s"), (course_id,))
        rc = cur.rowcount
        conn.commit()
        return rc > 0
    finally:
        conn.close()


def assign_user_course(username: str, course_id) -> bool:
    """Fija el curso activo del calificador (o lo quita con course_id=None)."""
    init_db()
    rc = _execute(
        "UPDATE users SET course_id = %s WHERE username = %s",
        (course_id, username.strip().lower()),
        fetch="rowcount",
    )
    return bool(rc)


def get_user_active_course(username: str) -> dict | None:
    """Devuelve el curso activo del usuario, o None."""
    user = get_user(username)
    if not user or not user.get("course_id"):
        return None
    return get_course(user["course_id"])


# ── Protección de rutas ──────────────────────────────────────────────────────

def _wants_html() -> bool:
    return "text/html" in request.headers.get("Accept", "")


def _deny():
    if _wants_html():
        return redirect(url_for("login", next=request.path))
    return jsonify({"error": "No autenticado."}), 401


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        username = session.get("user")
        if not username:
            return _deny()
        user = get_user(username)
        # Sesión inválida o bloqueada en caliente por un admin → fuera.
        if not user or user["is_blocked"]:
            session.clear()
            return _deny()
        # Fuerza el cambio de clave antes de usar el resto de la app.
        if user["must_change_password"] and request.endpoint not in ("change_password", "logout"):
            if _wants_html():
                return redirect(url_for("change_password"))
            return jsonify({"error": "Debes cambiar tu contraseña.", "must_change_password": True}), 403
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        user = get_user(session.get("user"))
        if not user or not user["is_admin"]:
            if _wants_html():
                return redirect(url_for("index"))
            return jsonify({"error": "Requiere permisos de administrador."}), 403
        return view(*args, **kwargs)
    return wrapped
