# app.py
import os
import sqlite3
import pandas as pd
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
import bcrypt
from datetime import datetime
from dotenv import load_dotenv

from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

# Create Claude client
claude_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# Load environment variables from .env file (for local development)
load_dotenv()

# --- OpenAI ---
#import openai
#openai.api_key = os.getenv('OPENAI_API_KEY')   # Make sure this is set in .env

#from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# Create the OpenAI client (once)
 

# Optional: if you still need Gemini (commented out)
# from google import genai
# client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database initialization
DB_PATH = 'examination.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        student_number INTEGER UNIQUE,
        is_verified INTEGER DEFAULT 0
    )''')
    
    # Subjects table
    c.execute('''CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_name TEXT NOT NULL,
        teacher_id INTEGER NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES users (id)
    )''')
    
    # Allowed students table
    c.execute('''CREATE TABLE IF NOT EXISTS allowed_students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_number INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        subject_id INTEGER NOT NULL,
        UNIQUE(student_number, subject_id),
        FOREIGN KEY (subject_id) REFERENCES subjects (id)
    )''')
    
    # Exams table
    c.execute('''CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        duration INTEGER NOT NULL,
        FOREIGN KEY (subject_id) REFERENCES subjects (id)
    )''')
    
    # Questions table
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
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
    
    # Results table
    c.execute('''CREATE TABLE IF NOT EXISTS results (
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
    
    # Insert default teacher if not exists
    teacher_email = "teacher@example.com"
    c.execute("SELECT id FROM users WHERE email = ?", (teacher_email,))
    if not c.fetchone():
        hashed = bcrypt.hashpw("teacher123".encode('utf-8'), bcrypt.gensalt())
        c.execute("INSERT INTO users (name, email, password, role, is_verified) VALUES (?, ?, ?, ?, ?)",
                  ("Default Teacher", teacher_email, hashed, "teacher", 1))
    
    # Insert default admin if not exists
    admin_email = "admin@example.com"
    c.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    if not c.fetchone():
        hashed_admin = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
        c.execute("INSERT INTO users (name, email, password, role, is_verified) VALUES (?, ?, ?, ?, ?)",
                  ("System Admin", admin_email, hashed_admin, "admin", 1))
    
    # Insert default subject "BSCS" if none exists
    c.execute("SELECT COUNT(*) FROM subjects")
    if c.fetchone()[0] == 0:
        teacher_id = c.execute("SELECT id FROM users WHERE role = 'teacher' LIMIT 1").fetchone()[0]
        c.execute("INSERT INTO subjects (subject_name, teacher_id) VALUES (?, ?)", ("BSCS", teacher_id))
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Get list of subjects for dropdown
    conn = get_db()
    subjects = conn.execute("SELECT id, subject_name FROM subjects").fetchall()
    conn.close()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        student_number = request.form.get('student_number')
        teacher_code = request.form.get('teacher_code')
        subject_id = request.form.get('subject_id')

        # Basic field validation
        if not name or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('register.html', subjects=subjects)

        # Password minimum length (6 characters)
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html', subjects=subjects)

        if role == 'teacher':
            if teacher_code != 'ADMIN123':
                flash('Invalid teacher registration code', 'danger')
                return render_template('register.html', subjects=subjects)
            student_number = None
            is_verified = 1
        else:  # student
            # Validate student number
            if not student_number or not student_number.strip():
                flash('Student number is required', 'danger')
                return render_template('register.html', subjects=subjects)
            student_number_clean = student_number.replace('-', '').strip()
            if not student_number_clean.isdigit():
                flash('Student number must contain only numbers and dashes', 'danger')
                return render_template('register.html', subjects=subjects)
            student_number = int(student_number_clean)

            # Check duplicate student number
            conn = get_db()
            existing = conn.execute("SELECT id FROM users WHERE student_number = ?", (student_number,)).fetchone()
            if existing:
                flash('Student number already registered', 'danger')
                conn.close()
                return render_template('register.html', subjects=subjects)
            conn.close()

            if not subject_id:
                flash('Please select a subject', 'danger')
                return render_template('register.html', subjects=subjects)

            is_verified = 1  # Auto-verified for students

        # Hash password
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        try:
            conn = get_db()
            # Insert user
            cursor = conn.execute("""
                INSERT INTO users (name, email, password, role, student_number, is_verified)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, hashed, role, student_number, is_verified))
            user_id = cursor.lastrowid

            # If student, add to allowed_students for chosen subject
            if role == 'student':
                conn.execute("""
                    INSERT OR IGNORE INTO allowed_students (student_number, student_name, subject_id)
                    VALUES (?, ?, ?)
                """, (student_number, name, subject_id))

            conn.commit()
            conn.close()
            flash('Registration successful! You can now login and take exams.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists', 'danger')
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
            user = conn.execute("SELECT * FROM users WHERE student_number = ?", (int(login_id),)).fetchone()
        else:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (login_id,)).fetchone()
        conn.close()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
            if user['is_verified'] == 0:
                flash('Your account is pending verification. Please contact teacher.', 'warning')
                return redirect(url_for('login'))
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            session['student_number'] = user['student_number']
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email/student number or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

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

# ==================== TEACHER ROUTES ====================
@app.route('/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    exams = conn.execute("SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE s.teacher_id = ?", 
                        (session['user_id'],)).fetchall()
    pending_verifications = conn.execute("SELECT * FROM users WHERE role = 'student' AND is_verified = 0").fetchall()
    conn.close()
    return render_template('teacher_dashboard.html', subjects=subjects, exams=exams, pending_verifications=pending_verifications)

@app.route('/teacher/create_subject', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def create_subject():
    if request.method == 'POST':
        subject_name = request.form['subject_name']
        if subject_name:
            conn = get_db()
            conn.execute("INSERT INTO subjects (subject_name, teacher_id) VALUES (?, ?)", 
                        (subject_name, session['user_id']))
            conn.commit()
            conn.close()
            flash('Subject created successfully', 'success')
            return redirect(url_for('teacher_dashboard'))
        flash('Subject name required', 'danger')
    return render_template('create_subject.html')

@app.route('/teacher/create_exam', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def create_exam():
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()
    
    if request.method == 'POST':
        subject_id = request.form['subject_id']
        title = request.form['title']
        duration = request.form['duration']
        
        if not title or not duration or not subject_id:
            flash('All fields required', 'danger')
            return redirect(url_for('create_exam'))
        
        conn = get_db()
        cursor = conn.execute("INSERT INTO exams (subject_id, title, duration) VALUES (?, ?, ?)",
                             (subject_id, title, duration))
        exam_id = cursor.lastrowid
        conn.commit()
        conn.close()
        flash('Exam created! Now add questions.', 'success')
        return redirect(url_for('add_questions', exam_id=exam_id))
    
    return render_template('create_exam.html', subjects=subjects)

@app.route('/teacher/add_questions/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def add_questions(exam_id):
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if not exam:
        flash('Exam not found', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if request.method == 'POST':
        question = request.form['question']
        option_a = request.form['option_a']
        option_b = request.form['option_b']
        option_c = request.form['option_c']
        option_d = request.form['option_d']
        correct_answer = request.form['correct_answer']
        
        conn.execute("INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (exam_id, question, option_a, option_b, option_c, option_d, correct_answer))
        conn.commit()
        flash('Question added successfully', 'success')
        conn.close()
        return redirect(url_for('add_questions', exam_id=exam_id))
    
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    conn.close()
    return render_template('add_questions.html', exam=exam, questions=questions)

# Auto-generate questions using OpenAI (GPT-3.5 Turbo)
@app.route('/teacher/auto_generate_questions/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def auto_generate_questions(exam_id):
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()
    
    if not exam:
        flash('Exam not found', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    if request.method == 'POST':
        topic = request.form['topic']
        num_questions = int(request.form['num_questions'])
        
        if num_questions < 1 or num_questions > 20:
            flash('Number of questions must be between 1 and 20.', 'danger')
            return redirect(url_for('auto_generate_questions', exam_id=exam_id))
        
        try:
            prompt = f"""Generate {num_questions} multiple-choice questions about "{topic}". 
Each question must have exactly four options (A, B, C, D) and one correct answer.
Format each question exactly as follows:

Question: [Your question text]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
Answer: [A/B/C/D]

Separate each question with a blank line.
Do not include any extra text beyond the questions."""

            # Claude API call (using claude-3-haiku-20240307 – mura, paspas)
            response = claude_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            generated_text = response.content[0].text

            # Pareho ra ang pag-parse sa mga pangutana
            questions_blocks = generated_text.strip().split('\n\n')
            saved_count = 0
            
            conn = get_db()
            for block in questions_blocks:
                lines = block.strip().split('\n')
                if len(lines) < 6:
                    continue
                question_line = lines[0].replace('Question:', '').strip()
                option_a = lines[1].replace('A)', '').strip()
                option_b = lines[2].replace('B)', '').strip()
                option_c = lines[3].replace('C)', '').strip()
                option_d = lines[4].replace('D)', '').strip()
                answer_line = lines[5].replace('Answer:', '').strip().upper()
                if answer_line not in ['A', 'B', 'C', 'D']:
                    continue
                conn.execute("""
                    INSERT INTO questions (exam_id, question, option_a, option_b, option_c, option_d, correct_answer)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (exam_id, question_line, option_a, option_b, option_c, option_d, answer_line))
                saved_count += 1
            
            conn.commit()
            conn.close()
            flash(f'Successfully generated and saved {saved_count} questions!', 'success')
        except Exception as e:
            flash(f'Error generating questions: {str(e)}', 'danger')
        
        return redirect(url_for('add_questions', exam_id=exam_id))
    
    return render_template('auto_generate.html', exam=exam)

@app.route('/teacher/upload_students', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def upload_students():
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    conn.close()
    
    if request.method == 'POST':
        subject_id = request.form['subject_id']
        if 'file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('upload_students'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'danger')
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
                    flash('File must contain student_number and student_name columns', 'danger')
                    return redirect(url_for('upload_students'))
                
                conn = get_db()
                count = 0
                for _, row in df.iterrows():
                    student_number = int(row['student_number'])
                    student_name = str(row['student_name'])
                    try:
                        conn.execute("INSERT OR REPLACE INTO allowed_students (student_number, student_name, subject_id) VALUES (?, ?, ?)",
                                    (student_number, student_name, subject_id))
                        count += 1
                    except:
                        pass
                conn.commit()
                conn.close()
                flash(f'Successfully uploaded {count} students', 'success')
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
            finally:
                os.remove(filepath)
        else:
            flash('Invalid file type. Upload CSV or Excel', 'danger')
        return redirect(url_for('upload_students'))
    
    return render_template('upload_students.html', subjects=subjects)

@app.route('/teacher/view_allowed_students')
@login_required
@role_required('teacher')
def view_allowed_students():
    conn = get_db()
    subjects = conn.execute("SELECT * FROM subjects WHERE teacher_id = ?", (session['user_id'],)).fetchall()
    selected_subject = request.args.get('subject_id')
    students = []
    if selected_subject:
        students = conn.execute("SELECT * FROM allowed_students WHERE subject_id = ?", (selected_subject,)).fetchall()
    conn.close()
    return render_template('view_allowed_students.html', subjects=subjects, students=students, selected_subject=selected_subject)

@app.route('/teacher/verify_student/<int:user_id>')
@login_required
@role_required('teacher')
def verify_student(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Student verified successfully', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/view_results')
@login_required
@role_required('teacher')
def view_results():
    conn = get_db()
    exams = conn.execute("SELECT e.*, s.subject_name FROM exams e JOIN subjects s ON e.subject_id = s.id WHERE s.teacher_id = ?", 
                        (session['user_id'],)).fetchall()
    results = []
    exam_id = request.args.get('exam_id')
    if exam_id:
        results = conn.execute("""
            SELECT r.*, u.name, u.student_number 
            FROM results r 
            JOIN users u ON r.student_id = u.id 
            WHERE r.exam_id = ?
        """, (exam_id,)).fetchall()
    conn.close()
    return render_template('view_results.html', exams=exams, results=results, selected_exam=exam_id)

# ==================== STUDENT ROUTES ====================
@app.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    student_number = session['student_number']
    conn = get_db()
    allowed_subjects = conn.execute("""
        SELECT DISTINCT s.id, s.subject_name 
        FROM allowed_students a
        JOIN subjects s ON a.subject_id = s.id
        WHERE a.student_number = ?
    """, (student_number,)).fetchall()
    
    exams = []
    for subject in allowed_subjects:
        subject_exams = conn.execute("""
            SELECT e.*, s.subject_name, 
                   CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END as taken
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            LEFT JOIN results r ON r.exam_id = e.id AND r.student_id = ?
            WHERE e.subject_id = ?
        """, (session['user_id'], subject['id'])).fetchall()
        exams.extend(subject_exams)
    
    conn.close()
    return render_template('student_dashboard.html', exams=exams)

@app.route('/student/take_exam/<int:exam_id>')
@login_required
@role_required('student')
def take_exam(exam_id):
    student_number = session['student_number']
    conn = get_db()
    
    exam = conn.execute("""
        SELECT e.*, s.id as subject_id 
        FROM exams e 
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.id = ?
    """, (exam_id,)).fetchone()
    
    if not exam:
        flash('Exam not found', 'danger')
        return redirect(url_for('student_dashboard'))
    
    # Check authorization
    allowed = conn.execute("""
        SELECT id FROM allowed_students 
        WHERE student_number = ? AND subject_id = ?
    """, (student_number, exam['subject_id'])).fetchone()
    if not allowed:
        flash('You are not authorized to take this exam', 'danger')
        return redirect(url_for('student_dashboard'))
    
    taken = conn.execute("SELECT id FROM results WHERE student_id = ? AND exam_id = ?",
                        (session['user_id'], exam_id)).fetchone()
    if taken:
        flash('You have already taken this exam', 'warning')
        return redirect(url_for('student_dashboard'))
    
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    if len(questions) == 0:
        flash('Exam has no questions', 'warning')
        return redirect(url_for('student_dashboard'))
    
    conn.close()
    return render_template('take_exam.html', exam=exam, questions=questions)

@app.route('/student/submit_exam/<int:exam_id>', methods=['POST'])
@login_required
@role_required('student')
def submit_exam(exam_id):
    conn = get_db()
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    
    score = 0
    for q in questions:
        answer = request.form.get(f'q_{q["id"]}')
        if answer and answer.upper() == q["correct_answer"].upper():
            score += 1
    
    total = len(questions)
    passing_score = total // 2
    
    try:
        conn.execute("INSERT INTO results (student_id, exam_id, score, total_questions) VALUES (?, ?, ?, ?)",
                    (session['user_id'], exam_id, score, total))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        flash('You have already submitted this exam', 'warning')
        return redirect(url_for('student_dashboard'))
    
    conn.close()
    
    if score >= passing_score:
        prediction = "Likely to PASS Final"
        prediction_class = "success"
    else:
        prediction = "Needs Improvement"
        prediction_class = "danger"
    
    return render_template('result.html', score=score, total=total, prediction=prediction, prediction_class=prediction_class)

# ==================== ADMIN ROUTES ====================
@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0]
    total_teachers = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher'").fetchone()[0]
    total_subjects = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    total_exams = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0]
    total_results = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    conn.close()
    return render_template('admin_dashboard.html', 
                         total_students=total_students,
                         total_teachers=total_teachers,
                         total_subjects=total_subjects,
                         total_exams=total_exams,
                         total_results=total_results)

