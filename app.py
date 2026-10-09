import os
import sqlite3
import json
import re
import secrets
from datetime import datetime, date, timedelta
from io import BytesIO
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file, g, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'attendance.db'))
# Ensure parent directory of DB exists if custom path provided (e.g. /data)
_db_dir = os.path.dirname(DB_PATH)
if _db_dir and not os.path.exists(_db_dir):
    try:
        os.makedirs(_db_dir, exist_ok=True)
    except Exception:
        pass


def get_db():
    db_path = app.config.get('DATABASE', DB_PATH)
    if 'db' not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(target_path=None):
    db_path = target_path or app.config.get('DATABASE', DB_PATH)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        
        # 1. Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                avatar_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. User sessions table (for multi-device persistent sessions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 3. Password reset tokens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 4. Settings table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                required_attendance REAL DEFAULT 75.0,
                warning_threshold REAL DEFAULT 75.0,
                critical_threshold REAL DEFAULT 65.0,
                theme TEXT DEFAULT 'system',
                college_name TEXT DEFAULT 'College of Engineering & Technology',
                student_name TEXT DEFAULT 'Student',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 5. Subjects table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                code TEXT NOT NULL,
                faculty TEXT,
                room TEXT,
                color TEXT DEFAULT '#3B82F6',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 6. Timetable table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timetable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                day TEXT NOT NULL,
                period_number INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                room TEXT,
                faculty TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            )
        ''')

        # 7. Attendance records table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT NOT NULL,
                period_id INTEGER,
                subject_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (period_id) REFERENCES timetable(id) ON DELETE SET NULL,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            )
        ''')

        # 8. Period slots (master periods) table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS period_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_number INTEGER NOT NULL,
                label TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # 9. Holidays table (per-user)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, date)
            )
        ''')

        # Run safe migrations for existing tables if user_id column doesn't exist
        for table in ['subjects', 'timetable', 'attendance', 'settings', 'period_slots', 'holidays']:
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [col[1] for col in cursor.fetchall()]
                if 'user_id' not in cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
            except Exception:
                pass

        try:
            cursor.execute("ALTER TABLE settings ADD COLUMN period_slots_initialized INTEGER DEFAULT 0")
        except Exception:
            pass

        # Check if settings table has legacy CHECK constraint 'id = 1'
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='settings'")
        settings_sql = cursor.fetchone()
        if settings_sql and 'id = 1' in (settings_sql[0] or ''):
            cursor.execute('''
                CREATE TABLE settings_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    required_attendance REAL DEFAULT 75.0,
                    warning_threshold REAL DEFAULT 75.0,
                    critical_threshold REAL DEFAULT 65.0,
                    theme TEXT DEFAULT 'system',
                    college_name TEXT DEFAULT 'College of Engineering & Technology',
                    student_name TEXT DEFAULT 'Student',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO settings_new (user_id, required_attendance, warning_threshold, critical_threshold, theme, college_name, student_name)
                    SELECT user_id, required_attendance, warning_threshold, critical_threshold, theme, college_name, student_name FROM settings
                ''')
            except Exception:
                pass
            cursor.execute("DROP TABLE settings")
            cursor.execute("ALTER TABLE settings_new RENAME TO settings")

        # Indices for optimal multi-tenant query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timetable_user ON timetable(user_id, day)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_user_date ON attendance(user_id, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attendance_user_subject ON attendance(user_id, subject_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_holidays_user_date ON holidays(user_id, date)')

        conn.commit()

# --- Auth Helpers & Middleware ---

def get_token_from_request():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip()
    token_param = request.args.get('token')
    if token_param:
        return token_param.strip()
    return request.cookies.get('session_token')

def get_authenticated_user():
    token = get_token_from_request()
    if not token:
        return None
    db = get_db()
    row = db.execute('''
        SELECT s.user_id, s.expires_at, u.id, u.name, u.email, u.avatar_url, u.created_at
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    ''', (token,)).fetchone()
    
    if not row:
        return None

    # Check expiration
    try:
        exp = datetime.fromisoformat(row['expires_at'])
        if datetime.now() > exp:
            db.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            db.commit()
            return None
    except Exception:
        pass

    return dict(row)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'Authentication required', 'code': 'UNAUTHORIZED'}), 401
        g.current_user = user
        g.user_id = user['id']
        return f(*args, **kwargs)
    return decorated

def get_current_settings(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if row:
        return dict(row)
    
    # Initialize default settings for this user
    user_row = db.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    student_name = user_row['name'] if user_row else 'Student'
    db.execute('''
        INSERT OR IGNORE INTO settings (user_id, required_attendance, warning_threshold, critical_threshold, theme, student_name)
        VALUES (?, 75.0, 75.0, 65.0, 'system', ?)
    ''', (user_id, student_name))
    db.commit()

    return {
        'user_id': user_id,
        'required_attendance': 75.0,
        'warning_threshold': 75.0,
        'critical_threshold': 65.0,
        'theme': 'system',
        'college_name': 'College of Engineering & Technology',
        'student_name': student_name
    }

def calculate_stats(attended, total, required=75.0):
    if total == 0:
        return {
            'attended': 0,
            'absent': 0,
            'total': 0,
            'percentage': 0.0,
            'can_miss': 0,
            'need_to_attend': 0,
            'status': 'Good'
        }
    
    pct = round((attended / total) * 100, 2)
    r = required / 100.0

    if pct >= required and r > 0:
        can_miss = max(0, int((attended / r) - total))
    else:
        can_miss = 0

    if pct < required:
        if r >= 1.0:
            need_to_attend = -1  # Impossible if missed any class
        else:
            diff = (r * total) - attended
            need_to_attend = max(0, int(round((diff / (1.0 - r)) + 0.49999999)))
    else:
        need_to_attend = 0

    return {
        'attended': attended,
        'absent': total - attended,
        'total': total,
        'percentage': pct,
        'can_miss': can_miss,
        'need_to_attend': need_to_attend
    }

# --- Main App Route ---

@app.route('/')
def index():
    return render_template('index.html')

# ================= AUTHENTICATION ENDPOINTS =================

@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    db = get_db()
    data = request.json or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'error': 'A valid email address is required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    # Check for existing user
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({'error': 'An account with this email already exists'}), 409

    # Hash password & create user
    pwd_hash = generate_password_hash(password)
    cur = db.execute('''
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
    ''', (name, email, pwd_hash))
    user_id = cur.lastrowid

    # Create initial settings for user
    db.execute('''
        INSERT INTO settings (user_id, student_name, required_attendance, warning_threshold, critical_threshold)
        VALUES (?, ?, 75.0, 75.0, 65.0)
    ''', (user_id, name))

    # Generate session token valid for 30 days
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()
    db.execute('''
        INSERT INTO user_sessions (user_id, token, expires_at)
        VALUES (?, ?, ?)
    ''', (user_id, token, expires_at))
    db.commit()

    resp = make_response(jsonify({
        'success': True,
        'message': 'Account created successfully!',
        'user': {
            'id': user_id,
            'name': name,
            'email': email
        },
        'token': token
    }), 201)
    resp.set_cookie('session_token', token, max_age=30*86400, httponly=True, samesite='Lax')
    return resp

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    db = get_db()
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid email or password'}), 401

    # Generate session token valid for 30 days
    token = secrets.token_hex(32)
    expires_at = (datetime.now() + timedelta(days=30)).isoformat()
    db.execute('''
        INSERT INTO user_sessions (user_id, token, expires_at)
        VALUES (?, ?, ?)
    ''', (user['id'], token, expires_at))
    db.commit()

    resp = make_response(jsonify({
        'success': True,
        'message': 'Logged in successfully!',
        'user': {
            'id': user['id'],
            'name': user['name'],
            'email': user['email'],
            'created_at': user['created_at']
        },
        'token': token
    }))
    resp.set_cookie('session_token', token, max_age=30*86400, httponly=True, samesite='Lax')
    return resp

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    token = get_token_from_request()
    if token:
        db = get_db()
        db.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        db.commit()

    resp = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}))
    resp.delete_cookie('session_token')
    return resp

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_authenticated_user()
    if not user:
        # Check if there is unmigrated local data in db
        db = get_db()
        unassigned_subjects = db.execute("SELECT COUNT(*) FROM subjects WHERE user_id IS NULL").fetchone()[0]
        return jsonify({
            'authenticated': False,
            'has_unassigned_data': unassigned_subjects > 0
        })

    db = get_db()
    unassigned_subjects = db.execute("SELECT COUNT(*) FROM subjects WHERE user_id IS NULL").fetchone()[0]

    return jsonify({
        'authenticated': True,
        'user': {
            'id': user['id'],
            'name': user['name'],
            'email': user['email'],
            'created_at': user['created_at']
        },
        'has_unassigned_data': unassigned_subjects > 0
    })

@app.route('/api/auth/forgot-password', methods=['POST'])
def auth_forgot_password():
    db = get_db()
    data = request.json or {}
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        # Return generic success to prevent email enumeration
        return jsonify({
            'success': True,
            'message': 'If this email is registered, a password reset token has been generated.'
        })

    token = secrets.token_urlsafe(16)
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()

    db.execute('''
        INSERT INTO password_resets (user_id, token, expires_at)
        VALUES (?, ?, ?)
    ''', (user['id'], token, expires_at))
    db.commit()

    return jsonify({
        'success': True,
        'message': 'Password reset token generated successfully.',
        'reset_token': token  # Returned so user can test the reset workflow immediately
    })

@app.route('/api/auth/reset-password', methods=['POST'])
def auth_reset_password():
    db = get_db()
    data = request.json or {}
    token = data.get('token', '').strip()
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not token or not new_password:
        return jsonify({'error': 'Token and new password are required'}), 400
    if len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if new_password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    record = db.execute('''
        SELECT * FROM password_resets WHERE token = ? AND used = 0
    ''', (token,)).fetchone()

    if not record:
        return jsonify({'error': 'Invalid or expired reset token'}), 400

    try:
        exp = datetime.fromisoformat(record['expires_at'])
        if datetime.now() > exp:
            return jsonify({'error': 'Reset token has expired'}), 400
    except Exception:
        pass

    # Update password
    pwd_hash = generate_password_hash(new_password)
    db.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (pwd_hash, record['user_id']))
    db.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (record['id'],))
    # Invalidate all prior sessions
    db.execute("DELETE FROM user_sessions WHERE user_id = ?", (record['user_id'],))
    db.commit()

    return jsonify({'success': True, 'message': 'Password updated successfully! Please log in.'})

# ================= DATA MIGRATION & OFFLINE SYNC =================

@app.route('/api/auth/migrate-local', methods=['POST'])
@require_auth
def auth_migrate_local():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    import_existing = data.get('import_existing', True)

    if not import_existing:
        # User chose "Start Fresh"
        return jsonify({'success': True, 'message': 'Started fresh with empty cloud account.'})

    # Migrate any unassigned database records to this user
    cur_sub = db.execute("UPDATE subjects SET user_id = ? WHERE user_id IS NULL", (user_id,))
    cur_tt = db.execute("UPDATE timetable SET user_id = ? WHERE user_id IS NULL", (user_id,))
    cur_att = db.execute("UPDATE attendance SET user_id = ? WHERE user_id IS NULL", (user_id,))
    
    # Or import payload from localStorage
    client_subjects = data.get('subjects', [])
    for s in client_subjects:
        existing = db.execute("SELECT id FROM subjects WHERE user_id = ? AND code = ?", (user_id, s.get('code'))).fetchone()
        if not existing:
            db.execute('''
                INSERT INTO subjects (user_id, name, code, faculty, room, color)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, s.get('name'), s.get('code'), s.get('faculty', ''), s.get('room', ''), s.get('color', '#3B82F6')))

    db.commit()
    return jsonify({
        'success': True,
        'message': 'Local data successfully migrated to your cloud account!',
        'migrated': {
            'subjects': cur_sub.rowcount,
            'timetable': cur_tt.rowcount,
            'attendance': cur_att.rowcount
        }
    })

