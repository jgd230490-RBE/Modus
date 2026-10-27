"""
G3 (14 Oct 2026) — per-person logins. The plan and the decisions D46–D57: notes\\g3-plan.md.

WHAT THIS IS
------------
A login per person, per tenant: an email, a name, a role (`team` with a team slot IPT1…IPT6,
`planner` or `admin`), a scrypt password hash and a disabled flag. Sign-in by email and
password makes a SERVER-SIDE session whose random token travels in an HttpOnly cookie
(`wayscope_session`); the database holds only the token's SHA-256, so Sign out and Disable
end a session at once — something the HMAC gate cookie (gate.py) can never do.

    users           the people (kind `staff`, or `demo` for a lead's expiring login, HU14)
    user_sessions   one row per signed-in browser
    auth_tokens     invite / reset links (single use) and demo links (reusable until the
                    login expires, D50)
    audit_log       every write, every sign-in event, and page opens for demo logins (D51)
    auth_attempts   the rate limit's memory (in the database, so a redeploy or a second
                    instance does not reset it)

WHAT A SESSION RESOLVES TO
--------------------------
`access_for(user)` returns the same dict `access.resolve()` returns for a shared code —
`{role, ipt, label}` — plus who the person is and `via: "login"`. Every line filter, every
`can_approve`, every `ipt_for_save` downstream reads only `role` and `ipt`, so nothing past
the middleware needed to change to know about logins. A team login's `label` is the tenant's
team NAME (taxonomy.team_name), never the slot id.

THE SHARED CODES (D49)
----------------------
access.resolve() still honours IPT1_CODE…IPT6_CODE, PLANNER_CODE and ADMIN_CODE for as long
as any of them is set on the server. The user deletes them on Render on Sat 31 Oct 2026; from
that redeploy on, a code resolves to nothing and only logins work. Nothing here reads a code.

TWO-STEP SIGN-IN (27 Oct 2026, pilot readiness F3 b)
----------------------------------------------------
Every STAFF login signs in with its password AND a 6-digit code from an authenticator app (TOTP,
RFC 6238: SHA-1, 30-second steps, one step either side accepted, a step works once). The password
step answers a short-lived single-use ticket (`auth_tokens` purpose `mfa`), never a session; the
code step turns the ticket into a session. A staff login without two-step set up gets the set-up
step instead, and a session of such a login does not resolve (resolve_session), so every person
signed in before this shipped sets it up at their next sign-in. Ten recovery codes, each usable
once, stored as SHA-256. Demo logins (leads, a fictional scheme) are exempt.

WHAT THIS IS NOT
----------------
No single sign-on, no per-section permission (D7: a login belongs to a team).
The public map keeps its shared password (D46).
"""
import base64
import csv
import datetime
import hashlib
import hmac
import io
import itertools
import json
import os
import re
import secrets
import time
import uuid

import db

# --------------------------------------------------------------------------- constants

SESSION_COOKIE = "wayscope_session"
#: D52 — a working day, or 30 days with "Keep me signed in on this device"
SESSION_TTL_S = 12 * 3600
REMEMBER_TTL_S = 30 * 24 * 3600
#: a session's last_seen_at is written at most this often (one write per five minutes, not per request)
TOUCH_EVERY_S = 300

INVITE_TTL_S = 72 * 3600
RESET_TTL_S = 60 * 60
#: D48 — a lead's personal login lasts 14 days; asking again on the form renews it
DEMO_DAYS = 14

#: the rate limits (plan §4.1). Window, then the count that trips it.
SIGNIN_WINDOW_S = 15 * 60
SIGNIN_FAILS_PER_EMAIL = 5
SIGNIN_TRIES_PER_IP = 30
RESET_WINDOW_S = 60 * 60
RESET_PER_EMAIL = 3
RESET_PER_IP = 10

ROLES = ("team", "planner", "admin")
KINDS = ("staff", "demo")
TEAM_SLOTS = ("IPT1", "IPT2", "IPT3", "IPT4", "IPT5", "IPT6")
PURPOSES = ("invite", "reset", "demo", "mfa")
#: purposes a link or ticket can be used for once only
SINGLE_USE = ("invite", "reset", "mfa")
#: the ticket between the password step and the code step
MFA_TTL_S = 10 * 60

PASSWORD_MIN = 10
PASSWORD_MAX = 200
#: the commonest choices, refused outright (NCSC: length beats complexity rules, but these are guessed first)
COMMON_PASSWORDS = frozenset("""
password password1 password12 password123 passw0rd 1234567890 12345678910 123456789a qwertyuiop
qwerty1234 qwerty12345 iloveyou12 letmein123 welcome123 welcome1234 abc1234567 1q2w3e4r5t
1qaz2wsx3edc zaq12wsxcvfr administrator admin12345 changeme123 wayscope123 wayscope2026
football123 monkey12345 sunshine123 princess123 trustno1234 aaaaaaaaaa 0000000000 1111111111
""".split())

EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

#: body keys never written to the audit log (matched case-insensitively, whole key or suffix)
SECRET_KEYS = ("password", "token", "code", "secret")
AUDIT_DETAIL_MAX = 4000

DEFAULT_APP_URL = "https://app.wayscope.co.uk"

#: the clock. Tests set it to a fixed datetime; None means the real time.
NOW = None


# --------------------------------------------------------------------------- time

def _now():
    n = NOW if NOW is not None else datetime.datetime.now(datetime.timezone.utc)
    return n.replace(microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _later(seconds, now=None):
    return _iso((now or _now()) + datetime.timedelta(seconds=seconds))


def app_url():
    """The address in every emailed link. From the environment, NEVER from the request's Host
    header: a forged Host must not be able to point a reset link at somebody else's site."""
    return (os.getenv("APP_URL") or DEFAULT_APP_URL).strip().rstrip("/")


# --------------------------------------------------------------------------- passwords

_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def hash_password(pw):
    """`scrypt$n$r$p$salt$hash`, base64. Python's own hashlib.scrypt: no new dependency."""
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    b = lambda x: base64.b64encode(x).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b(salt)}${b(dk)}"


