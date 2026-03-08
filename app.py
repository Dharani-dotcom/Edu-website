from flask import Flask, render_template, request, redirect, session, send_file
import mysql.connector
from mysql.connector import Error
import csv, io, os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key")

# ---------------- MySQL CONNECTION ----------------
def get_db():
    try:
        conn = mysql.connector.connect(
            host=os.environ.get("DB_HOST"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME"),
            port=int(os.environ.get("DB_PORT", 3306))
        )
        return conn
    except Error as e:
        print("Error connecting to MySQL:", e)
        return None

# ---------------- DB INIT ----------------
def init_db():
    db = get_db()
    if db is None:
        print("Database connection failed!")
        return
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255),
            email VARCHAR(255) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(50)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255),
            speaker VARCHAR(255),
            designation VARCHAR(255),
            price INT,
            schedule VARCHAR(255),
            form_link VARCHAR(255)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_id INT,
            name VARCHAR(255),
            email VARCHAR(255),
            phone VARCHAR(50),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            class VARCHAR(255),
            subject VARCHAR(255),
            schedule VARCHAR(255)
        )
    """)
    # default admin
    cursor.execute("SELECT * FROM users WHERE email=%s", ("admin@learnify.com",))
    admin = cursor.fetchone()
    if not admin:
        cursor.execute("""
            INSERT INTO users (username, email, password, role)
            VALUES (%s, %s, %s, %s)
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
    except mysql.connector.IntegrityError:
        return "Email already exists", 400
    finally:
        cursor.close()
        db.close()
    return redirect("/")

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
    app.run(debug=True)