@app.route('/api/attendance/sync-offline', methods=['POST'])
@require_auth
def sync_offline_attendance():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    actions = data.get('actions', [])

    synced_count = 0
    for act in actions:
        att_date = act.get('date')
        period_id = act.get('period_id')
        subject_id = act.get('subject_id')
        status = act.get('status')
        notes = act.get('notes', '')

        if not att_date or not subject_id or status not in ('Present', 'Absent'):
            continue

        if period_id:
            existing = db.execute('''
                SELECT id FROM attendance WHERE user_id = ? AND date = ? AND period_id = ?
            ''', (user_id, att_date, period_id)).fetchone()
            if existing:
                db.execute('''
                    UPDATE attendance
                    SET status = ?, subject_id = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                ''', (status, subject_id, notes, existing['id'], user_id))
                synced_count += 1
                continue

        db.execute('''
            INSERT INTO attendance (user_id, date, period_id, subject_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, att_date, period_id, subject_id, status, notes))
        synced_count += 1

    db.commit()
    return jsonify({'success': True, 'synced_count': synced_count})

# ================= USER-PROTECTED CORE APIS =================

@app.route('/api/settings', methods=['GET', 'POST'])
@require_auth
def handle_settings():
    db = get_db()
    user_id = g.user_id

    if request.method == 'POST':
        data = request.json or {}
        req_att = float(data.get('required_attendance', 75.0))
        warn_th = float(data.get('warning_threshold', 75.0))
        crit_th = float(data.get('critical_threshold', 65.0))
        theme = data.get('theme', 'system')
        college_name = data.get('college_name', 'College of Engineering & Technology')
        student_name = data.get('student_name', g.current_user['name'])

        db.execute('''
            INSERT INTO settings (user_id, required_attendance, warning_threshold, critical_threshold, theme, college_name, student_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                required_attendance = excluded.required_attendance,
                warning_threshold = excluded.warning_threshold,
                critical_threshold = excluded.critical_threshold,
                theme = excluded.theme,
                college_name = excluded.college_name,
                student_name = excluded.student_name,
                updated_at = CURRENT_TIMESTAMP
        ''', (user_id, req_att, warn_th, crit_th, theme, college_name, student_name))
        db.commit()
        return jsonify({'success': True, 'settings': get_current_settings(user_id)})
    
    return jsonify(get_current_settings(user_id))

@app.route('/api/subjects', methods=['GET', 'POST'])
@require_auth
def handle_subjects():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)
    req_att = settings['required_attendance']
    warn_th = settings['warning_threshold']
    crit_th = settings['critical_threshold']

    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        faculty = data.get('faculty', '').strip()
        room = data.get('room', '').strip()
        color = data.get('color', '#3B82F6').strip()

        if not name or not code:
            return jsonify({'error': 'Subject name and code are required'}), 400

        cursor = db.execute('''
            INSERT INTO subjects (user_id, name, code, faculty, room, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, name, code, faculty, room, color))
        db.commit()
        new_id = cursor.lastrowid
        row = db.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (new_id, user_id)).fetchone()
        return jsonify(dict(row)), 201

    subjects = db.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name ASC", (user_id,)).fetchall()
    result = []
    for s in subjects:
        s_dict = dict(s)
        att_row = db.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
            FROM attendance a
            WHERE a.subject_id = ? AND a.user_id = ?
              AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        ''', (s['id'], user_id, user_id)).fetchone()
        
        total = att_row['total'] or 0
        attended = att_row['attended'] or 0
        stats = calculate_stats(attended, total, req_att)
        
        if total == 0:
            status_badge = 'Good'
        elif stats['percentage'] >= warn_th:
            status_badge = 'Good'
        elif stats['percentage'] >= crit_th:
            status_badge = 'Warning'
        else:
            status_badge = 'Critical'

        s_dict.update(stats)
        s_dict['status_badge'] = status_badge
        result.append(s_dict)

    return jsonify(result)

@app.route('/api/subjects/<int:sub_id>', methods=['GET', 'PUT', 'DELETE'])
@require_auth
def handle_single_subject(sub_id):
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)
    
    # Verify ownership
    sub = db.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sub_id, user_id)).fetchone()
    if not sub:
        return jsonify({'error': 'Subject not found'}), 404

    if request.method == 'DELETE':
        db.execute("DELETE FROM subjects WHERE id = ? AND user_id = ?", (sub_id, user_id))
        db.commit()
        return jsonify({'success': True, 'id': sub_id})
    
    if request.method == 'PUT':
        data = request.json or {}
        name = data.get('name', '').strip()
        code = data.get('code', '').strip().upper()
        faculty = data.get('faculty', '').strip()
        room = data.get('room', '').strip()
        color = data.get('color', '#3B82F6').strip()

        if not name or not code:
            return jsonify({'error': 'Name and code are required'}), 400

        db.execute('''
            UPDATE subjects
            SET name = ?, code = ?, faculty = ?, room = ?, color = ?
            WHERE id = ? AND user_id = ?
        ''', (name, code, faculty, room, color, sub_id, user_id))
        db.commit()
        sub = db.execute("SELECT * FROM subjects WHERE id = ? AND user_id = ?", (sub_id, user_id)).fetchone()

    s_dict = dict(sub)
    att_row = db.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
        FROM attendance a
        WHERE a.subject_id = ? AND a.user_id = ?
          AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
    ''', (sub_id, user_id, user_id)).fetchone()

    total = att_row['total'] or 0
    attended = att_row['attended'] or 0
    stats = calculate_stats(attended, total, settings['required_attendance'])
    
    if total == 0:
        status_badge = 'Good'
    elif stats['percentage'] >= settings['warning_threshold']:
        status_badge = 'Good'
    elif stats['percentage'] >= settings['critical_threshold']:
        status_badge = 'Warning'
    else:
        status_badge = 'Critical'

    s_dict.update(stats)
    s_dict['status_badge'] = status_badge

    monthly_rows = db.execute('''
        SELECT 
            strftime('%Y-%m', a.date) as month,
            COUNT(*) as total,
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
        FROM attendance a
        WHERE a.subject_id = ? AND a.user_id = ?
          AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        GROUP BY month
        ORDER BY month ASC
    ''', (sub_id, user_id, user_id)).fetchall()
    
    s_dict['monthly'] = [
        {
            'month': m['month'],
            'total': m['total'],
            'attended': m['attended'],
            'absent': m['total'] - m['attended'],
            'percentage': round((m['attended'] / m['total']) * 100, 1) if m['total'] > 0 else 0
        } for m in monthly_rows
    ]

    recent_rows = db.execute('''
        SELECT a.id, a.date, a.status, a.notes, t.period_number, t.start_time, t.end_time,
               (CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END) as is_holiday,
               h.name as holiday_name
        FROM attendance a
        LEFT JOIN timetable t ON a.period_id = t.id
        LEFT JOIN holidays h ON a.user_id = h.user_id AND a.date = h.date
        WHERE a.subject_id = ? AND a.user_id = ?
        ORDER BY a.date DESC, t.period_number DESC
        LIMIT 50
    ''', (sub_id, user_id)).fetchall()
    s_dict['history'] = [dict(r) for r in recent_rows]

    return jsonify(s_dict)

def get_user_period_slots(user_id):
    db = get_db()
    rows = db.execute('''
        SELECT * FROM period_slots 
        WHERE user_id = ? 
        ORDER BY slot_number ASC, start_time ASC
    ''', (user_id,)).fetchall()
    
    if rows:
        return [dict(r) for r in rows]

    settings_row = db.execute("SELECT period_slots_initialized FROM settings WHERE user_id = ?", (user_id,)).fetchone()
    if settings_row and settings_row['period_slots_initialized']:
        return []

    existing_tt = db.execute('''
        SELECT DISTINCT period_number, start_time, end_time 
        FROM timetable 
        WHERE user_id = ?
        ORDER BY period_number ASC, start_time ASC
    ''', (user_id,)).fetchall()

    seen_numbers = set()
    if existing_tt:
        for r in existing_tt:
            s_num = r['period_number']
            if s_num not in seen_numbers:
                seen_numbers.add(s_num)
                db.execute('''
                    INSERT INTO period_slots (user_id, slot_number, label, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, s_num, f"Period {s_num}", r['start_time'], r['end_time']))

    default_slots = [
        (1, "Period 1", "09:00", "09:50"),
        (2, "Period 2", "09:50", "10:40"),
        (3, "Period 3", "11:00", "11:50"),
        (4, "Period 4", "11:50", "12:40"),
        (5, "Period 5", "13:30", "14:20"),
        (6, "Period 6", "14:20", "15:10"),
    ]
    for s_num, lbl, s_time, e_time in default_slots:
        if s_num not in seen_numbers:
            db.execute('''
                INSERT INTO period_slots (user_id, slot_number, label, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, s_num, lbl, s_time, e_time))

    db.execute("UPDATE settings SET period_slots_initialized = 1 WHERE user_id = ?", (user_id,))
    db.commit()

    rows = db.execute('''
        SELECT * FROM period_slots 
        WHERE user_id = ? 
        ORDER BY slot_number ASC, start_time ASC
    ''', (user_id,)).fetchall()
    return [dict(r) for r in rows]

