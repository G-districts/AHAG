import sys
import collections
from OpenSSL import crypto
import base64

# =========================
# Patch collections for hyper/apns2 compatibility
# =========================
if sys.version_info >= (3, 3):
    import collections.abc
    collections.Iterable = collections.abc.Iterable
    collections.Mapping = collections.abc.Mapping
    collections.MutableSet = collections.abc.MutableSet
    collections.MutableMapping = collections.abc.MutableMapping

# Now import everything else
from flask import Flask, request, jsonify, render_template, session, redirect, Response, url_for
from flask_cors import CORS
import json, os, time, sqlite3, traceback, uuid, re
from urllib.parse import urlparse
import random, time, hashlib
from datetime import datetime, time as dt_time
from collections import defaultdict
from image_filter_ai import classify_image as _gschool_classify_image
import jwt
from functools import wraps
import plistlib
from apns_mdm import send_mdm_push
from apns2.client import APNsClient
from apns2.payload import Payload

# ---------------------------
# Flask App Initialization
# ---------------------------
app = Flask(__name__, static_url_path="/static", static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Register AI blueprint (AI category classifier & chat)
try:
    from ai_routes import ai as ai_blueprint
    app.register_blueprint(ai_blueprint)
except Exception as e:
    print("[WARN] Failed to register AI blueprint:", e)


def _ice_servers():
    # Always include Google STUN
    servers = [{"urls": ["stun:stun.l.google.com:19302"]}]
    # Optional TURN from env
    turn_url = os.environ.get("TURN_URL")
    turn_user = os.environ.get("TURN_USER")
    turn_pass = os.environ.get("TURN_PASS")
    if turn_url and turn_user and turn_pass:
        servers.append({
            "urls": [turn_url],
            "username": turn_user,
            "credential": turn_pass
        })
    return servers


ROOT = os.path.dirname(__file__)
DATA_PATH = os.path.join(ROOT, "data.json")
DB_PATH = os.path.join(ROOT, "gschool.db")
SCENES_PATH = os.path.join(ROOT, "scenes.json")


# =========================
# Load APNS Certificate Safely
# =========================
def get_apns_cert_uuid():
    """Returns a valid APNS certificate UUID or fallback."""
    P12_PATH = os.path.join(ROOT, "mdm_identity.p12")
    P12_PASSWORD = b"supersecret"

    if not os.path.exists(P12_PATH):
        print("[WARN] APNS P12 file not found at", P12_PATH)
        return "00000000-0000-0000-0000-000000000000"  # fallback dummy UUID

    try:
        with open(P12_PATH, "rb") as f:
            p12_data = f.read()
        p12 = crypto.load_pkcs12(p12_data, P12_PASSWORD)
        cert = p12.get_certificate()
        uuid_val = str(uuid.uuid5(uuid.NAMESPACE_DNS, cert.get_subject().CN)).upper()
        return uuid_val
    except Exception as e:
        print("[WARN] Failed to load APNS certificate:", e)
        return "00000000-0000-0000-0000-000000000000"  # fallback dummy UUID

# These can be reused anywhere in the app
APNS_CERT_UUID = get_apns_cert_uuid()
APNS_TOPIC = "com.apple.mgmt.External.9507ef8f-dcbb-483e-89db-298d5471c6c1"

# Optional: initialize APNs client lazily (on first push)
apns_client = None
def get_apns_client():
    global apns_client
    if apns_client is None:
        try:
            apns_client = APNsClient(
                os.path.join(ROOT, "mdm_identity.p12"),
                use_sandbox=False,
                use_alternative_port=False
            )
        except Exception as e:
            print("[WARN] Failed to initialize APNs client:", e)
            apns_client = None
    return apns_client

# =========================
# Helpers: Data & Database
# =========================
def _clean_expired_bypass_codes(settings):
    now = time.time()
    settings["bypass_codes"] = [
        c for c in settings.get("bypass_codes", []) if c["expires"] > now
    ]

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()

def _clean_expired_bypass_codes(settings: dict):
    now = time.time()
    codes = settings.get("bypass_codes", [])
    settings["bypass_codes"] = [
        c for c in codes
        if c.get("expires", 0) > now
    ]

def db():
    """Open sqlite connection (row factory stays default to keep light)."""
    con = sqlite3.connect(DB_PATH)
    return con

def _init_db():
    """Create tables if missing; repair structure when possible."""
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            k TEXT PRIMARY KEY,
            v TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            role TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT,
            user_id TEXT,
            role TEXT,
            text TEXT,
            ts INTEGER
        );
    """)
    con.commit()
    con.close()

_init_db()

def _safe_default_data():
    return {
        "settings": {"chat_enabled": False},
        "classes": {
            "period1": {
                "name": "Period 1",
                "active": False,
                "focus_mode": False,
                "paused": False,
                "allowlist": [],
                "teacher_blocks": [],
                "students": [],
                "owner": None,
                "schedule": {}
            }
        },
        "categories": {},
        "pending_commands": {},
        "pending_per_student": {},
        "presence": {},
        "history": {},
        "screenshots": {},
        "dm": {},
        "alerts": [],
        "audit": []
    }

def _coerce_to_dict(obj):
    """If file accidentally became a list or invalid type, coerce to default dict."""
    if isinstance(obj, dict):
        return obj
    # Attempt to stitch a list of dict fragments
    if isinstance(obj, list):
        d = _safe_default_data()
        for item in obj:
            if isinstance(item, dict):
                d.update(item)
        return d
    return _safe_default_data()

def load_data():
    """Load JSON with self-repair for common corruption patterns."""
    if not os.path.exists(DATA_PATH):
        d = _safe_default_data()
        save_data(d)
        return d
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return ensure_keys(_coerce_to_dict(obj))
    except json.JSONDecodeError as e:
        # Try simple auto-repair: merge stray blocks like "} {"
        try:
            text = open(DATA_PATH, "r", encoding="utf-8").read().strip()
            # Fix common '}{' issues
            text = re.sub(r"}\s*{", "},{", text)
            if not text.startswith("["):
                text = "[" + text
            if not text.endswith("]"):
                text = text + "]"
            arr = json.loads(text)
            obj = _coerce_to_dict(arr)
            save_data(obj)
            return ensure_keys(obj)
        except Exception:
            print("[FATAL] data.json unrecoverable; starting fresh:", e)
            obj = _safe_default_data()
            save_data(obj)
            return obj
    except Exception as e:
        print("[WARN] load_data failed; using defaults:", e)
        return ensure_keys(_safe_default_data())

def save_data(d):
    d = ensure_keys(_coerce_to_dict(d))
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)

def get_setting(key, default=None):
    con = db(); cur = con.cursor()
    cur.execute("SELECT v FROM settings WHERE k=?", (key,))
    row = cur.fetchone()
    con.close()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return row[0]

def set_setting(key, value):
    con = db(); cur = con.cursor()
    cur.execute("REPLACE INTO settings (k, v) VALUES (?,?)", (key, json.dumps(value)))
    con.commit(); con.close()

def current_user():
    return session.get("user")


def ensure_keys(d):
    d.setdefault("settings", {}).setdefault("chat_enabled", False)

    # Ensure classes dict exists and normalize all class sessions.
    classes = d.setdefault("classes", {})
    classes.setdefault(
        "period1",
        {
            "name": "Period 1",
            "active": False,
            "focus_mode": False,
            "paused": False,
            "allowlist": [],
            "teacher_blocks": [],
            "students": [],
            "owner": None,
            "schedule": {},
        },
    )

    # Normalize every class object and student email list.
    for cid, cls in list(classes.items()):
        if not isinstance(cls, dict):
            classes[cid] = {
                "name": str(cls),
                "active": False,
                "focus_mode": False,
                "paused": False,
                "allowlist": [],
                "teacher_blocks": [],
                "students": [],
                "owner": None,
                "schedule": {},
            }
            cls = classes[cid]

        cls.setdefault("name", cid)
        cls.setdefault("active", False)
        cls.setdefault("focus_mode", False)
        cls.setdefault("paused", False)
        cls.setdefault("allowlist", [])
        cls.setdefault("teacher_blocks", [])
        cls.setdefault("students", [])
        cls.setdefault("owner", None)
        cls.setdefault("schedule", {})

        # Normalize student email list for this class (strip + lowercase).
        norm_students = []
        for s in cls.get("students") or []:
            if not s:
                continue
            s_norm = str(s).strip().lower()
            if s_norm and "@" in s_norm:
                norm_students.append(s_norm)
        cls["students"] = norm_students

    # Core collections
    d.setdefault("categories", {})
    d.setdefault("pending_commands", {})
    d.setdefault("pending_per_student", {})
    d.setdefault("student_scenes", {})
    d.setdefault("class_scenes", {})
    d.setdefault("presence", {})
    d.setdefault("history", {})
    d.setdefault("screenshots", {})
    d.setdefault("alerts", [])
    d.setdefault("dm", {})
    d.setdefault("audit", [])

    # Policy system
    #   policies:           id -> policy object
    #   policy_assignments: { "users": {email: policy_id}, "groups": {group: policy_id} }
    #   default_policy_id:  policy to use when user has no explicit group/user policy
    d.setdefault("policies", {})
    d.setdefault("policy_assignments", {}).setdefault("users", {})
    d.setdefault("policy_assignments", {}).setdefault("groups", {})
    d.setdefault("default_policy_id", None)

    # Feature flags
    d.setdefault("extension_enabled", True)
    return d

def log_action(entry):
    try:
        d = ensure_keys(load_data())
        log = d.setdefault("audit", [])
        entry = dict(entry or {})
        entry["ts"] = int(time.time())
        log.append(entry)
        d["audit"] = log[-500:]
        save_data(d)
    except Exception:
        pass


# =========================
# Guest handling helper
# =========================
_GUEST_TOKENS = ("guest", "anon", "anonymous", "trial", "temp")

def _is_guest_identity(email: str, name: str) -> bool:
    """Heuristic: treat empty email or names/emails containing guest-like tokens as guest."""
    e = (email or "").strip().lower()
    n = (name or "").strip().lower()
    if not e:
        return True
    if any(t in e for t in _GUEST_TOKENS):
        return True
    if any(t in n for t in _GUEST_TOKENS):
        return True
    return False
#=========================
# Parental control
#=========================


# =========================
# GPROTECT - PARENT CONTROLS
# =========================

# Add these imports at the top of app.py if not already present
# JWT secret for parent tokens (add to top of file)
PARENT_JWT_SECRET = os.environ.get("PARENT_JWT_SECRET", "gprotect_secret_key_change_in_production")

def parent_required(f):
    """Decorator to require parent authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        try:
            data = jwt.decode(token, PARENT_JWT_SECRET, algorithms=["HS256"])
            request.parent_email = data.get('email')
        except Exception:
            return jsonify({"ok": False, "error": "invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def _ensure_gprotect_structure(d):
    """Ensure GProtect data structure exists"""
    d.setdefault("gprotect", {
        "parents": {},  # email -> {password, children: [emails], settings}
        "children": {},  # child_email -> parent_email
        "schedules": {},  # child_email -> schedule config
        "ai_categories": {},  # child_email -> {category_name: blocked}
        "manual_blocks": {},  # child_email -> [urls]
        "manual_allows": {},  # child_email -> [urls]
        "active_sessions": {},  # child_email -> current active restrictions
        "mdm_tokens": {},  # child_email -> iOS MDM token
        "logs": []  # activity logs
    })
    return d

# =========================
# Parent Authentication
# =========================

@app.route("/gprotect/parent/register", methods=["POST"])
def gprotect_parent_register():
    """Register a new parent account"""
    body = request.json or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name = (body.get("name") or "").strip()
    
    if not email or not password or len(password) < 6:
        return jsonify({"ok": False, "error": "Invalid email or password too short"}), 400
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    if email in d["gprotect"]["parents"]:
        return jsonify({"ok": False, "error": "Parent already exists"}), 400
    
    d["gprotect"]["parents"][email] = {
        "password": password,  # In production, use bcrypt!
        "name": name,
        "children": [],
        "created_at": int(time.time())
    }
    
    save_data(d)
    
    token = jwt.encode({"email": email, "exp": int(time.time()) + 86400 * 30}, PARENT_JWT_SECRET, algorithm="HS256")
    
    log_action({"event": "gprotect_parent_register", "email": email})
    return jsonify({"ok": True, "token": token, "email": email, "name": name})

@app.route("/gprotect/parent/login", methods=["POST"])
def gprotect_parent_login():
    """Parent login"""
    body = request.json or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    parent = d["gprotect"]["parents"].get(email)
    if not parent or parent.get("password") != password:
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401
    
    token = jwt.encode({"email": email, "exp": int(time.time()) + 86400 * 30}, PARENT_JWT_SECRET, algorithm="HS256")
    
    return jsonify({
        "ok": True,
        "token": token,
        "email": email,
        "name": parent.get("name", ""),
        "children": parent.get("children", [])
    })

# =========================
# Child Management
# =========================

@app.route("/gprotect/children", methods=["GET", "POST"])
@parent_required
def gprotect_children():
    """Manage children"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    if request.method == "GET":
        parent = d["gprotect"]["parents"].get(parent_email, {})
        children_list = []
        for child_email in parent.get("children", []):
            children_list.append({
                "email": child_email,
                "schedules": d["gprotect"]["schedules"].get(child_email, {}),
                "ai_categories": d["gprotect"]["ai_categories"].get(child_email, {}),
                "manual_blocks": d["gprotect"]["manual_blocks"].get(child_email, []),
                "manual_allows": d["gprotect"]["manual_allows"].get(child_email, [])
            })
        return jsonify({"ok": True, "children": children_list})
    
    # POST - Add child
    body = request.json or {}
    child_email = (body.get("email") or "").strip().lower()
    
    if not child_email or "@" not in child_email:
        return jsonify({"ok": False, "error": "Invalid email"}), 400
    
    # Check if child already has a parent
    if child_email in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Child already registered"}), 400
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        parent.setdefault("children", []).append(child_email)
    
    d["gprotect"]["children"][child_email] = parent_email
    d["gprotect"]["parents"][parent_email] = parent
    
    # Initialize defaults
    d["gprotect"]["schedules"].setdefault(child_email, {
        "screen_time": {"enabled": False, "daily_minutes": 120, "timezone": "America/Los_Angeles"},
        "school_hours": {"enabled": False, "start": "08:00", "end": "15:00", "days": [1,2,3,4,5], "block_all": False},
        "homework_hours": {"enabled": False, "start": "15:30", "end": "18:00", "days": [1,2,3,4,5], "allow_educational": True},
        "downtime": {"enabled": False, "start": "21:00", "end": "07:00", "block_all": True}
    })
    
    save_data(d)
    log_action({"event": "gprotect_child_added", "parent": parent_email, "child": child_email})
    
    return jsonify({"ok": True, "child": child_email})

@app.route("/gprotect/children/<child_email>", methods=["DELETE"])
@parent_required
def gprotect_remove_child(child_email):
    """Remove a child"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        return jsonify({"ok": False, "error": "Not your child"}), 403
    
    parent["children"].remove(child_email)
    d["gprotect"]["parents"][parent_email] = parent
    d["gprotect"]["children"].pop(child_email, None)
    d["gprotect"]["schedules"].pop(child_email, None)
    d["gprotect"]["ai_categories"].pop(child_email, None)
    d["gprotect"]["manual_blocks"].pop(child_email, None)
    d["gprotect"]["manual_allows"].pop(child_email, None)
    
    save_data(d)
    return jsonify({"ok": True})

# =========================
# AI Categories Management
# =========================

@app.route("/gprotect/ai/categories", methods=["GET"])
def gprotect_get_ai_categories():
    """Get available AI categories"""
    d = ensure_keys(load_data())
    categories = []
    
    for name, cat in d.get("categories", {}).items():
        categories.append({
            "id": name,
            "name": name,
            "ai_labels": cat.get("ai_labels", []),
            "description": cat.get("description", "")
        })
    
    return jsonify({"ok": True, "categories": categories})

@app.route("/gprotect/ai/categories/<child_email>", methods=["GET", "POST"])
@parent_required
def gprotect_manage_ai_categories(child_email):
    """Manage AI category blocks for a child"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        return jsonify({"ok": False, "error": "Not your child"}), 403
    
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "categories": d["gprotect"]["ai_categories"].get(child_email, {})
        })
    
    # POST - Update categories
    body = request.json or {}
    categories = body.get("categories", {})
    
    d["gprotect"]["ai_categories"][child_email] = categories
    
    # Push policy refresh to child
    d.setdefault("pending_per_student", {}).setdefault(child_email, []).append({
        "type": "gprotect_refresh"
    })
    
    save_data(d)
    log_action({"event": "gprotect_ai_categories_update", "parent": parent_email, "child": child_email})
    
    return jsonify({"ok": True, "categories": categories})

# =========================
# Manual Blocks/Allows
# =========================

@app.route("/gprotect/manual/<child_email>", methods=["GET", "POST"])
@parent_required
def gprotect_manage_manual(child_email):
    """Manage manual blocks and allows"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        return jsonify({"ok": False, "error": "Not your child"}), 403
    
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "blocks": d["gprotect"]["manual_blocks"].get(child_email, []),
            "allows": d["gprotect"]["manual_allows"].get(child_email, [])
        })
    
    # POST - Update manual lists
    body = request.json or {}
    
    if "blocks" in body:
        d["gprotect"]["manual_blocks"][child_email] = body["blocks"]
    
    if "allows" in body:
        d["gprotect"]["manual_allows"][child_email] = body["allows"]
    
    # Push refresh
    d.setdefault("pending_per_student", {}).setdefault(child_email, []).append({
        "type": "gprotect_refresh"
    })
    
    save_data(d)
    log_action({"event": "gprotect_manual_update", "parent": parent_email, "child": child_email})
    
    return jsonify({"ok": True})