def verify_password(pw, stored):
    """Constant-time. False for a missing or malformed hash, never an exception."""
    if not pw or not stored or not isinstance(stored, str):
        return False
    try:
        algo, n, r, p, salt, want = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(want)
        got = hashlib.scrypt(str(pw).encode("utf-8"), salt=base64.b64decode(salt), dklen=len(want),
                             n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(got, want)
    except Exception:
        return False


# a hash nobody's password matches, so an unknown email costs the same time as a wrong password
_DUMMY_HASH = None


def _dummy_hash():
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_hex(16))
    return _DUMMY_HASH


def password_problem(pw, email=None):
    """None when the password is acceptable, else the sentence the screen shows."""
    pw = pw if isinstance(pw, str) else ""
    if len(pw) < PASSWORD_MIN:
        return f"Use at least {PASSWORD_MIN} characters. Three random words work well."
    if len(pw) > PASSWORD_MAX:
        return f"Use at most {PASSWORD_MAX} characters."
    low = pw.strip().lower()
    if email and low == (email or "").strip().lower():
        return "Don't use your email address as your password."
    if low in COMMON_PASSWORDS or len(set(low)) < 3:
        return "That password is too easy to guess. Three random words work well."
    return None


# --------------------------------------------------------------------------- helpers

def norm_email(email):
    return (email or "").strip().lower()


def email_ok(email):
    e = norm_email(email)
    return bool(e) and len(e) <= 200 and bool(EMAIL_RX.match(e))


def _hash_token(raw):
    return hashlib.sha256(("wayscope|" + (raw or "")).encode("utf-8")).hexdigest()


def _new_token():
    return secrets.token_urlsafe(32)


def ip_hash(ip):
    """The same salted hash demo_request.py stores for a lead's IP."""
    salt = (os.getenv("GATE_SECRET") or os.getenv("ADMIN_TOKEN") or "wayscope").strip()
    return hashlib.sha256((salt + "|" + (ip or "")).encode("utf-8")).hexdigest()[:32]


def _tenant():
    return db.current_tenant()


def team_label(slot):
    """The tenant's NAME for a team slot. Never the slot id on screen (G2)."""
    try:
        import taxonomy
        return taxonomy.team_name(slot)
    except Exception:
        return slot


def canonical_team(value):
    m = re.fullmatch(r"\s*ipt\s*[-_ ]?\s*([1-6])\s*", str(value or ""), re.I)
    return f"IPT{m.group(1)}" if m else None


# --------------------------------------------------------------------------- the people

PUBLIC_FIELDS = ("id", "email", "name", "role", "team", "disabled", "kind", "expires_at",
                 "created_at", "created_by", "last_sign_in_at", "password_set_at")


def public(user):
    """A user as the Users page sees it: no hash, and the team's NAME beside the slot. The slot
    is a value for the page's own select; the page renders `team_label` only."""
    if not user:
        return None
    out = {k: user.get(k) for k in PUBLIC_FIELDS}
    out["disabled"] = bool(user.get("disabled"))
    out["has_password"] = bool(user.get("password_hash"))
    out["team_label"] = team_label(user["team"]) if user.get("team") else None
    out["role_label"] = role_label(user)
    out["status"] = status_of(user)
    out["two_step"] = two_step_on(user)
    return out


def role_label(user):
    if user.get("role") == "team":
        return team_label(user.get("team"))
    return {"planner": "Planner", "admin": "Admin"}.get(user.get("role"), user.get("role"))


def status_of(user, now=None):
    if user.get("disabled"):
        return "disabled"
    if expired(user, now):
        return "expired"
    if not user.get("password_hash") and user.get("kind") != "demo":
        return "invited"
    return "active"


def expired(user, now=None):
    exp = _parse(user.get("expires_at")) if user.get("expires_at") else None
    return bool(exp) and exp <= (now or _now())


def get_user(user_id):
    rows = db.query("SELECT * FROM users WHERE tenant_id = ? AND id = ?", (_tenant(), user_id))
    return rows[0] if rows else None


def find_by_email(email):
    rows = db.query("SELECT * FROM users WHERE tenant_id = ? AND email = ?", (_tenant(), norm_email(email)))
    return rows[0] if rows else None


def list_users():
    return db.query("SELECT * FROM users WHERE tenant_id = ? ORDER BY kind DESC, name", (_tenant(),))


def count_admins(enabled_only=True):
    sql = "SELECT COUNT(*) AS n FROM users WHERE tenant_id = ? AND role = 'admin'"
    if enabled_only:
        sql += " AND (disabled = 0 OR disabled IS NULL)"
    return int(db.query(sql, (_tenant(),))[0]["n"])


def _check_role(role, team):
    """(role, team, error). A team login needs a slot; planner and admin carry none."""
    role = (role or "").strip().lower()
    if role not in ROLES:
        return None, None, "Pick a team, Planner or Admin."
    if role == "team":
        slot = canonical_team(team)
        if not slot:
            return None, None, "Pick the team this person belongs to."
        return role, slot, None
    return role, None, None


def create_user(email, name, role, team=None, kind="staff", expires_at=None, created_by=None,
                demo_request_id=None):
    """(user, error). The email is unique per tenant; a duplicate is an error, not an update."""
    email = norm_email(email)
    name = (name or "").strip()
    if not email_ok(email):
        return None, "That email address doesn't look right."
    if not name or len(name) > 120:
        return None, "Enter the person's name (at most 120 characters)."
    role, slot, err = _check_role(role, team)
    if err:
        return None, err
    if kind not in KINDS:
        return None, "unknown kind"
    if find_by_email(email):
        return None, "There is already a login for that email address."
    uid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO users (tenant_id, id, email, name, role, team, password_hash, disabled, kind, expires_at, "
        "demo_request_id, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?, ?)",
        (_tenant(), uid, email, name, role, slot, kind, expires_at, demo_request_id, _iso(_now()),
         (created_by or "")[:200] or None))
    return get_user(uid), None