@app.route('/api/period-slots', methods=['GET', 'POST'])
@require_auth
def handle_period_slots():
    db = get_db()
    user_id = g.user_id

    if request.method == 'POST':
        data = request.json or {}
        start_time = data.get('start_time', '').strip()
        end_time = data.get('end_time', '').strip()
        label = data.get('label', '').strip()

        if not start_time or not end_time:
            return jsonify({'error': 'Start time and end time are required'}), 400

        raw_num = data.get('slot_number')
        if raw_num is not None and str(raw_num).strip().isdigit():
            slot_number = int(raw_num)
        else:
            max_num = db.execute("SELECT COALESCE(MAX(slot_number), 0) FROM period_slots WHERE user_id = ?", (user_id,)).fetchone()[0]
            slot_number = max_num + 1

        if not label:
            label = f"Period {slot_number}"

        cursor = db.execute('''
            INSERT INTO period_slots (user_id, slot_number, label, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, slot_number, label, start_time, end_time))
        db.execute("UPDATE settings SET period_slots_initialized = 1 WHERE user_id = ?", (user_id,))
        db.commit()

        new_slot = db.execute("SELECT * FROM period_slots WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify({'id': cursor.lastrowid, 'success': True, 'slot': dict(new_slot)}), 201

    slots = get_user_period_slots(user_id)
    return jsonify(slots)

@app.route('/api/period-slots/<int:slot_id>', methods=['PUT', 'DELETE'])
@require_auth
def handle_single_period_slot(slot_id):
    db = get_db()
    user_id = g.user_id

    existing = db.execute("SELECT * FROM period_slots WHERE id = ? AND user_id = ?", (slot_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Period slot not found'}), 404

    if request.method == 'DELETE':
        db.execute("DELETE FROM period_slots WHERE id = ? AND user_id = ?", (slot_id, user_id))
        db.commit()
        return jsonify({'success': True, 'id': slot_id})

    data = request.json or {}
    start_time = data.get('start_time', existing['start_time']).strip()
    end_time = data.get('end_time', existing['end_time']).strip()
    label = data.get('label', existing['label']).strip()
    raw_num = data.get('slot_number')
    slot_number = int(raw_num) if raw_num is not None and str(raw_num).strip().isdigit() else existing['slot_number']

    db.execute('''
        UPDATE period_slots
        SET slot_number = ?, label = ?, start_time = ?, end_time = ?
        WHERE id = ? AND user_id = ?
    ''', (slot_number, label, start_time, end_time, slot_id, user_id))
    db.commit()

    updated = db.execute("SELECT * FROM period_slots WHERE id = ?", (slot_id,)).fetchone()
    return jsonify({'success': True, 'slot': dict(updated)})

@app.route('/api/period-slots/reset-defaults', methods=['POST'])
@require_auth
def reset_period_slots():
    db = get_db()
    user_id = g.user_id
    db.execute("DELETE FROM period_slots WHERE user_id = ?", (user_id,))
    default_slots = [
        (1, "Period 1", "09:00", "09:50"),
        (2, "Period 2", "09:50", "10:40"),
        (3, "Period 3", "11:00", "11:50"),
        (4, "Period 4", "11:50", "12:40"),
        (5, "Period 5", "13:30", "14:20"),
        (6, "Period 6", "14:20", "15:10"),
    ]
    for s_num, lbl, s_time, e_time in default_slots:
        db.execute('''
            INSERT INTO period_slots (user_id, slot_number, label, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, s_num, lbl, s_time, e_time))
    db.execute("UPDATE settings SET period_slots_initialized = 1 WHERE user_id = ?", (user_id,))
    db.commit()
    slots = [dict(r) for r in db.execute("SELECT * FROM period_slots WHERE user_id = ? ORDER BY slot_number ASC", (user_id,)).fetchall()]
    return jsonify({'success': True, 'slots': slots})