# =========================
# Schedule Management
# =========================

@app.route("/gprotect/schedules/<child_email>", methods=["GET", "POST"])
@parent_required
def gprotect_manage_schedules(child_email):
    """Manage time schedules"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        return jsonify({"ok": False, "error": "Not your child"}), 403
    
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "schedules": d["gprotect"]["schedules"].get(child_email, {})
        })
    
    # POST - Update schedules
    body = request.json or {}
    schedule_type = body.get("type")  # screen_time, school_hours, homework_hours, downtime
    config = body.get("config", {})
    
    if schedule_type not in ["screen_time", "school_hours", "homework_hours", "downtime"]:
        return jsonify({"ok": False, "error": "Invalid schedule type"}), 400
    
    schedules = d["gprotect"]["schedules"].get(child_email, {})
    schedules[schedule_type] = config
    d["gprotect"]["schedules"][child_email] = schedules
    
    # Push refresh
    d.setdefault("pending_per_student", {}).setdefault(child_email, []).append({
        "type": "gprotect_refresh"
    })
    
    save_data(d)
    log_action({"event": "gprotect_schedule_update", "parent": parent_email, "child": child_email, "type": schedule_type})
    
    return jsonify({"ok": True, "schedules": schedules})

# =========================
# Policy Evaluation (Extension calls this)
# =========================

@app.route("/gprotect/policy", methods=["POST"])
def gprotect_policy():
    """Get GProtect policy for a child (called by extension)"""
    body = request.json or {}
    child_email = (body.get("student") or body.get("email") or "").strip().lower()
    
    if not child_email:
        return jsonify({"ok": True, "active": False})
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    # Check if child is registered
    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": True, "active": False})
    
    parent_email = d["gprotect"]["children"][child_email]
    schedules = d["gprotect"]["schedules"].get(child_email, {})
    ai_categories = d["gprotect"]["ai_categories"].get(child_email, {})
    manual_blocks = d["gprotect"]["manual_blocks"].get(child_email, [])
    manual_allows = d["gprotect"]["manual_allows"].get(child_email, [])
    
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()  # 0=Monday, 6=Sunday
    
    # Determine active mode
    active_mode = "normal"
    block_all = False
    
    # Check downtime (highest priority)
    downtime = schedules.get("downtime", {})
    if downtime.get("enabled"):
        start = datetime.strptime(downtime.get("start", "21:00"), "%H:%M").time()
        end = datetime.strptime(downtime.get("end", "07:00"), "%H:%M").time()
        
        if start > end:  # Crosses midnight
            if current_time >= start or current_time < end:
                active_mode = "downtime"
                block_all = True
        else:
            if start <= current_time < end:
                active_mode = "downtime"
                block_all = True
    
    # Check school hours
    if active_mode == "normal":
        school_hours = schedules.get("school_hours", {})
        if school_hours.get("enabled") and current_day in school_hours.get("days", []):
            start = datetime.strptime(school_hours.get("start", "08:00"), "%H:%M").time()
            end = datetime.strptime(school_hours.get("end", "15:00"), "%H:%M").time()
            
            if start <= current_time < end:
                active_mode = "school_hours"
                if school_hours.get("block_all"):
                    block_all = True
    
    # Check homework hours
    if active_mode == "normal":
        hw_hours = schedules.get("homework_hours", {})
        if hw_hours.get("enabled") and current_day in hw_hours.get("days", []):
            start = datetime.strptime(hw_hours.get("start", "15:30"), "%H:%M").time()
            end = datetime.strptime(hw_hours.get("end", "18:00"), "%H:%M").time()
            
            if start <= current_time < end:
                active_mode = "homework_hours"
    
    # Check screen time
    screen_time = schedules.get("screen_time", {})
    screen_time_exceeded = False
    if screen_time.get("enabled"):
        # Simple daily limit check (you'd track usage in real implementation)
        daily_limit = screen_time.get("daily_minutes", 120)
        # TODO: Track actual usage and compare
    
    response = {
        "ok": True,
        "active": True,
        "parent_email": parent_email,
        "child_email": child_email,
        "active_mode": active_mode,
        "block_all": block_all,
        "ai_categories": ai_categories,
        "manual_blocks": manual_blocks,
        "manual_allows": manual_allows,
        "schedules": schedules,
        "screen_time_exceeded": screen_time_exceeded,
        "ts": int(time.time())
    }
    
    return jsonify(response)

# =========================
# MDM Token Management (iOS)
# =========================

@app.route("/gprotect/mdm/register", methods=["POST"])
def gprotect_mdm_register():
    """Register iOS device for MDM"""
    body = request.json or {}
    child_email = (body.get("email") or "").strip().lower()
    device_token = body.get("device_token")
    device_info = body.get("device_info", {})
    
    if not child_email or not device_token:
        return jsonify({"ok": False, "error": "Missing data"}), 400
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Not registered"}), 403
    
    d["gprotect"]["mdm_tokens"][child_email] = {
        "device_token": device_token,
        "device_info": device_info,
        "registered_at": int(time.time())
    }
    
    save_data(d)
    log_action({"event": "gprotect_mdm_register", "child": child_email})
    
    return jsonify({"ok": True})

@app.route("/gprotect/mdm/config/<child_email>", methods=["GET"])
def gprotect_mdm_config(child_email):
    """Get MDM configuration for device"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Not registered"}), 403
    
    schedules = d["gprotect"]["schedules"].get(child_email, {})
    
    # Build MDM restrictions
    restrictions = {
        "block_all_apps": False,
        "allowed_apps": [],
        "blocked_apps": [],
        "web_filter": {
            "enabled": True,
            "allowed_urls": d["gprotect"]["manual_allows"].get(child_email, []),
            "blocked_urls": d["gprotect"]["manual_blocks"].get(child_email, [])
        }
    }
    
    # Check if currently in downtime
    now = datetime.now()
    current_time = now.time()
    
    downtime = schedules.get("downtime", {})
    if downtime.get("enabled"):
        start = datetime.strptime(downtime.get("start", "21:00"), "%H:%M").time()
        end = datetime.strptime(downtime.get("end", "07:00"), "%H:%M").time()
        
        if start > end:
            if current_time >= start or current_time < end:
                restrictions["block_all_apps"] = True
        else:
            if start <= current_time < end:
                restrictions["block_all_apps"] = True
    
    return jsonify({
        "ok": True,
        "restrictions": restrictions,
        "schedules": schedules
    })

# =========================
# Activity Logs
# =========================

@app.route("/gprotect/logs/<child_email>", methods=["GET"])
@parent_required
def gprotect_logs(child_email):
    """Get activity logs for a child"""
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    parent_email = request.parent_email
    
    parent = d["gprotect"]["parents"].get(parent_email, {})
    if child_email not in parent.get("children", []):
        return jsonify({"ok": False, "error": "Not your child"}), 403
    
    logs = [log for log in d["gprotect"]["logs"] if log.get("child") == child_email]
    logs.sort(key=lambda x: x.get("ts", 0), reverse=True)
    
    return jsonify({"ok": True, "logs": logs[:500]})

@app.route("/gprotect/log", methods=["POST"])
def gprotect_log_event():
    """Log an event (called by extension/MDM)"""
    body = request.json or {}
    child_email = (body.get("child") or body.get("email") or "").strip().lower()
    event_type = body.get("type")
    url = body.get("url", "")
    data = body.get("data", {})
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    logs = d["gprotect"]["logs"]
    logs.append({
        "ts": int(time.time()),
        "child": child_email,
        "type": event_type,
        "url": url,
        "data": data
    })
    
    d["gprotect"]["logs"] = logs[-5000:]
    save_data(d)
    
    return jsonify({"ok": True})

# =========================
# Parent Dashboard Page
# =========================

@app.route("/gprotect")
def gprotect_dashboard():
    """Parent dashboard page"""
    return render_template("gprotect_dashboard.html")

@app.route("/gprotect/login")
def gprotect_login_page():
    """Parent login page"""
    return render_template("gprotect_login.html")

