from flask import Flask, request, redirect, render_template, jsonify, abort
import sqlite3
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
DB_PATH = "rsvp.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_base_url():
    # First priority: SITE_URL environment variable set in Railway
    env_url = os.environ.get("SITE_URL", "").rstrip("/")
    if env_url:
        return env_url
    # Second: saved in settings
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key='base_url'").fetchone()
    if row and row["value"]:
        return row["value"].rstrip("/")
    # Fallback: derive from request headers (Railway sets these)
    scheme = request.headers.get("X-Forwarded-Proto", "https")
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{scheme}://{host}"

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS guests (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id TEXT NOT NULL,
                action TEXT NOT NULL DEFAULT 'rsvp',
                ip TEXT,
                clicked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (guest_id) REFERENCES guests(id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

init_db()

# --- Guest RSVP click ---
@app.route("/rsvp/<guest_id>")
def rsvp_click(guest_id):
    db = get_db()
    guest = db.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
    if not guest:
        abort(404)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    db.execute("INSERT INTO clicks (guest_id, action, ip) VALUES (?, 'rsvp', ?)", (guest_id, ip))
    db.commit()
    redirect_url = os.environ.get("REDIRECT_URL", "/confirmed")
    return redirect(redirect_url)

@app.route("/confirmed")
def confirmed():
    return render_template("confirmed.html")

# --- Main admin UI ---
@app.route("/")
def admin():
    db = get_db()
    guests = db.execute("SELECT * FROM guests ORDER BY created_at DESC").fetchall()
    clicks = db.execute("""
        SELECT c.*, g.name, g.email
        FROM clicks c JOIN guests g ON c.guest_id = g.id
        ORDER BY c.clicked_at DESC
    """).fetchall()
    total_guests = len(guests)
    unique_responders = db.execute("SELECT COUNT(DISTINCT guest_id) as count FROM clicks").fetchone()["count"]
    settings = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
    base_url = get_base_url()
    return render_template("admin.html",
        guests=guests, clicks=clicks,
        total_guests=total_guests,
        unique_responders=unique_responders,
        settings=settings,
        base_url=base_url
    )

# --- API: Guests ---
@app.route("/api/guests", methods=["POST"])
def add_guest():
    data = request.json
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400
    guest_id = "g-" + uuid.uuid4().hex[:8]
    with get_db() as db:
        db.execute("INSERT INTO guests (id, name, email) VALUES (?, ?, ?)", (guest_id, name, email))
    base_url = get_base_url()
    return jsonify({"success": True, "id": guest_id, "rsvp_link": f"{base_url}/rsvp/{guest_id}"})

@app.route("/api/guests/<guest_id>", methods=["PUT"])
def update_guest(guest_id):
    data = request.json
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400
    with get_db() as db:
        db.execute("UPDATE guests SET name=?, email=? WHERE id=?", (name, email, guest_id))
    return jsonify({"success": True})

@app.route("/api/guests/<guest_id>", methods=["DELETE"])
def delete_guest(guest_id):
    with get_db() as db:
        db.execute("DELETE FROM clicks WHERE guest_id=?", (guest_id,))
        db.execute("DELETE FROM guests WHERE id=?", (guest_id,))
    return jsonify({"success": True})

# --- API: Settings ---
@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json
    with get_db() as db:
        for key, value in data.items():
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    return jsonify({"success": True})

# --- API: Send emails ---
@app.route("/api/send-emails", methods=["POST"])
def send_emails():
    data = request.json
    guest_ids = data.get("guest_ids", [])
    db = get_db()
    settings = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}

    gmail = settings.get("gmail", "")
    app_password = settings.get("app_password", "")
    event_name = settings.get("event_name", "Our Event")
    event_date = settings.get("event_date", "")
    event_location = settings.get("event_location", "")

    if not gmail or not app_password:
        return jsonify({"error": "Gmail settings not configured"}), 400

    base_url = get_base_url()
    sent = []
    errors = []

    for guest_id in guest_ids:
        guest = db.execute("SELECT * FROM guests WHERE id=?", (guest_id,)).fetchone()
        if not guest:
            continue
        rsvp_link = f"{base_url}/rsvp/{guest['id']}"
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"You're invited to {event_name}!"
            msg["From"] = gmail
            msg["To"] = guest["email"]
            html = f"""
            <html><body style="font-family:sans-serif;max-width:520px;margin:auto;padding:2rem;">
              <h2 style="margin-bottom:0.25rem;">Hi {guest['name']}! 👋</h2>
              <p style="color:#555;">You're invited to <strong>{event_name}</strong>.</p>
              {"<p>📅 " + event_date + "</p>" if event_date else ""}
              {"<p>📍 " + event_location + "</p>" if event_location else ""}
              <br>
              <a href="{rsvp_link}" style="background:#16a34a;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block;">✅ Yes, I'm coming!</a>
              <br><br>
              <p style="color:#aaa;font-size:0.8rem;">Can't click the button? Copy this link: {rsvp_link}</p>
            </body></html>"""
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail, app_password)
                server.sendmail(gmail, guest["email"], msg.as_string())
            sent.append(guest["name"])
        except Exception as e:
            errors.append({"name": guest["name"], "error": str(e)})

    return jsonify({"sent": sent, "errors": errors})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
