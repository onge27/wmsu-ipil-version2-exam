import os
import re
import json
import secrets as pysecrets
import sqlite3
from functools import wraps
from datetime import datetime

import bcrypt
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# ─── Gemini AI ───────────────────────────────────────────────────────────────
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
import google.generativeai as genai
_gemini_key = os.getenv('GEMINI_API_KEY')
if _gemini_key:
    genai.configure(api_key=_gemini_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

# ─── Database ────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('NEON_DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    USE_POSTGRES = True
else:
    USE_POSTGRES = False

def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect('examination.db')
        conn.row_factory = sqlite3.Row
        return conn

def db_cursor(conn):
    if USE_POSTGRES:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()

def db_execute(conn, sql, params=()):
    if USE_POSTGRES:
        sql = sql.replace('?', '%s')
    cur = db_cursor(conn)
    cur.execute(sql, params)
    return cur

def db_lastid(cur):
    if USE_POSTGRES:
        row = cur.fetchone()
        return row['id'] if row else None
    return cur.lastrowid

# ─── App ──────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'wmsu-oes-secure-key-2026')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}
app.config['CLERK_PUBLISHABLE_KEY'] = os.getenv('CLERK_PUBLISHABLE_KEY', '')
app.config['CLERK_SECRET_KEY'] = os.getenv('CLERK_SECRET_KEY', '')
app.config['YEAR'] = 2026
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── DB Init ─────────────────────────────────────────────────────────────────
def init_db():
    conn = get_db()
    cur = db_cursor(conn)

    if USE_POSTGRES:
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            student_number INTEGER UNIQUE,
            is_verified INTEGER DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            subject_name TEXT NOT NULL,
            teacher_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS allowed_students (
            id SERIAL PRIMARY KEY,
            student_number INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            UNIQUE(student_number, subject_id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            duration INTEGER NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS results (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, exam_id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exam_access_requests (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            UNIQUE(student_id, exam_id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exam_access_keys (
            id SERIAL PRIMARY KEY,
            exam_id INTEGER NOT NULL,
            access_key TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
    else:
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            student_number INTEGER UNIQUE,
            is_verified INTEGER DEFAULT 0
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT NOT NULL,
            teacher_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS allowed_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_number INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            UNIQUE(student_number, subject_id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            duration INTEGER NOT NULL,
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, exam_id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exam_access_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            UNIQUE(student_id, exam_id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS exam_access_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            access_key TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )''')

    # Default teacher
    teacher_email = "teacher@example.com"
    row = db_execute(conn, "SELECT id FROM users WHERE email = ?", (teacher_email,)).fetchone()
    if not row:
        hashed = bcrypt.hashpw("teacher123".encode(), bcrypt.gensalt())
        db_execute(conn, "INSERT INTO users (name, email, password, role, is_verified) VALUES (?, ?, ?, ?, ?)",
                   ("Default Teacher", teacher_email, hashed.decode() if USE_POSTGRES else hashed, "teacher", 1))

    # Default admin
    admin_email = "admin@example.com"
    row = db_execute(conn, "SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
    if not row:
        hashed_admin = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
        db_execute(conn, "INSERT INTO users (name, email, password, role, is_verified) VALUES (?, ?, ?, ?, ?)",
                   ("System Admin", admin_email, hashed_admin.decode() if USE_POSTGRES else hashed_admin, "admin", 1))

    # Default subject
    row = db_execute(conn, "SELECT COUNT(*) as cnt FROM subjects").fetchone()
    count = row['cnt'] if USE_POSTGRES else row[0]
    if count == 0:
        teacher = db_execute(conn, "SELECT id FROM users WHERE role = 'teacher' LIMIT 1").fetchone()
        if teacher:
            db_execute(conn, "INSERT INTO subjects (subject_name, teacher_id) VALUES (?, ?)",
                       ("Computer Science", teacher['id']))

    conn.commit()
    conn.close()


init_db()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to continue.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') != role:
                flash('You do not have permission to access that page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def check_password(stored, provided):
    if isinstance(stored, str):
        stored = stored.encode()
    return bcrypt.checkpw(provided.encode(), stored)


# ─── Routes: Public ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    conn = get_db()
    subjects = db_execute(conn, "SELECT id, subject_name FROM subjects").fetchall()
    conn.close()

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        role = request.form['role']
        student_number = request.form.get('student_number', '').strip()
        teacher_code = request.form.get('teacher_code', '')
        subject_id = request.form.get('subject_id')

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html', subjects=subjects)

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html', subjects=subjects)

        if role == 'teacher':
            if teacher_code != 'ADMIN123':
                flash('Invalid teacher registration code.', 'danger')
                return render_template('register.html', subjects=subjects)
            student_number = None
            is_verified = 1
        else:
            if not student_number:
                flash('Student number is required.', 'danger')
                return render_template('register.html', subjects=subjects)
            clean = student_number.replace('-', '').strip()
            if not clean.isdigit():
                flash('Student number must contain only numbers and dashes.', 'danger')
                return render_template('register.html', subjects=subjects)
            student_number = int(clean)

            conn = get_db()
            existing = db_execute(conn, "SELECT id FROM users WHERE student_number = ?", (student_number,)).fetchone()
            conn.close()
            if existing:
                flash('That student number is already registered.', 'danger')
                return render_template('register.html', subjects=subjects)

            if not subject_id:
                flash('Please select a subject.', 'danger')
                return render_template('register.html', subjects=subjects)

            is_verified = 1

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        hashed_store = hashed.decode() if USE_POSTGRES else hashed

        try:
            conn = get_db()
            if USE_POSTGRES:
                cur = db_execute(conn,
                    "INSERT INTO users (name, email, password, role, student_number, is_verified) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
                    (name, email, hashed_store, role, student_number, is_verified))
                user_id = db_lastid(cur)
            else:
                cur = db_execute(conn,
                    "INSERT INTO users (name, email, password, role, student_number, is_verified) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, email, hashed_store, role, student_number, is_verified))
                user_id = db_lastid(cur)

            if role == 'student':
                if USE_POSTGRES:
                    db_execute(conn,
                        "INSERT INTO allowed_students (student_number, student_name, subject_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (student_number, name, subject_id))
                else:
                    db_execute(conn,
                        "INSERT OR IGNORE INTO allowed_students (student_number, student_name, subject_id) VALUES (?, ?, ?)",
                        (student_number, name, subject_id))

            conn.commit()
            conn.close()
            flash('Registration successful! You can now sign in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Email address already exists. Please use a different email.', 'danger')
            return render_template('register.html', subjects=subjects)

    return render_template('register.html', subjects=subjects)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form['login_id'].strip()
        password = request.form['password']

        conn = get_db()
        user = None
        if login_id.isdigit():
            user = db_execute(conn, "SELECT * FROM users WHERE student_number = ?", (int(login_id),)).fetchone()
        else:
            user = db_execute(conn, "SELECT * FROM users WHERE email = ?", (login_id,)).fetchone()
        conn.close()

        if user and check_password(user['password'], password):
            if user['is_verified'] == 0:
                flash('Your account is pending verification. Please contact your teacher.', 'warning')
                return redirect(url_for('login'))
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            session['student_number'] = user['student_number']
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect email/student number or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('login'))

# ─── Google OAuth Callback (Clerk) ───────────────────────────────────────────
@app.route('/auth/google/callback')
def google_auth_callback():
    clerk_secret = app.config.get('CLERK_SECRET_KEY', '')
    if not clerk_secret:
        flash('Google sign-in is not configured.', 'danger')
        return redirect(url_for('login'))

    session_token = request.cookies.get('__session')
    if not session_token:
        flash('Authentication failed. Please try again.', 'danger')
        return redirect(url_for('login'))

    try:
        import urllib.request
        import urllib.parse
        req = urllib.request.Request(
            'https://api.clerk.com/v1/sessions/verify',
            data=urllib.parse.urlencode({'token': session_token}).encode(),
            headers={
                'Authorization': f'Bearer {clerk_secret}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            method='POST'
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        email = data.get('session', {}).get('user', {}).get('email_addresses', [{}])[0].get('email_address', '')
        if not email:
            email = data.get('user', {}).get('email_addresses', [{}])[0].get('email_address', '')

        if not email:
            flash('Could not retrieve email from Google account.', 'danger')
            return redirect(url_for('login'))

        conn = get_db()
        user = db_execute(conn, "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if not user:
            flash('No account found for that Google email. Please register first.', 'warning')
            return redirect(url_for('register'))

        if user['is_verified'] == 0:
            flash('Your account is pending verification.', 'warning')
            return redirect(url_for('login'))

        session['user_id'] = user['id']
        session['role'] = user['role']
        session['name'] = user['name']
        session['student_number'] = user['student_number']
        flash(f'Signed in with Google. Welcome, {user["name"]}!', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash('Google sign-in failed. Please try again.', 'danger')
        return redirect(url_for('login'))

# ─── Dashboard ───────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))


# ─── Teacher Routes ───────────────────────────────────────────────────────────
@app.route('/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    conn = get_db()
    subjects = db_execute(conn, "SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    exams = db_execute(conn,
        "SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE s.teacher_id = ?",
        (session['user_id'],)).fetchall()
    pending_verifications = db_execute(conn, "SELECT * FROM users WHERE role = 'student' AND is_verified = 0").fetchall()
    pending_requests = db_execute(conn, """
        SELECT r.*, u.name as student_name, u.student_number, e.title as exam_title, s.subject_name
        FROM exam_access_requests r
        JOIN users u ON r.student_id = u.id
        JOIN exams e ON r.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE s.teacher_id = ? AND r.status = 'pending'
        ORDER BY r.requested_at DESC
    """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('teacher_dashboard.html',
                           subjects=subjects, exams=exams,
                           pending_verifications=pending_verifications,
                           pending_requests=pending_requests)

@app.route('/teacher/create_subject', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def create_subject():
    if request.method == 'POST':
        subject_name = request.form['subject_name'].strip()
        if subject_name:
            conn = get_db()
            db_execute(conn, "INSERT INTO subjects (subject_name, teacher_id) VALUES (?, ?)",
                       (subject_name, session['user_id']))
            conn.commit()
            conn.close()
            flash('Subject created successfully.', 'success')
            return redirect(url_for('teacher_dashboard'))
        flash('Subject name is required.', 'danger')
    return render_template('create_subject.html')

@app.route('/teacher/create_exam', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def create_exam():
    conn = get_db()
    subjects = db_execute(conn, "SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()

    if request.method == 'POST':
        subject_id = request.form['subject_id']
        title = request.form['title'].strip()
        duration = request.form['duration']

        if not title or not duration or not subject_id:
            flash('All fields are required.', 'danger')
            return render_template('create_exam.html', subjects=subjects)

        conn = get_db()
        if USE_POSTGRES:
            cur = db_execute(conn, "INSERT INTO exams (subject_id, title, duration) VALUES (?, ?, ?) RETURNING id",
                             (subject_id, title, duration))
            exam_id = db_lastid(cur)
        else:
            cur = db_execute(conn, "INSERT INTO exams (subject_id, title, duration) VALUES (?, ?, ?)",
                             (subject_id, title, duration))
            exam_id = db_lastid(cur)
        conn.commit()
        conn.close()
        flash('Exam created! Now add your questions.', 'success')
        return redirect(url_for('add_questions', exam_id=exam_id))

    return render_template('create_exam.html', subjects=subjects)

@app.route('/teacher/add_questions/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def add_questions(exam_id):
    conn = get_db()
    exam = db_execute(conn, "SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not exam:
        flash('Exam not found.', 'danger')
        conn.close()
        return redirect(url_for('teacher_dashboard'))

    if request.method == 'POST':
        question = request.form['question']
        option_a = request.form['option_a']
        option_b = request.form['option_b']
        option_c = request.form['option_c']
        option_d = request.form['option_d']
        correct_answer = request.form['correct_answer']
        db_execute(conn,
            "INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exam_id, question, option_a, option_b, option_c, option_d, correct_answer))
        conn.commit()
        flash('Question added successfully.', 'success')
        conn.close()
        return redirect(url_for('add_questions', exam_id=exam_id))

    questions = db_execute(conn, "SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    conn.close()
    return render_template('add_questions.html', exam=exam, questions=questions)

@app.route('/teacher/delete_question/<int:question_id>', methods=['POST'])
@login_required
@role_required('teacher')
def delete_question(question_id):
    conn = get_db()
    q = db_execute(conn, "SELECT exam_id FROM questions WHERE id = ?", (question_id,)).fetchone()
    exam_id = q['exam_id'] if q else None
    db_execute(conn, "DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    flash('Question deleted.', 'success')
    return redirect(url_for('add_questions', exam_id=exam_id) if exam_id else url_for('teacher_dashboard'))

@app.route('/teacher/auto_generate_questions/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def auto_generate_questions(exam_id):
    conn = get_db()
    exam = db_execute(conn, "SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()

    if not exam:
        flash('Exam not found.', 'danger')
        return redirect(url_for('teacher_dashboard'))

    if request.method == 'POST':
        topic = request.form['topic'].strip()
        num_questions = int(request.form['num_questions'])

        if num_questions < 1 or num_questions > 20:
            flash('Number of questions must be between 1 and 20.', 'danger')
            return redirect(url_for('auto_generate_questions', exam_id=exam_id))

        if not gemini_model:
            flash('AI generation is not configured. Please set the GEMINI_API_KEY.', 'danger')
            return redirect(url_for('add_questions', exam_id=exam_id))

        try:
            prompt = f"""Generate exactly {num_questions} multiple-choice questions about "{topic}".
Each question must have exactly four options (A, B, C, D) and one correct answer.
Format each question EXACTLY as shown below with NO extra text or numbering:

Question: [Question text here]
A) [Option A text]
B) [Option B text]
C) [Option C text]
D) [Option D text]
Answer: [A/B/C/D]

Separate each question block with a single blank line."""

            response = gemini_model.generate_content(prompt)
            generated_text = response.text.strip()

            blocks = re.split(r'\n\s*\n', generated_text)
            saved_count = 0
            conn = get_db()

            for block in blocks:
                lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
                if len(lines) < 6:
                    continue
                q_line = next((l for l in lines if l.lower().startswith('question:')), None)
                a_line = next((l for l in lines if l.upper().startswith('A)')), None)
                b_line = next((l for l in lines if l.upper().startswith('B)')), None)
                c_line = next((l for l in lines if l.upper().startswith('C)')), None)
                d_line = next((l for l in lines if l.upper().startswith('D)')), None)
                ans_line = next((l for l in lines if l.lower().startswith('answer:')), None)

                if not all([q_line, a_line, b_line, c_line, d_line, ans_line]):
                    continue

                question_text = q_line.split(':', 1)[1].strip()
                opt_a = re.sub(r'^A\)', '', a_line, flags=re.IGNORECASE).strip()
                opt_b = re.sub(r'^B\)', '', b_line, flags=re.IGNORECASE).strip()
                opt_c = re.sub(r'^C\)', '', c_line, flags=re.IGNORECASE).strip()
                opt_d = re.sub(r'^D\)', '', d_line, flags=re.IGNORECASE).strip()
                answer = ans_line.split(':', 1)[1].strip().upper()

                if answer not in ['A', 'B', 'C', 'D']:
                    continue

                db_execute(conn,
                    "INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (exam_id, question_text, opt_a, opt_b, opt_c, opt_d, answer))
                saved_count += 1

            conn.commit()
            conn.close()

            if saved_count > 0:
                flash(f'Successfully generated and saved {saved_count} question(s)!', 'success')
            else:
                flash('Could not parse the AI response. Try a different topic or try again.', 'warning')

        except Exception as e:
            flash(f'Error generating questions: {str(e)}', 'danger')

        return redirect(url_for('add_questions', exam_id=exam_id))

    return render_template('auto_generate.html', exam=exam)

@app.route('/teacher/upload_students', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def upload_students():
    conn = get_db()
    subjects = db_execute(conn, "SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()

    if request.method == 'POST':
        subject_id = request.form['subject_id']
        if 'file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(url_for('upload_students'))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('upload_students'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    df = pd.read_excel(filepath)

                required_columns = ['student_number', 'student_name']
                if not all(col in df.columns for col in required_columns):
                    flash('File must have columns: student_number and student_name.', 'danger')
                    return redirect(url_for('upload_students'))

                conn = get_db()
                count = 0
                for _, row in df.iterrows():
                    snum = int(row['student_number'])
                    sname = str(row['student_name']).strip()
                    try:
                        if USE_POSTGRES:
                            db_execute(conn,
                                "INSERT INTO allowed_students (student_number, student_name, subject_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                (snum, sname, subject_id))
                        else:
                            db_execute(conn,
                                "INSERT OR REPLACE INTO allowed_students (student_number, student_name, subject_id) VALUES (?, ?, ?)",
                                (snum, sname, subject_id))
                        count += 1
                    except Exception:
                        pass
                conn.commit()
                conn.close()
                flash(f'Successfully imported {count} student(s).', 'success')
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Invalid file type. Please upload a CSV or Excel (.xlsx) file.', 'danger')
        return redirect(url_for('upload_students'))

    return render_template('upload_students.html', subjects=subjects)

@app.route('/teacher/view_allowed_students')
@login_required
@role_required('teacher')
def view_allowed_students():
    conn = get_db()
    subjects = db_execute(conn, "SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    selected_subject = request.args.get('subject_id')
    students = []
    if selected_subject:
        students = db_execute(conn, "SELECT * FROM allowed_students WHERE subject_id = ?", (selected_subject,)).fetchall()
    conn.close()
    return render_template('view_allowed_students.html', subjects=subjects, students=students, selected_subject=selected_subject)

@app.route('/teacher/verify_student/<int:user_id>')
@login_required
@role_required('teacher')
def verify_student(user_id):
    conn = get_db()
    db_execute(conn, "UPDATE users SET is_verified = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Student verified successfully.', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/view_results')
@login_required
@role_required('teacher')
def view_results():
    conn = get_db()
    exams = db_execute(conn,
        "SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE s.teacher_id = ?",
        (session['user_id'],)).fetchall()
    results = []
    exam_id = request.args.get('exam_id')
    if exam_id:
        results = db_execute(conn,
            "SELECT r.*, u.name, u.student_number FROM results r JOIN users u ON r.student_id = u.id WHERE r.exam_id = ?",
            (exam_id,)).fetchall()
    conn.close()
    return render_template('view_results.html', exams=exams, results=results, selected_exam=exam_id)

# ─── Teacher: Exam Access Requests ───────────────────────────────────────────
@app.route('/teacher/exam_requests')
@login_required
@role_required('teacher')
def exam_requests():
    conn = get_db()
    status_filter = request.args.get('status', 'pending')
    if status_filter == 'all':
        all_requests = db_execute(conn, """
            SELECT r.*, u.name as student_name, u.student_number, e.title as exam_title, s.subject_name
            FROM exam_access_requests r
            JOIN users u ON r.student_id = u.id
            JOIN exams e ON r.exam_id = e.id
            JOIN subjects s ON e.subject_id = s.id
            WHERE s.teacher_id = ?
            ORDER BY r.requested_at DESC
        """, (session['user_id'],)).fetchall()
    else:
        all_requests = db_execute(conn, """
            SELECT r.*, u.name as student_name, u.student_number, e.title as exam_title, s.subject_name
            FROM exam_access_requests r
            JOIN users u ON r.student_id = u.id
            JOIN exams e ON r.exam_id = e.id
            JOIN subjects s ON e.subject_id = s.id
            WHERE s.teacher_id = ? AND r.status = ?
            ORDER BY r.requested_at DESC
        """, (session['user_id'], status_filter)).fetchall()
    conn.close()
    return render_template('exam_requests.html', requests=all_requests, status_filter=status_filter)

@app.route('/teacher/approve_request/<int:req_id>', methods=['POST'])
@login_required
@role_required('teacher')
def approve_request(req_id):
    conn = get_db()
    db_execute(conn, "UPDATE exam_access_requests SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    flash('Request approved — student can now take the exam.', 'success')
    return redirect(request.referrer or url_for('exam_requests'))

@app.route('/teacher/reject_request/<int:req_id>', methods=['POST'])
@login_required
@role_required('teacher')
def reject_request(req_id):
    conn = get_db()
    db_execute(conn, "UPDATE exam_access_requests SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()
    flash('Request rejected.', 'success')
    return redirect(request.referrer or url_for('exam_requests'))

# ─── Teacher: Exam Access Keys ────────────────────────────────────────────────
@app.route('/teacher/exam_keys/<int:exam_id>')
@login_required
@role_required('teacher')
def exam_keys(exam_id):
    conn = get_db()
    exam = db_execute(conn,
        "SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE e.id = ? AND s.teacher_id = ?",
        (exam_id, session['user_id'])).fetchone()
    if not exam:
        flash('Exam not found.', 'danger')
        conn.close()
        return redirect(url_for('teacher_dashboard'))
    keys = db_execute(conn, "SELECT * FROM exam_access_keys WHERE exam_id = ? ORDER BY created_at DESC", (exam_id,)).fetchall()
    conn.close()
    return render_template('exam_keys.html', exam=exam, keys=keys)

@app.route('/teacher/generate_exam_key/<int:exam_id>', methods=['POST'])
@login_required
@role_required('teacher')
def generate_exam_key(exam_id):
    key = pysecrets.token_urlsafe(6).upper().replace('-', '').replace('_', '')[:8]
    conn = get_db()
    try:
        db_execute(conn, "INSERT INTO exam_access_keys (exam_id, access_key) VALUES (?, ?)", (exam_id, key))
        conn.commit()
        flash(f'Access key generated: {key} — share this with your students.', 'success')
    except Exception:
        flash('Could not generate key. Please try again.', 'danger')
    conn.close()
    return redirect(url_for('exam_keys', exam_id=exam_id))

@app.route('/teacher/deactivate_key/<int:key_id>', methods=['POST'])
@login_required
@role_required('teacher')
def deactivate_key(key_id):
    conn = get_db()
    k = db_execute(conn, "SELECT exam_id FROM exam_access_keys WHERE id = ?", (key_id,)).fetchone()
    exam_id = k['exam_id'] if k else None
    db_execute(conn, "UPDATE exam_access_keys SET is_active = 0 WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()
    flash('Access key deactivated.', 'success')
    return redirect(url_for('exam_keys', exam_id=exam_id) if exam_id else url_for('teacher_dashboard'))


# ─── Student Routes ───────────────────────────────────────────────────────────
@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    student_id = session['user_id']
    student_number = session['student_number']
    conn = get_db()

    # All exams in enrolled subjects, with access request status and taken status
    exams = db_execute(conn, """
        SELECT DISTINCT e.id, e.title, e.duration, s.subject_name,
               COALESCE(r.status, 'none') as access_status,
               r.id as request_id,
               CASE WHEN res.id IS NOT NULL THEN 1 ELSE 0 END as taken
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN allowed_students a ON a.subject_id = s.id AND a.student_number = ?
        LEFT JOIN exam_access_requests r ON r.exam_id = e.id AND r.student_id = ?
        LEFT JOIN results res ON res.exam_id = e.id AND res.student_id = ?
        ORDER BY s.subject_name, e.title
    """, (student_number, student_id, student_id)).fetchall()

    # Also include any key-approved exams outside enrolled subjects
    key_exams = db_execute(conn, """
        SELECT DISTINCT e.id, e.title, e.duration, s.subject_name,
               'approved' as access_status,
               r.id as request_id,
               CASE WHEN res.id IS NOT NULL THEN 1 ELSE 0 END as taken
        FROM exam_access_requests r
        JOIN exams e ON r.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN results res ON res.exam_id = e.id AND res.student_id = ?
        WHERE r.student_id = ? AND r.status = 'approved'
        AND s.id NOT IN (
            SELECT subject_id FROM allowed_students WHERE student_number = ?
        )
    """, (student_id, student_id, student_number)).fetchall()

    all_exams = list(exams) + list(key_exams)
    conn.close()
    return render_template('student_dashboard.html', exams=all_exams)

@app.route('/student/request_exam_access/<int:exam_id>', methods=['POST'])
@login_required
@role_required('student')
def request_exam_access(exam_id):
    student_id = session['user_id']
    conn = get_db()
    existing = db_execute(conn, "SELECT id, status FROM exam_access_requests WHERE student_id = ? AND exam_id = ?",
                          (student_id, exam_id)).fetchone()
    if existing:
        if existing['status'] == 'approved':
            flash('You already have approved access to this exam.', 'info')
        elif existing['status'] == 'pending':
            flash('Your access request is already pending approval.', 'info')
        elif existing['status'] == 'rejected':
            db_execute(conn, "UPDATE exam_access_requests SET status = 'pending', requested_at = CURRENT_TIMESTAMP WHERE id = ?",
                       (existing['id'],))
            conn.commit()
            flash('Access request re-submitted. Please wait for teacher approval.', 'success')
    else:
        db_execute(conn, "INSERT INTO exam_access_requests (student_id, exam_id) VALUES (?, ?)", (student_id, exam_id))
        conn.commit()
        flash('Access request submitted! Please wait for your teacher to approve.', 'success')
    conn.close()
    return redirect(url_for('student_dashboard'))

@app.route('/student/use_exam_key', methods=['POST'])
@login_required
@role_required('student')
def use_exam_key():
    key = request.form.get('access_key', '').strip().upper()
    if not key:
        flash('Please enter an access key.', 'danger')
        return redirect(url_for('student_dashboard'))

    conn = get_db()
    key_record = db_execute(conn,
        "SELECT * FROM exam_access_keys WHERE access_key = ? AND is_active = 1", (key,)).fetchone()

    if not key_record:
        flash('Invalid or expired access key. Please check with your teacher.', 'danger')
        conn.close()
        return redirect(url_for('student_dashboard'))

    exam_id = key_record['exam_id']
    student_id = session['user_id']

    existing = db_execute(conn, "SELECT id, status FROM exam_access_requests WHERE student_id = ? AND exam_id = ?",
                          (student_id, exam_id)).fetchone()
    if existing:
        if existing['status'] == 'approved':
            flash('You already have access to this exam.', 'info')
        else:
            db_execute(conn, "UPDATE exam_access_requests SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
                       (existing['id'],))
            conn.commit()
            flash('Access granted via key! You can now take the exam.', 'success')
    else:
        db_execute(conn,
            "INSERT INTO exam_access_requests (student_id, exam_id, status, reviewed_at) VALUES (?, ?, 'approved', CURRENT_TIMESTAMP)",
            (student_id, exam_id))
        conn.commit()
        exam = db_execute(conn, "SELECT title FROM exams WHERE id = ?", (exam_id,)).fetchone()
        flash(f'Access granted! You can now take "{exam["title"]}".', 'success')

    conn.close()
    return redirect(url_for('student_dashboard'))

@app.route('/student/take_exam/<int:exam_id>')
@login_required
@role_required('student')
def take_exam(exam_id):
    student_id = session['user_id']
    conn = get_db()
    exam = db_execute(conn,
        "SELECT e.*, s.id as subject_id FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE e.id = ?",
        (exam_id,)).fetchone()

    if not exam:
        flash('Exam not found.', 'danger')
        conn.close()
        return redirect(url_for('student_dashboard'))

    # Must have approved access request
    access = db_execute(conn,
        "SELECT id FROM exam_access_requests WHERE student_id = ? AND exam_id = ? AND status = 'approved'",
        (student_id, exam_id)).fetchone()
    if not access:
        flash('You need approved access to take this exam. Please request access first.', 'warning')
        conn.close()
        return redirect(url_for('student_dashboard'))

    taken = db_execute(conn, "SELECT id FROM results WHERE student_id = ? AND exam_id = ?",
                       (student_id, exam_id)).fetchone()
    if taken:
        flash('You have already submitted this exam.', 'warning')
        conn.close()
        return redirect(url_for('student_dashboard'))

    questions = db_execute(conn, "SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    conn.close()

    if len(questions) == 0:
        flash('This exam has no questions yet.', 'warning')
        return redirect(url_for('student_dashboard'))

    return render_template('take_exam.html', exam=exam, questions=questions)

@app.route('/student/submit_exam/<int:exam_id>', methods=['POST'])
@login_required
@role_required('student')
def submit_exam(exam_id):
    conn = get_db()
    questions = db_execute(conn, "SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()

    score = 0
    for q in questions:
        answer = request.form.get(f'q_{q["id"]}')
        if answer and answer.upper() == q['correct_answer'].upper():
            score += 1

    total = len(questions)
    passing_score = total // 2

    try:
        db_execute(conn, "INSERT INTO results (student_id, exam_id, score, total_questions) VALUES (?, ?, ?, ?)",
                   (session['user_id'], exam_id, score, total))
        conn.commit()
    except Exception:
        conn.close()
        flash('You have already submitted this exam.', 'warning')
        return redirect(url_for('student_dashboard'))

    conn.close()

    if score >= passing_score:
        prediction = "Likely to Pass the Final Exam"
        prediction_class = "success"
    else:
        prediction = "Needs Improvement — Keep Studying!"
        prediction_class = "danger"

    return render_template('result.html', score=score, total=total,
                           prediction=prediction, prediction_class=prediction_class)


# ─── Admin Routes ─────────────────────────────────────────────────────────────
@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()
    total_students = db_execute(conn, "SELECT COUNT(*) as cnt FROM users WHERE role = 'student'").fetchone()
    total_teachers = db_execute(conn, "SELECT COUNT(*) as cnt FROM users WHERE role = 'teacher'").fetchone()
    total_subjects = db_execute(conn, "SELECT COUNT(*) as cnt FROM subjects").fetchone()
    total_exams = db_execute(conn, "SELECT COUNT(*) as cnt FROM exams").fetchone()
    total_results = db_execute(conn, "SELECT COUNT(*) as cnt FROM results").fetchone()
    conn.close()

    def get_count(row):
        return row['cnt'] if USE_POSTGRES else row[0]

    return render_template('admin_dashboard.html',
        total_students=get_count(total_students),
        total_teachers=get_count(total_teachers),
        total_subjects=get_count(total_subjects),
        total_exams=get_count(total_exams),
        total_results=get_count(total_results))

@app.route('/admin/manage_teachers')
@login_required
@admin_required
def manage_teachers():
    conn = get_db()
    teachers = db_execute(conn, "SELECT * FROM users WHERE role = 'teacher'").fetchall()
    conn.close()
    return render_template('manage_teachers.html', teachers=teachers)

@app.route('/admin/delete_teacher/<int:user_id>')
@login_required
@admin_required
def delete_teacher(user_id):
    conn = get_db()
    db_execute(conn, "DELETE FROM users WHERE id = ? AND role = 'teacher'", (user_id,))
    conn.commit()
    conn.close()
    flash('Teacher removed successfully.', 'success')
    return redirect(url_for('manage_teachers'))

@app.route('/admin/view_all_subjects')
@login_required
@admin_required
def view_all_subjects():
    conn = get_db()
    subjects = db_execute(conn,
        "SELECT s.*, u.name as teacher_name FROM subjects s JOIN users u ON s.teacher_id = u.id"
    ).fetchall()
    conn.close()
    return render_template('view_all_subjects.html', subjects=subjects)

@app.route('/admin/delete_subject/<int:subject_id>')
@login_required
@admin_required
def delete_subject(subject_id):
    conn = get_db()
    subject = db_execute(conn, "SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    if not subject:
        flash('Subject not found.', 'danger')
        conn.close()
        return redirect(url_for('view_all_subjects'))

    try:
        db_execute(conn, "DELETE FROM allowed_students WHERE subject_id = ?", (subject_id,))
        exam_ids = db_execute(conn, "SELECT id FROM exams WHERE subject_id = ?", (subject_id,)).fetchall()
        for eid in exam_ids:
            db_execute(conn, "DELETE FROM questions WHERE exam_id = ?", (eid['id'],))
            db_execute(conn, "DELETE FROM results WHERE exam_id = ?", (eid['id'],))
            db_execute(conn, "DELETE FROM exam_access_requests WHERE exam_id = ?", (eid['id'],))
            db_execute(conn, "DELETE FROM exam_access_keys WHERE exam_id = ?", (eid['id'],))
        db_execute(conn, "DELETE FROM exams WHERE subject_id = ?", (subject_id,))
        db_execute(conn, "DELETE FROM subjects WHERE id = ?", (subject_id,))
        conn.commit()
        flash(f'Subject "{subject["subject_name"]}" and all its data have been permanently deleted.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting subject: {str(e)}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('view_all_subjects'))

@app.route('/admin/view_all_students')
@login_required
@admin_required
def view_all_students():
    conn = get_db()
    students = db_execute(conn, "SELECT * FROM users WHERE role = 'student'").fetchall()
    allowed = db_execute(conn,
        "SELECT a.*, s.subject_name FROM allowed_students a JOIN subjects s ON a.subject_id = s.id"
    ).fetchall()
    conn.close()
    return render_template('view_all_students.html', students=students, allowed=allowed)


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