# =========================
# Scenes Helpers
# =========================
def _load_scenes():
    try:
        with open(SCENES_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        obj = {"allowed": [], "blocked": [], "current": []}
    obj.setdefault("allowed", [])
    obj.setdefault("blocked", [])
    cur = obj.get("current")
    # Normalize current to a list
    if cur is None:
        obj["current"] = []
    elif isinstance(cur, dict):
        obj["current"] = [cur]
    elif isinstance(cur, list):
        obj["current"] = [c for c in cur if c]
    else:
        obj["current"] = []
    return obj

def _save_scenes(obj):
    obj = obj or {}
    obj.setdefault("allowed", [])
    obj.setdefault("blocked", [])
    cur = obj.get("current")
    if cur is None:
        obj["current"] = []
    elif isinstance(cur, dict):
        obj["current"] = [cur]
    elif isinstance(cur, list):
        obj["current"] = [c for c in cur if c]
    else:
        obj["current"] = []
    with open(SCENES_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def ai_get_categories():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403
        
    d = ensure_keys(load_data())

    out = []
    for name, c in d.get("categories", {}).items():
        out.append({
            "id": name,
            "name": name,
            "urls": c.get("urls", []),
            "ai_labels": c.get("ai_labels", []),
            "blockPage": c.get("blockPage", "")
        })

    return jsonify({"ok": True, "categories": out})


# # ------------------------------------------
# # SAVE an AI category (used by Admin)
# # ------------------------------------------
# @ai.route("/api/ai/category/save", methods=["POST"])
# def ai_category_save():
#     u = current_user()
#     if not u or u["role"] != "admin":
#         return jsonify({"ok": False, "error": "forbidden"}), 403
# 
#     body = request.json or {}
#     name = body.get("name")
#     urls = body.get("urls") or []
#     bp = body.get("blockPage") or ""
# 
#     if not name:
#         return jsonify({"ok": False, "error": "name required"}), 400
# 
#     d = ensure_keys(load_data())
#     d["categories"][name] = {
#         "urls": urls,
#         "ai_labels": body.get("ai_labels", []),
#         "blockPage": bp
#     }
# 
#     save_data(d)
#     return jsonify({"ok": True})
# 
# 
# # ------------------------------------------
# # DELETE AI category
# # ------------------------------------------
# @ai.route("/api/ai/delete", methods=["POST"])
# def ai_category_delete():
#     u = current_user()
#     if not u or u["role"] != "admin":
#         return jsonify({"ok": False, "error": "forbidden"}), 403
# 
#     body = request.json or {}
#     name = body.get("name")
# 
#     d = ensure_keys(load_data())
#     if name in d["categories"]:
#         del d["categories"][name]
#         save_data(d)
# 
#     return jsonify({"ok": True})
# 
# 
# # ------------------------------------------
# # EXTENSION → classify URL against categories
# # ------------------------------------------
# @ai.route("/api/ai/classify", methods=["POST"])
# def ai_classify():
#     body = request.json or {}
#     url = (body.get("url") or "").strip()
# 
#     if not url:
#         return jsonify({"ok": False, "error": "no url"}), 400
# 
#     d = ensure_keys(load_data())
#     cats = d.get("categories", {})
# 
#     matched = None
#     reason = None
# 
#     for name, cat in cats.items():
#         for pat in cat.get("urls", []):
#             if pat and pat.lower() in url.lower():
#                 matched = name
#                 reason = f"Matched pattern: {pat}"
#                 break
#         if matched:
#             break
# 
#     if not matched:
#         return jsonify({"ok": True, "blocked": False})
# 
#     block_page = cats[matched].get("blockPage") or "category_block"
# 
#     params = {
#         "url": url,
#         "policy": matched,
#         "rule": matched,
#         "path": block_page,
#         "bypass": 1
#     }
# 
#     block_url = "https://blocked.gdistrict.org/Gschool%20block?" + urlencode(params)
# 
#     return jsonify({
#         "ok": True,
#         "blocked": True,
#         "category": matched,
#         "reason": reason,
#         "redirect": block_url
#     })
# 
# =========================
# Pages
# =========================
@app.route("/")
def index():
    u = current_user()
    if not u:
        return redirect(url_for("login_page"))
    return redirect(url_for("teacher_page" if u["role"] != "admin" else "admin_page"))

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/api/bypass/list", methods=["GET"])
def list_bypass_codes():
    d = ensure_keys(load_data())
    settings = d.get("settings", {})
    codes = settings.get("bypass_codes", [])

    now = time.time()
    active = []

    for c in codes:
        if c.get("expires", 0) > now:
            active.append({
                "hash_preview": c["hash"][:8],  # safe display
                "expires_at": c["expires"],
                "seconds_left": int(c["expires"] - now)
            })

    return jsonify({"ok": True, "codes": active})


@app.route("/api/bypass/revoke", methods=["POST"])
def revoke_bypass_code():
    d = ensure_keys(load_data())
    settings = d.get("settings", {})
    codes = settings.get("bypass_codes", [])

    h = (request.json or {}).get("hash_preview")
    if not h:
        return jsonify({"ok": False}), 400

    settings["bypass_codes"] = [
        c for c in codes if not c["hash"].startswith(h)
    ]

    save_data(d)
    return jsonify({"ok": True})

@app.route("/api/bypass/generate", methods=["POST"])
def generate_bypass_code():
    d = ensure_keys(load_data())
    settings = d.setdefault("settings", {})
    settings.setdefault("bypass_codes", [])

    # Use TTL sent in request (must be an int)
    try:
        ttl_minutes = int((request.json or {}).get("ttl_minutes", 10))
    except Exception:
        ttl_minutes = 10

    # Clamp TTL
    ttl_minutes = max(1, min(1440, ttl_minutes))

    # Save TTL to settings so frontend can read it
    settings["bypass_ttl_minutes"] = ttl_minutes
    save_data(d)

    # Generate 6-digit code
    code = f"{random.randint(0, 999999):06d}"
    expires = time.time() + (ttl_minutes * 60)

    settings["bypass_codes"].append({
        "hash": _hash_code(code),
        "expires": expires
    })

    _clean_expired_bypass_codes(settings)
    save_data(d)

    return jsonify({
        "ok": True,
        "code": code,
        "expires_at": expires,
        "ttl_minutes": ttl_minutes
    })

@app.route("/admin")
def admin_page():
    u = current_user()
    if not u or u["role"] != "admin":
        return redirect(url_for("login_page"))
    return render_template("admin.html", data=load_data(), user=u)

@app.route("/teacher")
def teacher_page():
    """Landing page for teachers: choose or manage class sessions."""
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return redirect(url_for("login_page"))

    d = ensure_keys(load_data())
    email = (u.get("email") or "").strip().lower()
    class_items = _get_teacher_classes(d, email)

    # Sort by name for stable ordering
    class_items.sort(key=lambda x: str(x[1].get("name", "")))
    return render_template("teacher_classes.html", user=u, classes=class_items)


@app.route("/teacher/class/<cid>")
def teacher_class_page(cid):
    """Per-session teacher dashboard that reuses teacher.html."""
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return redirect(url_for("login_page"))

    d = ensure_keys(load_data())
    classes = d.setdefault("classes", {})
    cls = classes.get(cid)
    email = (u.get("email") or "").strip().lower()

    if cls is None:
        # Auto-create a new session shell
        cls = {
            "name": cid,
            "active": False,
            "focus_mode": False,
            "paused": False,
            "allowlist": [],
            "teacher_blocks": [],
            "students": [],
            "owner": email,
            "schedule": {},
        }
        classes[cid] = cls
        save_data(d)
    else:
        owner = (cls.get("owner") or "").strip().lower()
        if owner and owner != email and u.get("role") != "admin":
            # Not your class → redirect back
            return redirect(url_for("teacher_page"))
        if not owner:
            cls["owner"] = email
            save_data(d)

    return render_template("teacher.html", data=d, user=u, class_id=cid)


@app.route("/teacher/create_class", methods=["POST"])
def create_class_session():
    u = current_user()
    if not u or u.get("role") not in ("teacher", "admin"):
        return redirect(url_for("login_page"))

    name = (request.form.get("name") or "").strip() or "New Class"
    students_raw = request.form.get("students") or ""
    window = (request.form.get("window") or "").strip()

    students = []
    for line in students_raw.splitlines():
        for part in line.replace(",", " ").split():
            if "@" in part:
                students.append(part.strip().lower())

    d = ensure_keys(load_data())
    classes = d.setdefault("classes", {})

    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()) or "class"
    cid = base
    suffix = 1
    while cid in classes:
        cid = f"{base}-{suffix}"
        suffix += 1

    email = (u.get("email") or "").strip().lower()

    classes[cid] = {
        "name": name,
        "active": False,
        "focus_mode": False,
        "paused": False,
        "allowlist": [],
        "teacher_blocks": [],
        "students": students,
        "owner": email,
        "schedule": {"window": window} if window else {},
    }
    save_data(d)
    return redirect(url_for("teacher_class_page", cid=cid))

@app.route("/gprotect/mdm/commands", methods=["POST"])
def mdm_commands():
    """
    iOS device fetches pending MDM commands (restrictions, screen time, web filter)
    """
    plist = plistlib.loads(request.data)
    udid = plist.get("UDID")
    child_email = None

    # Match UDID to child_email
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    for email, info in d["gprotect"].get("mdm_tokens", {}).items():
        if info.get("udid") == udid:
            child_email = email
            break

    if not child_email:
        # Device not enrolled yet
        return Response(plistlib.dumps({}), mimetype="application/xml")

    schedules = d["gprotect"]["schedules"].get(child_email, {})
    manual_blocks = d["gprotect"]["manual_blocks"].get(child_email, [])
    manual_allows = d["gprotect"]["manual_allows"].get(child_email, [])

    # Build the dynamic MDM payload
    payload = {
        "PayloadContent": [
            # Screen Time / Downtime
            {
                "PayloadType": "com.apple.screentime",
                "PayloadVersion": 1,
                "PayloadUUID": str(uuid.uuid4()).upper(),
                "PayloadDisplayName": f"GProtect Screen Time for {child_email}",
                "familyControlsEnabled": True,
                "downtimeSchedule": {
                    "enabled": schedules.get("downtime", {}).get("enabled", True),
                    "start": {
                        "hour": int(schedules.get("downtime", {}).get("start", "21:00").split(":")[0]),
                        "minute": int(schedules.get("downtime", {}).get("start", "21:00").split(":")[1])
                    },
                    "end": {
                        "hour": int(schedules.get("downtime", {}).get("end", "07:00").split(":")[0]),
                        "minute": int(schedules.get("downtime", {}).get("end", "07:00").split(":")[1])
                    }
                },
                "appLimits": {
                    "application": {
                        "com.apple.mobilesafari": {"timeLimit": schedules.get("screen_time", {}).get("daily_minutes", 120)*60}
                    }
                },
                "alwaysAllowedBundleIDs": ["com.apple.mobilephone", "com.apple.FaceTime", "com.apple.MobileSMS"]
            },
            # Web Content Filter
            {
                "PayloadType": "com.apple.webcontent-filter",
                "PayloadVersion": 1,
                "PayloadUUID": str(uuid.uuid4()).upper(),
                "PayloadDisplayName": f"GProtect Web Filter for {child_email}",
                "FilterType": "Plugin",
                "UserDefinedName": "GProtect Filter",
                "PluginBundleID": "org.gdistrict.gprotect.filter",
                "ServerAddress": "https://gschool.gdistrict.org",
                "Organization": "GProtect",
                "FilterDataProviderBundleIdentifier": "org.gdistrict.gprotect.dataprovider",
                "FilterDataProviderDesignatedRequirement": 'identifier "org.gdistrict.gprotect.dataprovider"',
                "ContentFilterUUID": str(uuid.uuid4()).upper(),
                "FilterBrowsers": True,
                "FilterSockets": False,
                "FilterPackets": False,
                "VendorConfig": {
                    "child_email": child_email,
                    "manual_blocks": manual_blocks,
                    "manual_allows": manual_allows,
                    "api_endpoint": f"https://gschool.gdistrict.org/gprotect/mdm/config/{child_email}"
                }
            }
        ]
    }

    return Response(plistlib.dumps(payload), mimetype="application/xml")
@app.route("/gprotect/mdm/checkin", methods=["POST"])
def mdm_checkin():
    """
    iOS device posts check-in info here (UDID, device token, etc.)
    """
    try:
        plist = plistlib.loads(request.data)
        udid = plist.get("UDID")
        email = plist.get("UserEmail", "unknown@example.com")

        d = ensure_keys(load_data())
        _ensure_gprotect_structure(d)

        # Save UDID and device token
        d["gprotect"].setdefault("mdm_tokens", {})[email] = {
            "udid": udid,
            "device_token": plist.get("DeviceToken", ""),
            "last_checkin": int(time.time())
        }
        save_data(d)

        return Response(plistlib.dumps({}), mimetype="application/xml")
    except Exception as e:
        print("MDM checkin error:", e)
        return Response(plistlib.dumps({}), mimetype="application/xml")

@app.route("/gprotect/mdm/profile/<child_email>", methods=["GET"])
def generate_mdm_profile(child_email):
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)

    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Not registered"}), 403

    schedules = d["gprotect"]["schedules"].get(child_email, {})
    manual_blocks = d["gprotect"]["manual_blocks"].get(child_email, [])
    manual_allows = d["gprotect"]["manual_allows"].get(child_email, [])

    child_name = child_email.split("@")[0].capitalize()

    def new_uuid():
        return str(uuid.uuid4()).upper()

    # Always allowed apps
    always_allowed = ["com.apple.mobilephone", "com.apple.FaceTime", "com.apple.MobileSMS"]

    # Apps subject to downtime/blocks
    downtime_apps = [
        "com.instagram.ios",
        "com.snapchat.snapchat",
        "com.tiktok.tiktokv",
        "com.facebook.Facebook",
        "com.twitter.twitter",
        "com.apple.mobilesafari",
    ]

    # Generate Web Clips for overlays
    webclips = []
    all_blocked_apps = set(downtime_apps + manual_blocks)
    for app_bundle in all_blocked_apps:
        if app_bundle in always_allowed:
            continue
        if schedules.get("downtime", {}).get("enabled", True) and app_bundle in downtime_apps:
            url = f"https://blocked.gdistrict.org/downtime?website={app_bundle}"
            display_name = f"{app_bundle} (Downtime)"
        else:
            url = f"https://blocked.gdistrict.org/parent_block?website={app_bundle}"
            display_name = f"{app_bundle} (Blocked)"

        webclips.append({
            "PayloadType": "com.apple.webClip.managed",
            "PayloadVersion": 1,
            "PayloadIdentifier": f"org.gdistrict.gprotect.webclip.{child_email}.{app_bundle}",
            "PayloadUUID": new_uuid(),
            "PayloadDisplayName": display_name,
            "Label": display_name,  # REQUIRED for iOS
            "PayloadDescription": f"Overlay for {display_name}",
            "IsRemovable": False,
            "Precomposed": True,
            "URL": url
        })

    # --- Embed the certificate payload FIRST ---
    with open("mdm_identity.p12", "rb") as f:
        p12_data = base64.b64encode(f.read()).decode("ascii")

    cert_payload_uuid = APNS_CERT_UUID  # Must match IdentityCertificateUUID below

    profile = {
        "PayloadContent": [
            {
                "PayloadType": "com.apple.security.pkcs12",
                "PayloadVersion": 1,
                "PayloadIdentifier": f"org.gdistrict.gprotect.cert.{child_email}",
                "PayloadUUID": cert_payload_uuid,
                "PayloadDisplayName": "GProtect MDM Identity",
                "Password": APNS_CERT_PASSWORD,  # Set this to your .p12 password
                "PayloadContent": p12_data
            },
            # --- MDM Payload ---
            {
                "PayloadType": "com.apple.mdm",
                "PayloadVersion": 1,
                "PayloadIdentifier": f"org.gdistrict.gprotect.mdm.{child_email}",
                "PayloadUUID": new_uuid(),
                "PayloadDisplayName": f"GProtect MDM for {child_name}",
                "ServerURL": "https://gschool.gdistrict.org/mdm/commands",
                "CheckInURL": "https://gschool.gdistrict.org/mdm/checkin",
                "AccessRights": 8191,
                "IdentityCertificateUUID": cert_payload_uuid,  # EXACT UUID match
                "Topic": APNS_TOPIC,
                "SignMessage": True
            },
            # --- Web Content Filter ---
            {
                "PayloadType": "com.apple.webcontent-filter",
                "PayloadVersion": 1,
                "PayloadIdentifier": "org.gdistrict.gprotect.webfilter",
                "PayloadUUID": new_uuid(),
                "PayloadDisplayName": f"GProtect Web Filter for {child_name}",
                "PayloadDescription": "Content filtering controlled by parent",
                "FilterType": "Plugin",
                "UserDefinedName": "GProtect Filter",
                "PluginBundleID": "org.gdistrict.gprotect.filter",
                "ServerAddress": "https://gschool.gdistrict.org",
                "Organization": "GProtect",
                "FilterDataProviderBundleIdentifier": "org.gdistrict.gprotect.dataprovider",
                "FilterDataProviderDesignatedRequirement": 'identifier "org.gdistrict.gprotect.dataprovider"',
                "ContentFilterUUID": new_uuid(),
                "FilterBrowsers": True,
                "FilterSockets": False,
                "FilterPackets": False,
                "VendorConfig": {
                    "child_email": child_email,
                    "manual_blocks": manual_blocks,
                    "manual_allows": manual_allows,
                    "api_endpoint": "https://gschool.gdistrict.org/gprotect/mdm/config"
                }
            },
            # --- Restrictions ---
            {
                "PayloadType": "com.apple.applicationaccess",
                "PayloadVersion": 1,
                "PayloadIdentifier": "org.gdistrict.gprotect.restrictions",
                "PayloadUUID": new_uuid(),
                "PayloadDisplayName": f"GProtect Restrictions for {child_name}",
                "blacklistedAppBundleIDs": list(all_blocked_apps),
                "whitelistedAppBundleIDs": always_allowed,
                "allowSafari": True,
                "allowScreenTime": False
            }
        ] + webclips,  # Append Web Clips
        "PayloadDisplayName": f"GProtect Parental Controls for {child_name}",
        "PayloadIdentifier": "org.gdistrict.gprotect",
        "PayloadRemovalDisallowed": True,
        "PayloadType": "Configuration",
        "PayloadUUID": new_uuid(),
        "PayloadVersion": 1,
        "PayloadOrganization": "GProtect",
        "PayloadDescription": "This profile enforces parental controls on this device. Apps are overlaid with downtime/blocked pages.",
        "PayloadRemovalPassword": "220099"
    }

    plist_data = plistlib.dumps(profile)

    return Response(
        plist_data,
        mimetype="application/x-apple-aspen-config",
        headers={"Content-Disposition": f"attachment; filename={child_name}_gprotect.mobileconfig"}
    )