@app.route('/api/timetable', methods=['GET', 'POST'])
@require_auth
def handle_timetable():
    db = get_db()
    user_id = g.user_id

    if request.method == 'POST':
        data = request.json or {}
        day = data.get('day', '').capitalize()
        period_number = int(data.get('period_number', 1)) if data.get('period_number') else 1
        start_time = data.get('start_time', '').strip()
        end_time = data.get('end_time', '').strip()
        subject_id = int(data.get('subject_id', 0))
        room = data.get('room', '').strip()
        faculty = data.get('faculty', '').strip()

        slot_id = data.get('slot_id')
        if slot_id:
            slot = db.execute("SELECT * FROM period_slots WHERE id = ? AND user_id = ?", (slot_id, user_id)).fetchone()
            if slot:
                if not start_time:
                    start_time = slot['start_time']
                if not end_time:
                    end_time = slot['end_time']
                if not data.get('period_number'):
                    period_number = slot['slot_number']

        # Check subject belongs to user
        sub = db.execute("SELECT id FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id)).fetchone()
        if not sub:
            return jsonify({'error': 'Invalid subject for this user'}), 400

        cursor = db.execute('''
            INSERT INTO timetable (user_id, day, period_number, start_time, end_time, subject_id, room, faculty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, day, period_number, start_time, end_time, subject_id, room, faculty))
        db.commit()
        return jsonify({'id': cursor.lastrowid, 'success': True}), 201

    day_filter = request.args.get('day')
    query = '''
        SELECT t.*, s.name as subject_name, s.code as subject_code, s.color as subject_color,
               COALESCE(t.faculty, s.faculty) as effective_faculty,
               COALESCE(t.room, s.room) as effective_room
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.user_id = ?
    '''
    params = [user_id]
    if day_filter:
        query += ' AND t.day = ?'
        params.append(day_filter.capitalize())
    query += ' ORDER BY CASE t.day ' \
             'WHEN "Monday" THEN 1 ' \
             'WHEN "Tuesday" THEN 2 ' \
             'WHEN "Wednesday" THEN 3 ' \
             'WHEN "Thursday" THEN 4 ' \
             'WHEN "Friday" THEN 5 ' \
             'WHEN "Saturday" THEN 6 ' \
             'ELSE 7 END, t.period_number ASC'

    rows = db.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/timetable/<int:period_id>', methods=['PUT', 'DELETE'])
@require_auth
def handle_single_timetable(period_id):
    db = get_db()
    user_id = g.user_id

    # Verify ownership
    existing = db.execute("SELECT id FROM timetable WHERE id = ? AND user_id = ?", (period_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Period not found'}), 404

    if request.method == 'DELETE':
        db.execute("DELETE FROM timetable WHERE id = ? AND user_id = ?", (period_id, user_id))
        db.commit()
        return jsonify({'success': True, 'id': period_id})

    data = request.json or {}
    day = data.get('day', '').capitalize()
    period_number = int(data.get('period_number', 1))
    start_time = data.get('start_time', '').strip()
    end_time = data.get('end_time', '').strip()
    subject_id = int(data.get('subject_id', 0))
    room = data.get('room', '').strip()
    faculty = data.get('faculty', '').strip()

    db.execute('''
        UPDATE timetable
        SET day = ?, period_number = ?, start_time = ?, end_time = ?,
            subject_id = ?, room = ?, faculty = ?
        WHERE id = ? AND user_id = ?
    ''', (day, period_number, start_time, end_time, subject_id, room, faculty, period_id, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/timetable/reorder', methods=['POST'])
@require_auth
def reorder_timetable():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    ordered_ids = data.get('ordered_ids', [])
    for idx, pid in enumerate(ordered_ids, start=1):
        db.execute("UPDATE timetable SET period_number = ? WHERE id = ? AND user_id = ?", (idx, pid, user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/timetable/duplicate', methods=['POST'])
@require_auth
def duplicate_timetable():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    source_day = data.get('source_day', '').capitalize().strip()

    # Accept either target_days (list) or target_day (string)
    raw_target_days = data.get('target_days')
    if isinstance(raw_target_days, list):
        target_days = [str(d).capitalize().strip() for d in raw_target_days if str(d).strip()]
    else:
        target_day = data.get('target_day', '')
        target_days = [target_day.capitalize().strip()] if target_day else []

    # Valid weekdays
    valid_days = {'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'}
    if source_day not in valid_days:
        return jsonify({'error': f'Invalid source day: "{source_day}". Must be Monday through Saturday.'}), 400

    # Filter out source_day and invalid days from target_days
    target_days = [d for d in target_days if d in valid_days and d != source_day]

    if not target_days:
        return jsonify({'error': 'Please select at least one different target day.'}), 400

    # Ensure source day has periods scheduled
    rows = db.execute("SELECT * FROM timetable WHERE day = ? AND user_id = ? ORDER BY period_number ASC", (source_day, user_id)).fetchall()
    if not rows:
        return jsonify({'error': f'Source day "{source_day}" has no scheduled periods to duplicate.'}), 400

    replace_target = data.get('replace_target', True)

    total_inserted = 0
    for t_day in target_days:
        if replace_target:
            db.execute("DELETE FROM timetable WHERE day = ? AND user_id = ?", (t_day, user_id))
            for r in rows:
                db.execute('''
                    INSERT INTO timetable (user_id, day, period_number, start_time, end_time, subject_id, room, faculty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, t_day, r['period_number'], r['start_time'], r['end_time'], r['subject_id'], r['room'], r['faculty']))
                total_inserted += 1
        else:
            # Append mode: offset period numbers to avoid collision
            max_p = db.execute("SELECT COALESCE(MAX(period_number), 0) FROM timetable WHERE day = ? AND user_id = ?", (t_day, user_id)).fetchone()[0]
            for idx, r in enumerate(rows, start=1):
                db.execute('''
                    INSERT INTO timetable (user_id, day, period_number, start_time, end_time, subject_id, room, faculty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, t_day, max_p + idx, r['start_time'], r['end_time'], r['subject_id'], r['room'], r['faculty']))
                total_inserted += 1

    db.commit()
    return jsonify({
        'success': True,
        'source_day': source_day,
        'target_days': target_days,
        'count': len(rows),
        'total_inserted': total_inserted
    })

@app.route('/api/timetable/clear-day', methods=['POST'])
@require_auth
def clear_timetable_day():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    day = data.get('day', '').capitalize()
    if not day:
        return jsonify({'error': 'Day is required'}), 400
    db.execute("DELETE FROM timetable WHERE day = ? AND user_id = ?", (day, user_id))
    db.commit()
    return jsonify({'success': True, 'day': day})

@app.route('/api/attendance', methods=['GET', 'POST'])
@require_auth
def handle_attendance():
    db = get_db()
    user_id = g.user_id

    if request.method == 'POST':
        data = request.json or {}
        att_date = data.get('date', date.today().isoformat())
        period_id = data.get('period_id')
        subject_id = data.get('subject_id')
        status = data.get('status')
        notes = data.get('notes', '')

        if not subject_id or status not in ('Present', 'Absent'):
            return jsonify({'error': 'Invalid subject or status'}), 400

        # Verify subject belongs to user
        sub = db.execute("SELECT id FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id)).fetchone()
        if not sub:
            return jsonify({'error': 'Unauthorized subject'}), 403

        # Reject attendance marking if date is a designated holiday
        is_holiday = db.execute("SELECT 1 FROM holidays WHERE user_id = ? AND date = ?", (user_id, att_date)).fetchone()
        if is_holiday:
            return jsonify({'error': 'Cannot record attendance: This date is designated as a Holiday.'}), 400

        if period_id:
            existing = db.execute('''
                SELECT id FROM attendance WHERE user_id = ? AND date = ? AND period_id = ?
            ''', (user_id, att_date, period_id)).fetchone()
            if existing:
                db.execute('''
                    UPDATE attendance
                    SET status = ?, subject_id = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                ''', (status, subject_id, notes, existing['id'], user_id))
                db.commit()
                return jsonify({'id': existing['id'], 'action': 'updated', 'status': status})
        
        cursor = db.execute('''
            INSERT INTO attendance (user_id, date, period_id, subject_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, att_date, period_id, subject_id, status, notes))
        db.commit()
        return jsonify({'id': cursor.lastrowid, 'action': 'created', 'status': status}), 201

    date_filter = request.args.get('date')
    subject_filter = request.args.get('subject_id')
    status_filter = request.args.get('status')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    sort_by = request.args.get('sort', 'date')
    order = request.args.get('order', 'DESC').upper()

    # Special handling for "Holiday" status filter
    if status_filter == 'Holiday':
        hol_query = "SELECT * FROM holidays WHERE user_id = ?"
        hol_params = [user_id]
        if date_filter:
            hol_query += " AND date = ?"
            hol_params.append(date_filter)
        if from_date:
            hol_query += " AND date >= ?"
            hol_params.append(from_date)
        if to_date:
            hol_query += " AND date <= ?"
            hol_params.append(to_date)
        hol_query += f" ORDER BY date {order}"
        h_rows = db.execute(hol_query, hol_params).fetchall()
        results = []
        for h in h_rows:
            try:
                day_name = datetime.strptime(h['date'], '%Y-%m-%d').strftime('%A')
            except Exception:
                day_name = ''
            results.append({
                'id': f"hol_{h['id']}",
                'holiday_id': h['id'],
                'date': h['date'],
                'status': 'Holiday',
                'is_holiday': True,
                'subject_name': h['name'] or 'College Holiday',
                'subject_code': 'HOLIDAY',
                'subject_color': '#8B5CF6',
                'period_day': day_name,
                'period_number': '-',
                'start_time': 'All',
                'end_time': 'Day',
                'notes': h['name'] or 'Official Holiday'
            })
        return jsonify(results)

    query = '''
        SELECT a.*, s.name as subject_name, s.code as subject_code, s.color as subject_color,
               t.day as period_day, t.period_number, t.start_time, t.end_time,
               COALESCE(t.faculty, s.faculty) as effective_faculty,
               COALESCE(t.room, s.room) as effective_room,
               (CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END) as is_holiday,
               h.name as holiday_name
        FROM attendance a
        JOIN subjects s ON a.subject_id = s.id
        LEFT JOIN timetable t ON a.period_id = t.id
        LEFT JOIN holidays h ON a.user_id = h.user_id AND a.date = h.date
        WHERE a.user_id = ?
    '''
    params = [user_id]

    if date_filter:
        query += ' AND a.date = ?'
        params.append(date_filter)
    if from_date:
        query += ' AND a.date >= ?'
        params.append(from_date)
    if to_date:
        query += ' AND a.date <= ?'
        params.append(to_date)
    if subject_filter:
        query += ' AND a.subject_id = ?'
        params.append(subject_filter)
    if status_filter and status_filter in ('Present', 'Absent'):
        query += ' AND a.status = ? AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)'
        params.append(status_filter)
        params.append(user_id)

    order_col = 'a.date' if sort_by == 'date' else 't.period_number'
    query += f' ORDER BY {order_col} {order}, t.period_number ASC'

    rows = db.execute(query, params).fetchall()
    result = [dict(r) for r in rows]

    # If no subject filter and viewing all statuses, merge holidays
    if not subject_filter and not status_filter:
        hol_query = "SELECT * FROM holidays WHERE user_id = ?"
        hol_params = [user_id]
        if date_filter:
            hol_query += " AND date = ?"
            hol_params.append(date_filter)
        if from_date:
            hol_query += " AND date >= ?"
            hol_params.append(from_date)
        if to_date:
            hol_query += " AND date <= ?"
            hol_params.append(to_date)
        h_rows = db.execute(hol_query, hol_params).fetchall()
        for h in h_rows:
            try:
                day_name = datetime.strptime(h['date'], '%Y-%m-%d').strftime('%A')
            except Exception:
                day_name = ''
            result.append({
                'id': f"hol_{h['id']}",
                'holiday_id': h['id'],
                'date': h['date'],
                'status': 'Holiday',
                'is_holiday': True,
                'subject_name': h['name'] or 'College Holiday',
                'subject_code': 'HOLIDAY',
                'subject_color': '#8B5CF6',
                'period_day': day_name,
                'period_number': '-',
                'start_time': 'All',
                'end_time': 'Day',
                'notes': h['name'] or 'Official Holiday'
            })
        reverse = (order == 'DESC')
        result.sort(key=lambda x: x.get('date', ''), reverse=reverse)

    return jsonify(result)

@app.route('/api/attendance/<int:att_id>', methods=['PUT', 'DELETE'])
@require_auth
def handle_single_attendance(att_id):
    db = get_db()
    user_id = g.user_id

    existing = db.execute("SELECT id FROM attendance WHERE id = ? AND user_id = ?", (att_id, user_id)).fetchone()
    if not existing:
        return jsonify({'error': 'Attendance record not found'}), 404

    if request.method == 'DELETE':
        db.execute("DELETE FROM attendance WHERE id = ? AND user_id = ?", (att_id, user_id))
        db.commit()
        return jsonify({'success': True, 'id': att_id})

    data = request.json or {}
    status = data.get('status')
    notes = data.get('notes', '')
    if status not in ('Present', 'Absent'):
        return jsonify({'error': 'Invalid status'}), 400

    db.execute('''
        UPDATE attendance SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    ''', (status, notes, att_id, user_id))
    db.commit()
    return jsonify({'success': True, 'id': att_id, 'status': status})

@app.route('/api/attendance/unmark', methods=['POST'])
@require_auth
def unmark_attendance():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    att_date = data.get('date')
    period_id = data.get('period_id')
    if not att_date or not period_id:
        return jsonify({'error': 'Date and period_id required'}), 400

    db.execute("DELETE FROM attendance WHERE user_id = ? AND date = ? AND period_id = ?", (user_id, att_date, period_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/holidays', methods=['GET', 'POST', 'DELETE'])
@require_auth
def handle_holidays():
    db = get_db()
    user_id = g.user_id

    if request.method == 'POST':
        data = request.json or {}
        h_date = data.get('date', '').strip()
        h_name = data.get('name', '').strip()

        if not h_date or not re.match(r'^\d{4}-\d{2}-\d{2}$', h_date):
            return jsonify({'error': 'Valid date in YYYY-MM-DD format is required'}), 400

        try:
            datetime.strptime(h_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid calendar date'}), 400

        cursor = db.execute('''
            INSERT INTO holidays (user_id, date, name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET name = excluded.name, created_at = CURRENT_TIMESTAMP
        ''', (user_id, h_date, h_name or 'College Holiday'))
        db.commit()

        row = db.execute("SELECT * FROM holidays WHERE user_id = ? AND date = ?", (user_id, h_date)).fetchone()
        return jsonify({'success': True, 'holiday': dict(row)}), 201

    if request.method == 'DELETE':
        data = request.json or {}
        h_date = (data.get('date') or request.args.get('date', '')).strip()
        h_id = data.get('id') or request.args.get('id')

        if h_date:
            db.execute("DELETE FROM holidays WHERE user_id = ? AND date = ?", (user_id, h_date))
        elif h_id:
            db.execute("DELETE FROM holidays WHERE user_id = ? AND id = ?", (user_id, h_id))
        else:
            return jsonify({'error': 'Holiday date or id is required'}), 400

        db.commit()
        return jsonify({'success': True, 'date': h_date})

    # GET
    month = request.args.get('month')
    h_date = request.args.get('date')
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = "SELECT * FROM holidays WHERE user_id = ?"
    params = [user_id]
    if month:
        query += " AND strftime('%Y-%m', date) = ?"
        params.append(month)
    if h_date:
        query += " AND date = ?"
        params.append(h_date)
    if from_date:
        query += " AND date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date <= ?"
        params.append(to_date)
    query += " ORDER BY date ASC"

    rows = db.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/holidays/unmark', methods=['POST'])
@require_auth
def unmark_holiday():
    db = get_db()
    user_id = g.user_id
    data = request.json or {}
    h_date = (data.get('date') or request.args.get('date', '')).strip()
    if not h_date:
        return jsonify({'error': 'Holiday date is required'}), 400
    db.execute("DELETE FROM holidays WHERE user_id = ? AND date = ?", (user_id, h_date))
    db.commit()
    return jsonify({'success': True, 'date': h_date})

@app.route('/api/attendance/today', methods=['GET'])
@require_auth
def get_today_attendance():
    db = get_db()
    user_id = g.user_id
    query_date = request.args.get('date', date.today().isoformat())
    try:
        dt = datetime.strptime(query_date, '%Y-%m-%d')
    except ValueError:
        dt = datetime.today()
        query_date = dt.strftime('%Y-%m-%d')

    day_name = dt.strftime('%A')

    # Check if query_date is designated as a holiday
    holiday_row = db.execute("SELECT * FROM holidays WHERE user_id = ? AND date = ?", (user_id, query_date)).fetchone()
    if holiday_row:
        return jsonify({
            'date': query_date,
            'day': day_name,
            'is_holiday': True,
            'holiday_name': holiday_row['name'] or 'College Holiday',
            'periods': [],
            'summary': {
                'total': 0,
                'present': 0,
                'absent': 0,
                'unmarked': 0,
                'marked': 0,
                'percentage': 0.0
            }
        })

    timetable_rows = db.execute('''
        SELECT t.*, s.name as subject_name, s.code as subject_code, s.color as subject_color,
               COALESCE(t.faculty, s.faculty) as effective_faculty,
               COALESCE(t.room, s.room) as effective_room
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.user_id = ? AND t.day = ?
        ORDER BY t.period_number ASC
    ''', (user_id, day_name)).fetchall()

    att_rows = db.execute('''
        SELECT * FROM attendance WHERE user_id = ? AND date = ?
    ''', (user_id, query_date)).fetchall()
    att_map = {r['period_id']: dict(r) for r in att_rows if r['period_id']}

    periods = []
    total_periods = len(timetable_rows)
    present_count = 0
    absent_count = 0
    unmarked_count = 0

    for tr in timetable_rows:
        item = dict(tr)
        record = att_map.get(tr['id'])
        if record:
            item['status'] = record['status']
            item['record_id'] = record['id']
            if record['status'] == 'Present':
                present_count += 1
            elif record['status'] == 'Absent':
                absent_count += 1
        else:
            item['status'] = None
            item['record_id'] = None
            unmarked_count += 1
        periods.append(item)

    return jsonify({
        'date': query_date,
        'day': day_name,
        'is_holiday': False,
        'holiday_name': None,
        'periods': periods,
        'summary': {
            'total': total_periods,
            'present': present_count,
            'absent': absent_count,
            'unmarked': unmarked_count,
            'marked': present_count + absent_count,
            'percentage': round((present_count / (present_count + absent_count) * 100), 1) if (present_count + absent_count) > 0 else 0.0
        }
    })

@app.route('/api/attendance/summary', methods=['GET'])
@require_auth
def get_attendance_summary():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    where_clauses = ['a.user_id = ?', 'a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)']
    params = [user_id, user_id]
    if from_date:
        where_clauses.append('a.date >= ?')
        params.append(from_date)
    if to_date:
        where_clauses.append('a.date <= ?')
        params.append(to_date)
    where_sql = ' AND '.join(where_clauses)

    overall_row = db.execute(f'''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
        FROM attendance a
        WHERE {where_sql}
    ''', params).fetchone()

    total = overall_row['total'] or 0
    attended = overall_row['attended'] or 0
    overall_stats = calculate_stats(attended, total, settings['required_attendance'])

    if total == 0:
        overall_status = 'Good'
    elif overall_stats['percentage'] >= settings['warning_threshold']:
        overall_status = 'Good'
    elif overall_stats['percentage'] >= settings['critical_threshold']:
        overall_status = 'Warning'
    else:
        overall_status = 'Critical'
    overall_stats['status_badge'] = overall_status

    # Count holidays in selected range
    hol_clauses = ['user_id = ?']
    hol_params = [user_id]
    if from_date:
        hol_clauses.append('date >= ?')
        hol_params.append(from_date)
    if to_date:
        hol_clauses.append('date <= ?')
        hol_params.append(to_date)
    hol_sql = ' AND '.join(hol_clauses)
    total_holidays = db.execute(f"SELECT COUNT(*) FROM holidays WHERE {hol_sql}", hol_params).fetchone()[0]

    subjects = db.execute("SELECT * FROM subjects WHERE user_id = ? ORDER BY name ASC", (user_id,)).fetchall()
    subject_summaries = []
    for s in subjects:
        s_params = list(params) + [s['id']]
        sub_row = db.execute(f'''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended
            FROM attendance a
            WHERE {where_sql} AND a.subject_id = ?
        ''', s_params).fetchone()

        s_total = sub_row['total'] or 0
        s_att = sub_row['attended'] or 0
        s_stats = calculate_stats(s_att, s_total, settings['required_attendance'])

        if s_total == 0:
            s_badge = 'Good'
        elif s_stats['percentage'] >= settings['warning_threshold']:
            s_badge = 'Good'
        elif s_stats['percentage'] >= settings['critical_threshold']:
            s_badge = 'Warning'
        else:
            s_badge = 'Critical'

        subject_summaries.append({
            'id': s['id'],
            'name': s['name'],
            'code': s['code'],
            'faculty': s['faculty'],
            'room': s['room'],
            'color': s['color'],
            'attended': s_stats['attended'],
            'absent': s_stats['absent'],
            'total': s_stats['total'],
            'percentage': s_stats['percentage'],
            'can_miss': s_stats['can_miss'],
            'need_to_attend': s_stats['need_to_attend'],
            'status_badge': s_badge
        })

    return jsonify({
        'overall': overall_stats,
        'subjects': subject_summaries,
        'settings': settings,
        'total_holidays': total_holidays,
        'filter': {
            'from_date': from_date,
            'to_date': to_date
        }
    })

@app.route('/api/attendance/monthly', methods=['GET'])
@require_auth
def get_monthly_attendance():
    db = get_db()
    user_id = g.user_id
    rows = db.execute('''
        SELECT 
            strftime('%Y-%m', date) as month,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as attended,
            SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM attendance
        WHERE user_id = ?
          AND date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        GROUP BY month
        ORDER BY month ASC
    ''', (user_id, user_id)).fetchall()

    holiday_counts = db.execute('''
        SELECT strftime('%Y-%m', date) as month, COUNT(*) as holiday_count
        FROM holidays
        WHERE user_id = ?
        GROUP BY month
    ''', (user_id,)).fetchall()
    hol_map = {h['month']: h['holiday_count'] for h in holiday_counts}

    result = []
    for r in rows:
        total = r['total']
        att = r['attended']
        pct = round((att / total) * 100, 1) if total > 0 else 0
        try:
            m_date = datetime.strptime(r['month'], '%Y-%m')
            label = m_date.strftime('%b %Y')
        except Exception:
            label = r['month']

        result.append({
            'month': r['month'],
            'label': label,
            'total': total,
            'attended': att,
            'absent': r['absent'],
            'percentage': pct,
            'holidays': hol_map.get(r['month'], 0)
        })
    return jsonify(result)

@app.route('/api/attendance/calendar', methods=['GET'])
@require_auth
def get_calendar_attendance():
    db = get_db()
    user_id = g.user_id
    month_str = request.args.get('month')
    if not month_str:
        month_str = datetime.today().strftime('%Y-%m')

    rows = db.execute('''
        SELECT 
            date,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as attended,
            SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM attendance
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
          AND date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        GROUP BY date
        ORDER BY date ASC
    ''', (user_id, month_str, user_id)).fetchall()

    holiday_rows = db.execute('''
        SELECT date, name FROM holidays
        WHERE user_id = ? AND strftime('%Y-%m', date) = ?
        ORDER BY date ASC
    ''', (user_id, month_str)).fetchall()

    calendar_data = {}
    for r in rows:
        total = r['total']
        att = r['attended']
        absent = r['absent']
        if total == 0:
            status = 'none'
        elif absent == 0:
            status = 'all_present'
        elif att == 0:
            status = 'all_absent'
        else:
            status = 'partial'

        calendar_data[r['date']] = {
            'total': total,
            'attended': att,
            'absent': absent,
            'percentage': round((att / total) * 100, 1) if total > 0 else 0,
            'status': status,
            'is_holiday': False
        }

    # Add holidays to calendar data
    for h in holiday_rows:
        calendar_data[h['date']] = {
            'total': 0,
            'attended': 0,
            'absent': 0,
            'percentage': 0.0,
            'status': 'holiday',
            'is_holiday': True,
            'holiday_name': h['name'] or 'College Holiday'
        }

    return jsonify(calendar_data)

# --- Excel Export ---

@app.route('/api/export/excel', methods=['GET'])
@require_auth
def export_excel():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)
    scope = request.args.get('scope', 'all')
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    subject_id = request.args.get('subject_id', '').strip()

    where_clauses = ['a.user_id = ?', 'a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)']
    params = [user_id, user_id]
    scope_title = "Complete Attendance"
    sub_row = None

    if scope == 'range':
        if not from_date and not to_date:
            from_date = date.today().replace(day=1).isoformat()
            to_date = date.today().isoformat()

        scope_title = f"Attendance Report ({from_date or 'Start'} to {to_date or 'End'})"
        if from_date:
            where_clauses.append('a.date >= ?')
            params.append(from_date)
        if to_date:
            where_clauses.append('a.date <= ?')
            params.append(to_date)

    elif scope == 'subject':
        if not subject_id:
            first_sub = db.execute("SELECT id FROM subjects WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,)).fetchone()
            if first_sub:
                subject_id = str(first_sub['id'])
            else:
                return jsonify({'error': 'No subjects found to export.'}), 400

        sub_row = db.execute("SELECT id, name, code, faculty, room FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id)).fetchone()
        if not sub_row:
            return jsonify({'error': 'Selected subject not found.'}), 404

        scope_title = f"Subject Attendance: {sub_row['name']} ({sub_row['code']})"
        where_clauses.append('a.subject_id = ?')
        params.append(subject_id)

    where_sql = ' AND '.join(where_clauses)

    records = db.execute(f'''
        SELECT a.date, a.status, a.notes,
               s.name as subject_name, s.code as subject_code,
               t.period_number, t.start_time, t.end_time,
               COALESCE(t.faculty, s.faculty) as effective_faculty,
               COALESCE(t.room, s.room) as effective_room
        FROM attendance a
        JOIN subjects s ON a.subject_id = s.id
        LEFT JOIN timetable t ON a.period_id = t.id
        WHERE {where_sql}
        ORDER BY a.date DESC, t.period_number ASC
    ''', params).fetchall()

    if scope == 'subject' and sub_row:
        sub_where = "WHERE s.user_id = ? AND s.id = ?"
        sub_params = [user_id, sub_row['id']]
    else:
        sub_where = "WHERE s.user_id = ?"
        sub_params = [user_id]

    subject_stats = db.execute(f'''
        SELECT s.id, s.name, s.code, s.faculty, s.room,
               COUNT(a.id) as total,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended,
               SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM subjects s
        LEFT JOIN attendance a ON s.id = a.subject_id AND ({where_sql})
        {sub_where}
        GROUP BY s.id
        ORDER BY s.name ASC
    ''', params + sub_params).fetchall()

    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = "Summary Report"

    primary_font = Font(name="Arial", size=11)
    title_font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Arial", size=11, italic=True, color="475569")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Arial", size=11, bold=True)
    green_font = Font(name="Arial", size=11, bold=True, color="047857")
    yellow_font = Font(name="Arial", size=11, bold=True, color="B45309")
    red_font = Font(name="Arial", size=11, bold=True, color="B91C1C")

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    accent_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws_summary['A1'] = settings['college_name']
    ws_summary['A1'].font = title_font
    ws_summary['A2'] = f"{scope_title} | Student: {settings['student_name']} | Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    ws_summary['A2'].font = subtitle_font

    total_conducted = len(records)
    total_attended = sum(1 for r in records if r['status'] == 'Present')
    total_absent = total_conducted - total_attended
    overall_pct = round((total_attended / total_conducted * 100), 2) if total_conducted > 0 else 0.0

    ws_summary['A4'] = "Metric"
    ws_summary['B4'] = "Value"
    ws_summary['A4'].font = header_font
    ws_summary['B4'].font = header_font
    ws_summary['A4'].fill = header_fill
    ws_summary['B4'].fill = header_fill

    kpi_rows = [
        ("Overall Attendance", f"{overall_pct}%"),
        ("Total Classes Conducted", total_conducted),
        ("Classes Attended", total_attended),
        ("Classes Absent", total_absent),
        ("Required Attendance Target", f"{settings['required_attendance']}%"),
        ("Warning Threshold", f"{settings['warning_threshold']}%"),
        ("Critical Threshold", f"{settings['critical_threshold']}%")
    ]
    for idx, (m, v) in enumerate(kpi_rows, start=5):
        ws_summary[f'A{idx}'] = m
        ws_summary[f'B{idx}'] = v
        ws_summary[f'A{idx}'].font = bold_font
        ws_summary[f'A{idx}'].border = thin_border
        ws_summary[f'B{idx}'].border = thin_border
        ws_summary[f'A{idx}'].fill = accent_fill

    start_row = 14
    ws_summary[f'A{start_row}'] = "SUBJECT-WISE ATTENDANCE BREAKDOWN"
    ws_summary[f'A{start_row}'].font = Font(name="Arial", size=13, bold=True, color="1E3A8A")

    sub_headers = ["Code", "Subject Name", "Faculty", "Room", "Attended", "Absent", "Total", "Percentage", "Status", "Safe to Miss", "Need to Attend"]
    for col_idx, h in enumerate(sub_headers, start=1):
        cell = ws_summary.cell(row=start_row + 1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    curr_row = start_row + 2
    for s in subject_stats:
        tot = s['total'] or 0
        att = s['attended'] or 0
        ab = s['absent'] or 0
        pct = round((att / tot) * 100, 2) if tot > 0 else 0.0
        stats = calculate_stats(att, tot, settings['required_attendance'])

        if tot == 0:
            badge = "Good"
        elif pct >= settings['warning_threshold']:
            badge = "Good"
        elif pct >= settings['critical_threshold']:
            badge = "Warning"
        else:
            badge = "Critical"

        row_vals = [
            s['code'],
            s['name'],
            s['faculty'] or '-',
            s['room'] or '-',
            att,
            ab,
            tot,
            f"{pct}%",
            badge,
            stats['can_miss'],
            stats['need_to_attend'] if stats['need_to_attend'] >= 0 else "N/A"
        ]

        for col_idx, val in enumerate(row_vals, start=1):
            c = ws_summary.cell(row=curr_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (5, 6, 7, 8, 9, 10, 11):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 9:
                if badge == "Good": c.font = green_font
                elif badge == "Warning": c.font = yellow_font
                else: c.font = red_font
        curr_row += 1

    ws_detail = wb.create_sheet(title="Detailed Records")
    detail_headers = ["Date", "Day", "Period", "Start Time", "End Time", "Subject Code", "Subject Name", "Faculty", "Room", "Status", "Notes"]
    
    for col_idx, h in enumerate(detail_headers, start=1):
        cell = ws_detail.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    d_row = 2
    for r in records:
        try:
            day_name = datetime.strptime(r['date'], '%Y-%m-%d').strftime('%A')
        except Exception:
            day_name = '-'

        vals = [
            r['date'],
            day_name,
            r['period_number'] or '-',
            r['start_time'] or '-',
            r['end_time'] or '-',
            r['subject_code'],
            r['subject_name'],
            r['effective_faculty'] or '-',
            r['effective_room'] or '-',
            r['status'],
            r['notes'] or ''
        ]
        for col_idx, val in enumerate(vals, start=1):
            c = ws_detail.cell(row=d_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (1, 2, 3, 4, 5, 10):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 10:
                c.font = green_font if r['status'] == 'Present' else red_font
        d_row += 1

    # ---------------- SHEET 3: Declared Holidays ----------------
    ws_holidays = wb.create_sheet(title="Holidays")
    ws_holidays['A1'] = "Declared College Holidays"
    ws_holidays['A1'].font = title_font
    ws_holidays['A2'] = f"Student: {settings['student_name']} | Scope: {scope_title}"
    ws_holidays['A2'].font = subtitle_font

    hol_query = "SELECT * FROM holidays WHERE user_id = ?"
    hol_params = [user_id]
    if scope == 'range':
        if from_date:
            hol_query += " AND date >= ?"
            hol_params.append(from_date)
        if to_date:
            hol_query += " AND date <= ?"
            hol_params.append(to_date)
    hol_query += " ORDER BY date ASC"
    holidays_data = db.execute(hol_query, hol_params).fetchall()

    h_headers = ["#", "Date", "Day of Week", "Holiday Name / Reason"]
    for col_idx, h in enumerate(h_headers, start=1):
        cell = ws_holidays.cell(row=4, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    h_row = 5
    for idx, h in enumerate(holidays_data, start=1):
        try:
            day_name = datetime.strptime(h['date'], '%Y-%m-%d').strftime('%A')
        except Exception:
            day_name = '-'
        vals = [idx, h['date'], day_name, h['name'] or 'College Holiday']
        for col_idx, val in enumerate(vals, start=1):
            c = ws_holidays.cell(row=h_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (1, 2, 3):
                c.alignment = Alignment(horizontal="center")
        h_row += 1

    if not holidays_data:
        c = ws_holidays.cell(row=5, column=1, value="No declared holidays in this period.")
        c.font = subtitle_font

    for ws in [ws_summary, ws_detail, ws_holidays]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if cell.row in (1, 2) and ws in (ws_summary, ws_holidays):
                    continue
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    if scope == 'subject' and sub_row:
        safe_code = re.sub(r'[^a-zA-Z0-9_-]', '_', sub_row['code'])
        filename = f"Attendance_{safe_code}_{timestamp_str}.xlsx"
    elif scope == 'range':
        filename = f"Attendance_Range_{from_date or 'Start'}_to_{to_date or 'End'}_{timestamp_str}.xlsx"
    else:
        filename = f"Complete_Attendance_{timestamp_str}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/export/analytics', methods=['GET'])
@require_auth
def export_analytics():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)

    # 1. Fetch monthly stats (excluding holidays)
    monthly_rows = db.execute('''
        SELECT 
            strftime('%Y-%m', date) as month,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as attended,
            SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM attendance
        WHERE user_id = ?
          AND date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        GROUP BY month
        ORDER BY month ASC
    ''', (user_id, user_id)).fetchall()

    holiday_counts = db.execute('''
        SELECT strftime('%Y-%m', date) as month, COUNT(*) as holiday_count
        FROM holidays
        WHERE user_id = ?
        GROUP BY month
    ''', (user_id,)).fetchall()
    hol_map = {h['month']: h['holiday_count'] for h in holiday_counts}

    # 2. Fetch subject summary stats (excluding holidays)
    subject_stats = db.execute('''
        SELECT s.id, s.name, s.code, s.faculty, s.room,
               COUNT(a.id) as total,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended,
               SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM subjects s
        LEFT JOIN attendance a ON s.id = a.subject_id AND a.user_id = ? AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.name ASC
    ''', (user_id, user_id, user_id)).fetchall()

    # 3. Fetch monthly subject breakdown matrix (excluding holidays)
    matrix_rows = db.execute('''
        SELECT s.id as subject_id, s.code as subject_code, s.name as subject_name,
               strftime('%Y-%m', a.date) as month,
               COUNT(a.id) as total,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as attended,
               SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent
        FROM subjects s
        LEFT JOIN attendance a ON s.id = a.subject_id AND a.user_id = ? AND a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)
        WHERE s.user_id = ?
        GROUP BY s.id, month
        ORDER BY s.code ASC, month ASC
    ''', (user_id, user_id, user_id)).fetchall()

    wb = openpyxl.Workbook()

    # Styling
    primary_font = Font(name="Arial", size=11)
    title_font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Arial", size=11, italic=True, color="475569")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Arial", size=11, bold=True)
    green_font = Font(name="Arial", size=11, bold=True, color="047857")
    yellow_font = Font(name="Arial", size=11, bold=True, color="B45309")
    red_font = Font(name="Arial", size=11, bold=True, color="B91C1C")

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    sub_header_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    accent_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # ---------------- SHEET 1: Monthly Trends ----------------
    ws_trends = wb.active
    ws_trends.title = "Monthly Trends & KPIs"

    ws_trends['A1'] = settings['college_name']
    ws_trends['A1'].font = title_font
    ws_trends['A2'] = f"Monthly Attendance Analytics Report | Student: {settings['student_name']} | Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    ws_trends['A2'].font = subtitle_font

    all_tot = sum(r['total'] for r in monthly_rows)
    all_att = sum(r['attended'] for r in monthly_rows)
    all_abs = sum(r['absent'] for r in monthly_rows)
    all_pct = round((all_att / all_tot * 100), 2) if all_tot > 0 else 0.0

    best_m = "N/A"
    worst_m = "N/A"
    if monthly_rows:
        pct_list = []
        for r in monthly_rows:
            p = round((r['attended'] / r['total'] * 100), 2) if r['total'] > 0 else 0.0
            try:
                lbl = datetime.strptime(r['month'], '%Y-%m').strftime('%b %Y')
            except Exception:
                lbl = r['month']
            pct_list.append((lbl, p))
        best_m = max(pct_list, key=lambda x: x[1])[0] + f" ({max(pct_list, key=lambda x: x[1])[1]}%)"
        worst_m = min(pct_list, key=lambda x: x[1])[0] + f" ({min(pct_list, key=lambda x: x[1])[1]}%)"

    ws_trends['A4'] = "Metric"
    ws_trends['B4'] = "Value"
    ws_trends['A4'].font = header_font
    ws_trends['B4'].font = header_font
    ws_trends['A4'].fill = header_fill
    ws_trends['B4'].fill = header_fill

    kpi_rows = [
        ("Cumulative Attendance", f"{all_pct}%"),
        ("Total Classes Conducted", all_tot),
        ("Classes Attended", all_att),
        ("Classes Absent", all_abs),
        ("Total Declared Holidays", sum(hol_map.values())),
        ("Required Target", f"{settings['required_attendance']}%"),
        ("Tracked Months", len(monthly_rows)),
        ("Best Attendance Month", best_m),
        ("Lowest Attendance Month", worst_m)
    ]
    for idx, (m, v) in enumerate(kpi_rows, start=5):
        ws_trends[f'A{idx}'] = m
        ws_trends[f'B{idx}'] = v
        ws_trends[f'A{idx}'].font = bold_font
        ws_trends[f'A{idx}'].border = thin_border
        ws_trends[f'B{idx}'].border = thin_border
        ws_trends[f'A{idx}'].fill = accent_fill

    t_start = 16
    ws_trends[f'A{t_start}'] = "MONTH-BY-MONTH ATTENDANCE TRENDS"
    ws_trends[f'A{t_start}'].font = Font(name="Arial", size=13, bold=True, color="1E3A8A")

    trend_headers = ["Month Key", "Month Name", "Conducted", "Attended", "Absent", "Holidays", "Attendance %", "Status", "MoM Change"]
    for col_idx, h in enumerate(trend_headers, start=1):
        c = ws_trends.cell(row=t_start + 1, column=col_idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    curr_row = t_start + 2
    prev_pct = None
    for r in monthly_rows:
        tot = r['total']
        att = r['attended']
        ab = r['absent']
        m_hols = hol_map.get(r['month'], 0)
        pct = round((att / tot * 100), 2) if tot > 0 else 0.0
        try:
            m_label = datetime.strptime(r['month'], '%Y-%m').strftime('%B %Y')
        except Exception:
            m_label = r['month']

        if tot == 0:
            badge = "Good"
        elif pct >= settings['warning_threshold']:
            badge = "Good"
        elif pct >= settings['critical_threshold']:
            badge = "Warning"
        else:
            badge = "Critical"

        if prev_pct is None:
            mom_str = "Baseline"
        else:
            diff = round(pct - prev_pct, 2)
            mom_str = f"+{diff}%" if diff > 0 else f"{diff}%"
        prev_pct = pct

        vals = [r['month'], m_label, tot, att, ab, m_hols, f"{pct}%", badge, mom_str]
        for col_idx, val in enumerate(vals, start=1):
            c = ws_trends.cell(row=curr_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (1, 3, 4, 5, 6, 7, 8, 9):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 8:
                if badge == "Good": c.font = green_font
                elif badge == "Warning": c.font = yellow_font
                else: c.font = red_font
        curr_row += 1

    # ---------------- SHEET 2: Subject Performance ----------------
    ws_subs = wb.create_sheet(title="Subject Performance")
    ws_subs['A1'] = "Subject-Wise Cumulative Performance & Projections"
    ws_subs['A1'].font = Font(name="Arial", size=14, bold=True, color="1E3A8A")
    ws_subs['A2'] = f"Required Threshold: {settings['required_attendance']}% | Warning: {settings['warning_threshold']}% | Critical: {settings['critical_threshold']}%"
    ws_subs['A2'].font = subtitle_font

    sub_headers = ["Code", "Subject Name", "Faculty", "Room", "Attended", "Absent", "Total", "Percentage", "Status", "Safe to Miss", "Need to Attend"]
    for col_idx, h in enumerate(sub_headers, start=1):
        c = ws_subs.cell(row=4, column=col_idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    s_row = 5
    for s in subject_stats:
        tot = s['total'] or 0
        att = s['attended'] or 0
        ab = s['absent'] or 0
        pct = round((att / tot) * 100, 2) if tot > 0 else 0.0
        stats = calculate_stats(att, tot, settings['required_attendance'])

        if tot == 0:
            badge = "Good"
        elif pct >= settings['warning_threshold']:
            badge = "Good"
        elif pct >= settings['critical_threshold']:
            badge = "Warning"
        else:
            badge = "Critical"

        row_vals = [
            s['code'],
            s['name'],
            s['faculty'] or '-',
            s['room'] or '-',
            att,
            ab,
            tot,
            f"{pct}%",
            badge,
            stats['can_miss'],
            stats['need_to_attend'] if stats['need_to_attend'] >= 0 else "N/A"
        ]
        for col_idx, val in enumerate(row_vals, start=1):
            c = ws_subs.cell(row=s_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (5, 6, 7, 8, 9, 10, 11):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 9:
                if badge == "Good": c.font = green_font
                elif badge == "Warning": c.font = yellow_font
                else: c.font = red_font
        s_row += 1

    # ---------------- SHEET 3: Month x Subject Matrix ----------------
    ws_matrix = wb.create_sheet(title="Subject Monthly Matrix")
    ws_matrix['A1'] = "Subject-Wise Monthly Attendance Cross-Tabulation Matrix"
    ws_matrix['A1'].font = Font(name="Arial", size=14, bold=True, color="1E3A8A")
    ws_matrix['A2'] = "Values represent: Attendance % (Attended / Conducted)"
    ws_matrix['A2'].font = subtitle_font

    unique_months = [r['month'] for r in monthly_rows if r['month']]
    matrix_headers = ["Code", "Subject Name"] + [
        (datetime.strptime(m, '%Y-%m').strftime('%b %Y') if '-' in m else m) for m in unique_months
    ]

    for col_idx, h in enumerate(matrix_headers, start=1):
        c = ws_matrix.cell(row=4, column=col_idx, value=h)
        c.font = header_font
        c.fill = sub_header_fill if col_idx > 2 else header_fill
        c.alignment = Alignment(horizontal="center")

    matrix_map = {}
    for mr in matrix_rows:
        if mr['month']:
            matrix_map[(mr['subject_id'], mr['month'])] = mr

    m_row = 5
    for s in subject_stats:
        sid = s['id']
        c_code = ws_matrix.cell(row=m_row, column=1, value=s['code'])
        c_code.font = bold_font
        c_code.border = thin_border
        c_code.alignment = Alignment(horizontal="center")

        c_name = ws_matrix.cell(row=m_row, column=2, value=s['name'])
        c_name.font = primary_font
        c_name.border = thin_border

        for m_idx, m_key in enumerate(unique_months, start=3):
            cell = ws_matrix.cell(row=m_row, column=m_idx)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
            if (sid, m_key) in matrix_map:
                m_data = matrix_map[(sid, m_key)]
                m_tot = m_data['total']
                m_att = m_data['attended']
                m_pct = round((m_att / m_tot * 100), 1) if m_tot > 0 else 0.0
                cell.value = f"{m_pct}% ({m_att}/{m_tot})"
                cell.font = green_font if m_pct >= settings['warning_threshold'] else (yellow_font if m_pct >= settings['critical_threshold'] else red_font)
            else:
                cell.value = "-"
                cell.font = Font(name="Arial", size=11, color="94A3B8")
        m_row += 1

    for ws in [ws_trends, ws_subs, ws_matrix]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if cell.row in (1, 2) and ws in (ws_trends, ws_subs, ws_matrix):
                    continue
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Monthly_Analytics_Report_{timestamp_str}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

@app.route('/api/export/logs', methods=['GET'])
@require_auth
def export_logs():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)

    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    subject_id = request.args.get('subject_id', '').strip()
    status_filter = request.args.get('status', '').strip()
    sort_by = request.args.get('sort', 'date')
    order = request.args.get('order', 'DESC').upper()
    if order not in ('ASC', 'DESC'):
        order = 'DESC'

    where_clauses = ['a.user_id = ?']
    params = [user_id]
    active_filters_desc = []

    if from_date:
        where_clauses.append('a.date >= ?')
        params.append(from_date)
        active_filters_desc.append(f"From: {from_date}")
    if to_date:
        where_clauses.append('a.date <= ?')
        params.append(to_date)
        active_filters_desc.append(f"To: {to_date}")
    if subject_id:
        sub_row = db.execute("SELECT name, code FROM subjects WHERE id = ? AND user_id = ?", (subject_id, user_id)).fetchone()
        if sub_row:
            where_clauses.append('a.subject_id = ?')
            params.append(subject_id)
            active_filters_desc.append(f"Subject: {sub_row['code']} - {sub_row['name']}")
    if status_filter == 'Holiday':
        active_filters_desc.append("Status: Holiday")
        hol_query = "SELECT * FROM holidays WHERE user_id = ?"
        hol_params = [user_id]
        if from_date:
            hol_query += " AND date >= ?"
            hol_params.append(from_date)
        if to_date:
            hol_query += " AND date <= ?"
            hol_params.append(to_date)
        hol_query += f" ORDER BY date {order}"
        h_rows = db.execute(hol_query, hol_params).fetchall()
        records = []
        for h in h_rows:
            try:
                day_name = datetime.strptime(h['date'], '%Y-%m-%d').strftime('%A')
            except Exception:
                day_name = '-'
            records.append({
                'id': h['id'],
                'date': h['date'],
                'status': 'Holiday',
                'notes': h['name'] or 'College Holiday',
                'created_at': h['created_at'],
                'subject_name': h['name'] or 'College Holiday',
                'subject_code': 'HOLIDAY',
                'period_day': day_name,
                'period_number': '-',
                'start_time': '-',
                'end_time': '-',
                'effective_faculty': '-',
                'effective_room': '-'
            })
    else:
        if status_filter in ('Present', 'Absent'):
            where_clauses.append('a.status = ?')
            where_clauses.append('a.date NOT IN (SELECT date FROM holidays WHERE user_id = ?)')
            params.append(status_filter)
            params.append(user_id)
            active_filters_desc.append(f"Status: {status_filter}")

        where_sql = ' AND '.join(where_clauses)
        order_col = 'a.date' if sort_by == 'date' else 't.period_number'

        db_records = db.execute(f'''
            SELECT a.id, a.date, a.status, a.notes, a.created_at,
                   s.name as subject_name, s.code as subject_code,
                   t.day as period_day, t.period_number, t.start_time, t.end_time,
                   COALESCE(t.faculty, s.faculty) as effective_faculty,
                   COALESCE(t.room, s.room) as effective_room
            FROM attendance a
            JOIN subjects s ON a.subject_id = s.id
            LEFT JOIN timetable t ON a.period_id = t.id
            WHERE {where_sql}
            ORDER BY {order_col} {order}, t.period_number ASC
        ''', params).fetchall()
        records = [dict(r) for r in db_records]

        # If not filtering by specific subject or status, merge holidays
        if not subject_id and not status_filter:
            hol_query = "SELECT * FROM holidays WHERE user_id = ?"
            hol_params = [user_id]
            if from_date:
                hol_query += " AND date >= ?"
                hol_params.append(from_date)
            if to_date:
                hol_query += " AND date <= ?"
                hol_params.append(to_date)
            h_rows = db.execute(hol_query, hol_params).fetchall()
            for h in h_rows:
                try:
                    day_name = datetime.strptime(h['date'], '%Y-%m-%d').strftime('%A')
                except Exception:
                    day_name = '-'
                records.append({
                    'id': f"hol_{h['id']}",
                    'date': h['date'],
                    'status': 'Holiday',
                    'notes': h['name'] or 'College Holiday',
                    'created_at': h['created_at'],
                    'subject_name': h['name'] or 'College Holiday',
                    'subject_code': 'HOLIDAY',
                    'period_day': day_name,
                    'period_number': '-',
                    'start_time': '-',
                    'end_time': '-',
                    'effective_faculty': '-',
                    'effective_room': '-'
                })
            reverse = (order == 'DESC')
            records.sort(key=lambda x: str(x.get('date', '')), reverse=reverse)

    wb = openpyxl.Workbook()

    primary_font = Font(name="Arial", size=11)
    title_font = Font(name="Arial", size=16, bold=True, color="1E3A8A")
    subtitle_font = Font(name="Arial", size=11, italic=True, color="475569")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Arial", size=11, bold=True)
    green_font = Font(name="Arial", size=11, bold=True, color="047857")
    red_font = Font(name="Arial", size=11, bold=True, color="B91C1C")
    purple_font = Font(name="Arial", size=11, bold=True, color="7C3AED")

    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    accent_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # ---------------- SHEET 1: Filtered Records ----------------
    ws_records = wb.active
    ws_records.title = "Attendance Logs"

    ws_records['A1'] = settings['college_name']
    ws_records['A1'].font = title_font

    filter_summary_str = " | ".join(active_filters_desc) if active_filters_desc else "All Records (No Filters)"
    ws_records['A2'] = f"Filtered Attendance Logs | Student: {settings['student_name']} | Filters: [{filter_summary_str}] | Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    ws_records['A2'].font = subtitle_font

    log_headers = [
        "#", "Date", "Day", "Period", "Start Time", "End Time",
        "Subject Code", "Subject Name", "Faculty", "Room", "Status", "Notes", "Logged At"
    ]
    for col_idx, h in enumerate(log_headers, start=1):
        cell = ws_records.cell(row=4, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    r_row = 5
    for idx, r in enumerate(records, start=1):
        try:
            day_name = datetime.strptime(r['date'], '%Y-%m-%d').strftime('%A')
        except Exception:
            day_name = r.get('period_day') or '-'

        vals = [
            idx,
            r['date'],
            day_name,
            r['period_number'] or '-',
            r['start_time'] or '-',
            r['end_time'] or '-',
            r['subject_code'],
            r['subject_name'],
            r['effective_faculty'] or '-',
            r['effective_room'] or '-',
            r['status'],
            r['notes'] or '',
            r['created_at'] or '-'
        ]
        for col_idx, val in enumerate(vals, start=1):
            c = ws_records.cell(row=r_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (1, 2, 3, 4, 5, 6, 11):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 11:
                if r['status'] == 'Present':
                    c.font = green_font
                elif r['status'] == 'Holiday':
                    c.font = purple_font
                else:
                    c.font = red_font
        r_row += 1

    # ---------------- SHEET 2: Filter Summary & Stats ----------------
    ws_summary = wb.create_sheet(title="Log Summary")
    ws_summary['A1'] = "Filtered Logs - Summary & Distribution"
    ws_summary['A1'].font = Font(name="Arial", size=14, bold=True, color="1E3A8A")
    ws_summary['A2'] = f"Filters Applied: {filter_summary_str}"
    ws_summary['A2'].font = subtitle_font

    tot_log = len(records)
    att_log = sum(1 for r in records if r['status'] == 'Present')
    abs_log = sum(1 for r in records if r['status'] == 'Absent')
    hol_log = sum(1 for r in records if r['status'] == 'Holiday')
    reg_log = att_log + abs_log
    pct_log = round((att_log / reg_log * 100), 2) if reg_log > 0 else 0.0

    ws_summary['A4'] = "Summary Metric"
    ws_summary['B4'] = "Value"
    ws_summary['A4'].font = header_font
    ws_summary['B4'].font = header_font
    ws_summary['A4'].fill = header_fill
    ws_summary['B4'].fill = header_fill

    kpis = [
        ("Total Filtered Log Entries", tot_log),
        ("Present Count", att_log),
        ("Absent Count", abs_log),
        ("Holiday Entries", hol_log),
        ("Log Attendance Rate", f"{pct_log}%"),
        ("Date Sort Direction", f"{sort_by.capitalize()} ({order})")
    ]
    for idx, (m, v) in enumerate(kpis, start=5):
        ws_summary[f'A{idx}'] = m
        ws_summary[f'B{idx}'] = v
        ws_summary[f'A{idx}'].font = bold_font
        ws_summary[f'A{idx}'].border = thin_border
        ws_summary[f'B{idx}'].border = thin_border
        ws_summary[f'A{idx}'].fill = accent_fill

    sub_map = {}
    for r in records:
        if r['status'] == 'Holiday':
            continue
        sc = r['subject_code']
        sn = r['subject_name']
        if sc not in sub_map:
            sub_map[sc] = {'name': sn, 'present': 0, 'absent': 0, 'total': 0}
        sub_map[sc]['total'] += 1
        if r['status'] == 'Present':
            sub_map[sc]['present'] += 1
        elif r['status'] == 'Absent':
            sub_map[sc]['absent'] += 1

    s_start = 12
    ws_summary[f'A{s_start}'] = "SUBJECT DISTRIBUTION IN THIS LOG EXPORT"
    ws_summary[f'A{s_start}'].font = Font(name="Arial", size=12, bold=True, color="1E3A8A")

    sub_hdr = ["Subject Code", "Subject Name", "Present", "Absent", "Total", "Percentage"]
    for col_idx, h in enumerate(sub_hdr, start=1):
        c = ws_summary.cell(row=s_start + 1, column=col_idx, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    curr_s_row = s_start + 2
    for sc, sdata in sorted(sub_map.items()):
        s_pct = round((sdata['present'] / sdata['total'] * 100), 2) if sdata['total'] > 0 else 0.0
        row_v = [sc, sdata['name'], sdata['present'], sdata['absent'], sdata['total'], f"{s_pct}%"]
        for col_idx, val in enumerate(row_v, start=1):
            c = ws_summary.cell(row=curr_s_row, column=col_idx, value=val)
            c.font = primary_font
            c.border = thin_border
            if col_idx in (3, 4, 5, 6):
                c.alignment = Alignment(horizontal="center")
            if col_idx == 6:
                c.font = green_font if s_pct >= settings['warning_threshold'] else red_font
        curr_s_row += 1

    for ws in [ws_records, ws_summary]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if cell.row in (1, 2) and ws in (ws_records, ws_summary):
                    continue
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Attendance_Logs_{timestamp_str}.xlsx"

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

# --- Backup & Reset (User Scoped) ---

@app.route('/api/backup/export', methods=['GET'])
@require_auth
def backup_export():
    db = get_db()
    user_id = g.user_id
    settings = get_current_settings(user_id)
    subjects = [dict(r) for r in db.execute("SELECT * FROM subjects WHERE user_id = ?", (user_id,)).fetchall()]
    timetable = [dict(r) for r in db.execute("SELECT * FROM timetable WHERE user_id = ?", (user_id,)).fetchall()]
    attendance = [dict(r) for r in db.execute("SELECT * FROM attendance WHERE user_id = ?", (user_id,)).fetchall()]
    period_slots = [dict(r) for r in db.execute("SELECT * FROM period_slots WHERE user_id = ?", (user_id,)).fetchall()]
    holidays = [dict(r) for r in db.execute("SELECT * FROM holidays WHERE user_id = ?", (user_id,)).fetchall()]

    backup_data = {
        'version': '2.0',
        'user': {
            'email': g.current_user['email'],
            'name': g.current_user['name']
        },
        'exported_at': datetime.now().isoformat(),
        'settings': settings,
        'subjects': subjects,
        'timetable': timetable,
        'attendance': attendance,
        'period_slots': period_slots,
        'holidays': holidays
    }
    return jsonify(backup_data)

@app.route('/api/backup/import', methods=['POST'])
@require_auth
def backup_import():
    db = get_db()
    user_id = g.user_id
    data = request.json
    if not data or not isinstance(data, dict):
        return jsonify({'error': 'Invalid backup format'}), 400

    try:
        db.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM timetable WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM subjects WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM period_slots WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM holidays WHERE user_id = ?", (user_id,))

        s = data.get('settings', {})
        if s:
            db.execute('''
                INSERT INTO settings (user_id, required_attendance, warning_threshold, critical_threshold, theme, college_name, student_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    required_attendance = excluded.required_attendance,
                    warning_threshold = excluded.warning_threshold,
                    critical_threshold = excluded.critical_threshold,
                    theme = excluded.theme,
                    college_name = excluded.college_name,
                    student_name = excluded.student_name,
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                user_id,
                s.get('required_attendance', 75.0),
                s.get('warning_threshold', 75.0),
                s.get('critical_threshold', 65.0),
                s.get('theme', 'system'),
                s.get('college_name', 'College of Engineering & Technology'),
                s.get('student_name', g.current_user['name'])
            ))

        sub_id_map = {}
        subjects = data.get('subjects', [])
        for sub in subjects:
            cur = db.execute('''
                INSERT INTO subjects (user_id, name, code, faculty, room, color, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, sub.get('name'), sub.get('code'),
                sub.get('faculty', ''), sub.get('room', ''),
                sub.get('color', '#3B82F6'), sub.get('created_at', datetime.now().isoformat())
            ))
            if sub.get('id'):
                sub_id_map[sub['id']] = cur.lastrowid

        period_slots = data.get('period_slots', [])
        for ps in period_slots:
            db.execute('''
                INSERT INTO period_slots (user_id, slot_number, label, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user_id, ps.get('slot_number', 1),
                ps.get('label', ''), ps.get('start_time', '09:00'), ps.get('end_time', '09:50')
            ))

        period_id_map = {}
        timetable = data.get('timetable', [])
        for t in timetable:
            new_sub_id = sub_id_map.get(t.get('subject_id'), t.get('subject_id'))
            cur = db.execute('''
                INSERT INTO timetable (user_id, day, period_number, start_time, end_time, subject_id, room, faculty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, t.get('day'), t.get('period_number'),
                t.get('start_time'), t.get('end_time'), new_sub_id,
                t.get('room', ''), t.get('faculty', '')
            ))
            if t.get('id'):
                period_id_map[t['id']] = cur.lastrowid

        attendance = data.get('attendance', [])
        for a in attendance:
            new_sub_id = sub_id_map.get(a.get('subject_id'), a.get('subject_id'))
            new_period_id = period_id_map.get(a.get('period_id'), a.get('period_id'))
            db.execute('''
                INSERT INTO attendance (user_id, date, period_id, subject_id, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, a.get('date'), new_period_id,
                new_sub_id, a.get('status'), a.get('notes', ''),
                a.get('created_at', datetime.now().isoformat()),
                a.get('updated_at', datetime.now().isoformat())
            ))

        holidays = data.get('holidays', [])
        for h in holidays:
            db.execute('''
                INSERT INTO holidays (user_id, date, name, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                user_id, h.get('date'), h.get('name', 'College Holiday'),
                h.get('created_at', datetime.now().isoformat())
            ))

        db.commit()
        return jsonify({
            'success': True,
            'imported': {
                'subjects': len(subjects),
                'timetable': len(timetable),
                'attendance': len(attendance),
                'period_slots': len(period_slots),
                'holidays': len(holidays)
            }
        })
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Failed to import backup: {str(e)}'}), 500

@app.route('/api/backup/clear-attendance', methods=['POST'])
@require_auth
def clear_attendance():
    db = get_db()
    user_id = g.user_id
    db.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
    db.commit()
    return jsonify({'success': True, 'message': 'All attendance records cleared'})

@app.route('/api/backup/reset-all', methods=['POST'])
@require_auth
def reset_all():
    db = get_db()
    user_id = g.user_id
    db.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM timetable WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM subjects WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM period_slots WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM holidays WHERE user_id = ?", (user_id,))
    db.execute('''
        UPDATE settings
        SET required_attendance = 75.0, warning_threshold = 75.0, critical_threshold = 65.0,
            theme = 'system', college_name = 'College of Engineering & Technology',
            period_slots_initialized = 0
        WHERE user_id = ?
    ''', (user_id,))
    db.commit()
    return jsonify({'success': True, 'message': 'Account data reset to fresh state'})

@app.route('/api/backup/seed', methods=['POST'])
@require_auth
def seed_account_data():
    db = get_db()
    user_id = g.user_id
    # Reset existing user data first
    db.execute("DELETE FROM attendance WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM timetable WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM subjects WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM holidays WHERE user_id = ?", (user_id,))
    
    # Insert sample subjects
    sample_subjects = [
        ('Data Structures & Algorithms', 'CS201', 'Dr. Alan Turing', 'Room 301', '#3B82F6'),
        ('Database Management Systems', 'CS202', 'Prof. Grace Hopper', 'Lab 2', '#10B981'),
        ('Computer Networks', 'CS203', 'Dr. Vint Cerf', 'Room 204', '#F59E0B'),
        ('Operating Systems', 'CS204', 'Dr. Ken Thompson', 'Room 105', '#8B5CF6'),
        ('Mathematics III', 'MA201', 'Dr. John von Neumann', 'LH-1', '#EC4899')
    ]
    sub_ids = []
    for name, code, faculty, room, color in sample_subjects:
        cur = db.execute('''
            INSERT INTO subjects (user_id, name, code, faculty, room, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, name, code, faculty, room, color))
        sub_ids.append(cur.lastrowid)

    # Insert sample timetable
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    periods_def = [
        ('09:00', '09:50'),
        ('09:50', '10:40'),
        ('11:00', '11:50'),
        ('11:50', '12:40'),
    ]
    period_ids = []
    for day_idx, day in enumerate(days):
        for p_idx, (st, et) in enumerate(periods_def, start=1):
            sub_id = sub_ids[(day_idx + p_idx) % len(sub_ids)]
            cur = db.execute('''
                INSERT INTO timetable (user_id, day, period_number, start_time, end_time, subject_id, room, faculty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, day, p_idx, st, et, sub_id, 'Room 101', 'Faculty'))
            period_ids.append(cur.lastrowid)

    # Insert attendance records for the past 14 days
    today = date.today()
    for days_back in range(14, 0, -1):
        d = today - timedelta(days=days_back)
        day_name = d.strftime('%A')
        if day_name in ('Saturday', 'Sunday'):
            continue
        # Mark periods per day
        for p_num in range(1, 4):
            sub_id = sub_ids[(p_num + days_back) % len(sub_ids)]
            status = 'Present' if (days_back + p_num) % 5 != 0 else 'Absent'
            db.execute('''
                INSERT INTO attendance (user_id, date, period_id, subject_id, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, d.isoformat(), period_ids[p_num % len(period_ids)], sub_id, status))

    db.commit()
    return jsonify({'success': True, 'message': 'Sample data seeded for account'})

# Initialize DB on launch
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(debug=debug, port=port, host='0.0.0.0')