def update_user(user_id, fields, by_user_id=None):
    """(user, error). fields may hold name, role, team, disabled, expires_at. Disabling, or a change
    of role or team, ends every session of that person (they sign in again with the new rights).
    Refuses to leave the tenant with no enabled admin login while one exists."""
    user = get_user(user_id)
    if not user:
        return None, "No such login."
    sets, params = [], []
    end_sessions = False
    if "name" in fields:
        name = (fields.get("name") or "").strip()
        if not name or len(name) > 120:
            return None, "Enter the person's name (at most 120 characters)."
        sets.append("name = ?"); params.append(name)
    if "role" in fields or "team" in fields:
        role, slot, err = _check_role(fields.get("role", user["role"]),
                                      fields.get("team", user.get("team")))
        if err:
            return None, err
        if user["role"] == "admin" and role != "admin" and not user.get("disabled") and count_admins() <= 1:
            return None, "This is the last admin login. Make someone else an admin first."
        if (role, slot) != (user["role"], user.get("team")):
            end_sessions = True
        sets += ["role = ?", "team = ?"]; params += [role, slot]
    if "disabled" in fields:
        dis = 1 if fields.get("disabled") else 0
        if dis and user["role"] == "admin" and not user.get("disabled") and count_admins() <= 1:
            return None, "This is the last admin login. Make someone else an admin first."
        if dis and by_user_id and by_user_id == user_id:
            return None, "You can't disable your own login."
        if dis:
            end_sessions = True
        sets.append("disabled = ?"); params.append(dis)
    if "expires_at" in fields:
        exp = fields.get("expires_at")
        if exp is not None and not _parse(exp):
            return None, "expires_at must be YYYY-MM-DDTHH:MM:SSZ"
        sets.append("expires_at = ?"); params.append(exp)
    if not sets:
        return user, None
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE tenant_id = ? AND id = ?",
               tuple(params) + (_tenant(), user_id))
    if end_sessions:
        end_all_sessions(user_id)
    return get_user(user_id), None


def promote_demo(user_id, name, role, team=None):
    """
    (user, error). A lead who becomes a customer: their DEMO login becomes a staff login — the end date
    is cleared, the name, role and team are the admin's, every session ends and the personal demo link
    stops working (they will set a password from the invite). Called when an admin adds a staff login
    for an address that already holds a demo login; refused for anything but a demo login.
    """
    user = get_user(user_id)
    if not user or user.get("kind") != "demo":
        return None, "Only a demo login can become a staff login."
    name = (name or "").strip()
    if not name or len(name) > 120:
        return None, "Enter the person's name (at most 120 characters)."
    role, slot, err = _check_role(role, team)
    if err:
        return None, err
    sql = "UPDATE users SET kind = 'staff', expires_at = NULL, name = ?, role = ?, team = ?, disabled = 0 WHERE tenant_id = ? AND id = ?"
    db.execute(sql, (name, role, slot, _tenant(), user_id))
    db.execute("DELETE FROM auth_tokens WHERE tenant_id = ? AND user_id = ? AND purpose = 'demo'", (_tenant(), user_id))
    end_all_sessions(user_id)
    return get_user(user_id), None


def set_password(user_id, pw):
    """(ok, error). Ends every session of the person: a new password signs every other browser out."""
    user = get_user(user_id)
    if not user:
        return False, "No such login."
    problem = password_problem(pw, user["email"])
    if problem:
        return False, problem
    db.execute("UPDATE users SET password_hash = ?, password_set_at = ? WHERE tenant_id = ? AND id = ?",
               (hash_password(pw), _iso(_now()), _tenant(), user_id))
    end_all_sessions(user_id)
    return True, None


def usable(user, now=None):
    """Can this login sign in at all (password aside)?"""
    return bool(user) and not user.get("disabled") and not expired(user, now)


def access_for(user):
    """What a session grants: the access.resolve() shape, plus the person. `label` is what a
    person reads — the team's NAME for a team login."""
    role = user["role"]
    acc_role = "ipt" if role == "team" else role
    label = team_label(user["team"]) if role == "team" else role_label(user)
    return {"role": acc_role, "ipt": user.get("team") if role == "team" else None, "label": label,
            "via": "login", "user_id": user["id"], "name": user["name"], "email": user["email"],
            "kind": user.get("kind") or "staff", "expires_at": user.get("expires_at"),
            "two_step": two_step_on(user), "recovery_left": recovery_left(user)}


# --------------------------------------------------------------------------- sessions

def create_session(user_id, remember=False, ip=None, ua=None, now=None):
    """(raw_token, max_age_s). The raw token goes in the cookie and nowhere else."""
    now = now or _now()
    ttl = REMEMBER_TTL_S if remember else SESSION_TTL_S
    user = get_user(user_id)
    # a demo login's session never outlives the login
    if user and user.get("expires_at"):
        left = int((_parse(user["expires_at"]) - now).total_seconds())
        ttl = max(1, min(ttl, left))
    raw = _new_token()
    db.execute(
        "INSERT INTO user_sessions (tenant_id, token_hash, user_id, created_at, expires_at, last_seen_at, remember, "
        "ip_hash, ua) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (_tenant(), _hash_token(raw), user_id, _iso(now), _later(ttl, now), _iso(now), 1 if remember else 0,
         ip_hash(ip) if ip else None, (ua or "")[:120] or None))
    db.execute("UPDATE users SET last_sign_in_at = ? WHERE tenant_id = ? AND id = ?", (_iso(now), _tenant(), user_id))
    return raw, ttl


def resolve_session(raw, now=None):
    """(access, user) for a live session of a usable login, else (None, None). Touches last_seen_at
    at most every TOUCH_EVERY_S."""
    if not raw or not isinstance(raw, str) or len(raw) > 200:
        return None, None
    now = now or _now()
    th = _hash_token(raw)
    rows = db.query("SELECT * FROM user_sessions WHERE tenant_id = ? AND token_hash = ?", (_tenant(), th))
    if not rows:
        return None, None
    s = rows[0]
    exp = _parse(s["expires_at"])
    if not exp or exp <= now:
        db.execute("DELETE FROM user_sessions WHERE tenant_id = ? AND token_hash = ?", (_tenant(), th))
        return None, None
    user = get_user(s["user_id"])
    if not usable(user, now):
        return None, None
    if needs_two_step(user) and not two_step_on(user):
        # signed in before two-step shipped, or an admin reset it: sign in again and set it up
        return None, None
    seen = _parse(s.get("last_seen_at"))
    if not seen or (now - seen).total_seconds() >= TOUCH_EVERY_S:
        db.execute("UPDATE user_sessions SET last_seen_at = ? WHERE tenant_id = ? AND token_hash = ?",
                   (_iso(now), _tenant(), th))
    acc = access_for(user)
    acc["session_expires_at"] = s["expires_at"]
    return acc, user