@app.route("/gprotect/mdm/update/<child_email>", methods=["POST"])
def update_mdm_profile(child_email):
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)

    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Not registered"}), 403

    mdm_info = d["gprotect"]["mdm_tokens"].get(child_email)
    if not mdm_info:
        return jsonify({"ok": False, "error": "Device not enrolled"}), 400

    device_token = mdm_info.get("device_token")
    if not device_token:
        return jsonify({"ok": False, "error": "No device token for child"}), 400

    try:
        send_mdm_push(device_token)

        log_action({
            "event": "gprotect_mdm_update_sent",
            "child": child_email,
            "timestamp": int(time.time())
        })

        return jsonify({"ok": True, "message": "Update pushed to device"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/gprotect/mdm/check_in", methods=["POST"])
def mdm_device_check_in():
    """
    iOS device checks in periodically to get latest restrictions
    Called by the device every 5 minutes
    """
    body = request.json or {}
    child_email = body.get("email")
    device_token = body.get("device_token")
    
    if not child_email:
        return jsonify({"ok": False, "error": "Email required"}), 400
    
    d = ensure_keys(load_data())
    _ensure_gprotect_structure(d)
    
    if child_email not in d["gprotect"]["children"]:
        return jsonify({"ok": False, "error": "Not registered"}), 403
    
    schedules = d["gprotect"]["schedules"].get(child_email, {})
    
    # Determine current state
    now = datetime.now()
    current_time = now.time()
    
    # Check downtime
    downtime = schedules.get("downtime", {})
    in_downtime = False
    
    if downtime.get("enabled"):
        start = datetime.strptime(downtime.get("start", "21:00"), "%H:%M").time()
        end = datetime.strptime(downtime.get("end", "07:00"), "%H:%M").time()
        
        if start > end:  # Crosses midnight
            in_downtime = current_time >= start or current_time < end
        else:
            in_downtime = start <= current_time < end
    
    # Return current restrictions
    return jsonify({
        "ok": True,
        "active_mode": "downtime" if in_downtime else "normal",
        "block_all": in_downtime,
        "manual_blocks": d["gprotect"]["manual_blocks"].get(child_email, []),
        "manual_allows": d["gprotect"]["manual_allows"].get(child_email, []),
        "schedules": schedules,
        "needs_profile_update": False  # Set to True if settings changed
    })

@app.route("/teacher/class/<cid>/edit", methods=["POST"])
def edit_class_session(cid):
    u = current_user()
    if not u or u.get("role") not in ("teacher", "admin"):
        return redirect(url_for("login_page"))

    name = (request.form.get("name") or "").strip()
    students_raw = request.form.get("students") or ""
    window = (request.form.get("window") or "").strip()

    d = ensure_keys(load_data())
    classes = d.setdefault("classes", {})
    cls = classes.get(cid)
    if not cls:
        return redirect(url_for("teacher_page"))

    email = (u.get("email") or "").strip().lower()
    owner = (cls.get("owner") or "").strip().lower()
    if owner and owner != email and u.get("role") != "admin":
        return redirect(url_for("teacher_page"))

    if name:
        cls["name"] = name

    if students_raw:
        students = []
        for line in students_raw.splitlines():
            for part in line.replace(",", " ").split():
                if "@" in part:
                    students.append(part.strip().lower())
        cls["students"] = students

    if window:
        cls.setdefault("schedule", {})["window"] = window

    save_data(d)
    return redirect(url_for("teacher_page"))


@app.route("/teacher/class/<cid>/delete", methods=["POST"])
def delete_class_session(cid):
    u = current_user()
    if not u or u.get("role") not in ("teacher", "admin"):
        return redirect(url_for("login_page"))

    d = ensure_keys(load_data())
    classes = d.setdefault("classes", {})
    cls = classes.get(cid)
    if not cls:
        return redirect(url_for("teacher_page"))

    email = (u.get("email") or "").strip().lower()
    owner = (cls.get("owner") or "").strip().lower()
    if owner and owner != email and u.get("role") != "admin":
        return redirect(url_for("teacher_page"))

    classes.pop(cid, None)
    save_data(d)
    return redirect(url_for("teacher_page"))
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login_page"))


# =========================
# Teacher Presentation (WebRTC signaling via REST polling)
# =========================

PRESENT = defaultdict(lambda: {
    "offers": {},
    "answers": {},
    "cand_v": defaultdict(list),
    "cand_t": defaultdict(list),
    "updated": int(time.time()),
    "active": False
})

def _clean_room(room):
    r = PRESENT.get(room)
    if not r:
        return
    now = int(time.time())
    r["updated"] = now

@app.route("/teacher/present")
def teacher_present_page():
    u = session.get("user")
    if not u:
        return redirect(url_for("login_page"))
    # room id based on teacher email (stable across session)
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', (u.get("email") or "classroom").split("@")[0])
    return render_template(
        "teacher_present.html",
        data=load_data(),
        ice_servers=_ice_servers(),
        user=u,
        room=room,
    )

@app.route("/present/<room>")
def student_present_view(room):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    return render_template("present.html", room=room, ice_servers=_ice_servers())

@app.route("/api/present/<room>/start", methods=["POST"])
def api_present_start(room):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    PRESENT[room]["active"] = True
    PRESENT[room]["updated"] = int(time.time())
    return jsonify({"ok": True, "room": room})

@app.route("/api/present/<room>/end", methods=["POST"])
def api_present_end(room):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    PRESENT[room] = {
        "offers": {},
        "answers": {},
        "cand_v": defaultdict(list),
        "cand_t": defaultdict(list),
        "updated": int(time.time()),
        "active": False
    }
    return jsonify({"ok": True})

@app.route("/api/present/<room>/status", methods=["GET"])
def api_present_status(room):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    r = PRESENT.get(room) or {}
    return jsonify({"ok": True, "active": bool(r.get("active"))})

# Viewer posts offer and polls for answer
@app.route("/api/present/<room>/viewer/offer", methods=["POST"])
def api_present_viewer_offer(room):
    body = request.json or {}
    sdp = body.get("sdp")
    client_id = body.get("client_id") or str(uuid.uuid4())
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    r = PRESENT[room]
    r["offers"][client_id] = sdp
    r["updated"] = int(time.time())
    return jsonify({"ok": True, "client_id": client_id})

@app.route("/api/present/<room>/offers", methods=["GET"])
def api_present_offers(room):
    # Teacher polls for pending offers
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    offers = PRESENT[room]["offers"]
    return jsonify({"ok": True, "offers": offers})

@app.route("/api/present/<room>/answer/<client_id>", methods=["POST", "GET"])
def api_present_answer(room, client_id):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    client_id = re.sub(r'[^a-zA-Z0-9_-]+', '', client_id)
    r = PRESENT[room]
    if request.method == "POST":
        body = request.json or {}
        sdp = body.get("sdp")
        r["answers"][client_id] = sdp
        # once answered, remove offer (optional)
        if client_id in r["offers"]:
            del r["offers"][client_id]
        r["updated"] = int(time.time())
        return jsonify({"ok": True})
    else:
        ans = r["answers"].get(client_id)
        return jsonify({"ok": True, "answer": ans})

# ICE candidates (trickle)
@app.route("/api/present/<room>/candidate/<side>/<client_id>", methods=["POST", "GET"])
def api_present_candidate(room, side, client_id):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    client_id = re.sub(r'[^a-zA-Z0-9_-]+', '', client_id)
    side = "viewer" if side.lower().startswith("v") else "teacher"
    r = PRESENT[room]
    bucket_from = r["cand_v"] if side == "viewer" else r["cand_t"]
    bucket_to = r["cand_t"] if side == "viewer" else r["cand_v"]
    if request.method == "POST":
        body = request.json or {}
        cands = body.get("candidates") or []
        if cands:
            bucket_from[client_id].extend(cands)
        r["updated"] = int(time.time())
        return jsonify({"ok": True})
    else:
        # GET fetch and clear incoming candidates for this side
        cands = bucket_to.get(client_id, [])
        bucket_to[client_id] = []
        return jsonify({"ok": True, "candidates": cands})

@app.route("/api/present/<room>/diag", methods=["GET"])
def api_present_diag(room):
    room = re.sub(r'[^a-zA-Z0-9_-]+', '', room)
    r = PRESENT.get(room) or {"offers": {}, "answers": {}, "cand_v": {}, "cand_t": {}, "active": False}
    return jsonify({
        "ok": True,
        "active": bool(r.get("active")),
        "offers": len(r.get("offers", {})),
        "answers": len(r.get("answers", {})),
        "cand_v": {k: len(v) for k, v in (r.get("cand_v") or {}).items()},
        "cand_t": {k: len(v) for k, v in (r.get("cand_t") or {}).items()},
    })

# =========================
# User Admin (create/list/delete)
# =========================
@app.route("/api/users", methods=["GET", "POST"])
def api_users():
    u = current_user()
    # only admins can manage users
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    con = db()
    cur = con.cursor()

    if request.method == "GET":
        # (not used by the simplified admin.html, but handy for future)
        cur.execute("SELECT email, role FROM users ORDER BY email ASC")
        rows = cur.fetchall()
        con.close()
        return jsonify({"ok": True, "users": [{"email": r[0], "role": r[1]} for r in rows]})

    # POST: create or update a user
    body = request.json or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    role = (body.get("role") or "teacher").strip().lower()

    if not email:
        con.close()
        return jsonify({"ok": False, "error": "email required"}), 400
    if not password:
        # allow role-only updates if needed
        cur.execute("SELECT email FROM users WHERE email=?", (email,))
        if not cur.fetchone():
            con.close()
            return jsonify({"ok": False, "error": "password required for new user"}), 400

    if password:
        cur.execute(
            "REPLACE INTO users (email, password, role) VALUES (?,?,?)",
            (email, password, role)
        )
    else:
        cur.execute("UPDATE users SET role=? WHERE email=?", (role, email))

    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.route("/api/users/delete", methods=["POST"])
def api_users_delete():
    u = current_user()
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        return jsonify({"ok": False, "error": "email required"}), 400

    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM users WHERE email=?", (email,))
    con.commit()
    con.close()
    return jsonify({"ok": True})

# =========================
# Auth
# =========================
@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.json or request.form
    email = (body.get("email") or "").strip().lower()
    pw = body.get("password") or ""
    con = db(); cur = con.cursor()
    cur.execute("SELECT email,role FROM users WHERE email=? AND password=?", (email, pw))
    row = cur.fetchone()
    con.close()
    if row:
        session["user"] = {"email": row[0], "role": row[1]}
        return jsonify({"ok": True, "role": row[1]})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401



# -------------------------
# Class-session helpers
# -------------------------
def _get_teacher_classes(d, teacher_email):
    """Return (cid, cls) pairs for sessions owned by this teacher."""
    classes = d.get("classes") or {}
    out = []
    for cid, cls in classes.items():
        if not isinstance(cls, dict):
            continue
        owner = (cls.get("owner") or "").strip().lower()
        if not owner and teacher_email:
            # Backfill legacy sessions to first teacher who opens them
            cls["owner"] = teacher_email
            owner = teacher_email
        if owner == teacher_email:
            out.append((cid, cls))
    return out



def _get_active_class_for_student(d, student_email):
    """Find an active session this student belongs to (if any)."""
    classes = d.get("classes") or {}
    student_email = (student_email or "").strip().lower()
    matches = []
    for cid, cls in classes.items():
        if not isinstance(cls, dict):
            continue
        if not cls.get("active"):
            continue
        students = cls.get("students") or []
        norm_students = []
        for s in students:
            if not s:
                continue
            s_norm = str(s).strip().lower()
            if s_norm and "@" in s_norm:
                norm_students.append(s_norm)
        if student_email and student_email not in norm_students:
            continue
        matches.append((cid, cls))
    if not matches:
        return None, None
    # sort by name then id for stable ordering
    matches.sort(key=lambda x: (str(x[1].get("name", "")), str(x[0])))
    return matches[0]


# =========================
# Core Data & Settings
# =========================
@app.route("/api/data")
def api_data():
    """Data for teacher.html dashboard.

    Accepts optional ?class_id=XYZ so each teacher session can operate
    on its own class without affecting others.
    """
    d = ensure_keys(load_data())
    cid = request.args.get("class_id") or "period1"
    classes = d.get("classes") or {}
    cls = classes.get(cid) or classes.get("period1") or {}

    return jsonify({
        "settings": {
            "chat_enabled": bool(d.get("settings", {}).get("chat_enabled", True)),
            "youtube_mode": get_setting("youtube_mode", "normal"),
        },
        "lists": {
            "teacher_blocks": get_setting("teacher_blocks", []),
            "teacher_allow": get_setting("teacher_allow", []),
        },
        "classes": {
            cid: {
                "name": cls.get("name", "Class Session"),
                "active": bool(cls.get("active", False)),
                "focus_mode": bool(cls.get("focus_mode", False)),
                "paused": bool(cls.get("paused", False)),
                "allowlist": list(cls.get("allowlist", [])),
                "teacher_blocks": list(cls.get("teacher_blocks", [])),
                "students": list(cls.get("students", [])),
            }
        }
    })

@app.route("/api/bypass/active", methods=["GET"])
def get_active_bypass_codes():
    d = ensure_keys(load_data())
    settings = d.get("settings", {})

    _clean_expired_bypass_codes(settings)
    save_data(d)

    now = time.time()
    return jsonify({
        "ok": True,
        "codes": [
            {
                "expires": c["expires"],
                "ttl": int(c["expires"] - now)
            }
            for c in settings.get("bypass_codes", [])
        ]
    })
    
@app.route("/api/settings", methods=["POST"])
def api_settings():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    b = request.json or {}

    # existing settings
    if "blocked_redirect" in b:
        d["settings"]["blocked_redirect"] = b["blocked_redirect"]
    if "chat_enabled" in b:
        d["settings"]["chat_enabled"] = bool(b["chat_enabled"])
        set_setting("chat_enabled", bool(b["chat_enabled"]))
    if "passcode" in b and b["passcode"]:
        d["settings"]["passcode"] = b["passcode"]

    # NEW: global bypass settings
    if "bypass_enabled" in b:
        d["settings"]["bypass_enabled"] = bool(b["bypass_enabled"])
        set_setting("bypass_enabled", bool(b["bypass_enabled"]))
    if "bypass_code" in b:
        d["settings"]["bypass_code"] = b["bypass_code"]
    if "bypass_ttl_minutes" in b:
        try:
            ttl = int(b["bypass_ttl_minutes"])
        except Exception:
            ttl = 10
        if ttl < 1:
            ttl = 1
        if ttl > 1440:
            ttl = 1440
        d["settings"]["bypass_ttl_minutes"] = ttl

    save_data(d)
    return jsonify({"ok": True, "settings": d["settings"]})

@app.route("/api/categories", methods=["POST"])
def api_categories():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    b = request.json or {}
    name = b.get("name")
    urls = b.get("urls", [])
    bp = b.get("blockPage", "")
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400

    d["categories"][name] = {"urls": urls, "blockPage": bp}

    # Policy changed → force refresh for all extensions
    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "policy_refresh"
    })

    save_data(d)
    log_action({"event": "categories_update", "name": name})
    return jsonify({"ok": True})

@app.route("/api/categories/delete", methods=["POST"])
def api_categories_delete():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    name = (request.json or {}).get("name")
    if name in d["categories"]:
        del d["categories"][name]

        # Policy changed → force refresh
        d.setdefault("pending_commands", {}).setdefault("*", []).append({
            "type": "policy_refresh"
        })

        save_data(d)
        log_action({"event": "categories_delete", "name": name})
    return jsonify({"ok": True})


# # =========================
# # AI Category Helpers
# # =========================
# @app.route("/api/ai/categories", methods=["GET"])
# def api_ai_categories():
#     u = current_user()
#     if not u or u["role"] != "admin":
#         return jsonify({"ok": False, "error": "forbidden"}), 403
#     d = ensure_keys(load_data())
#     cats = []
#     for name, cat in d.get("categories", {}).items():
#         cats.append({
#             "id": name,
#             "name": name,
#             "ai_labels": cat.get("ai_labels", []),
#             "urls": cat.get("urls", []),
#             "blockPage": cat.get("blockPage", "")
#         })
#     return jsonify({"ok": True, "categories": cats})
# 
# @app.route("/api/ai/classify", methods=["POST"])
# def api_ai_classify():
#     body = request.json or {}
#     url = (body.get("url") or "").strip()
#     if not url:
#         return jsonify({"ok": False, "error": "no url"}), 400
# 
#     d = ensure_keys(load_data())
#     cats = d.get("categories", {})
# 
#     label = None
#     reason = None
#     matched_cat = None
# 
#     # Simple pattern-based match against category URL patterns
#     for name, cat in cats.items():
#         for pat in cat.get("urls", []):
#             if pat and pat.lower() in url.lower():
#                 label = name
#                 reason = f"Matched category pattern: {pat}"
#                 matched_cat = cat
#                 break
#         if label:
#             break
# 
#     if not label:
#         # Not blocked by AI / category patterns
#         return jsonify({"ok": True, "blocked": False})
# 
#     # Build block page URL using blockPage (your block page path) if set
#     path = (matched_cat or {}).get("blockPage") or f"category_{label}"
#     params = {
#         "url": url,
#         "policy": label,
#         "rule": label,
#         "path": path,
#     }
#     q = urlencode(params)
#     block_url = f"https://blocked.gdistrict.org/Gschool%20block?{q}"
# 
#     return jsonify({
#         "ok": True,
#         "blocked": True,
#         "label": label,
#         "reason": reason,
#         "block_url": block_url
#     })
# 
# 
# =========================
# Class / Teacher Controls
# =========================
@app.route("/api/announce", methods=["POST"])
def api_announce():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    body = request.json or {}

    msg = (
        (body.get("message") or "").strip()
        or (body.get("text") or "").strip()
        or (body.get("announcement") or "").strip()
    )

    d["announcements"] = msg

    # Tell all extensions to re-fetch /api/policy so they see the new announcement
    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "policy_refresh"
    })

    save_data(d)
    log_action({"event": "announce", "message": msg})
    return jsonify({"ok": True})

@app.route("/api/class/set", methods=["GET", "POST"])
def api_class_set():
    d = ensure_keys(load_data())
    classes = d.setdefault("classes", {})

    if request.method == "GET":
        cid = request.args.get("class_id") or "period1"
        cls = classes.get(cid) or classes.get("period1", {})
        return jsonify({"class": cls, "settings": d["settings"]})

    body = request.json or {}
    cid = body.get("class_id") or "period1"
    cls = classes.get(cid)
    if cls is None:
        cls = {
            "name": body.get("name") or cid,
            "active": False,
            "focus_mode": False,
            "paused": False,
            "allowlist": [],
            "teacher_blocks": [],
            "students": [],
            "owner": None,
            "schedule": {},
        }
        classes[cid] = cls

    prev_active = bool(cls.get("active", False))

    if "teacher_blocks" in body:
        set_setting("teacher_blocks", body["teacher_blocks"])
        cls["teacher_blocks"] = list(body["teacher_blocks"])
    else:
        cls.setdefault("teacher_blocks", [])

    if "allowlist" in body:
        set_setting("teacher_allow", body["allowlist"])
        cls["allowlist"] = list(body["allowlist"])
    else:
        cls.setdefault("allowlist", [])

    if "chat_enabled" in body:
        d.setdefault("settings", {})["chat_enabled"] = bool(body["chat_enabled"])
        set_setting("chat_enabled", body["chat_enabled"])

    if "active" in body:
        cls["active"] = bool(body["active"])

    if isinstance(body.get("schedule"), dict):
        cls["schedule"] = body["schedule"]

    if isinstance(body.get("students"), list):
        cls["students"] = [s.strip() for s in body["students"] if isinstance(s, str) and s.strip()]

    if "passcode" in body and body["passcode"]:
        d.setdefault("settings", {})["passcode"] = body["passcode"]

    # When this specific class becomes active, notify only its students
    if not prev_active and cls.get("active"):
        for student in cls.get("students", []):
            d.setdefault("pending_commands", {}).setdefault(student, []).append({
                "type": "notify",
                "title": "Class session is active",
                "message": "Please join and stay until dismissed.",
            })

    # Ask extensions to refresh policy (no longer global '*', but keep meta bucket)
    d.setdefault("pending_commands", {}).setdefault("_meta", []).append({
        "type": "policy_refresh"
    })

    save_data(d)
    log_action({"event": "class_set", "class_id": cid, "active": cls.get("active", False)})
    return jsonify({"ok": True, "class": cls, "settings": d["settings"]})
