from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import sqlite3
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super-secret-key"

DB = "learnify.db"

# ---------------- DB INIT ----------------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            speaker TEXT,
            designation TEXT,
            price INTEGER,
            schedule TEXT,
            form_link TEXT
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            name TEXT,
            email TEXT,
            phone TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class TEXT,
            subject TEXT,
            schedule TEXT
        );
        """)

        # default admin
        admin = db.execute(
            "SELECT * FROM users WHERE email=?",
            ("admin@learnify.com",)
        ).fetchone()

        if not admin:
            db.execute("""
                INSERT INTO users (username,email,password,role)
                VALUES (?,?,?,?)
            """, (
                "Admin",
                "admin@learnify.com",
                generate_password_hash("Admin@123"),
                "admin"
            ))
        db.commit()

init_db()

# ---------------- HOME ----------------
@app.route("/")
def home():
    db = get_db()
    courses = db.execute("SELECT * FROM courses").fetchall()
    sessions_data = db.execute("SELECT * FROM sessions").fetchall()
    return render_template("index.html", courses=courses, sessions=sessions_data)

# ---------------- AUTH ----------------
@app.route("/register", methods=["POST"])
def register():
    data = request.form

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return "All fields required", 400

    hashed_password = generate_password_hash(password)

    with get_db() as db:
        try:
            db.execute("""
                INSERT INTO users (username,email,password,role)
                VALUES (?,?,?,?)
            """, (username, email, hashed_password, "user"))
            db.commit()
            return redirect("/")
        except sqlite3.IntegrityError:
            return "Email already exists", 400

@app.route("/login", methods=["POST"])
def login():
    data = request.form

    email = data.get("email")
    password = data.get("password")

    user = get_db().execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    ).fetchone()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["username"] = user["username"]
        return redirect("/")

    return "Invalid email or password", 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- ADMIN ----------------
@app.route("/admin")
def admin_panel():
    if session.get("role") != "admin":
        return redirect("/")

    db = get_db()
    courses = db.execute("SELECT * FROM courses").fetchall()
    enrollments = db.execute("""
        SELECT c.title, e.name, e.email, e.phone
        FROM enrollments e JOIN courses c ON e.course_id=c.id
    """).fetchall()

    return render_template(
        "admin_panel.html",
        courses=courses,
        enrollments=enrollments
    )

# ---------------- COURSES ----------------
@app.route("/admin/course/add", methods=["POST"])
def add_course():
    if session.get("role") != "admin":
        return redirect("/")

    data = request.form

    with get_db() as db:
        db.execute("""
            INSERT INTO courses (title,speaker,designation,price,schedule,form_link)
            VALUES (?,?,?,?,?,?)
        """, (
            data.get("title"),
            data.get("speaker"),
            data.get("designation"),
            data.get("price"),
            data.get("schedule"),
            data.get("form_link")
        ))
        db.commit()

    return redirect("/admin")

@app.route("/admin/course/delete/<int:cid>")
def delete_course(cid):
    if session.get("role") != "admin":
        return redirect("/")

    with get_db() as db:
        db.execute("DELETE FROM courses WHERE id=?", (cid,))
        db.commit()

    return redirect("/admin")

# ---------------- ENROLLMENT ----------------
@app.route("/enroll", methods=["POST"])
def enroll():
    data = request.form

    with get_db() as db:
        db.execute("""
            INSERT INTO enrollments (course_id,name,email,phone)
            VALUES (?,?,?,?)
        """, (
            data.get("course_id"),
            data.get("name"),
            data.get("email"),
            data.get("phone")
        ))
        db.commit()

    return redirect("/")

# ---------------- SESSIONS ----------------
@app.route("/admin/session/add", methods=["POST"])
def add_session():
    if session.get("role") != "admin":
        return redirect("/")

    data = request.form

    with get_db() as db:
        db.execute("""
            INSERT INTO sessions (class,subject,schedule)
            VALUES (?,?,?)
        """, (
            data.get("class"),
            data.get("subject"),
            data.get("schedule")
        ))
        db.commit()

    return redirect("/admin")

# ---------------- CSV DOWNLOAD ----------------
@app.route("/admin/enrollments/csv")
def download_csv():
    if session.get("role") != "admin":
        return redirect("/")

    db = get_db()
    rows = db.execute("""
        SELECT c.title, e.name, e.email, e.phone
        FROM enrollments e JOIN courses c ON e.course_id=c.id
    """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Course", "Name", "Email", "Phone"])

    for r in rows:
        writer.writerow([r["title"], r["name"], r["email"], r["phone"]])

    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="learnify_enrollments.csv"
    )

# ---------------- RUN ----------------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render automatically sets PORT
    app.run(host="0.0.0.0", port=port, debug=True)