def session_expiry(raw):
    rows = db.query("SELECT expires_at FROM user_sessions WHERE tenant_id = ? AND token_hash = ?",
                    (_tenant(), _hash_token(raw or "")))
    return _parse(rows[0]["expires_at"]) if rows else None


def end_session(raw):
    db.execute("DELETE FROM user_sessions WHERE tenant_id = ? AND token_hash = ?", (_tenant(), _hash_token(raw or "")))


def end_all_sessions(user_id, keep_raw=None):
    if keep_raw:
        db.execute("DELETE FROM user_sessions WHERE tenant_id = ? AND user_id = ? AND token_hash <> ?",
                   (_tenant(), user_id, _hash_token(keep_raw)))
    else:
        db.execute("DELETE FROM user_sessions WHERE tenant_id = ? AND user_id = ?", (_tenant(), user_id))


def count_sessions(user_id):
    return int(db.query("SELECT COUNT(*) AS n FROM user_sessions WHERE tenant_id = ? AND user_id = ?",
                        (_tenant(), user_id))[0]["n"])


def cookie_kwargs(raw, max_age):
    """What main.py hands to response.set_cookie(). HttpOnly (no script reads it), Secure, and
    SameSite=Lax (another site's request does not carry it)."""
    return {"key": SESSION_COOKIE, "value": raw, "max_age": int(max_age), "path": "/",
            "httponly": True, "samesite": "lax", "secure": True}


# --------------------------------------------------------------------------- links (invite, reset, demo)

def issue_token(user_id, purpose, ttl_s=None, expires_at=None, now=None):
    """The raw token for a link. Issuing an invite or a reset retires that person's earlier
    unused ones of the same purpose, so only the newest link works."""
    if purpose not in PURPOSES:
        raise ValueError(purpose)
    now = now or _now()
    if expires_at is None:
        expires_at = _later(ttl_s or {"invite": INVITE_TTL_S, "mfa": MFA_TTL_S}.get(purpose, RESET_TTL_S), now)
    db.execute("DELETE FROM auth_tokens WHERE tenant_id = ? AND user_id = ? AND purpose = ? AND used_at IS NULL",
               (_tenant(), user_id, purpose))
    raw = _new_token()
    db.execute(
        "INSERT INTO auth_tokens (tenant_id, token_hash, user_id, purpose, created_at, expires_at, used_at, uses) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, 0)",
        (_tenant(), _hash_token(raw), user_id, purpose, _iso(now), expires_at))
    return raw


def peek_token(raw, purposes, now=None):
    """(row, user) for a live token of one of `purposes`, else (None, None). Does not use it up."""
    if not raw or not isinstance(raw, str) or len(raw) > 200:
        return None, None
    now = now or _now()
    rows = db.query("SELECT * FROM auth_tokens WHERE tenant_id = ? AND token_hash = ?", (_tenant(), _hash_token(raw)))
    if not rows or rows[0]["purpose"] not in purposes:
        return None, None
    t = rows[0]
    exp = _parse(t["expires_at"])
    if not exp or exp <= now:
        return None, None
    if t["purpose"] in SINGLE_USE and t.get("used_at"):
        return None, None
    user = get_user(t["user_id"])
    if not usable(user, now):
        return None, None
    return t, user


def use_token(raw, purposes, now=None):
    """Use a token: invite and reset become dead (single use); a demo link counts one more use
    and stays live until the login expires (D50). (row, user) or (None, None)."""
    now = now or _now()
    t, user = peek_token(raw, purposes, now)
    if not t:
        return None, None
    if t["purpose"] in SINGLE_USE:
        db.execute("UPDATE auth_tokens SET used_at = ?, uses = uses + 1 WHERE tenant_id = ? AND token_hash = ? "
                   "AND used_at IS NULL", (_iso(now), _tenant(), t["token_hash"]))
        # a race: another request used it between the read and the write
        again = db.query("SELECT used_at FROM auth_tokens WHERE tenant_id = ? AND token_hash = ?",
                         (_tenant(), t["token_hash"]))
        if not again or again[0]["used_at"] != _iso(now):
            return None, None
    else:
        db.execute("UPDATE auth_tokens SET uses = uses + 1 WHERE tenant_id = ? AND token_hash = ?",
                   (_tenant(), t["token_hash"]))
    return t, user


def link(purpose, raw):
    """The URL in an email. A FRAGMENT (#reset=…), so the token reaches neither a server log nor a
    Referer header, and a mail scanner that fetches the link with a GET uses nothing up — the
    page's script posts the token."""
    return f"{app_url()}/#{purpose}={raw}"


# --------------------------------------------------------------------------- rate limits

def _attempt_key(kind, value):
    return hashlib.sha256((kind + "|" + (value or "")).encode("utf-8")).hexdigest()[:40]


def _attempts_since(kind, key, seconds, now, ok=None):
    sql = "SELECT COUNT(*) AS n FROM auth_attempts WHERE tenant_id = ? AND kind = ? AND key_hash = ? AND at >= ?"
    params = [_tenant(), kind, key, _iso(now - datetime.timedelta(seconds=seconds))]
    if ok is not None:
        sql += " AND ok = ?"; params.append(1 if ok else 0)
    return int(db.query(sql, tuple(params))[0]["n"])


def record_attempt(kind, key, ok, now=None):
    """One attempt under `key` (already _attempt_key()-ed by the caller)."""
    now = now or _now()
    db.execute("INSERT INTO auth_attempts (tenant_id, id, kind, key_hash, at, ok) VALUES (?, ?, ?, ?, ?, ?)",
               (_tenant(), uuid.uuid4().hex, kind, key, _iso(now), 1 if ok else 0))
    # keep the table small: nothing older than a day matters to any limit
    db.execute("DELETE FROM auth_attempts WHERE tenant_id = ? AND at < ?",
               (_tenant(), _iso(now - datetime.timedelta(days=1))))