@app.route("/api/class/toggle", methods=["POST"])
def api_class_toggle():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    b = request.json or {}
    cid = b.get("class_id", "period1")
    key = b.get("key")
    val = bool(b.get("value"))

    classes = d.get("classes") or {}
    if cid in classes and key in ("focus_mode", "paused", "active"):
        classes[cid][key] = val
        save_data(d)
        log_action({"event": "class_toggle", "class_id": cid, "key": key, "value": val})
        return jsonify({"ok": True, "class": classes[cid]})

    return jsonify({"ok": False, "error": "invalid"}), 400
# =========================
# Commands
# =========================
@app.route("/api/command", methods=["POST"])
def api_command():
    """Send a command to a single student or all students in a class.

    Either `student` or `class_id` must be provided. We do NOT support
    global commands for all students at once.
    """
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    b = request.json or {}
    cmd = b.get("command")
    if not cmd or "type" not in cmd:
        return jsonify({"ok": False, "error": "invalid"}), 400

    student = (b.get("student") or "").strip()
    class_id = (b.get("class_id") or "").strip()
    d.setdefault("pending_commands", {})

    if student:
        # Direct student-targeted command
        d["pending_commands"].setdefault(student, []).append(cmd)
        target_desc = student
    elif class_id:
        # Fan out to all students in this class session
        classes = d.get("classes") or {}
        cls = classes.get(class_id, {})
        students = cls.get("students", []) or []
        for s in students:
            d["pending_commands"].setdefault(s, []).append(cmd)
        target_desc = f"class:{class_id}"
    else:
        return jsonify({"ok": False, "error": "missing student or class_id"}), 400

    save_data(d)
    log_action({"event": "command", "target": target_desc, "type": cmd.get("type")})
    return jsonify({"ok": True})


@app.route("/api/commands/<student>", methods=["GET", "POST"])
def api_commands(student):
    d = ensure_keys(load_data())

    if request.method == "GET":
        # Only deliver commands explicitly queued for this student.
        cmds = d.get("pending_commands", {}).get(student, [])
        d.setdefault("pending_commands", {})[student] = []
        save_data(d)
        return jsonify({"commands": cmds})

    # POST (push from teacher to a single student)
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    b = request.json or {}
    if not b.get("type"):
        return jsonify({"ok": False, "error": "missing type"}), 400

    d.setdefault("pending_commands", {}).setdefault(student, []).append(b)
    save_data(d)
    log_action({"event": "command_sent", "to": student, "cmd": b.get("type")})
    return jsonify({"ok": True})

# =========================
# Off-task Check (simple)
# =========================
@app.route("/api/offtask/check", methods=["POST"])
def api_offtask_check():
    b = request.json or {}
    student = (b.get("student") or "").strip()
    url = (b.get("url") or "")
    if not student or not url:
        return jsonify({"ok": False}), 400

    d = ensure_keys(load_data())
    # allowlist from policy (scene) if any
    scene_allowed = set()
    for patt in (d.get("policy", {}).get("allowlist") or []):
        m = re.match(r"\*\:\/\/\*\.(.+?)\/\*", patt)
        if m:
            scene_allowed.add(m.group(1).lower())

    host = ""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        pass

    on_task = any(host.endswith(dom) for dom in scene_allowed) if host else False
    bad_kw = ("coolmath", "roblox", "twitch", "steam", "epicgames")
    if any(k in url.lower() for k in bad_kw):
        on_task = False

    v = {"student": student, "url": url, "ts": int(time.time()), "on_task": bool(on_task)}
    d.setdefault("offtask_events", []).append(v)
    d["offtask_events"] = d["offtask_events"][-2000:]
    save_data(d)

    try:
        # If using socketio, you could emit here; safely ignore if not present
        from flask_socketio import SocketIO  # type: ignore
        socketio = SocketIO(message_queue=None)
        socketio.emit("offtask", v, broadcast=True)
    except Exception:
        pass

    return jsonify({"ok": True, "on_task": bool(on_task)})


# =========================
# Presence / Heartbeat
# =========================
@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    """Student heartbeat – updates presence, logs timeline, screenshots, and returns extension state."""
    b = request.json or {}
    student = (b.get("student") or "").strip().lower()
    display_name = b.get("student_name", "")

    # Global kill switch (safe if file type changed)
    data_global = ensure_keys(load_data())
    extension_enabled_global = bool(data_global.get("extension_enabled", True))

    # Hard-disable guest/anonymous identities – do NOT log or persist anything
    if _is_guest_identity(student, display_name):
        return jsonify({
            "ok": True,
            "server_time": int(time.time()),
            "extension_enabled": False  # completely disabled for guests
        })

    d = ensure_keys(load_data())
    d.setdefault("presence", {})

    if student:
        pres = d["presence"].setdefault(student, {})
        pres["last_seen"] = int(time.time())
        pres["student_name"] = display_name
        pres["tab"] = b.get("tab", {}) or {}
        pres["tabs"] = b.get("tabs", []) or []
        # support both camel and snake favicon key names
        if "favIconUrl" in pres.get("tab", {}):
            pass
        elif "favicon" in pres.get("tab", {}):
            pres["tab"]["favIconUrl"] = pres["tab"].get("favicon")

        pres["screenshot"] = b.get("screenshot", "") or ""

        # --- Keep only screenshots for open tabs shown in modal preview ---
        shots = pres.get("tabshots", {})
        for k, v in (b.get("tabshots", {}) or {}).items():
            shots[str(k)] = v
        open_ids = {str(t.get("id")) for t in pres["tabs"] if "id" in t}
        for k in list(shots.keys()):
            if k not in open_ids:
                del shots[k]
        pres["tabshots"] = shots
        d["presence"][student] = pres

        # ---------- Timeline & Screenshot history ----------
        try:
            timeline = d.setdefault("history", {}).setdefault(student, [])
            now = int(time.time())
            cur = pres.get("tab", {}) or {}
            url = (cur.get("url") or "").strip()
            title = (cur.get("title") or "").strip()
            fav = cur.get("favIconUrl")

            should_add = False
            if url:
                if not timeline:
                    should_add = True
                else:
                    last = timeline[-1]
                    if last.get("url") != url or now - int(last.get("ts", 0)) >= 15:
                        should_add = True

            if should_add:
                timeline.append({"ts": now, "title": title, "url": url, "favIconUrl": fav})
                d["history"][student] = timeline[-500:]  # cap

            # Screenshot history: if extension passes `shot_log: [{tabId,dataUrl,title,url}]`
            shot_log = b.get("shot_log") or []
            if shot_log:
                hist = d.setdefault("screenshots", {}).setdefault(student, [])
                for s in shot_log[:10]:
                    hist.append({
                        "ts": now,
                        "tabId": s.get("tabId"),
                        "dataUrl": s.get("dataUrl"),
                        "title": (s.get("title") or ""),
                        "url": (s.get("url") or "")
                    })
                d["screenshots"][student] = hist[-200:]
        except Exception as e:
            print("[WARN] Heartbeat logging error:", e)

    save_data(d)

    return jsonify({
        "ok": True,
        "server_time": int(time.time()),
        # Honor global kill switch but also keep guest lockout enforced above.
        "extension_enabled": bool(extension_enabled_global)
    })


@app.route("/api/presence")
def api_presence():
    """Return live presence/screen info for a specific class session.

    Requires ?class_id=XYZ. Only includes students assigned to that class,
    and hides all screens whenever the class is inactive.
    """
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    presence = d.get("presence", {}) or {}
    cid = (request.args.get("class_id") or "").strip()
    if not cid:
        # Strict mode: never return a global "everyone" view.
        return jsonify({})

    classes = d.get("classes") or {}
    cls = classes.get(cid)
    if not cls or not cls.get("active"):
        # When a class session is inactive, no screens are visible.
        return jsonify({})

    # Compare using normalized email addresses.
    allowed_students = set(
        (s or "").strip().lower() for s in cls.get("students") or [] if s
    )
    filtered = {}
    for s, info in presence.items():
        key = (s or "").strip().lower()
        if key in allowed_students:
            filtered[s] = info
    return jsonify(filtered)

@app.route("/api/extension/toggle", methods=["POST"])
def api_extension_toggle():
    """Toggle all student extensions (remote control by teacher/admin)."""
    user = current_user()
    if not user or user.get("role") not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}
    enabled = bool(body.get("enabled", True))

    data = ensure_keys(load_data())
    data["extension_enabled"] = enabled
    save_data(data)

    print(f"[INFO] Extension toggle → {'ENABLED' if enabled else 'DISABLED'} by {user.get('email')}")
    log_action({"event": "extension_toggle", "enabled": enabled, "by": user.get("email")})
    return jsonify({"ok": True, "extension_enabled": enabled})


# =========================
# Policy
# =========================

# =========================
# Policy helpers
# =========================

def _parse_hhmm(s):
    """Minimal HH:MM parser -> (hour, minute) or (None, None)"""
    if not s or not isinstance(s, str):
        return (None, None)
    parts = s.split(":")
    if len(parts) != 2:
        return (None, None)
    try:
        h = int(parts[0])
        m = int(parts[1])
        if 0 <= h < 24 and 0 <= m < 60:
            return (h, m)
    except Exception:
        pass
    return (None, None)



def _is_policy_schedule_active(policy, now_ts=None):
    """Return True if the policy is currently active based on its schedule.

    Rules:
    - If policy is not active (active=False) → always False.
    - If schedule.enabled is False or missing → always True.
    - If start/end are missing or invalid → treat as always on.
    - If weekdays_only is True → policy is inactive on Saturday/Sunday.
    - Supports overnight windows (e.g. 22:00–06:00).
    """
    if not policy or not policy.get("active", True):
        return False

    sched = (policy.get("schedule") or {})
    if not sched.get("enabled"):
        return True  # always on when schedule is disabled

    try:
        import time as _time
        import datetime as _dt
    except Exception:
        # If we cannot import time/datetime, fail open (treat as active)
        return True

    if now_ts is None:
        now_ts = int(_time.time())

    dt = _dt.datetime.fromtimestamp(now_ts)

    # Weekday filter (0 = Monday, 6 = Sunday)
    if sched.get("weekdays_only") and dt.weekday() >= 5:
        return False

    start_h, start_m = _parse_hhmm(sched.get("start") or "")
    end_h, end_m = _parse_hhmm(sched.get("end") or "")

    # If schedule fields are not set correctly, treat as always on
    if start_h is None or end_h is None:
        return True

    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    cur_min = dt.hour * 60 + dt.minute

    # If start == end → treat as "all day"
    if start_min == end_min:
        return True

    # Normal window (same day)
    if start_min < end_min:
        return start_min <= cur_min < end_min

    # Overnight window (e.g. 22:00–06:00)
    return cur_min >= start_min or cur_min < end_min
def _select_active_policy(data, student_email):
    """Determine the highest-priority policy that applies to this student.

    Emails can be assigned to multiple policies. We collect all applicable
    policy IDs and then choose the policy with the highest numeric priority
    (where 0 is the lowest priority).
    """
    data = ensure_keys(data or {})
    policies = data.get("policies", {}) or {}
    assigns = data.get("policy_assignments", {}) or {}

    # Normalize user assignment keys to lowercase and values to lists of IDs
    raw_user_map = assigns.get("users", {}) or {}
    user_map = {}
    for k, v in raw_user_map.items():
        email = (k or "").strip().lower()
        if not email:
            continue
        if isinstance(v, list):
            ids = [str(pid) for pid in v if pid]
        elif v:
            ids = [str(v)]
        else:
            ids = []
        if ids:
            user_map[email] = ids

    raw_group_map = assigns.get("groups", {}) or {}
    group_map = {}
    for k, v in raw_group_map.items():
        key = (k or "").strip()
        if not key:
            continue
        if isinstance(v, list):
            ids = [str(pid) for pid in v if pid]
        elif v:
            ids = [str(v)]
        else:
            ids = []
        if ids:
            group_map[key] = ids

    default_id = data.get("default_policy_id")
    applicable_ids = set()

    student_email = (student_email or "").strip().lower()
    if student_email and student_email in user_map:
        for pid in user_map.get(student_email) or []:
            applicable_ids.add(pid)

    # Class/group policies
    for cid, cls in (data.get("classes") or {}).items():
        try:
            students = cls.get("students") or []
        except Exception:
            students = []
        lowered = [(s or "").strip().lower() for s in students]
        if student_email and student_email in lowered:
            for pid in group_map.get(cid, []) or []:
                applicable_ids.add(pid)

    if not applicable_ids and default_id:
        applicable_ids.add(str(default_id))

    active = []
    for pid in applicable_ids:
        p = policies.get(pid)
        if not p:
            continue
        if _is_policy_schedule_active(p):
            active.append(p)

    if not active:
        return None

    active.sort(key=lambda p: int(p.get("priority", 0)), reverse=True)
    return active[0]


def _apply_policy_to_lists(base_allow, base_blocks, base_categories, policy):
    """Apply policy URLs and category overrides to the base lists/dict.

    - base_allow / base_blocks come from class + scenes
    - base_categories is the global categories dictionary
    - policy may define:
        * allow_urls
        * block_urls
        * blocked_categories
        * allowed_categories
    """
    allowlist = list(base_allow or [])
    teacher_blocks = list(base_blocks or [])
    categories = dict(base_categories or {})

    if not policy:
        return allowlist, teacher_blocks, categories

    # URL-level allow & block from the policy
    for url in (policy.get("allow_urls") or []):
        if url not in allowlist:
            allowlist.append(url)

    for url in (policy.get("block_urls") or []):
        if url not in teacher_blocks:
            teacher_blocks.append(url)

    # Category-level flags
    blocked = set()
    allowed = set()
    for name in (policy.get("blocked_categories") or []):
        if name:
            blocked.add(str(name))
    for name in (policy.get("allowed_categories") or []):
        if name:
            allowed.add(str(name))

    if blocked or allowed:
        updated = {}
        for name, cat in (categories or {}).items():
            if not isinstance(cat, dict):
                c = {"name": name, "blocked": False}
            else:
                c = dict(cat)
            if name in blocked:
                c["blocked"] = True
            elif name in allowed:
                c["blocked"] = False
            updated[name] = c
        categories = updated

    # 🔒 Manual URL blocks must always win over allow logic
    if teacher_blocks:
        blocked_set = set(teacher_blocks)
        allowlist = [u for u in allowlist if u not in blocked_set]

    return allowlist, teacher_blocks, categories



