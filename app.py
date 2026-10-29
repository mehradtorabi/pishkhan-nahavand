# -*- coding: utf-8 -*-
"""سامانه دفتر پیشخوان — نسخه 4.1 (MariaDB/MySQL + PyMySQL)"""
import os, re, uuid, json as _json
from functools import wraps
from datetime import datetime
from flask import (Flask, g, request, redirect, url_for, session, flash,
                   render_template_string, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
import pymysql
from pymysql.cursors import DictCursor
from urllib.parse import urlparse

# بارگذاری .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "CHANGE-THIS-SECRET-KEY-BEFORE-DEPLOYMENT"),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
)

APP_VERSION = "4.1"
DEFAULT_BLUE = "#1e3a8a"
DEFAULT_YELLOW = "#f4b41a"
DEF_SITE_NAME = "پیشخوان پلاس"
DEF_OFFICE_NAME = "دفتر پیشخوان پلاس"

@app.after_request
def add_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

DEFAULT_SETTINGS = {
    "site_name": DEF_SITE_NAME, "tagline": "خدمات دفتر، ساده‌تر و شفاف‌تر",
    "office_name": DEF_OFFICE_NAME,
    "office_address": "نشانی دفتر هنوز ثبت نشده است.",
    "office_phone": "اطلاعات تماس هنوز ثبت نشده است.",
    "office_hours": "ساعات کاری هنوز ثبت نشده است.",
    "office_services": "برای اطلاع از خدمات قابل ارائه، با دفتر تماس بگیرید.",
    "theme_color": DEFAULT_BLUE, "accent_color": DEFAULT_YELLOW,
    "card1_title": "اطلاعات", "card1_text": "نشانی و خدمات",
    "card2_title": "شماره‌ها", "card2_text": "جست‌وجو و مشاهده",
    "card3_title": "ارسال پیام", "card3_text": "ارتباط با دفتر",
    "slide1_title": "به {site_name} خوش آمدید",
    "slide1_text": "شماره‌های آماده را جست‌وجو کنید و مناسب‌ترین را پیدا کنید.",
    "slide1_link": "/#numbers",
    "slide2_title": "اطلاعات {office_name}",
    "slide2_text": "نشانی، ساعات کاری و خدمات را از نزدیک ببینید.",
    "slide2_link": "/about",
    "slide3_title": "ارتباط با ما",
    "slide3_text": "از طریق فرم پیام با {office_name} در تماس باشید.",
    "slide3_link": "/contact",
    "custom_css": "",
}

# ============ DB ============
def get_db_params():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("متغیر محیطی DATABASE_URL تنظیم نشده است.")
    # پشتیبانی از mysql://, mariadb://, mysql+pymysql://
    for scheme in ("mysql+pymysql://", "mysql://", "mariadb://"):
        if url.startswith(scheme):
            url = url[len(scheme):]
            break
    parsed = urlparse("mysql://" + url)
    return {
        "host": parsed.hostname or "localhost",
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "database": (parsed.path.lstrip("/").split("?")[0]) or "daftar_pishkhan",
        "port": parsed.port or 3306,
    }