def signin_blocked(email, ip, now=None):
    """True when this email has failed SIGNIN_FAILS_PER_EMAIL times in the window, or this IP has
    tried SIGNIN_TRIES_PER_IP times."""
    now = now or _now()
    if _attempts_since("signin-email", _attempt_key("signin-email", norm_email(email)), SIGNIN_WINDOW_S, now,
                       ok=False) >= SIGNIN_FAILS_PER_EMAIL:
        return True
    if ip and _attempts_since("signin-ip", _attempt_key("signin-ip", ip_hash(ip)), SIGNIN_WINDOW_S,
                              now) >= SIGNIN_TRIES_PER_IP:
        return True
    return False


def reset_blocked(email, ip, now=None):
    now = now or _now()
    if _attempts_since("reset-email", _attempt_key("reset-email", norm_email(email)), RESET_WINDOW_S,
                       now) >= RESET_PER_EMAIL:
        return True
    if ip and _attempts_since("reset-ip", _attempt_key("reset-ip", ip_hash(ip)), RESET_WINDOW_S,
                              now) >= RESET_PER_IP:
        return True
    return False


SIGNIN_REFUSED = "That email and password don't match."
SIGNIN_LOCKED = "Too many attempts. Try again in 15 minutes."


def sign_in(email, password, ip=None, now=None):
    """(user, error, status). One message for an unknown email, a wrong password, a disabled or
    an expired login — the screen never says whether an address has a login. 429 when locked."""
    now = now or _now()
    email = norm_email(email)
    if signin_blocked(email, ip, now):
        audit_event("signin-locked", label=email, ip=ip, now=now)
        return None, SIGNIN_LOCKED, 429
    user = find_by_email(email) if email_ok(email) else None
    good = verify_password(password, user.get("password_hash") if user else _dummy_hash())
    good = good and usable(user, now)
    record_attempt("signin-email", _attempt_key("signin-email", email), good, now)
    if ip:
        record_attempt("signin-ip", _attempt_key("signin-ip", ip_hash(ip)), good, now)
    if not good:
        audit_event("signin-refused", user=user, label=email, ip=ip, now=now, actor=("anonymous", None, email))
        return None, SIGNIN_REFUSED, 401
    audit_event("signin", user=user, ip=ip, now=now)
    return user, None, 200


# --------------------------------------------------------------------------- two-step sign-in (27 Oct 2026, F3 b)

TOTP_STEP_S = 30
TOTP_DIGITS = 6
#: one step either side of now is accepted (a phone's clock a little off)
TOTP_WINDOW = 1
RECOVERY_COUNT = 10
#: no 0/O, 1/I/L: a person types these off paper
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TOTP_ISSUER = "Wayscope"
CODE_REFUSED = "That code didn't work. Codes change every 30 seconds."


def needs_two_step(user):
    """Every staff login. A lead's demo login (a fictional scheme, a 14-day look) does not."""
    return bool(user) and (user.get("kind") or "staff") != "demo"


def two_step_on(user):
    return bool(user and user.get("totp_secret"))


def recovery_left(user):
    try:
        return len(json.loads(user.get("recovery_hashes") or "[]"))
    except (TypeError, ValueError):
        return 0


def new_totp_secret():
    """20 random bytes as base32, no padding: what an authenticator app is given."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _b32(secret):
    s = (secret or "").replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def totp_at(secret, step):
    """The code for one 30-second step (RFC 6238 over RFC 4226, SHA-1, 6 digits)."""
    mac = hmac.new(_b32(secret), int(step).to_bytes(8, "big"), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = int.from_bytes(mac[off:off + 4], "big") & 0x7FFFFFFF
    return str(n % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def totp_step(now=None):
    return int((now or _now()).timestamp()) // TOTP_STEP_S


def totp_match(secret, code, now=None, after_step=None):
    """The step a code matches, else None. `after_step`: a step already used — that one and any
    earlier are refused, so a code seen over someone's shoulder cannot be used again."""
    code = re.sub(r"\s", "", str(code or ""))
    if not secret or not re.fullmatch(r"\d{%d}" % TOTP_DIGITS, code):
        return None
    here = totp_step(now)
    for step in range(here - TOTP_WINDOW, here + TOTP_WINDOW + 1):
        if after_step is not None and step <= int(after_step):
            continue
        if hmac.compare_digest(totp_at(secret, step), code):
            return step
    return None


def otpauth_uri(secret, email):
    from urllib.parse import quote
    label = quote(f"{TOTP_ISSUER}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(TOTP_ISSUER)}&digits={TOTP_DIGITS}&period={TOTP_STEP_S}"


def qr_svg(text):
    """The set-up QR code as an SVG string (segno, drawn by the server: the key never goes to a third party)."""
    import segno
    buf = io.BytesIO()
    # omitsize: a viewBox and no fixed width / height, so the page sizes it without clipping
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, xmldecl=False, svgclass=None,
                                     lineclass=None, omitsize=True, title="QR code for your authenticator app")
    return buf.getvalue().decode("utf-8")


def _norm_recovery(code):
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper())


def _hash_recovery(code):
    return hashlib.sha256(("recovery|" + _norm_recovery(code)).encode("utf-8")).hexdigest()