@app.route("/api/policy", methods=["POST"])
def api_policy():
    b = request.json or {}
    student = (b.get("student") or "").strip().lower()
    d = ensure_keys(load_data())

    # Choose an active class session for this student, if any.
    cid = None
    cls = None
    if student:
        cid, cls = _get_active_class_for_student(d, student)

    # Fallback to legacy default class
    if cls is None:
        classes = d.get("classes") or {}
        cls = classes.get("period1", {})
        cid = "period1"

    # Base flags from chosen class
    focus = bool(cls.get("focus_mode", False))
    paused = bool(cls.get("paused", False))

    # Per-student overrides
    if student:
        ov = (d.get("student_overrides") or {}).get(student, {}) or {}
        focus = bool(ov.get("focus_mode", focus))
        paused = bool(ov.get("paused", paused))

    # Per-student pending items (open_tabs etc)
    pending = []
    if student:
        pending_all = d.get("pending_per_student", {}) or {}
        pend = pending_all.get(student, []) or []
        if pend:
            pending = pend
            pending_all.pop(student, None)
            d["pending_per_student"] = pending_all
            save_data(d)

    
    # Scene merge logic — pull from regular scenes data
    store = _load_scenes()

    # Class‑wide scenes come from data.json (per‑class), falling back to
    # the global scenes["current"] only if no class‑specific config exists.
    class_scenes_map = d.get("class_scenes") or {}
    current_raw = None
    if cid:
        cur = class_scenes_map.get(cid)
        if cur:
            current_raw = cur

    if current_raw is None:
        current_raw = store.get("current") or []

    # Global/class scenes configured by admin/teacher
    if isinstance(current_raw, dict):
        base_current = [current_raw]
    elif isinstance(current_raw, list):
        base_current = [c for c in current_raw if c]
    else:
        base_current = []

    # Optional per-student scenes stored in data.json
    student_scenes_map = d.get("student_scenes") or {}
    per_student_list = []
    if student and student in student_scenes_map:
        raw_list = student_scenes_map.get(student) or []
        for c in raw_list:
            if not c:
                continue
            per_student_list.append(
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "type": c.get("type"),
                }
            )

    # Combine global/class + per-student scenes, de-duplicated by id
    combined = []
    seen_ids = set()
    for src in (base_current, per_student_list):
        for c in src:
            if not c:
                continue
            sid = c.get("id")
            if sid is None:
                continue
            key = str(sid)
            if key in seen_ids:
                continue
            seen_ids.add(key)
            combined.append(c)

    current_list = combined



    # Start with class-level lists
    allowlist = list(cls.get("allowlist", []))
    teacher_blocks = list(cls.get("teacher_blocks", []))
    categories = d.get("categories", {}) or {}

    if current_list:
        scene_index = {}
        for bucket in ("allowed", "blocked"):
            for s in store.get(bucket, []) or []:
                sid = str(s.get("id"))
                if sid:
                    scene_index[sid] = s

        for cur in current_list:
            scene_obj = scene_index.get(str(cur.get("id")))
            if not scene_obj:
                continue
            if scene_obj.get("type") == "allowed":
                allowlist = list(allowlist) + list(scene_obj.get("allow", []))
                focus = True
            elif scene_obj.get("type") == "blocked":
                teacher_blocks = list(teacher_blocks) + list(scene_obj.get("block", []))

        # Dedup
        seen = set()
        dedup_allow = []
        for url in allowlist:
            if url not in seen:
                seen.add(url)
                dedup_allow.append(url)
        allowlist = dedup_allow

        seen = set()
        dedup_blocks = []
        for url in teacher_blocks:
            if url not in seen:
                seen.add(url)
                dedup_blocks.append(url)
        teacher_blocks = dedup_blocks

    # Which policy applies?
    active_policy = _select_active_policy(d, student)

    ap = None
    if active_policy:
        ap = {
            "id": active_policy.get("id"),
            "name": active_policy.get("name"),
            "priority": int(active_policy.get("priority", 0)),
            "blocked_categories": active_policy.get("blocked_categories") or [],
            "allow_urls": active_policy.get("allow_urls") or [],
            "block_urls": active_policy.get("block_urls") or [],
            "schedule": active_policy.get("schedule") or {},
        }

    scenes_current = current_list

    resp = {
        "blocked_redirect": d.get("settings", {}).get(
            "blocked_redirect", "https://blocked.gdistrict.org/Gschool%20block"
        ),
        "active_policy": ap,
        "focus_mode": bool(focus),
        "paused": bool(paused),
        "announcement": d.get("announcements", ""),
        "class": {
            "id": cid,
            "name": cls.get("name", "Class Session"),
            "active": bool(cls.get("active", False)),
        },
        "allowlist": allowlist,
        "teacher_blocks": teacher_blocks,
        "chat_enabled": d.get("settings", {}).get("chat_enabled", False),
        "pending": pending,
        "ts": int(time.time()),
        "scenes": {"current": scenes_current},
        "bypass_enabled": bool(d.get("settings", {}).get("bypass_enabled", False)),
        "bypass_ttl_minutes": int(d.get("settings", {}).get("bypass_ttl_minutes", 10)),
    }
    return jsonify(resp)


# =========================
# Timeline & Screenshots
# =========================
@app.route("/api/bypass", methods=["POST"])
def api_bypass():
    """
    Called by the block page / extension when a user enters the bypass code.
    Supports MULTIPLE active bypass codes with TTL.
    """
    d = ensure_keys(load_data())
    b = request.json or {}

    code = (b.get("code") or "").strip()
    url = (b.get("url") or "").strip()
    user = (b.get("user") or "").strip()

    settings = d.get("settings", {})
    if not settings.get("bypass_enabled"):
        return jsonify({"ok": False, "allow": False, "error": "disabled"}), 403

    # Remove expired codes first
    _clean_expired_bypass_codes(settings)

    hashed = _hash_code(code)
    valid = any(
        c.get("hash") == hashed
        for c in settings.get("bypass_codes", [])
    )

    if not valid:
        save_data(d)  # persist cleanup
        return jsonify({"ok": False, "allow": False, "error": "invalid"}), 403

    log_action({
        "event": "bypass_used",
        "user": user,
        "url": url
    })

    save_data(d)
    return jsonify({"ok": True, "allow": True})

# =========================
# Policy Management APIs
# =========================

@app.route("/api/policies", methods=["GET", "POST", "DELETE"])
def api_policies():
    u = current_user()
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    policies = d.get("policies", {})

    if request.method == "GET":
        return jsonify({
            "ok": True,
            "policies": policies,
            "default_policy_id": d.get("default_policy_id"),
        })

    body = request.json or {}
    if request.method == "DELETE":
        pid = (body.get("id") or "").strip()
        if pid and pid in policies:
            policies.pop(pid, None)
            d["policies"] = policies
            if d.get("default_policy_id") == pid:
                d["default_policy_id"] = None
            assigns = d.get("policy_assignments", {})
            for k in ("users", "groups"):
                mp = assigns.get(k, {})
                assigns[k] = {k2: v2 for k2, v2 in mp.items() if v2 != pid}
            d["policy_assignments"] = assigns
            save_data(d)
        return jsonify({"ok": True})

    pid = (body.get("id") or "").strip()
    if not pid:
        pid = str(uuid.uuid4())

    name = (body.get("name") or "").strip() or "Untitled Policy"
    priority = int(body.get("priority", 0))
    active = bool(body.get("active", True))
    blocked_categories = body.get("blocked_categories") or []
    allowed_categories = body.get("allowed_categories") or []
    block_urls = body.get("block_urls") or []
    allow_urls = body.get("allow_urls") or []
    schedule = body.get("schedule") or {}

    policies[pid] = {
        "id": pid,
        "name": name,
        "priority": priority,
        "active": active,
        "blocked_categories": blocked_categories,
        "allowed_categories": allowed_categories,
        "block_urls": block_urls,
        "allow_urls": allow_urls,
        "schedule": schedule,
    }
    d["policies"] = policies

    if "default_policy_id" in body:
        d["default_policy_id"] = body.get("default_policy_id")

    save_data(d)
    return jsonify({"ok": True, "id": pid, "policy": policies[pid]})



@app.route("/api/policy_assignments", methods=["GET", "POST"])
@app.route("/api/policy_assignments", methods=["GET", "POST"])
def api_policy_assignments():
    u = current_user()
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    d.setdefault("policy_assignments", {})
    d["policy_assignments"].setdefault("users", {})
    d["policy_assignments"].setdefault("groups", {})

    if request.method == "GET":
        return jsonify({
            "ok": True,
            "policy_assignments": d["policy_assignments"],
            "default_policy_id": d.get("default_policy_id"),
        })

    body = request.json or {}
    assigns = d["policy_assignments"]
    users = assigns.setdefault("users", {})
    groups = assigns.setdefault("groups", {})

    policy_id = (body.get("policy_id") or "").strip()

    if isinstance(body.get("users"), dict):
        if policy_id:
            for raw_email, flag in body["users"].items():
                email = (raw_email or "").strip().lower()
                if not email:
                    continue
                current = users.get(email)
                if isinstance(current, list):
                    cur_list = [str(x) for x in current if x]
                elif current:
                    cur_list = [str(current)]
                else:
                    cur_list = []
                flag_bool = bool(flag)
                if flag_bool:
                    if policy_id not in cur_list:
                        cur_list.append(policy_id)
                else:
                    cur_list = [pid for pid in cur_list if pid != policy_id]
                if cur_list:
                    users[email] = cur_list
                else:
                    users.pop(email, None)
        else:
            new_map = {}
            for raw_email, val in body["users"].items():
                email = (raw_email or "").strip().lower()
                if not email:
                    continue
                if isinstance(val, list):
                    ids = [str(pid) for pid in val if pid]
                elif val:
                    ids = [str(val)]
                else:
                    ids = []
                if ids:
                    new_map[email] = ids
            users.update(new_map)

    if isinstance(body.get("groups"), dict):
        for key, val in body["groups"].items():
            gkey = (key or "").strip()
            if not gkey:
                continue
            if isinstance(val, list):
                ids = [str(pid) for pid in val if pid]
            elif val:
                ids = [str(val)]
            else:
                ids = []
            if ids:
                groups[gkey] = ids
            else:
                groups.pop(gkey, None)

    if "default_policy_id" in body:
        d["default_policy_id"] = body.get("default_policy_id")

    d["policy_assignments"] = assigns
    save_data(d)
    return jsonify({"ok": True, "policy_assignments": assigns, "default_policy_id": d.get("default_policy_id")})


@app.route("/api/timeline", methods=["GET"])
def api_timeline():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    student = (request.args.get("student") or "").strip()
    limit = max(1, min(int(request.args.get("limit", 200)), 1000))
    since = int(request.args.get("since", 0))
    out = []
    if student:
        out = [e for e in d.get("history", {}).get(student, []) if e.get("ts", 0) >= since]
        out.sort(key=lambda x: x.get("ts", 0))
    else:
        for s, arr in (d.get("history", {}) or {}).items():
            for e in arr:
                if e.get("ts", 0) >= since:
                    out.append(dict(e, student=s))
        out.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return jsonify({"ok": True, "items": out[-limit:]})

@app.route("/api/screenshots", methods=["GET"])
def api_screenshots():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    student = (request.args.get("student") or "").strip()
    limit = max(1, min(int(request.args.get("limit", 100)), 500))
    items = []

    if student:
        items = list(d.get("screenshots", {}).get(student, []))
        for it in items:
            it.setdefault("student", student)
    else:
        for s, arr in (d.get("screenshots", {}) or {}).items():
            for e in arr:
                items.append(dict(e, student=s))
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)

    return jsonify({"ok": True, "items": items[-limit:]})


# =========================
# Alerts (Off-task)
# =========================
@app.route("/api/alerts", methods=["GET", "POST"])
def api_alerts():
    d = ensure_keys(load_data())
    if request.method == "POST":
        b = request.json or {}
        u = current_user()
        student = (b.get("student") or (u["email"] if (u and u.get("role") == "student") else "")).strip()
        if not student:
            return jsonify({"ok": False, "error": "student required"}), 400
        item = {
            "ts": int(time.time()),
            "student": student,
            "kind": b.get("kind", "off_task"),
            "score": float(b.get("score") or 0.0),
            "title": (b.get("title") or ""),
            "url": (b.get("url") or ""),
            "note": (b.get("note") or "")
        }
        d.setdefault("alerts", []).append(item)
        d["alerts"] = d["alerts"][-500:]
        save_data(d)
        log_action({"event": "alert", "student": student, "kind": item["kind"], "score": item["score"]})
        return jsonify({"ok": True})

    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "items": d.get("alerts", [])[-200:]})


@app.route("/api/alerts/clear", methods=["POST"])
def api_alerts_clear():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    b = request.json or {}
    student = (b.get("student") or "").strip()
    d = ensure_keys(load_data())
    if student:
        d["alerts"] = [a for a in d.get("alerts", []) if a.get("student") != student]
    else:
        d["alerts"] = []
    save_data(d)
    return jsonify({"ok": True})


# =========================
# Engagement API (NEW)
# =========================
@app.route("/api/engagement")
def api_engagement():
    """
    Simple engagement score per student over a time window.
    Query param: window (seconds) -> default 1800, min 60, max 14400.
    """
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    try:
        window = int(request.args.get("window", 1800))
    except Exception:
        window = 1800
    window = max(60, min(window, 14400))

    now = int(time.time())
    since = now - window

    d = ensure_keys(load_data())
    presence = d.get("presence", {}) or {}
    history = d.get("history", {}) or {}
    off_events = d.get("offtask_events", []) or []
    alerts = d.get("alerts", []) or []

    students = set(presence.keys())
    for student, arr in history.items():
        if any((e.get("ts") or 0) >= since for e in (arr or [])):
            students.add(student)

    results = []
    for student in sorted(students):
        if not student:
            continue

        hist = [e for e in (history.get(student) or []) if (e.get("ts") or 0) >= since]
        total_events = len(hist)

        student_off = [
            e for e in off_events
            if (e.get("student") == student and (e.get("ts") or 0) >= since and not bool(e.get("on_task", True)))
        ]
        off_count = len(student_off)

        student_alerts = [a for a in alerts if (a.get("student") == student and (a.get("ts") or 0) >= since)]
        alerts_count = len(student_alerts)

        if total_events > 0:
            ratio = off_count / float(total_events)
            engagement = max(0.0, min(1.0, 1.0 - ratio))
        else:
            engagement = 1.0  # neutral if no events

        risk = "low"
        if engagement < 0.6 or off_count >= 5 or alerts_count >= 3:
            risk = "medium"
        if engagement < 0.4 or off_count >= 10 or alerts_count >= 5:
            risk = "high"

        pres = presence.get(student) or {}
        tabs_open = len(pres.get("tabs") or []) if isinstance(pres.get("tabs"), list) else 0

        results.append({
            "student": student,
            "engagement": engagement,
            "offtask_events": off_count,
            "alerts": alerts_count,
            "tabs_open": tabs_open,
            "last_seen": pres.get("last_seen") or 0,
            "risk": risk
        })

    return jsonify({"ok": True, "window": window, "since": since, "now": now, "students": results})


# =========================
# Scenes API
# =========================

@app.route("/api/scenes", methods=["GET"])
def api_scenes_list():
    """List all available scenes plus the currently applied scene(s).

    If ?class_id=XYZ is provided, the "current" field reflects the
    scenes applied to that specific class session. Otherwise it falls
    back to the global scenes store.
    """
    scenes = _load_scenes()
    cid = (request.args.get("class_id") or "").strip()
    if not cid:
        return jsonify(scenes)

    d = ensure_keys(load_data())
    current_map = d.get("class_scenes", {}) or {}
    current_list = current_map.get(cid) or []
    out = dict(scenes)
    out["current"] = current_list
    return jsonify(out)

@app.route("/api/scenes", methods=["POST"])
def api_scenes_create():
    body = request.json or {}
    name = body.get("name")
    s_type = body.get("type")  # "allowed" or "blocked"
    if not name or s_type not in ("allowed", "blocked"):
        return jsonify({"ok": False, "error": "name and valid type required"}), 400

    scenes = _load_scenes()
    new_scene = {
        "id": str(int(time.time() * 1000)),
        "name": name,
        "type": s_type,
        "allow": body.get("allow", []),
        "block": body.get("block", []),
        "icon": body.get("icon", "blue")
    }
    scenes[s_type].append(new_scene)
    _save_scenes(scenes)

    log_action({"event": "scene_create", "id": new_scene["id"], "name": name})
    return jsonify({"ok": True, "scene": new_scene})