def db():
    if "db" not in g:
        params = get_db_params()
        g.db = pymysql.connect(
            host=params["host"],
            user=params["user"],
            password=params["password"],
            database=params["database"],
            port=params["port"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
    return g.db

def q(sql, params=None):
    cur = db().cursor()
    cur.execute(sql, params or ())
    return cur

@app.teardown_appcontext
def close_db(_e=None):
    conn = g.pop("db", None)
    if conn:
        try: conn.close()
        except Exception: pass

NAME_TEXT_FIELDS = [
    "tagline", "office_address", "office_hours", "office_services",
    "card1_title", "card1_text", "card2_title", "card2_text", "card3_title", "card3_text",
    "slide1_title", "slide1_text", "slide2_title", "slide2_text",
    "slide3_title", "slide3_text",
]

def replace_names_in_text(text, reps):
    if not text or not reps: return text
    pattern = re.compile("|".join(re.escape(k) for k in sorted(reps.keys(), key=len, reverse=True) if k))
    return pattern.sub(lambda m: reps.get(m.group(0), m.group(0)), text)

def propagate_names(cur, reps):
    if not reps: return
    for field in NAME_TEXT_FIELDS:
        try:
            cur.execute(f"SELECT {field} FROM site_settings WHERE id=1")
            row = cur.fetchone()
            if not row: continue
            current = row.get(field) or ""
            updated = replace_names_in_text(current, reps)
            if updated != current:
                cur.execute(f"UPDATE site_settings SET {field}=%s WHERE id=1", (updated,))
        except pymysql.Error:
            pass

def init_db():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("=" * 60, flush=True)
        print("⚠️  DATABASE_URL تنظیم نشده است!", flush=True)
        print("   فایل .env را در پوشهٔ پروژه بساز.", flush=True)
        print("=" * 60, flush=True)
        return

    try:
        params = get_db_params()
        conn = pymysql.connect(
            host=params["host"], user=params["user"], password=params["password"],
            database=params["database"], port=params["port"],
            charset="utf8mb4", cursorclass=DictCursor, autocommit=True,
        )
        print("✅ اتصال به دیتابیس برقرار شد.", flush=True)
    except Exception as e:
        print("=" * 60, flush=True)
        print(f"⚠️  اتصال به دیتابیس شکست خورد: {e}", flush=True)
        print("=" * 60, flush=True)
        return

    statements = [
        ("users", """CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            created_at VARCHAR(50) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),
        ("numbers", """CREATE TABLE IF NOT EXISTS numbers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_id INT,
            phone_number VARCHAR(50) NOT NULL,
            operator VARCHAR(50) NOT NULL DEFAULT 'سایر',
            category VARCHAR(50) NOT NULL DEFAULT 'عادی',
            price BIGINT NOT NULL DEFAULT 0,
            description TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'available',
            created_at VARCHAR(50) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),
        ("idx_numbers_status", "CREATE INDEX idx_numbers_status ON numbers(status)"),
        ("idx_numbers_id", "CREATE INDEX idx_numbers_id ON numbers(id)"),
        ("contact_messages", """CREATE TABLE IF NOT EXISTS contact_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(50) NOT NULL,
            message TEXT NOT NULL,
            number_id INT,
            user_id INT,
            is_read INT NOT NULL DEFAULT 0,
            created_at VARCHAR(50) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),
        ("idx_messages_read", "CREATE INDEX idx_messages_read ON contact_messages(is_read)"),
        ("site_settings", """CREATE TABLE IF NOT EXISTS site_settings (
            id INT PRIMARY KEY,
            site_name TEXT NOT NULL,
            tagline TEXT NOT NULL,
            office_name TEXT NOT NULL,
            office_address TEXT NOT NULL,
            office_phone TEXT NOT NULL,
            office_hours TEXT NOT NULL,
            office_services TEXT NOT NULL,
            theme_color VARCHAR(10) NOT NULL DEFAULT '#1e3a8a',
            accent_color VARCHAR(10) NOT NULL DEFAULT '#f4b41a',
            card1_title TEXT NOT NULL,
            card1_text TEXT NOT NULL,
            card2_title TEXT NOT NULL,
            card2_text TEXT NOT NULL,
            card3_title TEXT NOT NULL,
            card3_text TEXT NOT NULL,
            slide1_title TEXT NOT NULL,
            slide1_text TEXT NOT NULL,
            slide1_link TEXT NOT NULL,
            slide2_title TEXT NOT NULL,
            slide2_text TEXT NOT NULL,
            slide2_link TEXT NOT NULL,
            slide3_title TEXT NOT NULL,
            slide3_text TEXT NOT NULL,
            slide3_link TEXT NOT NULL,
            custom_css TEXT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),
    ]

    with conn.cursor() as cur:
        for name, sql in statements:
            try:
                cur.execute(sql)
            except pymysql.Error as e:
                # خطای 1061 = index already exists (طبیعی)
                if e.args[0] != 1061:
                    print(f"⚠️ ساخت {name}: {e}", flush=True)

        # seed settings row 1
        try:
            cur.execute("INSERT IGNORE INTO site_settings(id, site_name, tagline, office_name, "
                        "office_address, office_phone, office_hours, office_services, "
                        "card1_title, card1_text, card2_title, card2_text, card3_title, card3_text, "
                        "slide1_title, slide1_text, slide1_link, slide2_title, slide2_text, slide2_link, "
                        "slide3_title, slide3_text, slide3_link, custom_css) VALUES "
                        "(1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '')",
                        (DEF_SITE_NAME, "خدمات دفتر، ساده‌تر و شفاف‌تر", DEF_OFFICE_NAME,
                         "نشانی دفتر هنوز ثبت نشده است.", "اطلاعات تماس هنوز ثبت نشده است.",
                         "ساعات کاری هنوز ثبت نشده است.", "برای اطلاع از خدمات قابل ارائه، با دفتر تماس بگیرید.",
                         "اطلاعات", "نشانی و خدمات", "شماره‌ها", "جست‌وجو و مشاهده",
                         "ارسال پیام", "ارتباط با دفتر",
                         "به {site_name} خوش آمدید",
                         "شماره‌های آماده را جست‌وجو کنید و مناسب‌ترین را پیدا کنید.",
                         "/#numbers",
                         "اطلاعات {office_name}",
                         "نشانی، ساعات کاری و خدمات را از نزدیک ببینید.",
                         "/about",
                         "ارتباط با ما",
                         "از طریق فرم پیام با {office_name} در تماس باشید.",
                         "/contact"))
        except pymysql.Error as e:
            print(f"⚠️ seed settings: {e}", flush=True)

        # migrations (افزودن ستون‌های جدید اگر جا افتاده)
        try:
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'users'")
            user_cols = {r['column_name'] for r in cur.fetchall()}
            if 'role' not in user_cols:
                cur.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")

            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'contact_messages'")
            msg_cols = {r['column_name'] for r in cur.fetchall()}
            for col, ddl in [("is_read","INT NOT NULL DEFAULT 0"),
                             ("number_id","INT"),("user_id","INT")]:
                if col not in msg_cols:
                    try: cur.execute(f"ALTER TABLE contact_messages ADD COLUMN {col} {ddl}")
                    except pymysql.Error: pass

            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'site_settings'")
            ss_cols = {r['column_name'] for r in cur.fetchall()}
            new_cols = [
                ("card1_title","اطلاعات"),("card1_text","نشانی و خدمات"),
                ("card2_title","شماره‌ها"),("card2_text","جست‌وجو و مشاهده"),
                ("card3_title","ارسال پیام"),("card3_text","ارتباط با دفتر"),
                ("slide1_title","به {site_name} خوش آمدید"),
                ("slide1_text","شماره‌های آماده را جست‌وجو کنید و مناسب‌ترین را پیدا کنید."),
                ("slide1_link","/#numbers"),
                ("slide2_title","اطلاعات {office_name}"),
                ("slide2_text","نشانی، ساعات کاری و خدمات را از نزدیک ببینید."),
                ("slide2_link","/about"),
                ("slide3_title","ارتباط با ما"),
                ("slide3_text","از طریق فرم پیام با {office_name} در تماس باشید."),
                ("slide3_link","/contact"),
                ("office_phone","اطلاعات تماس هنوز ثبت نشده است."),
                ("custom_css",""),
            ]
            for col, default in new_cols:
                if col not in ss_cols:
                    try:
                        safe = default.replace("'","''")
                        cur.execute(f"ALTER TABLE site_settings ADD COLUMN {col} TEXT NOT NULL DEFAULT '{safe}'")
                    except pymysql.Error: pass
        except pymysql.Error as e:
            print(f"⚠️ migration: {e}", flush=True)

        # name sync
        try:
            cur.execute("SELECT site_name, office_name FROM site_settings WHERE id=1")
            row = cur.fetchone()
            if row:
                site = (row['site_name'] or "").strip()
                office = (row['office_name'] or "").strip()
                if site == DEF_SITE_NAME and office and office != DEF_OFFICE_NAME:
                    clean = office[5:].strip() if office.startswith("دفتر ") else office
                    cur.execute("UPDATE site_settings SET site_name=%s WHERE id=1", (clean,))
                elif office == DEF_OFFICE_NAME and site and site != DEF_SITE_NAME:
                    cur.execute("UPDATE site_settings SET office_name=%s WHERE id=1", ("دفتر " + site,))
        except pymysql.Error: pass

        # defaults fix
        try:
            cur.execute("UPDATE site_settings SET theme_color=%s, accent_color=%s "
                        "WHERE id=1 AND theme_color='#6484ff' AND accent_color='#55cdb7'",
                        (DEFAULT_BLUE, DEFAULT_YELLOW))
        except pymysql.Error: pass
        try: cur.execute("UPDATE numbers SET status='available' WHERE status='sold'")
        except pymysql.Error: pass
        # first user → admin
        try:
            cur.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'")
            if cur.fetchone()['c'] == 0:
                cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
                first = cur.fetchone()
                if first:
                    cur.execute("UPDATE users SET role='admin' WHERE id=%s", (first['id'],))
        except pymysql.Error: pass

    conn.close()
    print("✅ init_db کامل شد. جداول آماده‌اند.", flush=True)

try:
    init_db()
except Exception as e:
    print(f"⚠️ Startup: {e}", flush=True)

# ============ Helpers ============
def valid_phone(v):
    v = (v or "").strip()
    return 4 <= len(v) <= 30 and bool(re.fullmatch(r"[0-9۰-۹٠-٩+()\-\s.]+", v))

@app.before_request
def load_globals():
    g.user = None; g.site = None
    uid = session.get("user_id")
    if uid:
        try:
            row = q("SELECT id, name, email, role FROM users WHERE id=%s", (uid,)).fetchone()
            if row is None: session.clear()
            else: g.user = row
        except Exception: pass

def get_settings():
    if g.get("site") is None:
        try:
            row = q("SELECT * FROM site_settings WHERE id=1").fetchone()
            g.site = row if row else dict(DEFAULT_SETTINGS)
        except Exception:
            g.site = dict(DEFAULT_SETTINGS)
    return g.site

def is_admin():
    return bool(g.user and g.user["role"] == "admin")

def admin_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not g.user:
            flash("برای دسترسی به پنل مدیریت وارد شوید.", "warning")
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin": abort(403)
        return fn(*a, **kw)
    return w

@app.context_processor
def inject_common():
    r = {"unread_messages": 0}
    try:
        if is_admin():
            row = q("SELECT COUNT(*) AS c FROM contact_messages WHERE is_read=0").fetchone()
            r["unread_messages"] = row['c'] if row else 0
    except Exception: pass
    return r

# ============ CSS ============
CSS = """
html{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;-webkit-text-size-adjust:100%}
:root{
  --ink:#0f172a;--ink-soft:#334155;--muted:#64748b;
  --blue:{{ site.theme_color }};--yellow:{{ site.accent_color }};
  --line:rgba(15,23,42,.08);
  --glass-bg:linear-gradient(135deg,rgba(255,255,255,.32) 0%,rgba(255,255,255,.16) 100%);
  --glass-blur:blur(44px) saturate(240%);
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;min-height:100vh;font-family:'Vazirmatn',system-ui,Tahoma,sans-serif;
  color:var(--ink);direction:rtl;line-height:1.75;
  background:
    radial-gradient(ellipse at 15% 20%,{{ site.theme_color }}66,transparent 48%),
    radial-gradient(ellipse at 85% 15%,{{ site.accent_color }}59,transparent 48%),
    radial-gradient(ellipse at 50% 95%,{{ site.theme_color }}44,transparent 55%),
    radial-gradient(ellipse at 20% 80%,{{ site.accent_color }}38,transparent 45%),
    linear-gradient(135deg,#dde5f0,#d2dceb 50%,#e0e4ed);
  background-attachment:fixed;overflow-x:hidden}
body::before,body::after{content:'';position:fixed;border-radius:50%;filter:blur(120px);
  pointer-events:none;z-index:-1;animation:float 24s ease-in-out infinite}
body::before{width:520px;height:520px;top:-160px;right:-160px;background:{{ site.theme_color }}77}
body::after{width:480px;height:480px;bottom:-160px;left:-160px;background:{{ site.accent_color }}6b;animation-delay:-12s}
@keyframes float{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(35px,-45px) scale(1.12)}66%{transform:translate(-25px,35px) scale(.94)}}
a{color:inherit;text-decoration:none}
button,input,select,textarea{font:inherit;font-family:inherit}
h1,h2,h3,h4{margin:0;font-weight:700;letter-spacing:-.3px;line-height:1.45}
p{margin:0}
.wrap{width:min(1180px,92%);margin:auto}

.glass{background:var(--glass-bg);border:1px solid rgba(255,255,255,.65);border-radius:18px;position:relative;
  box-shadow:0 14px 44px rgba(31,38,135,.14),0 4px 12px rgba(0,0,0,.05),
    inset 0 1px 0 rgba(255,255,255,1),inset 0 -1px 0 rgba(255,255,255,.2);
  backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur)}
.glass::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,1),transparent);
  border-radius:18px 18px 0 0;pointer-events:none}
.glass::after{content:'';position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:linear-gradient(135deg,rgba(255,255,255,.22) 0%,transparent 45%,transparent 60%,rgba(255,255,255,.08) 100%)}

.nav{background:linear-gradient(135deg,rgba(255,255,255,.4),rgba(255,255,255,.18));
  border:1px solid rgba(255,255,255,.7);border-radius:16px;padding:12px 22px;margin-top:16px;
  display:flex;align-items:center;justify-content:space-between;gap:14px;
  box-shadow:0 14px 44px rgba(31,38,135,.14),inset 0 1px 0 rgba(255,255,255,1);
  backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur);position:relative}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.02rem;position:relative;z-index:2;min-width:0}
.brand-mark{width:38px;height:38px;display:grid;place-items:center;border-radius:11px;
  color:#fff;font-weight:800;flex-shrink:0;
  background:linear-gradient(145deg,var(--blue),#152e6f);
  box-shadow:0 6px 16px var(--blue)55,inset 0 1px 0 rgba(255,255,255,.3)}
.brand > span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.navlinks{display:flex;align-items:center;gap:16px;flex-wrap:wrap;font-size:.88rem;font-weight:500;position:relative;z-index:2}
.navlinks a{padding:8px 12px;border-radius:8px;transition:all .2s;min-height:40px;display:inline-flex;align-items:center}
.navlinks a:hover{color:var(--blue);background:rgba(255,255,255,.4)}
.badge{display:inline-block;background:#ef5350;color:#fff;font-size:.68rem;border-radius:999px;padding:1px 7px;margin-right:4px;font-weight:700}

.btn{display:inline-flex;justify-content:center;align-items:center;gap:6px;border:0;cursor:pointer;
  border-radius:11px;padding:11px 18px;font-weight:600;transition:all .2s;white-space:nowrap;
  font-size:.9rem;position:relative;overflow:hidden;min-height:44px}
.btn:hover{transform:translateY(-2px)}
.primary{color:#fff;background:linear-gradient(135deg,var(--blue),#152e6f);
  box-shadow:0 8px 22px var(--blue)55,inset 0 1px 0 rgba(255,255,255,.3)}
.primary:hover{box-shadow:0 12px 30px var(--blue)66,inset 0 1px 0 rgba(255,255,255,.35)}
.soft{background:rgba(255,255,255,.45);border:1px solid rgba(255,255,255,.9);color:var(--ink-soft);
  backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.soft:hover{background:rgba(255,255,255,.7)}
.danger{background:rgba(255,241,241,.5);color:#b83e4c;border:1px solid rgba(244,218,218,.9);backdrop-filter:blur(16px)}

.section{padding:24px 0 48px}
.section-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:18px}
.section-head h2{font-size:1.4rem;margin:2px 0}
.muted{color:var(--muted)}
.small{font-size:.84rem}
.pill{display:inline-block;border-radius:999px;padding:4px 11px;font-size:.75rem;
  background:var(--yellow)3d;color:#8a6212;font-weight:600;backdrop-filter:blur(8px)}
.pill.blue{background:var(--blue)26;color:var(--blue)}
.tag{padding:4px 10px;border-radius:7px;background:var(--blue)1f;color:var(--blue);font-size:.75rem;font-weight:500}

.hero-split{display:grid;grid-template-columns:240px 1fr;gap:14px;padding:22px 0 16px;align-items:stretch}
.hero-cards{display:flex;flex-direction:column;gap:10px}
.part-card{padding:14px 16px;display:flex;align-items:center;gap:10px;text-align:right;
  transition:all .25s;flex:1;min-height:64px}
.part-card:hover{transform:translateX(-4px);box-shadow:0 22px 52px rgba(31,38,135,.18),inset 0 1px 0 rgba(255,255,255,1)}
.tc-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:10px;font-size:1rem;flex-shrink:0}
.tc-icon.blue{background:linear-gradient(135deg,var(--blue),#2b4cae);color:#fff;box-shadow:0 4px 12px var(--blue)55}
.tc-icon.yellow{background:linear-gradient(135deg,var(--yellow),#d69b0e);color:#fff;box-shadow:0 4px 12px var(--yellow)66}
.part-card > div:last-child{display:flex;flex-direction:column;min-width:0;position:relative;z-index:2}
.part-card h3{font-size:.9rem;margin:0;line-height:1.3}
.part-card p{font-size:.74rem;color:var(--muted);margin:2px 0 0;line-height:1.35}

.hero-slideshow{position:relative;min-height:340px;border-radius:20px;overflow:hidden;
  background:linear-gradient(135deg,#0f172a,#1e3a8a);
  box-shadow:0 24px 72px rgba(31,38,135,.24),inset 0 1px 0 rgba(255,255,255,.15)}
.slide{position:absolute;inset:0;opacity:0;transition:opacity .9s cubic-bezier(.4,0,.2,1);z-index:1;pointer-events:none}
.slide.active{opacity:1;z-index:2;pointer-events:auto}
.slide-bg{position:absolute;inset:0;background-size:cover;background-position:center;
  transform:scale(1.1);transition:transform 9s ease-out}
.slide.active .slide-bg{transform:scale(1)}
.slide-overlay{position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(15,23,42,.82) 0%,rgba(15,23,42,.35) 60%,rgba(15,23,42,.65) 100%)}
.slide-body{position:relative;z-index:3;padding:36px;height:100%;display:flex;flex-direction:column;
  justify-content:flex-end;color:#fff;transform:translateY(20px);opacity:0;
  transition:transform .8s cubic-bezier(.4,0,.2,1) .1s,opacity .8s ease .1s}
.slide.active .slide-body{transform:translateY(0);opacity:1}
.slide-body h2{font-size:clamp(1.5rem,2.8vw,2.2rem);margin:0 0 10px;line-height:1.35;
  text-shadow:0 4px 20px rgba(0,0,0,.4);font-weight:800;letter-spacing:-.5px}
.slide-body p{font-size:1rem;line-height:1.85;max-width:540px;
  text-shadow:0 2px 12px rgba(0,0,0,.5);opacity:.95}
.slide-cta{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;margin-top:18px;
  padding:12px 22px;border-radius:12px;background:linear-gradient(135deg,var(--yellow),#d69b0e);
  color:#1a1a1a;font-weight:800;font-size:.9rem;min-height:44px;
  box-shadow:0 8px 24px var(--yellow)66,inset 0 1px 0 rgba(255,255,255,.4);transition:all .2s}
.slide-cta:hover{transform:translateY(-2px) scale(1.02)}
.slide-nav{position:absolute;bottom:18px;right:24px;z-index:5;display:flex;align-items:center;gap:8px}
.slide-dot{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,.4);
  border:0;cursor:pointer;padding:0;transition:all .3s;min-width:10px;min-height:10px}
.slide-dot:hover{background:rgba(255,255,255,.7)}
.slide-dot.active{width:28px;border-radius:5px;background:var(--yellow);box-shadow:0 0 12px var(--yellow)88}
.slide-arrow{position:absolute;top:50%;transform:translateY(-50%);z-index:5;width:44px;height:44px;
  border-radius:50%;background:rgba(255,255,255,.2);backdrop-filter:blur(14px) saturate(180%);
  -webkit-backdrop-filter:blur(14px) saturate(180%);
  border:1px solid rgba(255,255,255,.4);color:#fff;cursor:pointer;display:grid;place-items:center;
  font-size:1.1rem;transition:all .25s;opacity:0;min-width:44px;min-height:44px}
.hero-slideshow:hover .slide-arrow{opacity:1}
.slide-arrow:hover{background:rgba(255,255,255,.35);transform:translateY(-50%) scale(1.1)}
.slide-prev{right:16px}
.slide-next{left:16px}
.slide-progress{position:absolute;bottom:0;right:0;left:0;height:3px;
  background:rgba(255,255,255,.15);z-index:5}
.slide.active .slide-progress-bar{height:100%;background:linear-gradient(90deg,var(--yellow),#fbbf24);
  animation:slideProgress 6s linear forwards;box-shadow:0 0 12px var(--yellow)88}
@keyframes slideProgress{from{width:0}to{width:100%}}

.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.num-card{padding:16px;display:flex;flex-direction:column;transition:all .25s}
.num-card:hover{transform:translateY(-4px);box-shadow:0 22px 52px rgba(31,38,135,.18),inset 0 1px 0 rgba(255,255,255,1)}
.num-top{display:flex;justify-content:space-between;gap:6px;align-items:center;position:relative;z-index:2}
.num-card h3{font-size:1rem;letter-spacing:.2px;margin:10px 0;overflow-wrap:anywhere;position:relative;z-index:2}
.price{font-weight:800;font-size:.95rem;color:var(--blue);position:relative;z-index:2}
.meta{display:flex;gap:5px;flex-wrap:wrap;margin:8px 0;position:relative;z-index:2}
.card-foot{display:flex;justify-content:space-between;align-items:center;gap:6px;
  margin-top:auto;padding-top:10px;border-top:1px dashed rgba(255,255,255,.5);position:relative;z-index:2}
.num-card .btn{font-size:.78rem;padding:9px 14px}
.num-card p{position:relative;z-index:2}

.filters{padding:14px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr auto;gap:8px;margin-bottom:16px}
.field{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.field label{font-size:.9rem;font-weight:700;color:var(--ink-soft);display:block;margin-bottom:2px}
.field label .muted{font-weight:400}
.control{width:100%;min-height:48px;height:48px;padding:12px 14px;border-radius:12px;
  background:rgba(255,255,255,.55);border:1.5px solid rgba(255,255,255,.9);
  color:var(--ink);outline:none;transition:.15s;
  backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.7);font-size:.94rem;font-weight:500}
.control:focus{background:rgba(255,255,255,.9);border-color:var(--blue);
  box-shadow:0 0 0 4px var(--blue)26,inset 0 1px 0 rgba(255,255,255,.95)}
select.control{appearance:none;-webkit-appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2 4l4 4 4-4' stroke='%2364748b' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:left 14px center;padding-left:36px}
textarea.control{resize:vertical;min-height:96px;height:auto;line-height:1.6}
input[type=color].control{height:52px;min-height:52px;padding:6px;cursor:pointer;background:rgba(255,255,255,.7)}
input[type=color].control::-webkit-color-swatch-wrapper{padding:0;border-radius:8px}
input[type=color].control::-webkit-color-swatch{border:2px solid rgba(0,0,0,.08);border-radius:8px}
input[type=color].control::-moz-color-swatch{border:2px solid rgba(0,0,0,.08);border-radius:8px}
.preview-bar{height:52px;border-radius:12px;border:1.5px solid rgba(0,0,0,.08);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.6);flex-shrink:0}

.form-card{width:min(540px,100%);margin:28px auto;padding:28px}
.form-card h1{font-size:1.4rem;margin-bottom:6px}
.form-card p.muted{margin:0 0 18px}
.auth-link{color:var(--blue);font-weight:600}

.table-wrap{overflow:auto;border-radius:12px;position:relative;z-index:2;-webkit-overflow-scrolling:touch}
.data-table{width:100%;border-collapse:collapse;min-width:620px;font-size:.88rem;
  background:rgba(255,255,255,.42);backdrop-filter:blur(24px) saturate(180%);
  -webkit-backdrop-filter:blur(24px) saturate(180%);border-radius:12px;overflow:hidden}
.data-table th,.data-table td{text-align:right;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.35)}
.data-table th{color:var(--muted);font-weight:600;background:rgba(255,255,255,.35);font-size:.82rem}
.data-table tr:hover td{background:rgba(255,255,255,.35)}
.data-table tr:last-child td{border-bottom:0}

.flash{margin:12px 0;padding:12px 18px;border-radius:11px;
  background:rgba(255,255,255,.5);border:1px solid rgba(255,255,255,.9);font-size:.9rem;
  backdrop-filter:blur(24px) saturate(180%);-webkit-backdrop-filter:blur(24px) saturate(180%);
  box-shadow:0 8px 20px rgba(31,38,135,.08),inset 0 1px 0 rgba(255,255,255,.8)}
.flash.success{background:rgba(233,251,244,.65);color:#1e7a5f;border-color:rgba(200,240,222,.9)}
.flash.warning{background:rgba(255,247,230,.65);color:#8a6318;border-color:rgba(244,227,184,.9)}
.flash.error{background:rgba(255,240,240,.65);color:#a93443;border-color:rgba(244,218,218,.9)}

.empty{padding:36px;text-align:center;grid-column:1/-1;position:relative;z-index:2}
.pager{display:flex;justify-content:center;align-items:center;gap:8px;margin-top:20px;flex-wrap:wrap}
.footer{border-top:1px solid rgba(255,255,255,.5);padding:22px 0;color:var(--muted);
  font-size:.84rem;margin-top:16px;backdrop-filter:blur(16px)}
.info-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.info-grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.info-box{padding:18px}
.info-box h3{font-size:.98rem;margin-bottom:6px;position:relative;z-index:2}
.info-box p{position:relative;z-index:2}
.notice{padding:12px 16px;border-radius:10px;background:rgba(255,247,230,.55);color:#6f531c;
  font-size:.86rem;line-height:1.85;border:1px solid rgba(244,227,184,.85);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);position:relative;z-index:2}
.phone-box{display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center}
.phone-display{font-size:1.35rem;font-weight:800;color:var(--blue);letter-spacing:1.5px;
  margin-top:12px;direction:ltr;text-shadow:0 2px 14px var(--blue)44;
  font-variant-numeric:tabular-nums;position:relative;z-index:2;word-break:break-all}
.side-phone{font-size:1.15rem;font-weight:800;color:var(--blue);direction:ltr;
  display:inline-block;letter-spacing:1px;text-shadow:0 2px 10px var(--blue)33}

.contact-options{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:18px}
.contact-card{padding:18px;border-radius:14px;background:rgba(255,255,255,.42);
  border:1px solid rgba(255,255,255,.9);backdrop-filter:blur(20px) saturate(180%);
  -webkit-backdrop-filter:blur(20px) saturate(180%);box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.contact-card h4{font-size:.94rem;margin:0 0 6px}
.contact-card p{line-height:1.8;margin:0 0 8px;font-size:.88rem}
.contact-card .btn{width:100%;margin-top:6px}
.contact-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:11px;
  background:linear-gradient(135deg,var(--blue),#2b4cae);color:#fff;font-size:1.05rem;margin-bottom:10px;
  box-shadow:0 4px 12px var(--blue)55}
.detail-card{padding:clamp(20px,4vw,36px);max-width:820px;margin:16px auto}
.detail-card h1,.detail-card h3,.detail-card p,.detail-card .price,.detail-card .meta,
.detail-card .contact-options,.detail-card > p:last-child{position:relative;z-index:2}

.hero{padding:30px 0;display:grid;grid-template-columns:1.15fr .85fr;gap:28px;align-items:center}
.hero h1{font-size:clamp(1.7rem,3.5vw,2.6rem);line-height:1.35;margin:10px 0}
.hero p{color:var(--muted);line-height:2;max-width:540px}
.hero-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.eyebrow{display:inline-block;background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.9);
  padding:6px 12px;border-radius:999px;color:var(--ink-soft);font-size:.8rem;font-weight:500;backdrop-filter:blur(16px)}
.side-card{padding:20px}
.side-card h3{font-size:.98rem;margin-bottom:10px;position:relative;z-index:2}
.side-card p{position:relative;z-index:2}

.admin-tabs{display:flex;gap:4px;margin-bottom:18px;flex-wrap:wrap;
  background:rgba(255,255,255,.4);padding:6px;border-radius:12px;
  border:1px solid rgba(255,255,255,.9);width:fit-content;
  backdrop-filter:blur(24px) saturate(180%);-webkit-backdrop-filter:blur(24px) saturate(180%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.admin-tab{padding:10px 16px;border-radius:9px;font-size:.86rem;font-weight:600;
  color:var(--ink-soft);transition:.15s;min-height:40px;display:inline-flex;align-items:center}
.admin-tab:hover{background:rgba(255,255,255,.55)}
.admin-tab.active{background:linear-gradient(135deg,var(--blue),#152e6f);color:#fff;box-shadow:0 4px 12px var(--blue)55}
.admin-tab.active .badge{background:rgba(255,255,255,.3)}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
.stat-card{padding:18px;border-radius:14px;background:rgba(255,255,255,.42);
  border:1px solid rgba(255,255,255,.9);backdrop-filter:blur(20px) saturate(180%);
  -webkit-backdrop-filter:blur(20px) saturate(180%);box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.stat-card b{display:block;font-size:1.5rem;letter-spacing:-.4px;margin-bottom:2px}
.stat-card span{font-size:.8rem;color:var(--muted)}

.admin-settings-form{max-width:920px !important}
.admin-settings-form .info-grid{grid-template-columns:1fr 1fr 1fr;gap:14px}
.admin-settings-form h3{font-size:1.05rem;padding-bottom:8px;border-bottom:2px solid var(--line);margin-bottom:14px}
.admin-settings-form .glass{padding:16px !important}

.version-badge{text-align:center;padding:12px 0 4px;color:var(--muted);font-size:.7rem;opacity:.55}

@media(max-width:1024px){
  .cards{grid-template-columns:repeat(3,minmax(0,1fr))}
  .admin-settings-form .info-grid{grid-template-columns:1fr 1fr}
}
@media(max-width:900px){
  .hero{grid-template-columns:1fr;padding-top:20px;gap:18px}
  .filters{grid-template-columns:1fr 1fr}
  .info-grid,.info-grid-4{grid-template-columns:repeat(2,1fr)}
  .stat-grid{grid-template-columns:repeat(2,1fr)}
  .nav{flex-direction:column;align-items:flex-start;padding:12px 16px;gap:10px}
  .brand{width:100%;min-width:0}
  .navlinks{gap:6px;font-size:.85rem;width:100%;justify-content:flex-start}
  .navlinks a{padding:8px 10px;font-size:.82rem;flex-shrink:0}
  .hero-split{grid-template-columns:1fr;gap:12px;padding-top:16px}
  .hero-cards{flex-direction:row;flex-wrap:wrap;order:2}
  .part-card{flex:1 1 calc(50% - 5px);min-height:auto}
  .hero-slideshow{order:1;min-height:300px}
  body::before,body::after{filter:blur(90px)}
  .admin-settings-form .info-grid{grid-template-columns:1fr}
}
@media(max-width:768px){
  .cards{grid-template-columns:repeat(2,minmax(0,1fr))}
  .wrap{width:min(1180px,94%)}
  .slide-arrow{opacity:.85}
  .control,input,select,textarea{font-size:16px !important}
}
@media(max-width:560px){
  body{line-height:1.7;font-size:.94rem}
  .wrap{width:94%}
  .cards{grid-template-columns:1fr;gap:10px}
  .filters{grid-template-columns:1fr;padding:12px;gap:10px}
  .contact-options{grid-template-columns:1fr}
  .section-head{flex-direction:column;align-items:flex-start;gap:8px}
  .section-head h2{font-size:1.25rem}
  .form-card{padding:20px 16px}
  .stat-grid{grid-template-columns:1fr 1fr;gap:8px}
  .stat-card{padding:14px}
  .stat-card b{font-size:1.25rem}
  .part-card{flex:1 1 100%;padding:12px 14px}
  .tc-icon{width:34px;height:34px;font-size:.9rem}
  .part-card h3{font-size:.86rem}
  .part-card p{font-size:.72rem}
  .hero-slideshow{min-height:clamp(220px,45vh,300px);border-radius:16px}
  .slide-body{padding:22px 20px 52px}
  .slide-body h2{font-size:1.28rem;margin-bottom:8px}
  .slide-body p{font-size:.88rem;line-height:1.7}
  .slide-cta{padding:10px 16px;font-size:.85rem;min-height:42px;margin-top:14px}
  .slide-arrow{width:34px;height:34px;font-size:.9rem;opacity:.75}
  .slide-prev{right:8px}
  .slide-next{left:8px}
  .slide-nav{bottom:14px;right:14px;gap:6px}
  .slide-dot{min-width:8px;min-height:8px}
  .info-grid,.info-grid-4{grid-template-columns:1fr}
  .info-box{padding:16px}
  .nav{padding:10px 12px}
  .brand{font-size:.95rem}
  .brand-mark{width:34px;height:34px}
  .btn{padding:11px 14px;font-size:.86rem}
  .control{font-size:16px !important;min-height:48px;height:48px}
  input[type=color].control{height:52px;min-height:52px}
  .data-table{font-size:.82rem}
  .data-table th,.data-table td{padding:10px 10px}
  .detail-card{padding:18px}
  .detail-card h1{font-size:1.35rem !important}
  .detail-card .price{font-size:1.15rem !important}
  .contact-card{padding:14px}
  .phone-display{font-size:1.15rem}
  .side-phone{font-size:1.02rem}
  .admin-tabs{width:100%;padding:5px}
  .admin-tab{padding:9px 12px;font-size:.8rem}
  .field label{font-size:.86rem}
  .admin-settings-form{max-width:100% !important}
}
@media(max-width:400px){
  .part-card h3{font-size:.82rem}
  .slide-body h2{font-size:1.15rem}
  .slide-body p{font-size:.82rem}
  .btn{font-size:.82rem;padding:10px 12px}
  .navlinks a{font-size:.78rem;padding:6px 8px}
  .hero-slideshow{min-height:240px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}.slide-bg{transform:scale(1)!important}}
@media(hover:none){
  .slide-arrow{opacity:.85}
  .part-card:hover{transform:none}
  .num-card:hover{transform:none}
  .btn:hover{transform:none}
}
"""

BASE = """
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,viewport-fit=cover">
<meta name="theme-color" content="{{ site.theme_color }}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>""" + CSS + """</style>
{% if site.custom_css %}<style>{{ site.custom_css | safe }}</style>{% endif %}
</head>
<body>
<div class="wrap">
<header class="nav">
  <a class="brand" href="{{ url_for('index') }}">
    <span class="brand-mark">پ</span>
    <span>{{ site.site_name }}</span>
  </a>
  <nav class="navlinks">
    <a href="{{ url_for('index') }}">خانه</a>
    <a href="{{ url_for('index') }}#numbers">شماره‌ها</a>
    <a href="{{ url_for('about') }}">اطلاعات</a>
    <a href="{{ url_for('contact') }}">ارسال پیام</a>
    {% if g.user %}
      {% if g.user['role']=='admin' %}
        <a class="btn primary" href="{{ url_for('admin') }}">پنل مدیریت{% if unread_messages %}<span class="badge">{{ unread_messages }}</span>{% endif %}</a>
      {% else %}
        <a class="btn soft" href="{{ url_for('dashboard') }}">پنل من</a>
      {% endif %}
    {% else %}
      <a href="{{ url_for('login') }}">ورود</a>
      <a class="btn primary" href="{{ url_for('register') }}">ثبت‌نام</a>
    {% endif %}
  </nav>
</header>
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% for cat, msg in msgs %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
{% endwith %}
{% block content %}{% endblock %}
<footer class="footer">
  <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
    <span>© {{ year }} {{ site.site_name }} — {{ site.tagline }}</span>
    <span>سامانه معرفی و مدیریت شماره‌ها</span>
  </div>
</footer>
<div class="version-badge">نسخه {{ APP_VERSION }}</div>
</div>
</body>
</html>
"""
app.jinja_loader = DictLoader({"base.html": BASE})

INDEX = """
{% extends "base.html" %}{% block content %}
<section class="hero-split">
  <div class="hero-cards">
    <a class="glass part-card" href="{{ url_for('about') }}">
      <div class="tc-icon blue">ⓘ</div>
      <div><h3>{{ site.card1_title }}</h3><p>{{ site.card1_text }}</p></div>
    </a>
    <a class="glass part-card" href="#numbers">
      <div class="tc-icon yellow">▦</div>
      <div><h3>{{ site.card2_title }}</h3><p>{{ site.card2_text }}</p></div>
    </a>
    <a class="glass part-card" href="{{ url_for('contact') }}">
      <div class="tc-icon blue">✉</div>
      <div><h3>{{ site.card3_title }}</h3><p>{{ site.card3_text }}</p></div>
    </a>
  </div>

  <div class="hero-slideshow" id="heroSlideshow">
    {% set gradients = [
      'linear-gradient(135deg,#1e3a8a,#4c1d95)',
      'linear-gradient(135deg,#1e3a8a,#0f766e)',
      'linear-gradient(135deg,#1e3a8a,#b45309)'
    ] %}
    {% for i in [1,2,3] %}
      {% set s_title = (site['slide' ~ i ~ '_title'] or '') | replace('{site_name}', site.site_name or '') | replace('{office_name}', site.office_name or '') %}
      {% set s_text = (site['slide' ~ i ~ '_text'] or '') | replace('{site_name}', site.site_name or '') | replace('{office_name}', site.office_name or '') %}
      {% set s_link = site['slide' ~ i ~ '_link'] %}
      {% if s_title or s_text %}
      <div class="slide {% if i == 1 %}active{% endif %}" data-idx="{{ i-1 }}">
        <div class="slide-bg" style="background:{{ gradients[i-1] }}"></div>
        <div class="slide-overlay"></div>
        <div class="slide-body">
          {% if s_title %}<h2>{{ s_title }}</h2>{% endif %}
          {% if s_text %}<p>{{ s_text }}</p>{% endif %}
          {% if s_link %}<a class="slide-cta" href="{{ s_link }}">مشاهده ←</a>{% endif %}
        </div>
        <div class="slide-progress"><div class="slide-progress-bar"></div></div>
      </div>
      {% endif %}
    {% endfor %}
    <button class="slide-arrow slide-prev" aria-label="قبلی">→</button>
    <button class="slide-arrow slide-next" aria-label="بعدی">←</button>
    <div class="slide-nav">
      {% for i in [1,2,3] %}<button class="slide-dot {% if i == 1 %}active{% endif %}" aria-label="اسلاید {{ i }}"></button>{% endfor %}
    </div>
  </div>
</section>

<section class="section" id="numbers">
<div class="section-head">
  <div><h2>شماره‌های آماده</h2><div class="muted small">جست‌وجو، فیلتر قیمت و مشاهده جزئیات.</div></div>
  <span class="pill">{{ total }} مورد</span>
</div>
<form class="glass filters" method="get" action="{{ url_for('index') }}">
  <input class="control" name="q" value="{{ q }}" placeholder="جست‌وجوی شماره یا توضیحات…">
  <select class="control" name="operator"><option value="">همه اپراتورها</option>
    {% for x in operators %}<option value="{{ x }}" {% if operator==x %}selected{% endif %}>{{ x }}</option>{% endfor %}
  </select>
  <select class="control" name="category"><option value="">همه دسته‌ها</option>
    {% for x in categories %}<option value="{{ x }}" {% if category==x %}selected{% endif %}>{{ x }}</option>{% endfor %}
  </select>
  <input class="control" type="number" name="price_min" value="{{ price_min }}" placeholder="حداقل قیمت" min="0" inputmode="numeric">
  <input class="control" type="number" name="price_max" value="{{ price_max }}" placeholder="حداکثر قیمت" min="0" inputmode="numeric">
  <select class="control" name="sort">
    <option value="new" {% if sort=='new' %}selected{% endif %}>جدیدترین</option>
    <option value="low" {% if sort=='low' %}selected{% endif %}>ارزان‌ترین</option>
    <option value="high" {% if sort=='high' %}selected{% endif %}>گران‌ترین</option>
  </select>
  <button class="btn primary" type="submit">اعمال فیلتر</button>
</form>

<div class="cards">
{% for n in numbers %}
<article class="glass num-card">
  <div class="num-top"><span class="pill blue">{{ n['operator'] }}</span><span class="muted small">#{{ n['id'] }}</span></div>
  <h3>{{ n['phone_number'] }}</h3>
  <div class="price">{{ "{:,}".format(n['price']) }} تومان</div>
  <div class="meta"><span class="tag">{{ n['category'] }}</span>{% if n['status']=='reserved' %}<span class="pill">رزرو</span>{% endif %}</div>
  <p class="muted small" style="line-height:1.7;font-size:.8rem">{{ n['description'][:70] or 'بدون توضیح.' }}</p>
  <div class="card-foot"><span class="muted small">{{ n['created_at'][:10] }}</span>
    <a class="btn primary" href="{{ url_for('number_detail', number_id=n['id']) }}">مشاهده</a></div>
</article>
{% else %}
<div class="glass empty"><h3>نتیجه‌ای پیدا نشد</h3>
  <p class="muted">عبارت جست‌وجو یا فیلترها را تغییر دهید.</p>
  <a class="btn soft" href="{{ url_for('index') }}" style="margin-top:10px">پاک‌کردن فیلترها</a></div>
{% endfor %}
</div>
{% if pages > 1 %}
<div class="pager">
  {% if page>1 %}<a class="btn soft" href="{{ url_for('index',q=q,operator=operator,category=category,sort=sort,price_min=price_min,price_max=price_max,page=page-1) }}">قبلی</a>{% endif %}
  <span class="muted small">صفحه {{ page }} از {{ pages }}</span>
  {% if page<pages %}<a class="btn soft" href="{{ url_for('index',q=q,operator=operator,category=category,sort=sort,price_min=price_min,price_max=price_max,page=page+1) }}">بعدی</a>{% endif %}
</div>
{% endif %}
</section>

<script>
(function(){
  const box = document.getElementById('heroSlideshow');
  if (!box) return;
  const slides = box.querySelectorAll('.slide');
  const dots = box.querySelectorAll('.slide-dot');
  const prev = box.querySelector('.slide-prev');
  const next = box.querySelector('.slide-next');
  if (slides.length < 2) return;
  let current = 0, timer = null;
  const DURATION = 6000;
  function show(idx){
    idx = (idx + slides.length) % slides.length;
    slides.forEach((s, i) => s.classList.toggle('active', i === idx));
    dots.forEach((d, i) => d.classList.toggle('active', i === idx));
    current = idx;
  }
  function restart(){
    if (timer) clearInterval(timer);
    timer = setInterval(() => show(current + 1), DURATION);
    const bar = slides[current].querySelector('.slide-progress-bar');
    if (bar) { bar.style.animation = 'none'; void bar.offsetWidth; bar.style.animation = ''; }
  }
  dots.forEach((d, i) => d.addEventListener('click', () => { show(i); restart(); }));
  if (prev) prev.addEventListener('click', () => { show(current - 1); restart(); });
  if (next) next.addEventListener('click', () => { show(current + 1); restart(); });
  box.addEventListener('mouseenter', () => { if (timer) clearInterval(timer); });
  box.addEventListener('mouseleave', restart);
  let tx = 0;
  box.addEventListener('touchstart', e => { tx = e.changedTouches[0].screenX; }, {passive:true});
  box.addEventListener('touchend', e => {
    const diff = tx - e.changedTouches[0].screenX;
    if (Math.abs(diff) > 50) { show(current + (diff > 0 ? 1 : -1)); restart(); }
  }, {passive:true});
  box.setAttribute('tabindex', '0');
  restart();
})();
</script>
{% endblock %}
"""

AUTH = """
{% extends "base.html" %}{% block content %}
<section class="form-card glass">
<h1 style="position:relative;z-index:2">{{ heading }}</h1>
<p class="muted" style="position:relative;z-index:2">{{ subtitle }}</p>
<form method="post" style="position:relative;z-index:2">
{% if mode=='register' %}
<div class="field"><label>نام و نام خانوادگی</label><input class="control" name="name" value="{{ form_name or '' }}" required maxlength="80" autocomplete="name"></div>
{% endif %}
<div class="field"><label>ایمیل</label><input class="control" type="email" name="email" value="{{ form_email or '' }}" required maxlength="254" autocomplete="email" inputmode="email"></div>
<div class="field"><label>رمز عبور</label><input class="control" type="password" name="password" required minlength="8" autocomplete="{{ 'new-password' if mode=='register' else 'current-password' }}"></div>
<button class="btn primary" type="submit" style="width:100%">{{ 'ساخت حساب' if mode=='register' else 'ورود' }}</button>
</form>
<p class="muted small" style="margin-top:14px;position:relative;z-index:2">
  {% if mode=='register' %}حساب دارید؟ <a class="auth-link" href="{{ url_for('login') }}">وارد شوید</a>
  {% else %}حساب ندارید؟ <a class="auth-link" href="{{ url_for('register') }}">ثبت‌نام کنید</a>{% endif %}
</p>
<div class="notice small" style="margin-top:14px">
  {% if mode=='register' %}اولین حساب به‌عنوان مدیر سایت ثبت می‌شود.{% else %}پس از ورود، اگر مدیر باشید به پنل مدیریت هدایت می‌شوید.{% endif %}
</div>
</section>{% endblock %}
"""

DASHBOARD = """
{% extends "base.html" %}{% block content %}
<section class="section">
<div class="section-head">
  <div><h2>پنل کاربری</h2><p class="muted">سلام {{ g.user['name'] }}؛ اطلاعات حساب شما.</p></div>
  <a class="btn danger" href="{{ url_for('logout') }}">خروج از حساب</a>
</div>
<div class="glass" style="padding:20px;margin-bottom:16px">
  <h3 style="margin-bottom:12px;position:relative;z-index:2">اطلاعات حساب</h3>
  <p class="muted small" style="position:relative;z-index:2"><b>نام:</b> {{ g.user['name'] }}</p>
  <p class="muted small" style="margin-top:6px;position:relative;z-index:2"><b>ایمیل:</b> {{ g.user['email'] }}</p>
</div>
<div class="glass" style="padding:20px">
  <h3 style="margin-bottom:12px;position:relative;z-index:2">پیام‌های ارسالی شما</h3>
  {% if my_messages %}
  <div class="table-wrap"><table class="data-table">
    <thead><tr><th>موضوع</th><th>متن</th><th>تاریخ</th><th>وضعیت</th></tr></thead><tbody>
    {% for m in my_messages %}<tr>
      <td>{% if m['number_id'] %}آگهی #{{ m['number_id'] }}{% else %}عمومی{% endif %}</td>
      <td>{{ m['message'][:80] }}</td>
      <td class="muted small">{{ m['created_at'][:10] }}</td>
      <td>{% if m['is_read'] %}<span class="tag">خوانده‌شده</span>{% else %}<span class="pill">جدید</span>{% endif %}</td>
    </tr>{% endfor %}
    </tbody></table></div>
  {% else %}
  <p class="muted small" style="position:relative;z-index:2">هنوز پیامی ارسال نکرده‌اید.</p>
  {% endif %}
</div>
</section>{% endblock %}
"""

DETAIL = """
{% extends "base.html" %}{% block content %}
<section class="section">
<div class="glass detail-card">
  <span class="pill blue">{{ item['operator'] }}</span>
  {% if item['status']=='reserved' %}<span class="pill" style="margin-right:6px">رزرو</span>{% endif %}
  <h1 style="font-size:clamp(1.4rem,4vw,2.2rem);overflow-wrap:anywhere;margin:12px 0 6px">{{ item['phone_number'] }}</h1>
  <div class="price" style="font-size:1.35rem">{{ "{:,}".format(item['price']) }} تومان</div>
  <div class="meta"><span class="tag">{{ item['category'] }}</span><span class="tag">ثبت: {{ item['created_at'][:10] }}</span></div>
  <h3 style="margin-top:16px;font-size:1rem">توضیحات</h3>
  <p style="line-height:2;white-space:pre-wrap;margin-top:4px">{{ item['description'] or 'توضیحی ثبت نشده است.' }}</p>
  <div class="contact-options">
    <div class="contact-card">
      <div class="contact-icon">⌂</div>
      <h4>مراجعه حضوری</h4>
      <p class="muted small">{{ site.office_address }}</p>
      <p class="small muted">ساعات کاری: {{ site.office_hours }}</p>
    </div>
    <div class="contact-card">
      <div class="contact-icon">✉</div>
      <h4>ارسال پیام به دفتر</h4>
      <p class="muted small">پیام شما در سامانه ثبت می‌شود.</p>
      <form method="post" action="{{ url_for('number_message', number_id=item['id']) }}">
        <input class="control" name="name" placeholder="نام شما" required maxlength="80" value="{{ g.user['name'] if g.user else '' }}" style="margin-bottom:6px">
        <input class="control" name="phone" placeholder="شماره تماس" required maxlength="30" inputmode="tel" style="margin-bottom:6px">
        <textarea class="control" name="message" placeholder="متن پیام…" required maxlength="2000" rows="3" style="margin-bottom:6px"></textarea>
        <button class="btn primary" type="submit" style="width:100%">ارسال پیام</button>
      </form>
    </div>
  </div>
  <p class="muted small" style="margin-top:16px">ارسال پیام به‌معنی پرداخت یا انتقال مالکیت نیست.</p>
</div></section>
{% endblock %}
"""

ABOUT = """
{% extends "base.html" %}{% block content %}
<section class="section">
<div class="hero">
  <div style="position:relative;z-index:2">
    <span class="eyebrow">اطلاعات دفتر</span>
    <h1>{{ site.office_name }}</h1>
    <p>{{ site.tagline }}. در این سایت می‌توانید آگهی شماره‌ها را ببینید یا برای هماهنگی با دفتر پیام بفرستید.</p>
    <div class="hero-actions">
      <a class="btn primary" href="{{ url_for('contact') }}">ارسال پیام به دفتر</a>
      <a class="btn soft" href="{{ url_for('index') }}#numbers">مشاهده شماره‌ها</a>
    </div>
  </div>
  <div class="glass side-card">
    <h3>اطلاعات دفتر</h3>
    <p class="muted small"><b>شماره تماس:</b><br><span class="side-phone">{{ site.office_phone }}</span></p>
    <p class="muted small" style="margin-top:10px"><b>نشانی:</b><br>{{ site.office_address }}</p>
    <p class="muted small" style="margin-top:10px"><b>ساعات کاری:</b><br>{{ site.office_hours }}</p>
  </div>
</div>
<div class="info-grid-4">
  <div class="glass info-box phone-box">
    <h3>تماس</h3>
    <p class="phone-display">{{ site.office_phone }}</p>
  </div>
  <div class="glass info-box">
    <h3>خدمات دفتر</h3>
    <p class="muted small" style="line-height:2;white-space:pre-line">{{ site.office_services }}</p>
  </div>
  <div class="glass info-box">
    <h3>آگهی شفاف</h3>
    <p class="muted small">مشخصات، دسته‌بندی و قیمت هر شماره در صفحه آگهی نمایش داده می‌شود.</p>
  </div>
  <div class="glass info-box">
    <h3>دو روش ارتباط</h3>
    <p class="muted small">مراجعه حضوری به دفتر یا ارسال پیام از طریق سایت.</p>
  </div>
</div>
</section>{% endblock %}
"""

CONTACT = """
{% extends "base.html" %}{% block content %}
<section class="section">
<div class="section-head">
  <div><h2>ارسال پیام به دفتر</h2>
  <p class="muted small">می‌توانید حضوری مراجعه کنید یا از طریق فرم زیر پیام بفرستید. ارسال پیام نیازی به ثبت‌نام ندارد.</p></div>
</div>
<div class="contact-options" style="margin-bottom:18px">
  <div class="contact-card">
    <div class="contact-icon">⌂</div>
    <h4>مراجعه حضوری</h4>
    <p class="muted small">{{ site.office_address }}</p>
    <p class="small muted">ساعات کاری: {{ site.office_hours }}</p>
  </div>
  <div class="contact-card">
    <div class="contact-icon">✉</div>
    <h4>فرم پیام</h4>
    <p class="muted small">پیام شما در سامانه ثبت و بررسی می‌شود.</p>
    <a class="btn soft" href="#form">رفتن به فرم</a>
  </div>
</div>
<div class="form-card glass" id="form" style="margin-top:0">
<h1 style="position:relative;z-index:2">ارسال پیام</h1>
<p class="muted" style="position:relative;z-index:2">فرم زیر را تکمیل کنید.</p>
<form method="post" style="position:relative;z-index:2">
  <div class="field"><label>نام</label><input class="control" name="name" maxlength="80" value="{{ form.name if form else (g.user['name'] if g.user else '') }}" required></div>
  <div class="field"><label>شماره تماس</label><input class="control" name="phone" maxlength="30" inputmode="tel" value="{{ form.phone if form else '' }}" required></div>
  <div class="field"><label>پیام</label><textarea class="control" name="message" rows="5" maxlength="2000" required>{{ form.message if form else '' }}</textarea></div>
  <button class="btn primary" style="width:100%">ارسال پیام</button>
</form>
</div>
</section>{% endblock %}
"""

ADMIN = """
{% extends "base.html" %}{% block content %}
<section class="section">
<div class="section-head">
  <div><h2>{{ page_title }}</h2><p class="muted small">{{ page_desc }}</p></div>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <a class="btn soft" href="{{ url_for('index') }}">مشاهده سایت</a>
    <a class="btn danger" href="{{ url_for('logout') }}">خروج</a>
  </div>
</div>
<nav class="admin-tabs">
  <a class="admin-tab {% if active=='overview' %}active{% endif %}" href="{{ url_for('admin') }}">نمای کلی</a>
  <a class="admin-tab {% if active=='numbers' %}active{% endif %}" href="{{ url_for('admin_numbers') }}">شماره‌ها</a>
  <a class="admin-tab {% if active=='messages' %}active{% endif %}" href="{{ url_for('admin_messages') }}">پیام‌ها{% if unread_messages %}<span class="badge">{{ unread_messages }}</span>{% endif %}</a>
  <a class="admin-tab {% if active=='settings' %}active{% endif %}" href="{{ url_for('admin_settings') }}">تنظیمات</a>
  <a class="admin-tab {% if active=='settings_slides' %}active{% endif %}" href="{{ url_for('admin_settings_slides') }}">اسلایدشو</a>
</nav>

{% if active == 'overview' %}
<div class="stat-grid">
  <div class="stat-card"><b>{{ stats.total_numbers }}</b><span>کل آگهی‌ها</span></div>
  <div class="stat-card"><b>{{ stats.available }}</b><span>موجود</span></div>
  <div class="stat-card"><b>{{ stats.reserved }}</b><span>رزرو</span></div>
  <div class="stat-card"><b>{{ stats.unread }}</b><span>پیام خوانده‌نشده</span></div>
</div>
<div class="glass" style="padding:16px;margin-bottom:14px">
<h3 style="margin-bottom:10px;font-size:1rem;position:relative;z-index:2">آخرین آگهی‌ها</h3>
<div class="table-wrap"><table class="data-table">
<thead><tr><th>شماره</th><th>اپراتور</th><th>قیمت</th><th>وضعیت</th></tr></thead><tbody>
{% for n in recent_numbers %}<tr>
<td>{{ n['phone_number'] }}</td><td>{{ n['operator'] }}</td>
<td>{{ "{:,}".format(n['price']) }}</td>
<td>{% if n['status']=='available' %}<span class="pill blue">موجود</span>{% else %}<span class="pill">رزرو</span>{% endif %}</td></tr>
{% else %}<tr><td colspan="4" class="muted">آگهی‌ای ثبت نشده.</td></tr>{% endfor %}
</tbody></table></div></div>
<div class="glass" style="padding:16px">
<h3 style="margin-bottom:10px;font-size:1rem;position:relative;z-index:2">آخرین پیام‌ها</h3>
<div class="table-wrap"><table class="data-table">
<thead><tr><th>نام</th><th>تلفن</th><th>پیام</th><th>وضعیت</th></tr></thead><tbody>
{% for m in recent_messages %}<tr>
<td>{{ m['name'] }}</td><td>{{ m['phone'] }}</td>
<td>{{ m['message'][:60] }}</td>
<td>{% if m['is_read'] %}<span class="tag">خوانده‌شده</span>{% else %}<span class="pill">جدید</span>{% endif %}</td></tr>
{% else %}<tr><td colspan="4" class="muted">پیامی ثبت نشده.</td></tr>{% endfor %}
</tbody></table></div></div>

{% elif active == 'numbers' %}
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
  <div class="muted small">{{ numbers|length }} آگهی</div>
  <a class="btn primary" href="{{ url_for('admin_number_add') }}">+ افزودن شماره</a>
</div>
<div class="glass" style="padding:14px">
<div class="table-wrap"><table class="data-table">
<thead><tr><th>شماره</th><th>اپراتور</th><th>دسته</th><th>قیمت</th><th>وضعیت</th><th>اقدام</th></tr></thead><tbody>
{% for n in numbers %}<tr>
<td>{{ n['phone_number'] }}</td><td>{{ n['operator'] }}</td><td>{{ n['category'] }}</td>
<td>{{ "{:,}".format(n['price']) }}</td>
<td>{% if n['status']=='available' %}<span class="pill blue">موجود</span>{% else %}<span class="pill">رزرو</span>{% endif %}</td>
<td><div style="display:flex;gap:5px;flex-wrap:wrap">
  <a class="btn soft" style="padding:7px 10px;font-size:.76rem;min-height:36px" href="{{ url_for('admin_number_edit', nid=n['id']) }}">ویرایش</a>
  <a class="btn soft" style="padding:7px 10px;font-size:.76rem;min-height:36px" href="{{ url_for('number_detail', number_id=n['id']) }}">مشاهده</a>
  <form method="post" action="{{ url_for('admin_number_delete', nid=n['id']) }}" onsubmit="return confirm('حذف شود؟')"><button class="btn danger" style="padding:7px 10px;font-size:.76rem;min-height:36px">حذف</button></form>
</div></td></tr>
{% else %}<tr><td colspan="6" class="muted">آگهی‌ای ثبت نشده.</td></tr>{% endfor %}
</tbody></table></div></div>

{% elif active == 'messages' %}
<div class="glass" style="padding:14px">
<h3 style="margin-bottom:10px;font-size:1rem;position:relative;z-index:2">پیام‌های دریافتی ({{ messages|length }})</h3>
<div class="table-wrap"><table class="data-table">
<thead><tr><th>نام</th><th>تلفن</th><th>پیام</th><th>موضوع</th><th>وضعیت</th><th>تاریخ</th><th>اقدام</th></tr></thead><tbody>
{% for m in messages %}<tr>
<td>{{ m['name'] }}</td><td>{{ m['phone'] }}</td>
<td style="max-width:280px;line-height:1.7">{{ m['message'] }}</td>
<td>{% if m['number_id'] %}<a class="tag" href="{{ url_for('number_detail', number_id=m['number_id']) }}">#{{ m['number_id'] }}</a>{% else %}—{% endif %}</td>
<td>{% if m['is_read'] %}<span class="tag">خوانده</span>{% else %}<span class="pill">جدید</span>{% endif %}</td>
<td class="muted small">{{ m['created_at'][:10] }}</td>
<td><div style="display:flex;gap:5px;flex-wrap:wrap">
  {% if not m['is_read'] %}
  <form method="post" action="{{ url_for('admin_message_read', mid=m['id']) }}"><button class="btn soft" style="padding:7px 10px;font-size:.76rem;min-height:36px">خوانده شد</button></form>
  {% endif %}
  <form method="post" action="{{ url_for('admin_message_delete', mid=m['id']) }}" onsubmit="return confirm('حذف شود؟')"><button class="btn danger" style="padding:7px 10px;font-size:.76rem;min-height:36px">حذف</button></form>
</div></td></tr>
{% else %}<tr><td colspan="7" class="muted">پیامی ثبت نشده.</td></tr>{% endfor %}
</tbody></table></div></div>

{% elif active == 'settings' %}
<div class="glass admin-settings-form" style="padding:24px">
<form method="post" style="position:relative;z-index:2">
<div class="notice small" style="margin-bottom:12px">
  💡 وقتی یکی از دو نام زیر را تغییر دهید، نام قدیمی در همه‌جای سایت (شعار، خدمات، کارت‌ها، اسلایدها) به‌طور خودکار جایگزین می‌شود.
</div>
<h3 style="margin-bottom:14px;font-size:1.05rem">هویت سایت</h3>
<div class="field">
  <label>نام سایت <span class="muted" style="font-weight:400">— نمایش در هدر</span></label>
  <input class="control" name="site_name" value="{{ form_data.site_name }}" maxlength="60" required>
</div>
<div class="field"><label>شعار کوتاه</label><input class="control" name="tagline" value="{{ form_data.tagline }}" maxlength="120" required></div>

<h3 style="margin:18px 0 14px;font-size:1.05rem">کارت‌های سمت راست صفحه اصلی</h3>
{% for i in [1,2,3] %}
<div class="glass" style="padding:16px;margin-bottom:10px;border-radius:12px">
  <div class="field" style="position:relative;z-index:2"><label>کارت {{ i }} — عنوان</label><input class="control" name="card{{ i }}_title" value="{{ form_data['card' ~ i ~ '_title'] }}" maxlength="60" required></div>
  <div class="field" style="position:relative;z-index:2;margin-bottom:0"><label>کارت {{ i }} — توضیح</label><input class="control" name="card{{ i }}_text" value="{{ form_data['card' ~ i ~ '_text'] }}" maxlength="200" required></div>
</div>
{% endfor %}

<h3 style="margin:18px 0 14px;font-size:1.05rem">رنگ‌بندی</h3>
<div class="info-grid">
  <div class="field"><label>رنگ اصلی</label><input class="control" type="color" name="theme_color" value="{{ form_data.theme_color }}" required></div>
  <div class="field"><label>رنگ مکمل</label><input class="control" type="color" name="accent_color" value="{{ form_data.accent_color }}" required></div>
  <div class="field"><label>پیش‌نمایش</label><div class="preview-bar" style="background:linear-gradient(120deg,{{ form_data.theme_color }},{{ form_data.accent_color }})"></div></div>
</div>

<h3 style="margin:18px 0 14px;font-size:1.05rem">اطلاعات دفتر</h3>
<div class="field">
  <label>نام دفتر <span class="muted" style="font-weight:400">— نمایش در اسلایدها و صفحه «اطلاعات»</span></label>
  <input class="control" name="office_name" value="{{ form_data.office_name }}" maxlength="100" required>
</div>
<div class="field"><label>شماره تماس</label><input class="control" name="office_phone" value="{{ form_data.office_phone }}" maxlength="40" inputmode="tel" required></div>
<div class="field"><label>نشانی</label><input class="control" name="office_address" value="{{ form_data.office_address }}" maxlength="250" required></div>
<div class="field"><label>ساعات کاری</label><input class="control" name="office_hours" value="{{ form_data.office_hours }}" maxlength="120" required></div>
<div class="field"><label>خدمات (هر خدمت یک خط)</label><textarea class="control" name="office_services" rows="3" maxlength="1000" required>{{ form_data.office_services }}</textarea></div>

<h3 style="margin:18px 0 14px;font-size:1.05rem">CSS سفارشی (پیشرفته)</h3>
<div class="field">
  <label>کد CSS — روی کل سایت اعمال می‌شود</label>
  <textarea class="control" name="custom_css" rows="5" maxlength="5000">{{ form_data.custom_css }}</textarea>
</div>

<button class="btn primary" style="width:100%" type="submit">ذخیره تغییرات</button>
</form>
</div>

{% elif active == 'settings_slides' %}
<div class="glass admin-settings-form" style="padding:24px">
<form method="post" style="position:relative;z-index:2">
<div class="notice small" style="margin-bottom:14px">
  در متن‌ها می‌توانید از <code>{site_name}</code> و <code>{office_name}</code> استفاده کنید.
</div>
{% for i in [1,2,3] %}
<div class="glass" style="padding:16px;margin-bottom:12px;border-radius:12px">
  <h4 style="margin:0 0 12px;font-size:1rem;position:relative;z-index:2;color:var(--blue)">اسلاید {{ i }}</h4>
  <div class="field" style="position:relative;z-index:2"><label>عنوان</label><input class="control" name="slide{{ i }}_title" value="{{ form_data['slide' ~ i ~ '_title'] }}" maxlength="80"></div>
  <div class="field" style="position:relative;z-index:2"><label>متن</label><textarea class="control" name="slide{{ i }}_text" rows="2" maxlength="300">{{ form_data['slide' ~ i ~ '_text'] }}</textarea></div>
  <div class="field" style="position:relative;z-index:2;margin-bottom:0"><label>لینک دکمه (اختیاری)</label><input class="control" name="slide{{ i }}_link" value="{{ form_data['slide' ~ i ~ '_link'] }}" maxlength="200" placeholder="/contact یا /#numbers"></div>
</div>
{% endfor %}
<div style="display:flex;gap:8px;flex-wrap:wrap">
  <button class="btn primary" style="flex:1;min-width:200px" type="submit">ذخیره اسلایدها</button>
  <button class="btn soft" style="flex:1;min-width:200px" type="submit" name="reset_defaults" value="1"
          onclick="return confirm('همهٔ اسلایدها به پیش‌فرض بازگردند؟')">بازنویسی با پیش‌فرض</button>
</div>
</form>
</div>
{% endif %}
</section>{% endblock %}
"""

NUMBER_FORM = """
{% extends "base.html" %}{% block content %}
<section class="form-card glass" style="width:min(600px,100%)">
<h1 style="position:relative;z-index:2">{{ heading }}</h1>
<p class="muted" style="position:relative;z-index:2">اطلاعات آگهی را وارد کنید.</p>
<form method="post" style="position:relative;z-index:2">
<div class="field"><label>شماره</label><input class="control" name="phone_number" value="{{ item['phone_number'] if item else '' }}" required maxlength="30" placeholder="مثلاً 0912..." inputmode="tel"></div>
<div class="field"><label>اپراتور</label><select class="control" name="operator" required>
  {% for x in ['همراه اول','ایرانسل','رایتل','سایر'] %}<option {% if item and item['operator']==x %}selected{% endif %}>{{ x }}</option>{% endfor %}
</select></div>
<div class="field"><label>دسته‌بندی</label><select class="control" name="category" required>
  {% for x in ['عادی','رند','طلایی','کارکرده','سایر'] %}<option {% if item and item['category']==x %}selected{% endif %}>{{ x }}</option>{% endfor %}
</select></div>
<div class="field"><label>قیمت (تومان)</label><input class="control" type="number" name="price" min="0" max="1000000000000" value="{{ item['price'] if item else 0 }}" required inputmode="numeric"></div>
<div class="field"><label>توضیحات</label><textarea class="control" name="description" rows="4" maxlength="1000">{{ item['description'] if item else '' }}</textarea></div>
{% if item %}<div class="field"><label>وضعیت</label><select class="control" name="status">
  {% for key,label in [('available','موجود'),('reserved','رزرو')] %}<option value="{{ key }}" {% if item['status']==key %}selected{% endif %}>{{ label }}</option>{% endfor %}
</select></div>{% endif %}
<button class="btn primary" style="width:100%" type="submit">ذخیره</button>
<a class="btn soft" href="{{ url_for('admin_numbers') }}" style="width:100%;margin-top:8px">بازگشت</a>
</form></section>{% endblock %}
"""

# ============ render ============
def render_page(template, **context):
    site = context.pop("site", None) or get_settings()
    context.setdefault("year", datetime.now().year)
    context.setdefault("title", site.get("site_name", "پیشخوان"))
    context.setdefault("APP_VERSION", APP_VERSION)
    return render_template_string(template, base=BASE, site=site, **context)

# ============ Routes ============
@app.route("/")
def index():
    qv = request.args.get("q","").strip()[:100]
    operator = request.args.get("operator","").strip()
    category = request.args.get("category","").strip()
    price_min = request.args.get("price_min","").strip()
    price_max = request.args.get("price_max","").strip()
    sort = request.args.get("sort","new")
    try: page = max(1, int(request.args.get("page","1")))
    except ValueError: page = 1
    where = []; params = []
    if qv:
        where.append("(phone_number LIKE %s OR description LIKE %s)")
        params += [f"%{qv}%", f"%{qv}%"]
    if operator in ["همراه اول","ایرانسل","رایتل","سایر"]:
        where.append("operator=%s"); params.append(operator)
    if category in ["عادی","رند","طلایی","کارکرده","سایر"]:
        where.append("category=%s"); params.append(category)
    if price_min.isdigit():
        where.append("price >= %s"); params.append(int(price_min))
    if price_max.isdigit():
        where.append("price <= %s"); params.append(int(price_max))
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = q("SELECT COUNT(*) AS c FROM numbers" + where_sql, params).fetchone()['c']
    pages = max(1, (total + 19)//20); page = min(page, pages)
    order = {"low":"price ASC, id DESC","high":"price DESC, id DESC"}.get(sort, "id DESC")
    rows = q("SELECT * FROM numbers" + where_sql + f" ORDER BY {order} LIMIT 20 OFFSET %s",
             params + [(page-1)*20]).fetchall()
    return render_page(INDEX, title="خانه", numbers=rows, total=total,
        pages=pages, page=page, q=qv, operator=operator, category=category,
        price_min=price_min, price_max=price_max, sort=sort,
        operators=["همراه اول","ایرانسل","رایتل","سایر"],
        categories=["عادی","رند","طلایی","کارکرده","سایر"])

@app.route("/numbers/<int:number_id>")
def number_detail(number_id):
    item = q("SELECT * FROM numbers WHERE id=%s", (number_id,)).fetchone()
    if not item: abort(404)
    return render_page(DETAIL, title="جزئیات شماره", item=item)

@app.route("/numbers/<int:number_id>/message", methods=["POST"])
def number_message(number_id):
    item = q("SELECT id FROM numbers WHERE id=%s", (number_id,)).fetchone()
    if not item: abort(404)
    name = request.form.get("name","").strip()
    phone = request.form.get("phone","").strip()
    message = request.form.get("message","").strip()
    if len(name) < 2 or len(name) > 80: flash("نام باید ۲ تا ۸۰ نویسه باشد.", "error")
    elif not valid_phone(phone): flash("شماره تماس معتبر نیست.", "error")
    elif not message or len(message) > 2000: flash("متن پیام معتبر نیست.", "error")
    else:
        q("INSERT INTO contact_messages(name,phone,message,number_id,user_id,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
          (name,phone,message,number_id,g.user["id"] if g.user else None,
           datetime.now().isoformat(timespec="seconds")))
        db().commit()
        flash("پیام شما ثبت شد.", "success")
    return redirect(url_for("number_detail", number_id=number_id))

@app.route("/about")
def about():
    return render_page(ABOUT, title="اطلاعات دفتر")

@app.route("/contact", methods=["GET","POST"])
def contact():
    form = None
    if request.method == "POST":
        form = {
            "name": request.form.get("name","").strip(),
            "phone": request.form.get("phone","").strip(),
            "message": request.form.get("message","").strip(),
        }
        if len(form["name"]) < 2 or len(form["name"]) > 80: flash("نام باید ۲ تا ۸۰ نویسه باشد.", "error")
        elif not valid_phone(form["phone"]): flash("شماره تماس معتبر نیست.", "error")
        elif not form["message"] or len(form["message"]) > 2000: flash("متن پیام معتبر نیست.", "error")
        else:
            q("INSERT INTO contact_messages(name,phone,message,user_id,created_at) VALUES(%s,%s,%s,%s,%s)",
              (form["name"],form["phone"],form["message"],
               g.user["id"] if g.user else None,
               datetime.now().isoformat(timespec="seconds")))
            db().commit()
            flash("پیام شما ارسال شد.", "success")
            return redirect(url_for("contact"))
    return render_page(CONTACT, title="ارسال پیام", form=form)

@app.route("/register", methods=["GET","POST"])
def register():
    if g.user:
        return redirect(url_for("admin") if g.user["role"]=="admin" else url_for("dashboard"))
    form_name = form_email = ""
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        form_name, form_email = name, email
        if len(name) < 2 or len(name) > 80: flash("نام باید ۲ تا ۸۰ نویسه باشد.", "error")
        elif len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("ایمیل معتبر وارد کنید.", "error")
        elif len(password) < 8: flash("رمز عبور حداقل ۸ کاراکتر.", "error")
        else:
            try:
                cnt = q("SELECT COUNT(*) AS c FROM users").fetchone()['c']
                role = "admin" if cnt == 0 else "user"
                cur = q("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(%s,%s,%s,%s,%s)",
                        (name,email,generate_password_hash(password),role,
                         datetime.now().isoformat(timespec="seconds")))
                new_id = cur.lastrowid
                db().commit()
                session.clear(); session["user_id"] = new_id
                flash("ثبت‌نام موفق بود." + (" شما مدیر سایت هستید." if role=="admin" else ""), "success")
                return redirect(url_for("admin") if role=="admin" else url_for("dashboard"))
            except pymysql.IntegrityError:
                db().rollback()
                flash("این ایمیل قبلاً ثبت شده. وارد شوید.", "error")
    return render_page(AUTH, title="ثبت‌نام", heading="ساخت حساب",
                       subtitle="برای دسترسی به امکانات حساب بسازید.",
                       mode="register", form_name=form_name, form_email=form_email)

@app.route("/login", methods=["GET","POST"])
def login():
    if g.user:
        return redirect(url_for("admin") if g.user["role"]=="admin" else url_for("dashboard"))
    form_email = ""
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        form_email = email
        user = q("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["user_id"] = user["id"]
            flash("خوش آمدید.", "success")
            nxt = request.args.get("next","")
            if nxt.startswith("/") and not nxt.startswith("//"): return redirect(nxt)
            return redirect(url_for("admin") if user["role"]=="admin" else url_for("dashboard"))
        flash("ایمیل یا رمز عبور صحیح نیست.", "error")
    return render_page(AUTH, title="ورود", heading="ورود به حساب",
                       subtitle="مشخصات حساب خود را وارد کنید.",
                       mode="login", form_email=form_email)

@app.route("/logout")
def logout():
    session.clear()
    flash("از حساب خارج شدید.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if not g.user: return redirect(url_for("login", next=request.path))
    if g.user["role"] == "admin": return redirect(url_for("admin"))
    my_messages = q("SELECT * FROM contact_messages WHERE user_id=%s ORDER BY id DESC LIMIT 50",
                    (g.user["id"],)).fetchall()
    return render_page(DASHBOARD, title="پنل من", my_messages=my_messages)

@app.route("/admin")
@admin_required
def admin():
    stats = {
        "total_numbers": q("SELECT COUNT(*) AS c FROM numbers").fetchone()['c'],
        "available": q("SELECT COUNT(*) AS c FROM numbers WHERE status='available'").fetchone()['c'],
        "reserved": q("SELECT COUNT(*) AS c FROM numbers WHERE status='reserved'").fetchone()['c'],
        "unread": q("SELECT COUNT(*) AS c FROM contact_messages WHERE is_read=0").fetchone()['c'],
    }
    recent_numbers = q("SELECT * FROM numbers ORDER BY id DESC LIMIT 5").fetchall()
    recent_messages = q("SELECT * FROM contact_messages ORDER BY id DESC LIMIT 5").fetchall()
    return render_page(ADMIN, title="نمای کلی", active="overview",
                       page_title="نمای کلی", page_desc="خلاصه وضعیت و آخرین فعالیت‌ها.",
                       stats=stats, recent_numbers=recent_numbers, recent_messages=recent_messages)

@app.route("/admin/numbers")
@admin_required
def admin_numbers():
    numbers = q("SELECT * FROM numbers ORDER BY id DESC LIMIT 200").fetchall()
    return render_page(ADMIN, title="شماره‌ها", active="numbers",
                       page_title="مدیریت شماره‌ها", page_desc="افزودن، ویرایش و حذف آگهی‌ها.",
                       numbers=numbers)

@app.route("/admin/numbers/add", methods=["GET","POST"])
@admin_required
def admin_number_add():
    if request.method == "POST":
        phone = request.form.get("phone_number","").strip()
        operator = request.form.get("operator","سایر")
        category = request.form.get("category","عادی")
        description = request.form.get("description","").strip()
        try: price = int(request.form.get("price","0"))
        except ValueError: price = -1
        err = None
        if not valid_phone(phone): err = "شماره معتبر نیست."
        elif operator not in ["همراه اول","ایرانسل","رایتل","سایر"]: err = "اپراتور نامعتبر."
        elif category not in ["عادی","رند","طلایی","کارکرده","سایر"]: err = "دسته‌بندی نامعتبر."
        elif price < 0 or price > 1_000_000_000_000: err = "قیمت نامعتبر."
        elif len(description) > 1000: err = "توضیحات طولانی."
        if err: flash(err, "error")
        else:
            q("""INSERT INTO numbers(owner_id,phone_number,operator,category,price,description,status,created_at)
                 VALUES(%s,%s,%s,%s,%s,%s,'available',%s)""",
              (g.user["id"],phone,operator,category,price,description,
               datetime.now().isoformat(timespec="seconds")))
            db().commit()
            flash("آگهی ثبت شد.", "success")
            return redirect(url_for("admin_numbers"))
    return render_page(NUMBER_FORM, title="افزودن شماره", heading="افزودن شماره جدید", item=None)

@app.route("/admin/numbers/<int:nid>/edit", methods=["GET","POST"])
@admin_required
def admin_number_edit(nid):
    item = q("SELECT * FROM numbers WHERE id=%s", (nid,)).fetchone()
    if not item: abort(404)
    if request.method == "POST":
        phone = request.form.get("phone_number","").strip()
        operator = request.form.get("operator","سایر")
        category = request.form.get("category","عادی")
        description = request.form.get("description","").strip()
        status = request.form.get("status","available")
        try: price = int(request.form.get("price","0"))
        except ValueError: price = -1
        ok = (valid_phone(phone)
              and operator in ["همراه اول","ایرانسل","رایتل","سایر"]
              and category in ["عادی","رند","طلایی","کارکرده","سایر"]
              and status in ["available","reserved"]
              and 0 <= price <= 1_000_000_000_000
              and len(description) <= 1000)
        if not ok: flash("اطلاعات نامعتبر؛ فرم را بررسی کنید.", "error")
        else:
            q("""UPDATE numbers SET phone_number=%s,operator=%s,category=%s,price=%s,
                 description=%s,status=%s WHERE id=%s""",
              (phone,operator,category,price,description,status,nid))
            db().commit()
            flash("تغییرات ذخیره شد.", "success")
            return redirect(url_for("admin_numbers"))
    return render_page(NUMBER_FORM, title="ویرایش شماره", heading="ویرایش آگهی", item=item)

@app.route("/admin/numbers/<int:nid>/delete", methods=["POST"])
@admin_required
def admin_number_delete(nid):
    q("UPDATE contact_messages SET number_id=NULL WHERE number_id=%s", (nid,))
    q("DELETE FROM numbers WHERE id=%s", (nid,))
    db().commit()
    flash("آگهی حذف شد.", "success")
    return redirect(url_for("admin_numbers"))

@app.route("/admin/messages")
@admin_required
def admin_messages():
    messages = q("SELECT * FROM contact_messages ORDER BY id DESC LIMIT 200").fetchall()
    return render_page(ADMIN, title="پیام‌ها", active="messages",
                       page_title="پیام‌های دریافتی",
                       page_desc="پیام‌های ارسال‌شده از فرم تماس و فرم هر شماره.",
                       messages=messages)

@app.route("/admin/messages/<int:mid>/read", methods=["POST"])
@admin_required
def admin_message_read(mid):
    q("UPDATE contact_messages SET is_read=1 WHERE id=%s", (mid,))
    db().commit(); return redirect(url_for("admin_messages"))

@app.route("/admin/messages/<int:mid>/delete", methods=["POST"])
@admin_required
def admin_message_delete(mid):
    q("DELETE FROM contact_messages WHERE id=%s", (mid,))
    db().commit()
    flash("پیام حذف شد.", "success")
    return redirect(url_for("admin_messages"))

# ============ Settings ============
GENERAL_KEYS = ["site_name","tagline","theme_color","accent_color",
                "card1_title","card1_text","card2_title","card2_text","card3_title","card3_text",
                "office_name","office_phone","office_address","office_hours","office_services",
                "custom_css"]
GENERAL_LIMITS = {
    "site_name":60,"tagline":120,
    "card1_title":60,"card1_text":200,"card2_title":60,"card2_text":200,
    "card3_title":60,"card3_text":200,
    "theme_color":7,"accent_color":7,
    "office_name":100,"office_phone":40,"office_address":250,"office_hours":120,
    "office_services":1000,"custom_css":5000,
}
GENERAL_REQUIRED = {"site_name","tagline","office_name","office_phone",
                    "office_address","office_hours","office_services",
                    "card1_title","card2_title","card3_title",
                    "theme_color","accent_color"}

@app.route("/admin/settings", methods=["GET","POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        old_data = dict(get_settings())
        form_data = {}
        for k in GENERAL_KEYS:
            form_data[k] = request.form.get(k,"").strip()

        old_site = (old_data.get("site_name") or "").strip()
        old_office = (old_data.get("office_name") or "").strip()
        new_site = form_data["site_name"]
        new_office = form_data["office_name"]

        site_changed = old_site != new_site
        office_changed = old_office != new_office

        if site_changed and not office_changed:
            if old_office == DEF_OFFICE_NAME:
                form_data["office_name"] = "دفتر " + new_site if len(new_site) > 2 else new_site
                new_office = form_data["office_name"]
            elif old_office == old_site:
                form_data["office_name"] = new_site
                new_office = form_data["office_name"]
        elif office_changed and not site_changed:
            if old_site == DEF_SITE_NAME:
                clean = new_office[5:].strip() if new_office.startswith("دفتر ") else new_office
                form_data["site_name"] = clean
                new_site = form_data["site_name"]
            elif old_site == old_office:
                clean = new_office[5:].strip() if new_office.startswith("دفتر ") else new_office
                form_data["site_name"] = clean
                new_site = form_data["site_name"]

        reps = {}
        if old_site and old_site != new_site: reps[old_site] = new_site
        if old_office and old_office != new_office and old_office != old_site:
            reps[old_office] = new_office
        if reps:
            for k in ["tagline","office_address","office_hours","office_services",
                      "card1_title","card1_text","card2_title","card2_text",
                      "card3_title","card3_text"]:
                if k in form_data:
                    form_data[k] = replace_names_in_text(form_data[k], reps)

        color_ok = re.compile(r"^#[0-9a-fA-F]{6}$")
        errors = []
        for k in GENERAL_KEYS:
            if k == "custom_css":
                if len(form_data[k]) > GENERAL_LIMITS[k]:
                    errors.append("CSS سفارشی طولانی است.")
                continue
            if k in GENERAL_REQUIRED and not form_data[k]:
                errors.append(f"«{k}» خالی است.")
            elif len(form_data[k]) > GENERAL_LIMITS[k]:
                errors.append(f"«{k}» طولانی است.")
        if not color_ok.match(form_data.get("theme_color","")): errors.append("رنگ اصلی نامعتبر است.")
        if not color_ok.match(form_data.get("accent_color","")): errors.append("رنگ مکمل نامعتبر است.")

        if not errors:
            cols = ",".join(f"{k}=%s" for k in GENERAL_KEYS)
            q(f"UPDATE site_settings SET {cols} WHERE id=1",
              [form_data[k] for k in GENERAL_KEYS])
            if reps:
                propagate_names(db().cursor(), reps)
            db().commit()
            g.site = None
            msg = "تنظیمات سایت ذخیره شد."
            if reps: msg += " نام قدیمی در همه‌جای سایت به‌روز شد."
            flash(msg, "success")
            return redirect(url_for("admin_settings"))
        else:
            flash("؛ ".join(errors), "error")
    form_data = dict(get_settings())
    return render_page(ADMIN, title="تنظیمات", active="settings",
                       page_title="تنظیمات سایت",
                       page_desc="هویت، رنگ‌ها و اطلاعات دفتر را تغییر دهید.",
                       form_data=form_data)

SLIDES_KEYS = ["slide1_title","slide1_text","slide1_link",
               "slide2_title","slide2_text","slide2_link",
               "slide3_title","slide3_text","slide3_link"]
SLIDES_LIMITS = {"slide1_title":80,"slide1_text":300,"slide1_link":200,
                 "slide2_title":80,"slide2_text":300,"slide2_link":200,
                 "slide3_title":80,"slide3_text":300,"slide3_link":200}

@app.route("/admin/settings/slides", methods=["GET","POST"])
@admin_required
def admin_settings_slides():
    if request.method == "POST":
        if request.form.get("reset_defaults") == "1":
            defaults = {
                "slide1_title": "به {site_name} خوش آمدید",
                "slide1_text": "شماره‌های آماده را جست‌وجو کنید و مناسب‌ترین را پیدا کنید.",
                "slide1_link": "/#numbers",
                "slide2_title": "اطلاعات {office_name}",
                "slide2_text": "نشانی، ساعات کاری و خدمات را از نزدیک ببینید.",
                "slide2_link": "/about",
                "slide3_title": "ارتباط با ما",
                "slide3_text": "از طریق فرم پیام با {office_name} در تماس باشید.",
                "slide3_link": "/contact",
            }
            for k, v in defaults.items():
                q(f"UPDATE site_settings SET {k}=%s WHERE id=1", (v,))
            db().commit()
            g.site = None
            flash("اسلایدها به پیش‌فرض بازگشتند.", "success")
            return redirect(url_for("admin_settings_slides"))

        form_data = {}
        for k in SLIDES_KEYS:
            form_data[k] = request.form.get(k,"").strip()
        errors = []
        for k in SLIDES_KEYS:
            if len(form_data[k]) > SLIDES_LIMITS[k]:
                errors.append(f"«{k}» طولانی است.")
        if errors:
            flash("؛ ".join(errors), "error")
        else:
            cols = ",".join(f"{k}=%s" for k in SLIDES_KEYS)
            q(f"UPDATE site_settings SET {cols} WHERE id=1",
              [form_data[k] for k in SLIDES_KEYS])
            db().commit()
            g.site = None
            flash("اسلایدها ذخیره شد.", "success")
            return redirect(url_for("admin_settings_slides"))
    form_data = dict(get_settings())
    return render_page(ADMIN, title="اسلایدشو", active="settings_slides",
                       page_title="مدیریت اسلایدشو",
                       page_desc="متن و لینک هر اسلاید را تنظیم کنید.",
                       form_data=form_data)

@app.route("/health")
def health():
    info = {"version": APP_VERSION,
            "database_url_set": bool((os.environ.get("DATABASE_URL") or "").strip()),
            "db_connected": False, "tables": {}, "user_count": 0,
            "settings_ready": False, "error": None}
    try:
        conn = pymysql.connect(**get_db_params(), charset="utf8mb4",
                               cursorclass=DictCursor, autocommit=True)
        info["db_connected"] = True
        with conn.cursor() as cur:
            for tbl in ["users","numbers","contact_messages","site_settings"]:
                try:
                    cur.execute(f"SELECT COUNT(*) AS c FROM {tbl}")
                    info["tables"][tbl] = cur.fetchone()['c']
                except Exception as e:
                    info["tables"][tbl] = f"ERROR: {e}"
            try:
                cur.execute("SELECT COUNT(*) AS c FROM users")
                info["user_count"] = cur.fetchone()['c']
            except Exception: pass
            try:
                cur.execute("SELECT COUNT(*) AS c FROM site_settings WHERE id=1")
                info["settings_ready"] = cur.fetchone()['c'] > 0
            except Exception: pass
        conn.close()
    except Exception as e:
        info["error"] = str(e)
    return _json.dumps(info, ensure_ascii=False, indent=2), 200, \
           {"Content-Type": "application/json; charset=utf-8"}

@app.errorhandler(403)
def forbidden(_e):
    return render_page("""{% extends "base.html" %}{% block content %}
    <section class="form-card glass"><h1 style="position:relative;z-index:2">دسترسی محدود</h1>
    <p class="muted" style="position:relative;z-index:2">این بخش فقط برای مدیر سایت است.</p>
    <a class="btn primary" href="{{ url_for('index') }}" style="margin-top:10px;position:relative;z-index:2">بازگشت</a></section>
    {% endblock %}""", title="دسترسی محدود"), 403

@app.errorhandler(404)
def not_found(_e):
    return render_page("""{% extends "base.html" %}{% block content %}
    <section class="form-card glass"><h1 style="position:relative;z-index:2">صفحه پیدا نشد</h1>
    <p class="muted" style="position:relative;z-index:2">آگهی حذف شده یا نشانی اشتباه است.</p>
    <a class="btn primary" href="{{ url_for('index') }}" style="margin-top:10px;position:relative;z-index:2">بازگشت به خانه</a></section>
    {% endblock %}""", title="یافت نشد"), 404

@app.errorhandler(500)
def server_error(_e):
    try:
        if "db" in g: g.db.rollback()
    except Exception: pass
    return render_page("""{% extends "base.html" %}{% block content %}
    <section class="form-card glass"><h1 style="position:relative;z-index:2">خطای سرور</h1>
    <p class="muted" style="position:relative;z-index:2">مشکلی رخ داده. لطفاً دوباره تلاش کنید.</p>
    <a class="btn primary" href="{{ url_for('index') }}" style="margin-top:10px;position:relative;z-index:2">بازگشت به خانه</a></section>
    {% endblock %}""", title="خطای سرور"), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5001")), debug=False)