@app.route('/admin/manage_teachers')
@login_required
@admin_required
def manage_teachers():
    conn = get_db()
    teachers = conn.execute("SELECT * FROM users WHERE role = 'teacher'").fetchall()
    conn.close()
    return render_template('manage_teachers.html', teachers=teachers)

@app.route('/admin/delete_teacher/<int:user_id>')
@login_required
@admin_required
def delete_teacher(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ? AND role = 'teacher'", (user_id,))
    conn.commit()
    conn.close()
    flash('Teacher deleted', 'success')
    return redirect(url_for('manage_teachers'))

@app.route('/admin/view_all_subjects')
@login_required
@admin_required
def view_all_subjects():
    conn = get_db()
    subjects = conn.execute("""
        SELECT s.*, u.name as teacher_name 
        FROM subjects s 
        JOIN users u ON s.teacher_id = u.id
    """).fetchall()
    conn.close()
    return render_template('view_all_subjects.html', subjects=subjects)

@app.route('/admin/delete_subject/<int:subject_id>')
@login_required
@admin_required
def delete_subject(subject_id):
    conn = get_db()
    
    # Check if subject exists
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    if not subject:
        flash('Subject not found', 'danger')
        return redirect(url_for('view_all_subjects'))
    
    try:
        # 1. Delete allowed_students entries for this subject
        conn.execute("DELETE FROM allowed_students WHERE subject_id = ?", (subject_id,))
        
        # 2. Delete questions of exams belonging to this subject
        # First get all exam ids for this subject
        exam_ids = conn.execute("SELECT id FROM exams WHERE subject_id = ?", (subject_id,)).fetchall()
        for exam_id_row in exam_ids:
            exam_id = exam_id_row['id']
            conn.execute("DELETE FROM questions WHERE exam_id = ?", (exam_id,))
        
        # 3. Delete exams of this subject
        conn.execute("DELETE FROM exams WHERE subject_id = ?", (subject_id,))
        
        # 4. Delete the subject itself
        conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        
        conn.commit()
        conn.close()
        flash(f'Subject "{subject["subject_name"]}" and all its associated data (exams, questions, enrollments) have been permanently deleted.', 'success')
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f'Error deleting subject: {str(e)}', 'danger')
    
    return redirect(url_for('view_all_subjects'))

@app.route('/admin/view_all_students')
@login_required
@admin_required
def view_all_students():
    conn = get_db()
    students = conn.execute("SELECT * FROM users WHERE role = 'student'").fetchall()
    allowed = conn.execute("""
        SELECT a.*, s.subject_name 
        FROM allowed_students a
        JOIN subjects s ON a.subject_id = s.id
    """).fetchall()
    conn.close()
    return render_template('view_all_students.html', students=students, allowed=allowed)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)