@app.route("/api/scenes/<sid>", methods=["PUT"])
def api_scenes_update(sid):
    body = request.json or {}
    scenes = _load_scenes()
    updated = None
    for bucket in ("allowed", "blocked"):
        for s in scenes.get(bucket, []):
            if s.get("id") == sid:
                s.update(body)
                updated = s
                break
    if not updated:
        return jsonify({"ok": False, "error": "not found"}), 404
    _save_scenes(scenes)
    log_action({"event": "scene_update", "id": sid})
    return jsonify({"ok": True, "scene": updated})

@app.route("/api/scenes/<sid>", methods=["DELETE"])
@app.route("/api/scenes/<sid>", methods=["DELETE"])
def api_scenes_delete(sid):
    scenes = _load_scenes()
    for bucket in ("allowed", "blocked"):
        scenes[bucket] = [s for s in scenes.get(bucket, []) if s.get("id") != sid]

    cur = scenes.get("current") or []
    if isinstance(cur, dict):
        cur_list = [cur]
    elif isinstance(cur, list):
        cur_list = [c for c in cur if c]
    else:
        cur_list = []

    cur_list = [c for c in cur_list if str(c.get("id")) != str(sid)]
    scenes["current"] = cur_list
    _save_scenes(scenes)
    log_action({"event": "scene_delete", "id": sid})
    return jsonify({"ok": True})


@app.route("/api/scenes/export", methods=["GET"])
def api_scenes_export():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    store = _load_scenes()
    scene_id = request.args.get("id")
    if scene_id:
        for bucket in ("allowed", "blocked"):
            for s in store.get(bucket, []):
                if s.get("id") == scene_id:
                    return jsonify({"ok": True, "scene": s})
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "scenes": store})

@app.route("/api/scenes/import", methods=["POST"])
def api_scenes_import():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    body = request.json or {}
    store = _load_scenes()
    if "scene" in body:
        sc = dict(body["scene"])
        sc["id"] = sc.get("id") or ("scene_" + str(int(time.time() * 1000)))
        if sc.get("type") == "allowed":
            store.setdefault("allowed", []).append(sc)
        else:
            sc["type"] = "blocked"
            store.setdefault("blocked", []).append(sc)
        _save_scenes(store)
        return jsonify({"ok": True, "id": sc["id"]})
    elif "scenes" in body:
        _save_scenes(body["scenes"])
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "invalid payload"}), 400



@app.route("/api/scenes/apply", methods=["POST"])
def api_scenes_apply():
    """
    Apply a scene to the whole class or a subset of students.

    JSON body:
      - scene_id / id: ID of the scene to apply.
      - class_id: optional class session id. Required for class‑wide apply
                  from the teacher UI, so scenes are per‑class not global.
      - disable: bool – if true, clears scenes (class‑wide if class_id is
                  provided, otherwise global legacy behaviour).
      - replace: bool – if true, replaces current scenes instead of appending.
      - students: optional list of student emails – if present, the scene is
                  applied only to those students (per‑student scenes).
    """
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}
    sid = body.get("id") or body.get("scene_id")
    disable = bool(body.get("disable", False))
    replace_mode = bool(body.get("replace", False))
    class_id = (body.get("class_id") or "").strip()

    store = _load_scenes()

    # Disable scenes – class‑scoped when class_id is provided, otherwise global.
    if disable:
        d = ensure_keys(load_data())
        if class_id:
            classes = d.get("classes") or {}
            cls = classes.get(class_id) or {}
            students = [
                (s or "").strip().lower()
                for s in cls.get("students") or []
                if s and "@" in str(s)
            ]

            # Clear class‑wide scenes for this session.
            cs_map = d.setdefault("class_scenes", {})
            cs_map[class_id] = []

            # Optionally clear per‑student scenes for students in this class.
            student_scenes = d.setdefault("student_scenes", {})
            for stu in students:
                if stu in student_scenes:
                    student_scenes.pop(stu, None)
                d.setdefault("pending_per_student", {}).setdefault(stu, []).append(
                    {"type": "policy_refresh"}
                )

            save_data(d)
            log_action({"event": "scene_disabled_class", "class_id": class_id})
            return jsonify({"ok": True, "current": []})
        else:
            # Legacy global disable – keep behaviour but do not push a global "*" command.
            store["current"] = []
            _save_scenes(store)

            d["student_scenes"] = {}
            d["class_scenes"] = {}
            save_data(d)
            log_action({"event": "scene_disabled_global"})
            return jsonify({"ok": True, "current": []})

    if not sid:
        return jsonify({"ok": False, "error": "scene_id required"}), 400

    # Resolve the scene object from the global scenes library.
    found = None
    for bucket in ("allowed", "blocked"):
        for s in store.get(bucket, []) or []:
            if str(s.get("id")) == str(sid):
                found = {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "type": s.get("type") or bucket.rstrip("d"),  # "allowed"/"blocked"
                }
                break
        if found:
            break

    if not found:
        return jsonify({"ok": False, "error": "scene not found"}), 404

    d = ensure_keys(load_data())

    # Optional per‑student targeting.
    students = body.get("students") or []
    if students:
        student_scenes = d.setdefault("student_scenes", {})
        norm_students = []
        for stu in students:
            if not stu:
                continue
            s_norm = str(stu).strip().lower()
            if s_norm and "@" in s_norm:
                norm_students.append(s_norm)

        for stu in norm_students:
            cur_list = list(student_scenes.get(stu) or [])
            if replace_mode:
                cur_list = [found]
            else:
                # Append if not already present for that student
                existing_ids = {str(c.get("id")) for c in cur_list}
                if str(found.get("id")) not in existing_ids:
                    cur_list.append(found)
            student_scenes[stu] = cur_list

            # Push a per‑student policy refresh so the extension re‑loads policy.
            d.setdefault("pending_per_student", {}).setdefault(stu, []).append(
                {"type": "policy_refresh"}
            )

        save_data(d)
        log_action(
            {"event": "scene_applied_students", "scene": found, "students": norm_students}
        )

        # For teacher UI, return the class‑specific current scene list if available.
        if class_id:
            current_map = d.get("class_scenes", {}) or {}
            return jsonify({"ok": True, "current": current_map.get(class_id) or []})
        else:
            return jsonify({"ok": True, "current": store.get("current") or []})

    # No explicit students → class‑wide behaviour.
    if class_id:
        # Apply to a specific class session only.
        cs_map = d.setdefault("class_scenes", {})
        current_raw = cs_map.get(class_id) or []
    else:
        # Legacy global behaviour – operate on scenes["current"].
        current_raw = store.get("current") or []

    if isinstance(current_raw, dict):
        current_list = [current_raw]
    elif isinstance(current_raw, list):
        current_list = [c for c in current_raw if c]
    else:
        current_list = []

    if replace_mode:
        current_list = [found]
    else:
        existing_ids = {str(c.get("id")) for c in current_list}
        if str(found.get("id")) not in existing_ids:
            current_list.append(found)

    if class_id:
        cs_map = d.setdefault("class_scenes", {})
        cs_map[class_id] = current_list

        # Push per‑student policy refresh for every student in this class.
        classes = d.get("classes") or {}
        cls = classes.get(class_id) or {}
        students = [
            (s or "").strip().lower()
            for s in cls.get("students") or []
            if s and "@" in str(s)
        ]
        for stu in students:
            d.setdefault("pending_per_student", {}).setdefault(stu, []).append(
                {"type": "policy_refresh"}
            )
        save_data(d)
    else:
        # Legacy global update of scenes["current"].
        store["current"] = current_list
        _save_scenes(store)
        save_data(d)

    log_action({"event": "scene_applied", "scene": found, "class_id": class_id or None})
    return jsonify({"ok": True, "current": current_list})


@app.route("/api/scenes/clear", methods=["POST"])
@app.route("/api/scenes/clear", methods=["POST"])
def api_scenes_clear():
    """Clear all scenes globally and per‑class.

    This is primarily an admin/maintenance endpoint. Teacher‑scoped
    scene clearing should use /api/scenes/apply with {"disable": true,
    "class_id": "..."} instead.
    """
    scenes = _load_scenes()
    scenes["current"] = []
    _save_scenes(scenes)
    log_action({"event": "scene_clear"})

    d = ensure_keys(load_data())
    d["student_scenes"] = {}
    d["class_scenes"] = {}
    save_data(d)
    return jsonify({"ok": True})

@app.route("/api/scenes/set_default", methods=["POST"])
def api_scenes_set_default():
    """Mark a scene as the default classroom scene (used by teacher UI)."""
    u = current_user()
    if not u or u.get("role") not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}
    sid = body.get("scene_id") or body.get("id")
    if not sid:
        return jsonify({"ok": False, "error": "scene_id required"}), 400

    scenes = _load_scenes()
    # Verify the scene exists
    exists = False
    for bucket in ("allowed", "blocked"):
        for s in scenes.get(bucket, []) or []:
            if str(s.get("id")) == str(sid):
                exists = True
                break
        if exists:
            break

    if not exists:
        return jsonify({"ok": False, "error": "scene not found"}), 404

    scenes["default_id"] = sid
    _save_scenes(scenes)
    log_action({"event": "scene_set_default", "id": sid})
    return jsonify({"ok": True, "default_id": sid})



@app.route("/api/dm/send", methods=["POST"])
def api_dm_send():
    body = request.json or {}
    u = current_user()

    if not u:
        if body.get("from") == "student" and body.get("student"):
            u = {"email": body["student"], "role": "student"}

    if not u:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400

    if u["role"] == "student":
        room = f"dm:{u['email']}"
        role = "student"; user_id = u["email"]
    elif u["role"] in ("teacher", "admin"):
        # allow admins to send DMs same as teachers
        student = body.get("student")
        if not student:
            return jsonify({"ok": False, "error": "no student"}), 400
        room = f"dm:{student}"
        role = "teacher"; user_id = u["email"]
    else:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    con = db(); cur = con.cursor()
    cur.execute(
        "INSERT INTO chat_messages(room,user_id,role,text,ts) VALUES(?,?,?,?,?)",
        (room, user_id, role, text, int(time.time())),
    )
    con.commit(); con.close()
    return jsonify({"ok": True})

@app.route("/api/dm/me", methods=["GET"])
def api_dm_me():
    u = current_user()
    student = None

    if u and u["role"] == "student":
        student = u["email"]
    if not student:
        student = request.args.get("student")

    if not student:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    con = db(); cur = con.cursor()
    cur.execute("SELECT user_id,role,text,ts FROM chat_messages WHERE room=? ORDER BY ts ASC", (f"dm:{student}",))
    msgs = [{"from": r[1], "user": r[0], "text": r[2], "ts": r[3]} for r in cur.fetchall()]
    con.close()
    return jsonify(msgs)

@app.route("/api/dm/<student>", methods=["GET"])
def api_dm_get(student):
    u = current_user()
    if not u:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    msgs = d.get("dm", {}).get(student, [])[-200:]
    return jsonify({"messages": msgs})

@app.route("/api/dm/unread", methods=["GET"])
def api_dm_unread():
    d = ensure_keys(load_data())
    out = {}
    for student, msgs in d.get("dm", {}).items():
        out[student] = sum(1 for m in msgs if m.get("from") == "student" and m.get("unread", True))
    return jsonify(out)

@app.route("/api/dm/mark_read", methods=["POST"])
def api_dm_mark_read():
    body = request.json or {}
    student = body.get("student")
    d = ensure_keys(load_data())
    if student in d.get("dm", {}):
        for m in d["dm"][student]:
            if m.get("from") == "student":
                m["unread"] = False
        save_data(d)
    return jsonify({"ok": True})


# =========================
# Attention Check
# =========================
@app.route("/api/attention_check", methods=["POST"])
def api_attention_check():
    body = request.json or {}
    title = body.get("title", "Are you paying attention?")
    timeout = int(body.get("timeout", 30))

    d = ensure_keys(load_data())
    d["attention_check"] = {"title": title, "timeout": timeout, "ts": int(time.time()), "responses": {}}

    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "attention_check",
        "title": title,
        "timeout": timeout
    })
    save_data(d)
    log_action({"event": "attention_check_start", "title": title})
    return jsonify({"ok": True})

@app.route("/api/attention_response", methods=["POST"])
def api_attention_response():
    b = request.json or {}
    student = (b.get("student") or "").strip()
    response = b.get("response", "")
    d = ensure_keys(load_data())
    check = d.get("attention_check")
    if not check:
        return jsonify({"ok": False, "error": "no active check"}), 400
    check["responses"][student] = {"response": response, "ts": int(time.time())}
    save_data(d)
    log_action({"event": "attention_response", "student": student, "response": response})
    return jsonify({"ok": True})

@app.route("/api/attention_results")
def api_attention_results():
    d = ensure_keys(load_data())
    return jsonify(d.get("attention_check", {}))


# =========================
# Per-Student Controls
# =========================
@app.route("/api/student/set", methods=["POST"])
def api_student_set():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    b = request.json or {}
    student = (b.get("student") or "").strip()
    if not student:
        return jsonify({"ok": False, "error": "student required"}), 400
    d = ensure_keys(load_data())
    ov = d.setdefault("student_overrides", {}).setdefault(student, {})
    if "focus_mode" in b:
        ov["focus_mode"] = bool(b.get("focus_mode"))
    if "paused" in b:
        ov["paused"] = bool(b.get("paused"))
    save_data(d)
    log_action({"event": "student_set", "student": student, "focus_mode": ov.get("focus_mode"), "paused": ov.get("paused")})
    return jsonify({"ok": True, "overrides": ov})

@app.route("/api/open_tabs", methods=["POST"])
def api_open_tabs_alias():
    """Teacher request to open URLs on student devices.

    If `student` is provided, only that student is targeted.
    Otherwise, `class_id` must be provided and only students in that
    class session receive the command. There is no global broadcast.
    """
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    b = request.json or {}
    urls = b.get("urls") or []
    student = (b.get("student") or "").strip()
    class_id = (b.get("class_id") or "").strip()
    if not urls:
        return jsonify({"ok": False, "error": "urls required"}), 400

    d = ensure_keys(load_data())
    d.setdefault("pending_commands", {})

    if student:
        pend = d.setdefault("pending_per_student", {})
        arr = pend.setdefault(student, [])
        arr.append({"type": "open_tabs", "urls": urls, "ts": int(time.time())})
        arr[:] = arr[-50:]
        log_action({"event": "student_tabs", "student": student, "type": "open_tabs", "count": len(urls)})
    elif class_id:
        classes = d.get("classes") or {}
        cls = classes.get(class_id, {})
        students = cls.get("students", []) or []
        for s in students:
            d["pending_commands"].setdefault(s, []).append({"type": "open_tabs", "urls": urls, "ts": int(time.time())})
        log_action({"event": "class_tabs", "target": class_id, "type": "open_tabs", "count": len(urls)})
    else:
        return jsonify({"ok": False, "error": "missing student or class_id"}), 400

    save_data(d)
    return jsonify({"ok": True})
@app.route("/api/student/tabs_action", methods=["POST"])
def api_student_tabs_action():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    b = request.json or {}
    student = (b.get("student") or "").strip()
    action = (b.get("action") or "").strip()  # 'restore_tabs' | 'close_tabs'
    if not student or action not in ("restore_tabs", "close_tabs"):
        return jsonify({"ok": False, "error": "student and valid action required"}), 400
    d = ensure_keys(load_data())
    pend = d.setdefault("pending_per_student", {})
    arr = pend.setdefault(student, [])
    arr.append({"type": action, "ts": int(time.time())})
    arr[:] = arr[-50:]
    save_data(d)
    log_action({"event": "student_tabs", "student": student, "type": action})
    return jsonify({"ok": True})


# =========================
# Class Chat
# =========================
@app.route("/api/chat/<class_id>", methods=["GET", "POST"])
def api_chat(class_id):
    d = ensure_keys(load_data())
    d.setdefault("chat", {}).setdefault(class_id, [])
    if request.method == "POST":
        b = request.json or {}
        txt = (b.get("text") or "")[:500]
        sender = b.get("from") or "student"
        if not txt:
            return jsonify({"ok": False, "error": "empty"}), 400
        d["chat"][class_id].append({"from": sender, "text": txt, "ts": int(time.time())})
        d["chat"][class_id] = d["chat"][class_id][-200:]
        save_data(d)
        return jsonify({"ok": True})
    return jsonify({"enabled": d.get("settings", {}).get("chat_enabled", False), "messages": d["chat"][class_id][-100:]})