def new_recovery_codes(user_id):
    """Ten fresh codes ("7KQ2-M9XD"); the old ones stop working. Returns the codes (shown once)."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))
        codes.append(raw[:4] + "-" + raw[4:])
    db.execute("UPDATE users SET recovery_hashes = ? WHERE tenant_id = ? AND id = ?",
               (json.dumps([_hash_recovery(c) for c in codes]), _tenant(), user_id))
    return codes


def use_recovery_code(user, code):
    """True and the code is spent, or False."""
    if len(_norm_recovery(code)) != 8:
        return False
    try:
        hashes = json.loads(user.get("recovery_hashes") or "[]")
    except (TypeError, ValueError):
        return False
    h = _hash_recovery(code)
    hit = next((x for x in hashes if hmac.compare_digest(x, h)), None)
    if not hit:
        return False
    hashes.remove(hit)
    db.execute("UPDATE users SET recovery_hashes = ? WHERE tenant_id = ? AND id = ?",
               (json.dumps(hashes), _tenant(), user["id"]))
    return True


def start_two_step(user, now=None):
    """After a right password (or a used invite / reset link): the ticket for the code step and what
    the screen needs. {"step": "code" | "setup", "ticket", "email"} (+ "key", "qr" for set-up)."""
    raw = issue_token(user["id"], "mfa", now=now)
    out = {"step": "code" if two_step_on(user) else "setup", "ticket": raw, "email": user["email"]}
    if out["step"] == "setup":
        # a fresh key each time the set-up screen is reached; it counts only once confirmed
        key = new_totp_secret()
        db.execute("UPDATE users SET totp_pending = ? WHERE tenant_id = ? AND id = ?", (key, _tenant(), user["id"]))
        out["key"] = " ".join(key[i:i + 4] for i in range(0, len(key), 4))
        out["qr"] = qr_svg(otpauth_uri(key, user["email"]))
    return out


def _code_blocked(user, ip, now):
    return signin_blocked(user["email"], ip, now)


def _code_failed(user, ip, now):
    record_attempt("signin-email", _attempt_key("signin-email", user["email"]), False, now)
    if ip:
        record_attempt("signin-ip", _attempt_key("signin-ip", ip_hash(ip)), False, now)


def finish_code(ticket, code, ip=None, now=None):
    """(user, error, status). The code step: a 6-digit code, or a recovery code. A wrong one counts
    towards the sign-in limit (five, then 15 minutes) and leaves the ticket live; a right one uses
    the ticket."""
    now = now or _now()
    t, user = peek_token(ticket, ("mfa",), now)
    if not t:
        return None, "That took too long. Sign in again.", 410
    if not two_step_on(user):
        return None, "Set up two-step sign-in first.", 409
    if _code_blocked(user, ip, now):
        audit_event("signin-locked", user=user, ip=ip, now=now)
        return None, SIGNIN_LOCKED, 429
    step = totp_match(user["totp_secret"], code, now, after_step=user.get("totp_last_step"))
    via = "app"
    if step is None:
        if use_recovery_code(user, code):
            via = "recovery code"
        else:
            _code_failed(user, ip, now)
            audit_event("signin-code-refused", user=user, ip=ip, now=now)
            return None, CODE_REFUSED, 401
    t, user = use_token(ticket, ("mfa",), now)
    if not t:
        return None, "That took too long. Sign in again.", 410
    if step is not None:
        db.execute("UPDATE users SET totp_last_step = ? WHERE tenant_id = ? AND id = ?", (step, _tenant(), user["id"]))
    audit_event("signin", user=user, ip=ip, now=now, detail={"second_step": via})
    return get_user(user["id"]), None, 200


def finish_setup(ticket, code, ip=None, now=None):
    """(user, recovery_codes, error, status). The set-up step: the code from the newly added key turns
    two-step on, issues ten recovery codes and uses the ticket."""
    now = now or _now()
    t, user = peek_token(ticket, ("mfa",), now)
    if not t:
        return None, None, "That took too long. Sign in again.", 410
    if two_step_on(user):
        return None, None, "Two-step sign-in is already on. Sign in again.", 409
    if _code_blocked(user, ip, now):
        return None, None, SIGNIN_LOCKED, 429
    key = user.get("totp_pending")
    step = totp_match(key, code, now)
    if step is None:
        _code_failed(user, ip, now)
        return None, None, CODE_REFUSED, 401
    t, user = use_token(ticket, ("mfa",), now)
    if not t:
        return None, None, "That took too long. Sign in again.", 410
    sql = "UPDATE users SET totp_secret = ?, totp_pending = NULL, totp_on_at = ?, totp_last_step = ? WHERE tenant_id = ? AND id = ?"
    db.execute(sql, (key, _iso(now), step, _tenant(), user["id"]))
    codes = new_recovery_codes(user["id"])
    audit_event("two-step-on", user=user, ip=ip, now=now)
    audit_event("signin", user=user, ip=ip, now=now, detail={"second_step": "set up"})
    return get_user(user["id"]), codes, None, 200


def renew_recovery_codes(user, code, ip=None, now=None):
    """(codes, error, status) — a signed-in person asks for new codes; a code from the app first."""
    now = now or _now()
    if not two_step_on(user):
        return None, "Two-step sign-in is not on.", 409
    if _code_blocked(user, ip, now):
        return None, SIGNIN_LOCKED, 429
    step = totp_match(user["totp_secret"], code, now, after_step=user.get("totp_last_step"))
    if step is None:
        _code_failed(user, ip, now)
        return None, CODE_REFUSED, 400
    db.execute("UPDATE users SET totp_last_step = ? WHERE tenant_id = ? AND id = ?", (step, _tenant(), user["id"]))
    codes = new_recovery_codes(user["id"])
    audit_event("recovery-codes-new", user=user, ip=ip, now=now)
    return codes, None, 200


def reset_two_step(user_id):
    """An admin's "Reset two-step", or the recovery command: the key and the codes go, every session
    ends, and the person sets it up again at their next sign-in."""
    sql = ("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_on_at = NULL, recovery_hashes = NULL, totp_last_step = NULL WHERE tenant_id = ? AND id = ?")
    db.execute(sql, (_tenant(), user_id))
    end_all_sessions(user_id)
    return get_user(user_id)


def note_reset_request(email, ip, now=None):
    now = now or _now()
    record_attempt("reset-email", _attempt_key("reset-email", norm_email(email)), True, now)
    if ip:
        record_attempt("reset-ip", _attempt_key("reset-ip", ip_hash(ip)), True, now)


# --------------------------------------------------------------------------- the audit trail

def scrub(value, depth=0):
    """The body with every secret removed: any key that is, or ends in _, password / token / code /
    secret, or contains password or token. Nested dicts and lists are walked."""
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            kl = str(k).lower()
            if kl in SECRET_KEYS or any(kl.endswith("_" + s) for s in SECRET_KEYS) or "password" in kl or "token" in kl:
                out[k] = "(removed)"
            else:
                out[k] = scrub(v, depth + 1)
        return out
    if isinstance(value, list):
        return [scrub(v, depth + 1) for v in value]
    return value


def _detail(obj):
    if obj is None:
        return None
    try:
        s = json.dumps(scrub(obj), ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= AUDIT_DETAIL_MAX else s[:AUDIT_DETAIL_MAX - 1] + "…"


def actor_of(acc, token_used=False):
    """(actor_kind, actor_id, actor_label) for an access dict. A login names the person; a shared
    code says which code (the typed name, when there is one, is in the request body); the admin
    token says so."""
    if acc and acc.get("via") == "login":
        return "user", acc.get("user_id"), f"{acc.get('name')} <{acc.get('email')}>"
    if acc:
        label = f"{acc.get('label') or acc.get('role')} code (shared)"
        return "code", None, label + (", with the admin token" if token_used else "")
    if token_used:
        return "token", None, "admin token"
    return "anonymous", None, "not signed in"


_AUDIT_SEQ = itertools.count()


def _audit_id():
    """Time-ordered (nanoseconds, then a per-process counter, then random), so rows written in the same
    second still list newest first: audit_rows() orders by `at`, then this id. The counter is there
    because Windows' clock can return the same nanoseconds for two writes in a row."""
    return "%020d%08d%s" % (time.time_ns(), next(_AUDIT_SEQ) % 100000000, uuid.uuid4().hex[:8])


