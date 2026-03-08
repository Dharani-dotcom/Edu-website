from flask import Flask, render_template, request, redirect, session, send_file
import mysql.connector
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key")

# ---------------- DATABASE ----------------
def get_db():
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306))
    )
    return conn

# ---------------- DB INIT ----------------
def init_db():
    db = get_db()
    cursor = db.cursor()
    # Users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(150) UNIQUE,
            password TEXT,
            role VARCHAR(20)
        )
    """)
    # Courses
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200),
            speaker VARCHAR(200),
            designation VARCHAR(200),
            price INT,
            schedule VARCHAR(200),
            form_link TEXT
        )
    """)
    # Enrollments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_id INT,
            name VARCHAR(200),
            email VARCHAR(200),
            phone VARCHAR(50)
        )
    """)
    # Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            class VARCHAR(100),
            subject VARCHAR(100),
            schedule VARCHAR(200)
        )
    """)

    # Default admin
    cursor.execute("SELECT * FROM users WHERE email=%s", ("admin@learnify.com",))
    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (username,email,password,role)
            VALUES (%s,%s,%s,%s)
        """, ("Admin", "admin@learnify.com", generate_password_hash("Admin@123"), "admin"))

    db.commit()
    cursor.close()
    db.close()

init_db()

# ---------------- HOME ----------------
@app.route("/")
def home():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.execute("SELECT * FROM sessions")
    sessions_data = cursor.fetchall()
    cursor.close()
    db.close()
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

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (username,email,password,role)
            VALUES (%s,%s,%s,%s)
        """, (username, email, hashed_password, "user"))
        db.commit()
        return redirect("/")
    except mysql.connector.IntegrityError:
        return "Email already exists", 400
    finally:
        cursor.close()
        db.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.form
    email = data.get("email")
    password = data.get("password")
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    cursor.close()
    db.close()
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
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM courses")
    courses = cursor.fetchall()
    cursor.execute("""
        SELECT c.title, e.name, e.email, e.phone
        FROM enrollments e JOIN courses c ON e.course_id=c.id
    """)
    enrollments = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("admin_panel.html", courses=courses, enrollments=enrollments)

# ---------------- COURSES ----------------
@app.route("/admin/course/add", methods=["POST"])
def add_course():
    if session.get("role") != "admin":
        return redirect("/")
    data = request.form
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO courses (title,speaker,designation,price,schedule,form_link)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        data.get("title"),
        data.get("speaker"),
        data.get("designation"),
        data.get("price"),
        data.get("schedule"),
        data.get("form_link")
    ))
    db.commit()
    cursor.close()
    db.close()
    return redirect("/admin")

@app.route("/admin/course/delete/<int:cid>")
def delete_course(cid):
    if session.get("role") != "admin":
        return redirect("/")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM courses WHERE id=%s", (cid,))
    db.commit()
    cursor.close()
    db.close()
    return redirect("/admin")

# ---------------- ENROLLMENT ----------------
@app.route("/enroll", methods=["POST"])
def enroll():
    data = request.form
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO enrollments (course_id,name,email,phone)
        VALUES (%s,%s,%s,%s)
    """, (
        data.get("course_id"),
        data.get("name"),
        data.get("email"),
        data.get("phone")
    ))
    db.commit()
    cursor.close()
    db.close()
    return redirect("/")

# ---------------- SESSIONS ----------------
@app.route("/admin/session/add", methods=["POST"])
def add_session():
    if session.get("role") != "admin":
        return redirect("/")
    data = request.form
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO sessions (class,subject,schedule)
        VALUES (%s,%s,%s)
    """, (
        data.get("class"),
        data.get("subject"),
        data.get("schedule")
    ))
    db.commit()
    cursor.close()
    db.close()
    return redirect("/admin")

# ---------------- CSV DOWNLOAD ----------------
@app.route("/admin/enrollments/csv")
def download_csv():
    if session.get("role") != "admin":
        return redirect("/")
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.title, e.name, e.email, e.phone
        FROM enrollments e JOIN courses c ON e.course_id=c.id
    """)
    rows = cursor.fetchall()
    cursor.close()
    db.close()

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
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