# =========================
# Raise Hand
# =========================
@app.route("/api/raise_hand", methods=["POST"])
def api_raise_hand():
    b = request.json or {}
    student = (b.get("student") or "").strip()
    note = (b.get("note") or "").strip()
    d = ensure_keys(load_data())
    d.setdefault("raises", [])
    d["raises"].append({"student": student, "note": note, "ts": int(time.time())})
    d["raises"] = d["raises"][-200:]
    save_data(d)
    log_action({"event": "raise_hand", "student": student})
    return jsonify({"ok": True})

@app.route("/api/raise_hand", methods=["GET"])
def get_hands():
    d = ensure_keys(load_data())
    return jsonify({"hands": d.get("raises", [])})

@app.route("/api/raise_hand/clear", methods=["POST"])
def clear_hand():
    b = request.json or {}
    student = (b.get("student") or "").strip()
    d = ensure_keys(load_data())
    lst = d.get("raises", [])
    if student:
        lst = [r for r in lst if r.get("student") != student]
    else:
        lst = []
    d["raises"] = lst
    save_data(d)
    return jsonify({"ok": True, "remaining": len(lst)})


# =========================
# YouTube / Doodle settings
# =========================
@app.route("/api/youtube_rules", methods=["GET", "POST"])
def api_youtube_rules():
    if request.method == "POST":
        body = request.json or {}
        set_setting("yt_block_keywords", body.get("block_keywords", []))
        set_setting("yt_block_channels", body.get("block_channels", []))
        set_setting("yt_allow", body.get("allow", []))
        set_setting("yt_allow_mode", bool(body.get("allow_mode", False)))

        # Broadcast an update command to all present students
        d = ensure_keys(load_data())
        d.setdefault("pending_commands", {}).setdefault("*", []).append({
            "type": "update_youtube_rules",
            "rules": {
                "block_keywords": body.get("block_keywords", []),
                "block_channels": body.get("block_channels", []),
                "allow": body.get("allow", []),
                "allow_mode": bool(body.get("allow_mode", False))
            }
        })
        save_data(d)

        log_action({"event": "youtube_rules_update"})
        return jsonify({"ok": True})

    rules = {
        "block_keywords": get_setting("yt_block_keywords", []),
        "block_channels": get_setting("yt_block_channels", []),
        "allow": get_setting("yt_allow", []),
        "allow_mode": bool(get_setting("yt_allow_mode", False)),
    }
    return jsonify(rules)

@app.route("/api/doodle_block", methods=["GET", "POST"])
def api_doodle_block():
    if request.method == "POST":
        body = request.json or {}
        enabled = bool(body.get("enabled", False))
        set_setting("block_google_doodles", enabled)
        log_action({"event": "doodle_block_update", "enabled": enabled})
        return jsonify({"ok": True, "enabled": enabled})
    return jsonify({"enabled": bool(get_setting("block_google_doodles", False))})


# =========================
# Global Overrides (Admin)
# =========================
@app.route("/api/overrides", methods=["GET"])
def api_get_overrides():
    d = ensure_keys(load_data())
    return jsonify({
        "allowlist": d.get("allowlist", []),
        "teacher_blocks": d.get("teacher_blocks", [])
    })

@app.route("/api/overrides", methods=["POST"])
def api_save_overrides():
    u = current_user()
    if not u or u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    b = request.json or {}
    d["allowlist"] = b.get("allowlist", [])
    d["teacher_blocks"] = b.get("teacher_blocks", [])

    # Policy changed → force refresh for all students
    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "policy_refresh"
    })

    save_data(d)
    log_action({"event": "overrides_save"})
    return jsonify({"ok": True})


# =========================
# Poll
# =========================
@app.route("/api/poll", methods=["POST"])
def api_poll():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    body = request.json or {}
    q = (body.get("question") or "").strip()
    opts = [o.strip() for o in (body.get("options") or []) if o and o.strip()]
    if not q or not opts:
        return jsonify({"ok": False, "error": "question and options required"}), 400
    poll_id = "poll_" + str(int(time.time() * 1000))
    d = ensure_keys(load_data())
    d.setdefault("polls", {})[poll_id] = {"question": q, "options": opts, "responses": []}
    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "poll", "id": poll_id, "question": q, "options": opts
    })
    save_data(d)
    log_action({"event": "poll_create", "poll_id": poll_id})
    return jsonify({"ok": True, "poll_id": poll_id})

@app.route("/api/poll_response", methods=["POST"])
def api_poll_response():
    b = request.json or {}
    poll_id = b.get("poll_id")
    answer = b.get("answer")
    student = (b.get("student") or "").strip()
    if not poll_id:
        return jsonify({"ok": False, "error": "no poll id"}), 400
    d = ensure_keys(load_data())
    if poll_id not in d.get("polls", {}):
        return jsonify({"ok": False, "error": "unknown poll"}), 404
    d["polls"][poll_id].setdefault("responses", []).append({
        "student": student,
        "answer": answer,
        "ts": int(time.time())
    })
    save_data(d)
    log_action({"event": "poll_response", "poll_id": poll_id, "student": student})
    return jsonify({"ok": True})


# =========================
# State (feature flags bucket)
# =========================
@app.route("/api/state")
def api_state():
    d = ensure_keys(load_data())
    yt_rules = {
        "block": get_setting("yt_block_keywords", []),
        "allow": get_setting("yt_allow", []),
        "allow_mode": bool(get_setting("yt_allow_mode", False))
    }
    features = d.setdefault("settings", {}).setdefault("features", {})
    features["youtube_rules"] = yt_rules
    features.setdefault("youtube_filter", True)
    return jsonify(d)


# =========================
# Student: open tabs (explicit)
# =========================
@app.route("/api/student/open_tabs", methods=["POST"])
def api_student_open_tabs():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    b = request.json or {}
    student = (b.get("student") or "").strip()
    urls = b.get("urls") or []
    if not student or not urls:
        return jsonify({"ok": False, "error": "student and urls required"}), 400

    d = load_data()
    pend = d.setdefault("pending_per_student", {})
    arr = pend.setdefault(student, [])
    arr.append({"type": "open_tabs", "urls": urls, "ts": int(time.time())})
    arr[:] = arr[-50:]
    save_data(d)
    return jsonify({"ok": True})


# =========================
# Exam Mode
# =========================
@app.route("/api/exam", methods=["POST"])
def api_exam():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}
    action = (body.get("action") or "").strip()
    url = (body.get("url") or "").strip()
    class_id = (body.get("class_id") or "").strip()

    if not class_id:
        return jsonify({"ok": False, "error": "class_id required"}), 400

    d = ensure_keys(load_data())
    d.setdefault("pending_commands", {})
    classes = d.get("classes") or {}
    cls = classes.get(class_id, {})
    students = cls.get("students", []) or []

    if action == "start":
        if not url:
            return jsonify({"ok": False, "error": "url required"}), 400
        for s in students:
            d["pending_commands"].setdefault(s, []).append({"type": "exam_start", "url": url})
        d.setdefault("exam_state", {})[class_id] = {"active": True, "url": url}
        save_data(d)
        log_action({"event": "exam", "action": "start", "class_id": class_id, "url": url})
        return jsonify({"ok": True})
    elif action == "end":
        for s in students:
            d["pending_commands"].setdefault(s, []).append({"type": "exam_end"})
        d.setdefault("exam_state", {}).setdefault(class_id, {})["active"] = False
        save_data(d)
        log_action({"event": "exam", "action": "end", "class_id": class_id})
        return jsonify({"ok": True})

    return jsonify({"ok": False, "error": "invalid action"}), 400
@app.route("/api/exam_violation", methods=["POST"])
def api_exam_violation():
    b = request.json or {}
    student = (b.get("student") or "").strip()
    url = (b.get("url") or "").strip()
    reason = (b.get("reason") or "tab_violation").strip()
    if not student:
        return jsonify({"ok": False, "error": "student required"}), 400
    d = ensure_keys(load_data())
    d.setdefault("exam_violations", []).append({
        "student": student, "url": url, "reason": reason, "ts": int(time.time())
    })
    d["exam_violations"] = d["exam_violations"][-500:]
    save_data(d)
    log_action({"event": "exam_violation", "student": student, "reason": reason})
    return jsonify({"ok": True})

@app.route("/api/exam_violations", methods=["GET"])
def api_exam_violations():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    d = ensure_keys(load_data())
    return jsonify({"ok": True, "items": d.get("exam_violations", [])[-200:]})

@app.route("/api/exam_violations/clear", methods=["POST"])
def api_exam_violations_clear():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    b = request.json or {}
    student = (b.get("student") or "").strip()
    d = ensure_keys(load_data())
    if student:
        d["exam_violations"] = [v for v in d.get("exam_violations", []) if v.get("student") != student]
    else:
        d["exam_violations"] = []
    save_data(d)
    log_action({"event": "exam_violations_clear", "student": student or "*"})
    return jsonify({"ok": True})


# =========================
# Notify
# =========================
@app.route("/api/notify", methods=["POST"])
def api_notify():
    u = current_user()
    if not u or u["role"] not in ("teacher", "admin"):
        return jsonify({"ok": False, "error": "forbidden"}), 403
    b = request.json or {}
    title = (b.get("title") or "G School")[:120]
    message = (b.get("message") or "")[:500]
    d = ensure_keys(load_data())
    d.setdefault("pending_commands", {}).setdefault("*", []).append({
        "type": "notify", "title": title, "message": message
    })
    save_data(d)
    log_action({"event": "notify", "title": title})
    return jsonify({"ok": True})

# =========================
# Image AI Filter (per-image, for extension)
# =========================

def _ensure_image_filter_config(d):
    """
    Ensure d["image_filter"] exists with safe defaults.

    We intentionally do NOT change ensure_keys() so existing behavior
    stays exactly the same unless this feature is used.
    """
    cfg = d.setdefault("image_filter", {})
    cfg.setdefault("enabled", False)
    cfg.setdefault("mode", "block")  # "block" or "monitor"
    cfg.setdefault("block_threshold", 0.6)  # 0–1, higher = stricter
    cfg.setdefault("alert_on_block", True)
    cfg.setdefault("max_log_entries", 500)
    d.setdefault("image_filter_events", [])
    return cfg


@app.route("/api/image_filter/config", methods=["GET", "POST"])
def api_image_filter_config():
    """
    GET: anyone (including extension) can read generic config.
    POST: only admin can update it.
    """
    d = ensure_keys(load_data())
    cfg = _ensure_image_filter_config(d)

    if request.method == "GET":
        return jsonify({"ok": True, "config": cfg})

    # POST = admin only
    u = current_user()
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    body = request.json or {}

    if "enabled" in body:
        cfg["enabled"] = bool(body["enabled"])

    if body.get("mode") in ("block", "monitor"):
        cfg["mode"] = body["mode"]

    if "block_threshold" in body:
        try:
            th = float(body["block_threshold"])
            th = max(0.1, min(0.99, th))
            cfg["block_threshold"] = th
        except Exception:
            pass

    if "alert_on_block" in body:
        cfg["alert_on_block"] = bool(body["alert_on_block"])

    if "max_log_entries" in body:
        try:
            m = int(body["max_log_entries"])
            if m >= 50:
                cfg["max_log_entries"] = m
        except Exception:
            pass

    d["image_filter"] = cfg
    save_data(d)
    log_action({"event": "image_filter_config_update", "config": cfg})
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/image_filter/evaluate", methods=["POST"])
def api_image_filter_evaluate():
    """
    Called by the extension for EACH image.

    Body:
      {
        "thumbnail": "data:image/jpeg;base64,...",  # optional small thumbnail
        "src": "https://example.com/image.jpg",
        "page_url": "https://example.com/page",
        "student": "student@example.com"
      }

    Response:
      {
        "ok": true,
        "action": "allow" | "block" | "monitor",
        "reason": "explicit_nudity" | "other",
        "scores": {label: score}
      }
    """
    d = ensure_keys(load_data())
    cfg = _ensure_image_filter_config(d)

    body = request.json or {}
    thumbnail = body.get("thumbnail") or body.get("image") or ""
    src = (body.get("src") or "").strip()
    page_url = (body.get("page_url") or "").strip()
    student = (body.get("student") or "").strip()

    # If disabled, always allow (but still respond).
    if not cfg.get("enabled", False):
        return jsonify({"ok": True, "action": "allow", "reason": "disabled", "scores": {}})

    # Run lightweight classifier
    try:
        scores = _gschool_classify_image(thumbnail or None, src=src, page_url=page_url)
    except Exception as e:
        log_action({"event": "image_filter_error", "error": str(e)})
        return jsonify({"ok": True, "action": "allow", "reason": "error", "scores": {}})

    # Decide based on highest concerning label
    block_threshold = float(cfg.get("block_threshold", 0.6))
    primary_labels = [
        "explicit_nudity",
        "partial_nudity",
        "suggestive",
        "violence",
        "weapon",
        "self_harm",
    ]

    best_label = "other"
    best_score = 0.0
    for label in primary_labels:
        val = float(scores.get(label, 0.0))
        if val > best_score:
            best_score = val
            best_label = label

    action = "allow"
    if best_score >= block_threshold:
        action = "block" if cfg.get("mode", "block") == "block" else "monitor"

    # Append to dedicated log buffer
    events = d.setdefault("image_filter_events", [])
    events.append({
        "ts": int(time.time()),
        "student": student,
        "page_url": page_url,
        "src": src,
        "action": action,
        "label": best_label,
        "score": best_score,
    })
    max_events = int(cfg.get("max_log_entries", 500) or 500)
    d["image_filter_events"] = events[-max_events:]
    save_data(d)

    # When blocked, also create an alert for the teacher/admin
    if action == "block" and cfg.get("alert_on_block", True):
        try:
            d2 = ensure_keys(load_data())
            alerts = d2.setdefault("alerts", [])
            alerts.append({
                "ts": int(time.time()),
                "student": student or "",
                "kind": "image_inappropriate",
                "score": float(best_score),
                "title": best_label,
                "url": page_url or src,
                "note": src,
            })
            d2["alerts"] = alerts[-500:]
            save_data(d2)
            log_action({
                "event": "image_filter_block",
                "student": student,
                "label": best_label,
                "score": best_score,
                "page_url": page_url,
                "src": src,
            })
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "action": action,
        "reason": best_label,
        "scores": scores,
    })


@app.route("/api/image_filter/logs", methods=["GET"])
def api_image_filter_logs():
    """
    Admin-only endpoint to see recent image filter events.
    Used by admin.html to show a live log of blocked/flagged images.
    """
    u = current_user()
    if not u or u.get("role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    d = ensure_keys(load_data())
    events = d.get("image_filter_events", [])[-500:]
    return jsonify({"ok": True, "events": events})

# =========================
# Off-task alert (student)
# =========================
@app.route("/api/off_task", methods=["POST"])
def api_off_task():
    try:
        b = request.json or {}
        student = (b.get("student") or "").strip()
        url = (b.get("url") or "").strip()
        reason = (b.get("reason") or "blocked_visit")
        log_action({"event": "off_task", "student": student, "url": url, "reason": reason, "ts": int(time.time())})
        d = ensure_keys(load_data())
        d.setdefault("pending_commands", {}).setdefault("*", []).append({
            "type": "notify",
            "title": "Off-task detected",
            "message": f"{student or 'Student'} visited a blocked page."
        })
        save_data(d)
        return jsonify({"ok": True})
    except Exception as e:
        try:
            log_action({"event": "off_task_error", "error": str(e)})
        except:
            pass
        return jsonify({"ok": False}), 500


# =========================
# Run
# =========================
if __name__ == "__main__":
    # Ensure data.json exists and is sane on boot
    save_data(ensure_keys(load_data()))
    app.run(host="0.0.0.0", port=5000, debug=True)