def audit(kind, acc=None, method=None, path=None, target=None, status=None, detail=None, ip=None,
          token_used=False, now=None, actor=None):
    """One audit_log row. Never raises: a failed audit write is printed, not turned into a failed
    request (the write it records has already happened)."""
    try:
        ak, aid, al = actor or actor_of(acc, token_used)
        db.execute(
            "INSERT INTO audit_log (tenant_id, id, at, kind, actor_kind, actor_id, actor_label, method, path, target, "
            "status, detail, ip_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_tenant(), _audit_id(), _iso(now or _now()), kind, ak, aid, (al or "")[:300], method,
             (path or "")[:300] or None, (target or "")[:300] or None, status, _detail(detail),
             ip_hash(ip) if ip else None))
    except Exception as e:  # noqa: BLE001
        print(f"audit: write failed {e.__class__.__name__}: {str(e)[:200]}")


def audit_event(kind, user=None, label=None, ip=None, detail=None, now=None, actor=None):
    """An account event (sign-in, reset, a login added or changed) about `user`. `actor` is
    actor_of(...) for whoever did it when that is not the person themself (an admin, the token)."""
    if actor is None:
        actor = (("user", user["id"], f"{user['name']} <{user['email']}>") if user
                 else ("anonymous", None, label or "not signed in"))
    d = dict(detail or {})
    if user and actor[1] != user["id"]:
        d.setdefault("login", f"{user['name']} <{user['email']}>")
    audit(kind, detail=d or None, ip=ip, now=now, actor=actor,
          target=user["id"] if user else None)


def record_page(acc, page, now=None):
    """D51 — page opens for DEMO logins only. A staff login, a code or nobody: nothing is written. The
    page is reduced to a short word ([a-z0-9-], 40 characters), so the log holds no free text."""
    if not acc or acc.get("via") != "login" or acc.get("kind") != "demo":
        return False
    p = re.sub(r"[^a-z0-9-]", "", str(page or "").lower())[:40]
    if not p:
        return False
    audit("page", acc=acc, target=p, now=now)
    return True


def audit_rows(actor_id=None, kind=None, since=None, limit=500):
    sql = "SELECT * FROM audit_log WHERE tenant_id = ?"
    params = [_tenant()]
    if actor_id:
        sql += " AND actor_id = ?"; params.append(actor_id)
    if kind:
        sql += " AND kind = ?"; params.append(kind)
    if since:
        sql += " AND at >= ?"; params.append(since)
    sql += " ORDER BY at DESC, id DESC"
    rows = db.query(sql, tuple(params))
    return rows[:max(1, min(int(limit or 500), 5000))]


AUDIT_CSV_COLUMNS = ("at", "kind", "actor_label", "actor_kind", "method", "path", "target", "status", "detail")


def audit_csv(actor_id=None, kind=None, since=None):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(AUDIT_CSV_COLUMNS)
    for r in audit_rows(actor_id, kind, since, limit=5000):
        w.writerow([r.get(k) if r.get(k) is not None else "" for k in AUDIT_CSV_COLUMNS])
    return buf.getvalue()


def demo_activity(user_id):
    """For the leads CSV (HU14): sign-ins, first and last seen, and pages opened with counts."""
    rows = db.query("SELECT kind, at, target FROM audit_log WHERE tenant_id = ? AND actor_id = ? "
                    "AND kind IN ('signin', 'demo-link', 'page') ORDER BY at", (_tenant(), user_id))
    pages = {}
    for r in rows:
        if r["kind"] == "page" and r.get("target"):
            pages[r["target"]] = pages.get(r["target"], 0) + 1
    return {"sign_ins": sum(1 for r in rows if r["kind"] in ("signin", "demo-link")),
            "first_seen": rows[0]["at"] if rows else "",
            "last_seen": rows[-1]["at"] if rows else "",
            "pages": " · ".join(f"{k} {v}" for k, v in sorted(pages.items(), key=lambda kv: (-kv[1], kv[0])))}


# --------------------------------------------------------------------------- HU14: a lead's own login

def demo_slot():
    """The team slot a lead's login belongs to: DEMO_TEAM_CODE_VAR names it (`IPT1_CODE` → IPT1).
    Since G3 only the NAME of that variable is read — never the code it holds."""
    var = (os.getenv("DEMO_TEAM_CODE_VAR") or "IPT1_CODE").strip()
    return canonical_team(var.upper().replace("_CODE", "")) or "IPT1"


def demo_login(email, name, request_id=None, now=None):
    """
    Create or renew a lead's expiring login and issue their personal link.

    Returns {"status", "user", "link", "expires_at"}:
      new       a fresh demo login, 14 days
      renewed   an existing demo login (live or expired) gets a fresh 14 days and a new link
      staff     the address already has a staff login: no link — they sign in as usual
      disabled  an admin disabled this lead: stays disabled, no link
    """
    now = now or _now()
    exp = _iso(now + datetime.timedelta(days=DEMO_DAYS))
    user = find_by_email(email)
    if user and user.get("kind") != "demo":
        return {"status": "staff", "user": user, "link": None, "expires_at": None}
    if user and user.get("disabled"):
        return {"status": "disabled", "user": user, "link": None, "expires_at": None}
    if user:
        db.execute("UPDATE users SET expires_at = ?, demo_request_id = ? WHERE tenant_id = ? AND id = ?",
                   (exp, request_id or user.get("demo_request_id"), _tenant(), user["id"]))
        status = "renewed"
    else:
        user, err = create_user(email, name or email, "team", demo_slot(), kind="demo", expires_at=exp,
                                created_by="demo request", demo_request_id=request_id)
        if err:
            return {"status": "error", "user": None, "link": None, "expires_at": None, "error": err}
        status = "new"
    raw = issue_token(user["id"], "demo", expires_at=exp, now=now)
    return {"status": status, "user": get_user(user["id"]), "link": link("demo", raw), "expires_at": exp}


def nice_date(iso):
    """'Wed 28 Oct 2026' for an email."""
    d = _parse(iso)
    return d.strftime("%a %d %b %Y").replace(" 0", " ") if d else ""


# --------------------------------------------------------------------------- the emails

def mail_settings():
    """The three variables an invite or reset needs (the lead notification also needs DEMO_NOTIFY,
    which demo_request.smtp_settings() checks). None when any is missing."""
    s = {k: (os.getenv(k) or "").strip() for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM")}
    if not all(s.values()):
        return None
    import demo_request
    s["host"], s["port"] = demo_request.SMTP_HOST, demo_request.SMTP_PORT
    s["reply_to"] = (os.getenv("DEMO_REPLY_TO") or os.getenv("DEMO_NOTIFY") or s["DEMO_FROM"]).strip()
    return s


def account_message(purpose, user, url, settings):
    """The invite or the reset email. Plain words, the link, how long it lasts."""
    from email.message import EmailMessage
    first = (user.get("name") or "").split(" ")[0] or "there"
    if purpose == "invite":
        subject = "Your Wayscope sign-in"
        lead = f"Hello {first},\n\nYou have a Wayscope login for {user['email']}. Set your password here:"
        last = "The link works once and for 72 hours. After that, ask your administrator to send a new one."
    else:
        subject = "Reset your Wayscope password"
        lead = f"Hello {first},\n\nSomebody asked to reset the password for {user['email']}. To choose a new one:"
        last = ("The link works once and for 60 minutes. If you did not ask for this, ignore this email; "
                "your password has not changed.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["DEMO_FROM"]          # as the lead email: DEMO_FROM is already "Wayscope <address>"
    msg["To"] = user["email"]
    msg["Reply-To"] = settings["reply_to"]
    msg.set_content(f"{lead}\n\n{url}\n\n{last}\n\nWayscope\n")
    return msg


def send_account_email(purpose, user, url):
    """'sent', 'unsent' (no sender configured) or 'failed: <Error>'. Never raises."""
    settings = mail_settings()
    if settings is None:
        return "unsent"
    try:
        import demo_request
        demo_request.send(account_message(purpose, user, url, settings), settings)
        return "sent"
    except Exception as e:  # noqa: BLE001
        print(f"users: {purpose} email FAILED {e.__class__.__name__}: {str(e)[:200]}")
        return "failed: " + e.__class__.__name__


def codes_enabled():
    """D49 — are the shared codes still on? True while any of the eight variables is set."""
    try:
        import access
        return bool(access.configured_codes())
    except Exception:
        return False


# --------------------------------------------------------------------------- the first admin, and recovery (27 Oct 2026, F3 c)

def _make_admin(user_id):
    sql = "UPDATE users SET role = 'admin', team = NULL, kind = 'staff', expires_at = NULL, disabled = 0 WHERE tenant_id = ? AND id = ?"
    db.execute(sql, (_tenant(), user_id))


def ensure_first_admin(now=None):
    """
    A new deployment's first admin, without the admin token (F3 c). When FIRST_ADMIN_EMAIL is set and this
    organisation has NO admin login yet (enabled or not), make one for that address and send its invite (72 h).
    When email is not set up, the link is printed to the service log, where only someone signed in to Render
    can read it. Once any admin exists this does nothing, so a restart never sends a second invite.
    Returns what happened, for the log and the tests: "off" | "exists" | "bad-email" | "sent" | "logged" | "error".
    """
    email = norm_email(os.getenv("FIRST_ADMIN_EMAIL") or "")
    if not email:
        return "off"
    if count_admins(enabled_only=False) > 0:
        return "exists"
    if not email_ok(email):
        print("first admin: FIRST_ADMIN_EMAIL does not look like an email address; nothing done")
        return "bad-email"
    user = find_by_email(email)
    if user:
        _make_admin(user["id"])
        user = get_user(user["id"])
    else:
        name = (os.getenv("FIRST_ADMIN_NAME") or "").strip() or email.split("@")[0]
        user, err = create_user(email, name, "admin", created_by="FIRST_ADMIN_EMAIL")
        if err:
            print(f"first admin: not created: {err}")
            return "error"
    purpose = "reset" if user.get("password_hash") else "invite"
    url = link(purpose, issue_token(user["id"], purpose, now=now))
    sent = send_account_email(purpose, user, url)
    audit_event("first-admin", user=user, actor=("system", None, "FIRST_ADMIN_EMAIL"), detail={"email": sent}, now=now)
    if sent == "sent":
        print(f"first admin: invite sent to {email}")
        return "sent"
    print(f"first admin: email is not set up; open this link to set the password (72 hours): {url}")
    return "logged"


def recover_admin(email, now=None):
    """
    Lock-out insurance without a standing secret (F3 c): run from the server's shell by someone signed in to
    the hosting. The login for `email` (made if missing) becomes an enabled admin, its two-step sign-in is reset,
    every session ends, and a single-use link comes back: a reset (60 min) when it has a password, else an
    invite (72 h). (link, error).
    """
    email = norm_email(email)
    if not email_ok(email):
        return None, "That email address doesn't look right."
    user = find_by_email(email)
    if user:
        _make_admin(user["id"])
        user = reset_two_step(user["id"])
    else:
        user, err = create_user(email, email.split("@")[0], "admin", created_by="recovery command")
        if err:
            return None, err
    purpose = "reset" if user.get("password_hash") else "invite"
    url = link(purpose, issue_token(user["id"], purpose, now=now))
    audit_event("recovery-command", user=user, actor=("system", None, "recovery command"), now=now)
    return url, None
