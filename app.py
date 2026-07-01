import os
import sqlite3
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "teachsphere_secret"
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
PROFILE_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
RESOURCE_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "jpg", "jpeg", "png", "gif", "webp"}


def dict_factory(cursor, row):
    return {column[0]: row[idx] for idx, column in enumerate(cursor.description)}


def get_db():
    connection = sqlite3.connect("teachers.db")
    connection.row_factory = dict_factory
    return connection


def init_db():
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            subject TEXT NOT NULL,
            password TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            type TEXT,
            location TEXT,
            password TEXT NOT NULL,
            about TEXT,
            logo TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER UNIQUE NOT NULL,
            qualification TEXT,
            school TEXT,
            institution_name TEXT,
            experience TEXT,
            bio TEXT,
            profile_photo TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            subject TEXT,
            post_type TEXT DEFAULT 'General',
            author_role TEXT DEFAULT 'teacher',
            file TEXT,
            likes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            subject TEXT NOT NULL,
            file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            downloads INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS seminar_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_teacher_id INTEGER,
            receiver_teacher_id INTEGER,
            title TEXT,
            event_type TEXT,
            event_description TEXT, 
            message TEXT,
            location TEXT, 
            event_date TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS collaborators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            sender_role TEXT NOT NULL,
            receiver_id INTEGER NOT NULL,
            receiver_role TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL
        )
        """
    )

    # Migration: Add created_at column to posts if it doesn't exist
    cursor.execute("PRAGMA table_info(posts)")
    columns = {col["name"] for col in cursor.fetchall()}
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    if 'post_type' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN post_type TEXT DEFAULT 'General'")
    if 'author_role' not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN author_role TEXT DEFAULT 'teacher'")

    cursor.execute("PRAGMA table_info(resources)")
    res_cols = {col["name"] for col in cursor.fetchall()}
    if 'downloads' not in res_cols:
        cursor.execute("ALTER TABLE resources ADD COLUMN downloads INTEGER DEFAULT 0")

    # Migration: Add account_type to teachers and institutions
    cursor.execute("PRAGMA table_info(teachers)")
    teacher_cols = {col["name"] for col in cursor.fetchall()}
    if 'account_type' not in teacher_cols:
        cursor.execute("ALTER TABLE teachers ADD COLUMN account_type TEXT DEFAULT 'teacher'")

    cursor.execute("PRAGMA table_info(institutions)")
    inst_cols = {col["name"] for col in cursor.fetchall()}
    if 'account_type' not in inst_cols:
        cursor.execute("ALTER TABLE institutions ADD COLUMN account_type TEXT DEFAULT 'institution'")

    cursor.execute("PRAGMA table_info(profiles)")
    profile_columns = {col["name"] for col in cursor.fetchall()}
    profile_migrations = {
        "specialization": "ALTER TABLE profiles ADD COLUMN specialization TEXT",
        "research_interests": "ALTER TABLE profiles ADD COLUMN research_interests TEXT",
        "years_experience": "ALTER TABLE profiles ADD COLUMN years_experience TEXT",
        "skills": "ALTER TABLE profiles ADD COLUMN skills TEXT",
        "designation": "ALTER TABLE profiles ADD COLUMN designation TEXT",
        "school_college_university": "ALTER TABLE profiles ADD COLUMN school_college_university TEXT",
        "institution_name": "ALTER TABLE profiles ADD COLUMN institution_name TEXT",
    }
    for column, statement in profile_migrations.items():
        if column not in profile_columns:
            cursor.execute(statement)

    # Migration for institutions table
    cursor.execute("PRAGMA table_info(institutions)")
    inst_columns = {col["name"] for col in cursor.fetchall()}
    inst_migrations = {
        "email": "ALTER TABLE institutions ADD COLUMN email TEXT",
        "type": "ALTER TABLE institutions ADD COLUMN type TEXT",
        "location": "ALTER TABLE institutions ADD COLUMN location TEXT",
        "password": "ALTER TABLE institutions ADD COLUMN password TEXT",
        "about": "ALTER TABLE institutions ADD COLUMN about TEXT",
        "logo": "ALTER TABLE institutions ADD COLUMN logo TEXT",
    }
    for column, statement in inst_migrations.items():
        if column not in inst_columns:
            cursor.execute(statement)

    connection.commit()
    connection.close()
    
    # Add foreign key constraints (SQLite doesn't enforce by default, but good practice)
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    # Note: SQLite ALTER TABLE does not support adding foreign key constraints directly.
    # For existing tables, you'd typically need to recreate the table, copy data, then drop/rename.
    # For this project, we'll add them to the CREATE TABLE statements above for new databases.
    # If the database already exists, these PRAGMA statements will ensure enforcement for future operations.
    # For a real migration, a more robust solution would be needed.
    connection.commit()
    connection.close()




init_db()


def allowed_file(filename, allowed_extensions):
    if not filename:
        return False
    return "." in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_file(file_storage, allowed_extensions):
    if not file_storage or not file_storage.filename:
        return ""

    if not allowed_file(file_storage.filename, allowed_extensions):
        return ""

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    # Generate unique upload filename
    filename = (
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_"
        f"{secure_filename(file_storage.filename)}"
    )
    destination = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(destination)
    return os.path.join("uploads", filename).replace("\\", "/")


def current_user():
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or not role:
        return None

    connection = get_db()
    cursor = connection.cursor()
    table = 'teachers' if role == 'teacher' else 'institutions'
    cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    connection.close()
    if user: user['role'] = role
    return user


def get_profile(teacher_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM profiles WHERE teacher_id = ?", (teacher_id,))
    profile = cursor.fetchone()
    connection.close()
    return profile


@app.context_processor
def inject_nav_profile():
    user = current_user()
    if not user:
        return {"nav_profile": None}

    photo = ""
    if user["role"] == "teacher":
        profile = get_profile(user["id"])
        if profile:
            photo = profile.get("profile_photo") or ""
        profile_url = url_for("profile")
        default_image = "images/default_avatar.svg"
    else:
        photo = user.get("logo") or ""
        profile_url = url_for("institution_profile")
        default_image = "images/default_institution.svg"

    return {
        "nav_profile": {
            "name": user.get("name", "User"),
            "photo": photo,
            "profile_url": profile_url,
            "default_image": default_image,
        }
    }


def get_saved_post_ids(teacher_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute("SELECT post_id FROM saved_posts WHERE teacher_id = ?", (teacher_id,))
    saved = [row['post_id'] for row in cursor.fetchall()]
    connection.close()
    return set(saved)


def get_dashboard_stats():
    connection = get_db()
    cursor = connection.cursor()
    stats = {}
    for key, table in {
        "teachers": "teachers",
        "resources": "resources",
        "posts": "posts",
        "invitations": "seminar_invites",
        "institutions": "institutions",
    }.items():
        cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
        stats[key] = cursor.fetchone()["total"]
    connection.close()
    return stats


POST_TYPES = [
    "Teaching Tip",
    "Achievement",
    "Research",
    "Workshop",
    "Seminar",
    "Collaboration",
    "Resource",
    "General",
]


def profile_completion(profile):
    if not profile:
        return 0

    # Updated required fields as per feature request
    fields = ["qualification", "institution_name", "designation", "experience", "bio", "specialization"]
    completed = sum(1 for field in fields if profile.get(field))
    return round((completed / len(fields)) * 100)


@app.route('/')
def home():
    if current_user(): # Check if user is logged in
        return redirect(url_for('feed'))
    stats = get_dashboard_stats()
    return render_template(
        'dashboard.html',
        stats=stats,
        total_teachers=stats.get('teachers', 0),
        total_institutions=stats.get('institutions', 0),
        total_resources=stats.get('resources', 0),
        total_seminars=stats.get('invitations', 0)
    )


@app.route('/dashboard')
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        '''
        SELECT profiles.*
        FROM profiles
        WHERE profiles.teacher_id = ?
        ''',
        (user['id'],)
    )
    profile = cursor.fetchone()

    # Calculate completion
    completion = profile_completion(profile)

    # Fetch featured teachers (excluding current user)
    cursor.execute('''
        SELECT teachers.id, teachers.name, teachers.subject, profiles.profile_photo 
        FROM teachers 
        LEFT JOIN profiles ON teachers.id = profiles.teacher_id 
        WHERE teachers.id != ? 
        LIMIT 4
    ''', (user['id'],))
    featured_teachers = cursor.fetchall()

    # Fetch recent resources
    cursor.execute('''
        SELECT resources.*, teachers.name as author 
        FROM resources 
        JOIN teachers ON resources.teacher_id = teachers.id 
        ORDER BY resources.created_at DESC LIMIT 5
    ''')
    recent_resources = cursor.fetchall()

    cursor.execute(
        '''
        SELECT seminar_invites.*, teachers.name AS sender_name
        FROM seminar_invites
        JOIN teachers ON teachers.id = seminar_invites.sender_teacher_id
        WHERE seminar_invites.receiver_teacher_id = ? AND seminar_invites.status = 'Pending'
        ORDER BY seminar_invites.event_date ASC
        LIMIT 5
        ''',
        (user['id'],)
    )
    upcoming_invitations = cursor.fetchall()
    connection.close()

    return render_template(
        'user_dashboard.html',
        user=user,
        profile=profile,
        stats=get_dashboard_stats(),
        completion=completion,
        featured_teachers=featured_teachers,
        recent_resources=recent_resources,
        upcoming_invitations=upcoming_invitations,
    )

@app.route('/community/<path:inst_name>')
def workplace_community(inst_name):
    user = current_user()
    if not user: return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()

    # Members
    cursor.execute('''
        SELECT teachers.name, teachers.subject, profiles.* FROM teachers
        JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ?
    ''', (inst_name,))
    members = cursor.fetchall()

    # Community Posts
    cursor.execute('''
        SELECT posts.*, teachers.name AS author_name FROM posts
        JOIN teachers ON posts.teacher_id = teachers.id
        JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ?
          AND (posts.author_role IS NULL OR posts.author_role = 'teacher')
        ORDER BY posts.created_at DESC
    ''', (inst_name,))
    posts = cursor.fetchall()

    # Community Resources
    cursor.execute('''
        SELECT resources.*, teachers.name AS author_name FROM resources
        JOIN teachers ON resources.teacher_id = teachers.id
        JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ? ORDER BY resources.created_at DESC
    ''', (inst_name,))
    resources = cursor.fetchall()

    connection.close()
    return render_template('community.html', user=user, inst_name=inst_name, members=members, posts=posts, resources=resources)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        account_type = request.form.get('account_type', 'teacher')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if account_type == 'teacher':
            subject = request.form.get('subject', '').strip()
            if not (name and email and subject and password):
                error = 'Please complete every field.'
            else:
                connection = get_db()
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        'INSERT INTO teachers (name, email, subject, password, account_type) VALUES (?, ?, ?, ?, ?)',
                        (name, email, subject, password, 'teacher')
                    )
                    connection.commit()
                    connection.close()
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    error = 'This email is already registered.'
                    connection.close()
        else:
            inst_type = request.form.get('type', '').strip()
            location = request.form.get('location', '').strip()
            if not (name and email and inst_type and location and password):
                error = 'Please complete every field.'
            else:
                connection = get_db()
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        'INSERT INTO institutions (name, email, type, location, password, about, logo, account_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (name, email, inst_type, location, password, '', '', 'institution')
                    )
                    connection.commit()
                    connection.close()
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    error = 'This email is already registered.'
                    connection.close()

    return render_template('register.html', error=error or None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        print(f"DEBUG - LOGIN ATTEMPT - EMAIL: {email}")

        if not email or "@" not in email:
            error = 'Invalid email address.'
            return render_template('login.html', error=error)

        connection = get_db()
        cursor = connection.cursor()

        # Check teachers table
        cursor.execute('SELECT * FROM teachers WHERE email = ?', (email,))
        user = cursor.fetchone()
        print(f"DEBUG - TEACHER QUERY RESULT: {user}")

        if user:
            if user['password'] == password:
                session['user_id'] = user['id']
                session['role'] = 'teacher'

                # Feature 2: Check Profile Completion
                cursor.execute("SELECT * FROM profiles WHERE teacher_id = ?", (user['id'],))
                profile = cursor.fetchone()
                
                required_fields = ["qualification", "institution_name", "designation", "experience", "bio", "specialization"]
                is_complete = profile is not None and all(profile.get(f) for f in required_fields)
                
                session['profile_completed'] = is_complete
                connection.close()
                return redirect(url_for('teacher_dashboard'))
            else:
                error = 'Invalid password.'
        else:
            # Check institutions table
            cursor.execute('SELECT * FROM institutions WHERE email = ?', (email,))
            institution = cursor.fetchone()
            print(f"DEBUG - INSTITUTION QUERY RESULT: {institution}")

            if institution:
                if institution['password'] == password:
                    session['user_id'] = institution['id']
                    session['role'] = 'institution'
                    connection.close()
                    # Redirect institutions to dashboard
                    return redirect(url_for('institution_dashboard'))
                else:
                    error = 'Invalid password.'
            else:
                error = 'Account not found.'

        connection.close()

    return render_template('login.html', error=error or None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    # Redirect institutions to their profile page
    if user and user.get('role') == 'institution':
        return redirect(url_for('institution_profile'))

    profile_data = get_profile(user['id'])
    completion = profile_completion(profile_data)
    error = None

    if request.method == 'POST':
        qualification = request.form.get('qualification', '').strip()
        school_college_university = request.form.get('school_college_university', '').strip()
        institution_name = request.form.get('institution_name', '').strip()
        experience = request.form.get('experience', '').strip()
        specialization = request.form.get('specialization', '').strip()
        research_interests = request.form.get('research_interests', '').strip()
        designation = request.form.get('designation', '').strip()
        years_experience = request.form.get('years_experience', '').strip()
        skills = request.form.get('skills', '').strip()
        achievements = request.form.get('achievements', '').strip()
        bio = request.form.get('bio', '').strip()
        photo_path = save_file(request.files.get('profile_photo'), PROFILE_PHOTO_EXTENSIONS) or (profile_data['profile_photo'] if profile_data and profile_data['profile_photo'] else '')

        if not (qualification and institution_name and experience and bio and designation and specialization):
            error = 'Please fill in all required profile fields.'
        else:
            connection = get_db()
            cursor = connection.cursor()
            if profile_data:
                cursor.execute(
                    '''
                    UPDATE profiles
                    SET qualification = ?, school_college_university = ?, school = ?, institution_name = ?, experience = ?, bio = ?, profile_photo = ?,
                        specialization = ?, research_interests = ?, designation = ?, years_experience = ?,
                        skills = ?, achievements = ?
                    WHERE teacher_id = ?
                    ''',
                    (
                        qualification,
                        school_college_university,
                        school_college_university,
                        institution_name,
                        experience,
                        bio,
                        photo_path,
                        specialization,
                        research_interests,
                        designation,
                        years_experience,
                        skills,
                        achievements,
                        user['id'],
                    )
                )
            else:
                cursor.execute(
                    '''
                    INSERT INTO profiles (
                        teacher_id, qualification, school_college_university, school, institution_name, experience, bio, profile_photo, specialization, research_interests, designation, years_experience, skills, achievements
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        user['id'],
                        qualification,
                        school_college_university,
                        school_college_university,
                        institution_name,
                        experience,
                        bio,
                        photo_path,
                        specialization,
                        research_interests,
                        designation,
                        years_experience,
                        skills,
                        achievements,
                    )
                )
            connection.commit()
            connection.close()
            session['profile_completed'] = True
            flash('Profile completed successfully!')
            return redirect(url_for('feed'))
    
    return render_template('profile.html', user=user, profile=profile_data, error=error, post_types=POST_TYPES, completion=completion)


@app.route('/feed', methods=['GET', 'POST'])
def feed():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        subject = request.form.get('subject', '').strip()
        post_type = request.form.get('post_type', 'General').strip()
        if post_type not in POST_TYPES:
            post_type = 'General'
        attachment = save_file(request.files.get('attachment'), RESOURCE_EXTENSIONS)

        if title and content:
            connection = get_db()
            cursor = connection.cursor()
            cursor.execute(
                '''
                INSERT INTO posts (teacher_id, title, content, subject, post_type, author_role, file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (user['id'], title, content, subject, post_type, 'teacher', attachment, datetime.utcnow().isoformat())
            )
            connection.commit()
            connection.close()
            return redirect(url_for('feed'))

    subject_filter = request.args.get('subject', '').strip()
    post_type_filter = request.args.get('post_type', '').strip()
    saved_only = request.args.get('saved') == '1'

    connection = get_db()
    cursor = connection.cursor()
    query = '''
        SELECT posts.*, teachers.name AS author_name, teachers.subject AS author_subject,
               profiles.school AS author_school, profiles.profile_photo AS author_photo,
               profiles.specialization AS author_specialization,
               COUNT(comments.id) AS comment_count
        FROM posts
        JOIN teachers ON posts.teacher_id = teachers.id
        LEFT JOIN profiles ON profiles.teacher_id = teachers.id
        LEFT JOIN comments ON comments.post_id = posts.id
    '''
    conditions = []
    params = []
    conditions.append("(posts.author_role IS NULL OR posts.author_role = 'teacher')")

    if subject_filter:
        conditions.append('posts.subject LIKE ?')
        params.append(f'%{subject_filter}%')

    if post_type_filter:
        conditions.append('posts.post_type = ?')
        params.append(post_type_filter)

    if saved_only:
        conditions.append('posts.id IN (SELECT post_id FROM saved_posts WHERE teacher_id = ?)')
        params.append(user['id'])

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY posts.id ORDER BY posts.id DESC'
    cursor.execute(query, params)
    posts = cursor.fetchall()

    cursor.execute(
        '''
        SELECT comments.*, teachers.name AS teacher_name
        FROM comments
        JOIN teachers ON teachers.id = comments.teacher_id
        ORDER BY comments.created_at ASC
        '''
    )
    comments_by_post = {}
    for comment in cursor.fetchall():
        comments_by_post.setdefault(comment['post_id'], []).append(comment)

    cursor.execute('SELECT COUNT(*) AS total FROM saved_posts WHERE teacher_id = ?', (user['id'],))
    saved_count = cursor.fetchone()['total']
    saved_ids = get_saved_post_ids(user['id'])
    connection.close()

    return render_template(
        'feed.html',
        user=user,
        posts=posts,
        saved_ids=saved_ids,
        saved_count=saved_count,
        subject_filter=subject_filter,
        post_type_filter=post_type_filter,
        post_types=POST_TYPES,
        saved_only=saved_only
        ,
        comments_by_post=comments_by_post
    )


@app.route('/institution-feed', methods=['GET', 'POST'])
def institution_feed():
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        attachment = save_file(request.files.get('attachment'), RESOURCE_EXTENSIONS)

        if not (title and content):
            error = 'Post title and content are required.'
        else:
            connection = get_db()
            cursor = connection.cursor()
            cursor.execute(
                '''
                INSERT INTO posts (teacher_id, title, content, subject, post_type, author_role, file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    user['id'],
                    title,
                    content,
                    user.get('type') or 'Institution',
                    'Institution Update',
                    'institution',
                    attachment,
                    datetime.utcnow().isoformat(),
                )
            )
            connection.commit()
            connection.close()
            return redirect(url_for('institution_feed'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        '''
        SELECT posts.*, institutions.name AS institution_name, institutions.logo AS institution_logo
        FROM posts
        JOIN institutions ON institutions.id = posts.teacher_id
        WHERE posts.author_role = 'institution'
        ORDER BY posts.created_at DESC
        '''
    )
    posts = cursor.fetchall()
    connection.close()
    return render_template('institution_feed.html', user=user, posts=posts, error=error)


@app.route('/institution-feed/<int:post_id>/delete', methods=['POST'])
def delete_institution_post(post_id):
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM posts WHERE id = ? AND teacher_id = ? AND author_role = 'institution'",
        (post_id, user['id'])
    )
    connection.commit()
    connection.close()
    return redirect(url_for('institution_feed'))


@app.route('/posts/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    comment = request.form.get('comment', '').strip()
    if comment:
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            '''
            INSERT INTO comments (post_id, teacher_id, comment, created_at)
            VALUES (?, ?, ?, ?)
            ''',
            (post_id, user['id'], comment, datetime.utcnow().isoformat())
        )
        connection.commit()
        connection.close()

    return redirect(request.referrer or url_for('feed'))


@app.route('/post-action/<int:post_id>/<action>', methods=['POST'])
def post_action(post_id, action):
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    if action not in {'save', 'like'}:
        return redirect(url_for('feed'))

    connection = get_db()
    cursor = connection.cursor()

    if action == 'save':
        cursor.execute(
            'SELECT 1 FROM saved_posts WHERE teacher_id = ? AND post_id = ?',
            (user['id'], post_id)
        )
        if not cursor.fetchone():
            cursor.execute(
                'INSERT INTO saved_posts (teacher_id, post_id) VALUES (?, ?)',
                (user['id'], post_id)
            )
    else:
        cursor.execute(
            'UPDATE posts SET likes = likes + 1 WHERE id = ?',
            (post_id,)
        )

    connection.commit()
    connection.close()
    return redirect(request.referrer or url_for('feed'))


@app.route('/resources', methods=['GET', 'POST'])
def resources():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        subject = request.form.get('subject', '').strip()
        attachment = save_file(request.files.get('file'), RESOURCE_EXTENSIONS)

        if not (title and description and subject and attachment):
            error = 'All resource fields are required, and attachments must be PDF, DOC, or PPT.'
        else:
            connection = get_db()
            cursor = connection.cursor()
            cursor.execute(
                '''
                INSERT INTO resources (teacher_id, title, description, subject, file, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (user['id'], title, description, subject, attachment, datetime.utcnow().isoformat())
            )
            connection.commit()
            connection.close()
            return redirect(url_for('resources'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        '''
        SELECT resources.*, teachers.name AS author_name
        FROM resources
        JOIN teachers ON resources.teacher_id = teachers.id
        ORDER BY resources.created_at DESC
        '''
    )
    resources_list = cursor.fetchall()
    connection.close()

    return render_template('resources.html', user=user, resources=resources_list, error=error)

@app.route('/resources/download/<int:resource_id>')
def download_resource(resource_id):
    user = current_user()
    if not user: return redirect(url_for('login'))
    
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT file FROM resources WHERE id = ?', (resource_id,))
    resource = cursor.fetchone()

    if not resource:
        connection.close()
        abort(404)

    cursor.execute('UPDATE resources SET downloads = downloads + 1 WHERE id = ?', (resource_id,))
    connection.commit()
    connection.close()
    return redirect(url_for('static', filename=resource['file']))


@app.route('/directory')
def directory():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    name_query = request.args.get('name', '').strip()
    subject_query = request.args.get('subject', '').strip()
    expertise_query = request.args.get('expertise', '').strip()

    connection = get_db()
    cursor = connection.cursor()
    # Fetch matching teachers
    query = '''
        SELECT teachers.*,
               profiles.qualification,
               profiles.school_college_university,
               profiles.school,
               profiles.experience,
               profiles.profile_photo,
               profiles.specialization,
               profiles.research_interests,
               profiles.years_experience,
               profiles.institution_name
        FROM teachers
        LEFT JOIN profiles ON profiles.teacher_id = teachers.id
        WHERE teachers.name LIKE ?
          AND teachers.subject LIKE ?
    '''
    params = [f'%{name_query}%', f'%{subject_query}%']

    if expertise_query:
        query += '''
          AND (
              profiles.specialization LIKE ?
              OR profiles.research_interests LIKE ?
              OR profiles.qualification LIKE ?
              OR profiles.skills LIKE ?
          )
        '''
        params.extend([f'%{expertise_query}%'] * 4)

    query += ' ORDER BY teachers.name'
    cursor.execute(query, params)
    teachers = cursor.fetchall()

    # Enrich with collaboration status
    for t in teachers:
        cursor.execute(
            "SELECT status, sender_id FROM collaborators WHERE ((sender_id = ? AND sender_role = ?) AND (receiver_id = ? AND receiver_role = 'teacher')) OR ((receiver_id = ? AND receiver_role = ?) AND (sender_id = ? AND sender_role = 'teacher'))",
            (user['id'], user['role'], t['id'], user['id'], user['role'], t['id'])
        )
        rel = cursor.fetchone()
        t['collab_status'] = rel['status'] if rel else None
        t['is_sender'] = rel['sender_id'] == user['id'] if rel else False

    connection.close()

    return render_template(
        'directory.html',
        user=user,
        teachers=teachers,
        name_query=name_query,
        subject_query=subject_query,
        expertise_query=expertise_query
    )


@app.route('/invite/<int:teacher_id>', methods=['GET', 'POST'])
def invite_teacher(teacher_id):
    sender = current_user()
    if not sender:
        return redirect(url_for('login'))

    # Only teachers can send seminar invitations
    if sender['role'] != 'teacher':
        return redirect(url_for('institution_dashboard'))

    if sender['id'] == teacher_id:
        return redirect(url_for('teacher_profile', teacher_id=teacher_id))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
    receiver = cursor.fetchone()

    if not receiver:
        connection.close()
        abort(404)

    error = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        event_description = request.form.get('event_description', '').strip()
        event_type = request.form.get('event_type', '').strip()
        event_date = request.form.get('event_date', '').strip()
        location = request.form.get('location', '').strip()
        message = request.form.get('message', '').strip()

        if not (title and event_type and event_date and message and event_description and location):
            error = 'Please complete every invitation field.'
        else:
            cursor.execute(
                '''
                INSERT INTO seminar_invites (
                    sender_teacher_id, receiver_teacher_id, title, event_type, event_description,
                    message, location, event_date, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    sender['id'],
                    receiver['id'],
                    title,
                    event_type,
                    event_description,
                    message,
                    location,
                    event_date,
                    'Pending',
                    datetime.utcnow().isoformat(),
                )
            )
            connection.commit()
            connection.close()
            return redirect(url_for('invitations'))

    connection.close()
    return render_template(
        'invite_teacher.html',
        user=sender,
        receiver=receiver,
        error=error,
        today=date.today().isoformat()
    )


@app.route('/invitations')
def invitations():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if user.get('role') != 'teacher':
        return redirect(url_for('institution_dashboard'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT c.id AS request_id, t.id AS teacher_id, t.name, t.subject,
               p.profile_photo, p.institution_name
        FROM collaborators c
        JOIN teachers t ON c.sender_id = t.id
        LEFT JOIN profiles p ON t.id = p.teacher_id
        WHERE c.receiver_id = ?
          AND c.receiver_role = 'teacher'
          AND c.sender_role = 'teacher'
          AND c.status = 'pending'
        ORDER BY c.created_at DESC
        """,
        (user['id'],)
    )
    received = cursor.fetchall()

    cursor.execute(
        """
        SELECT c.id AS request_id, t.id AS teacher_id, t.name, t.subject,
               p.profile_photo, p.institution_name, c.status
        FROM collaborators c
        JOIN teachers t ON c.receiver_id = t.id
        LEFT JOIN profiles p ON t.id = p.teacher_id
        WHERE c.sender_id = ?
          AND c.sender_role = 'teacher'
          AND c.receiver_role = 'teacher'
          AND c.status = 'pending'
        ORDER BY c.created_at DESC
        """,
        (user['id'],)
    )
    sent = cursor.fetchall()

    cursor.execute(
        """
        SELECT c.id AS request_id,
               CASE WHEN c.sender_id = ? THEN receiver.id ELSE sender.id END AS teacher_id,
               CASE WHEN c.sender_id = ? THEN receiver.name ELSE sender.name END AS name,
               CASE WHEN c.sender_id = ? THEN receiver.subject ELSE sender.subject END AS subject,
               p.profile_photo,
               p.institution_name
        FROM collaborators c
        JOIN teachers sender ON c.sender_id = sender.id
        JOIN teachers receiver ON c.receiver_id = receiver.id
        LEFT JOIN profiles p
          ON p.teacher_id = CASE WHEN c.sender_id = ? THEN receiver.id ELSE sender.id END
        WHERE c.status = 'accepted'
          AND c.sender_role = 'teacher'
          AND c.receiver_role = 'teacher'
          AND (c.sender_id = ? OR c.receiver_id = ?)
        ORDER BY c.created_at DESC
        """,
        (user['id'], user['id'], user['id'], user['id'], user['id'], user['id'])
    )
    accepted = cursor.fetchall()
    connection.close()

    return render_template('invitations.html', user=user, received=received, sent=sent, accepted=accepted)


@app.route('/invitations/<int:invite_id>/<action>', methods=['POST'])
def invitation_action(invite_id, action):
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if user.get('role') != 'teacher':
        return redirect(url_for('login'))

    if action not in {'accept', 'reject'}:
        return redirect(url_for('invitations'))

    connection = get_db()
    cursor = connection.cursor()
    if action == 'accept':
        cursor.execute(
            """
            UPDATE collaborators
            SET status = 'accepted'
            WHERE id = ?
              AND receiver_id = ?
              AND receiver_role = 'teacher'
              AND sender_role = 'teacher'
              AND status = 'pending'
            """,
            (invite_id, user['id'])
        )
    else:
        cursor.execute(
            """
            DELETE FROM collaborators
            WHERE id = ?
              AND receiver_id = ?
              AND receiver_role = 'teacher'
              AND sender_role = 'teacher'
              AND status = 'pending'
            """,
            (invite_id, user['id'])
        )
    connection.commit()
    connection.close()
    return redirect(url_for('invitations'))


@app.route('/teacher/<int:teacher_id>')
@app.route('/teachers/<int:teacher_id>')
def teacher_profile(teacher_id):
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
    teacher = cursor.fetchone()

    if not teacher:
        connection.close()
        return redirect(url_for('directory'))

    cursor.execute(
        '''
        SELECT profiles.*
        FROM profiles
        WHERE profiles.teacher_id = ?
        ''',
        (teacher_id,)
    )
    profile = cursor.fetchone()

    cursor.execute(
        "SELECT * FROM posts WHERE teacher_id = ? AND (author_role IS NULL OR author_role = 'teacher') ORDER BY created_at DESC LIMIT 5",
        (teacher_id,)
    )
    posts = cursor.fetchall()

    cursor.execute('SELECT * FROM resources WHERE teacher_id = ? ORDER BY created_at DESC', (teacher_id,))
    resources = cursor.fetchall()
    connection.close()

    return render_template('teacher_profile.html', user=current_user(), teacher=teacher, profile=profile, posts=posts, resources=resources)


@app.route('/posts/<int:post_id>/edit', methods=['GET', 'POST'])
def edit_post(post_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT * FROM posts WHERE id = ? AND teacher_id = ? AND (author_role IS NULL OR author_role = 'teacher')",
        (post_id, user['id'])
    )
    post = cursor.fetchone()

    if not post:
        connection.close()
        return redirect(url_for('feed'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        subject = request.form.get('subject', '').strip()
        post_type = request.form.get('post_type', 'General').strip()
        if post_type not in POST_TYPES:
            post_type = 'General'
        
        new_attachment = request.files.get('attachment')
        if new_attachment and new_attachment.filename:
            attachment_path = save_file(new_attachment, RESOURCE_EXTENSIONS)
        else:
            attachment_path = post['file']

        if title and content:
            cursor.execute(
                '''
                UPDATE posts
                SET title = ?, content = ?, subject = ?, post_type = ?, file = ?
                WHERE id = ? AND teacher_id = ? AND (author_role IS NULL OR author_role = 'teacher')
                ''',
                (title, content, subject, post_type, attachment_path, post_id, user['id'])
            )
            connection.commit()
            connection.close()
            return redirect(url_for('feed'))
        else:
            connection.close()
            return render_template('edit_post_modal.html', post=post, post_types=POST_TYPES, error="Title and content are required.")

    connection.close()
    return render_template('edit_post_modal.html', post=post, post_types=POST_TYPES)

@app.route('/posts/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM posts WHERE id = ? AND teacher_id = ? AND (author_role IS NULL OR author_role = 'teacher')",
        (post_id, user['id'])
    )
    connection.commit()
    connection.close()
    return redirect(url_for('feed'))

@app.route('/faculty')
def faculty():
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    
    # 1. Faculty Members list
    cursor.execute('''
        SELECT teachers.id, teachers.name, teachers.subject, profiles.profile_photo, 
               profiles.qualification, profiles.designation, profiles.years_experience, profiles.experience
        FROM teachers JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ? ORDER BY teachers.name ASC
    ''', (user['name'],))
    faculty_list = cursor.fetchall()

    # 2. Statistics
    cursor.execute('SELECT COUNT(*) AS total FROM profiles WHERE institution_name = ?', (user['name'],))
    teachers_count = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(DISTINCT subject) AS total FROM teachers WHERE id IN (SELECT teacher_id FROM profiles WHERE institution_name = ?)', (user['name'],))
    dept_count = cursor.fetchone()['total']
    
    cursor.execute('''
        SELECT name FROM teachers 
        JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ? 
        ORDER BY teachers.id DESC LIMIT 3
    ''', (user['name'],))
    recent = [r['name'] for r in cursor.fetchall()]
    recent_joined = ", ".join(recent) if recent else "None"

    connection.close()
    return render_template('faculty_members.html', 
                           user=user, 
                           faculty=faculty_list, 
                           teachers_count=teachers_count, 
                           dept_count=dept_count, 
                           recent_joined=recent_joined)

@app.route('/institution/dashboard')
def institution_dashboard():
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    
    # Dashboard Statistics
    cursor.execute('SELECT COUNT(*) AS total FROM profiles WHERE institution_name = ?', (user['name'],))
    teachers_count = cursor.fetchone()['total']
    
    cursor.execute(
        'SELECT COUNT(*) AS total FROM resources WHERE teacher_id IN (SELECT teacher_id FROM profiles WHERE institution_name = ?)',
        (user['name'],)
    )
    resources_count = cursor.fetchone()['total']
    
    cursor.execute(
        "SELECT COUNT(*) AS total FROM posts WHERE (author_role IS NULL OR author_role = 'teacher') AND teacher_id IN (SELECT teacher_id FROM profiles WHERE institution_name = ?)",
        (user['name'],)
    )
    posts_count = cursor.fetchone()['total']

    cursor.execute(
        "SELECT COUNT(*) AS total FROM posts WHERE teacher_id = ? AND author_role = 'institution'",
        (user['id'],)
    )
    institution_posts_count = cursor.fetchone()['total']

    cursor.execute(
        "SELECT COUNT(*) AS total FROM collaborators WHERE (sender_id = ? AND sender_role = 'institution' AND status = 'accepted') OR (receiver_id = ? AND receiver_role = 'institution' AND status = 'accepted')",
        (user['id'], user['id'])
    )
    collabs_count = cursor.fetchone()['total']
    
    # Faculty Members (Linked teachers based on institution name)
    cursor.execute('''
        SELECT teachers.id, teachers.name, teachers.subject, profiles.profile_photo, 
               profiles.qualification, profiles.designation, profiles.years_experience, profiles.experience
        FROM teachers JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ? ORDER BY teachers.name ASC
    ''', (user['name'],))
    faculty_members = cursor.fetchall()

    cursor.execute('''
        SELECT resources.*, teachers.name as author_name 
        FROM resources JOIN teachers ON resources.teacher_id = teachers.id
        JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE profiles.institution_name = ? ORDER BY resources.created_at DESC LIMIT 5
    ''', (user['name'],))
    recent_resources = cursor.fetchall()

    cursor.execute(
        '''
        SELECT *
        FROM posts
        WHERE teacher_id = ? AND author_role = 'institution'
        ORDER BY created_at DESC LIMIT 5
        ''',
        (user['id'],)
    )
    recent_institution_posts = cursor.fetchall()

    # Suggestions
    # Suggest collaborators not already connected
    cursor.execute('''
        SELECT id, name, type, location, logo FROM institutions 
        WHERE id != ? AND id NOT IN (
            SELECT receiver_id FROM collaborators WHERE sender_id = ? AND sender_role = 'institution'
            UNION
            SELECT sender_id FROM collaborators WHERE receiver_id = ? AND receiver_role = 'institution'
        ) LIMIT 3
    ''', (user['id'], user['id'], user['id']))
    suggested_institutions = cursor.fetchall()
    
    connection.close()
    return render_template(
        'institution_dashboard.html',
        user=user,
        teachers_count=teachers_count,
        resources_count=resources_count,
        posts_count=posts_count,
        institution_posts_count=institution_posts_count,
        collabs_count=collabs_count,
        faculty_members=faculty_members,
        recent_resources=recent_resources,
        recent_institution_posts=recent_institution_posts,
        suggested_institutions=suggested_institutions
    )

@app.route('/teacher-dashboard')
def teacher_dashboard():
    user = current_user()
    if not user or user.get('role') != 'teacher':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) AS total FROM posts WHERE teacher_id = ? AND (author_role IS NULL OR author_role = 'teacher')",
        (user['id'],)
    )
    posts_count = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM resources WHERE teacher_id = ?", (user['id'],))
    resources_count = cursor.fetchone()['total']

    cursor.execute(
        "SELECT COUNT(*) AS total FROM collaborators WHERE (sender_id = ? OR receiver_id = ?) AND status = 'accepted' AND sender_role = 'teacher' AND receiver_role = 'teacher'",
        (user['id'], user['id'])
    )
    peers_count = cursor.fetchone()['total']

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM collaborators
        WHERE (sender_id = ? OR receiver_id = ?)
          AND sender_role = 'teacher'
          AND receiver_role = 'teacher'
          AND status = 'pending'
        """,
        (user['id'], user['id'])
    )
    pending_count = cursor.fetchone()['total']

    cursor.execute("SELECT posts.*, teachers.name AS author_name FROM posts JOIN teachers ON posts.teacher_id = teachers.id WHERE (posts.author_role IS NULL OR posts.author_role = 'teacher') ORDER BY posts.created_at DESC LIMIT 5")
    recent_posts = cursor.fetchall()

    cursor.execute("SELECT resources.*, teachers.name AS author_name FROM resources JOIN teachers ON resources.teacher_id = teachers.id ORDER BY resources.created_at DESC LIMIT 5")
    recent_resources = cursor.fetchall()

    cursor.execute('''
        SELECT teachers.id, teachers.name, teachers.subject, profiles.profile_photo, profiles.institution_name
        FROM teachers LEFT JOIN profiles ON teachers.id = profiles.teacher_id
        WHERE teachers.id != ? AND teachers.id NOT IN (
            SELECT receiver_id FROM collaborators WHERE sender_id = ? AND sender_role = 'teacher'
            UNION
            SELECT sender_id FROM collaborators WHERE receiver_id = ? AND receiver_role = 'teacher'
        ) LIMIT 4
    ''', (user['id'], user['id'], user['id']))
    suggested_peers = cursor.fetchall()

    connection.close()
    return render_template('teacher_dashboard.html', user=user, posts_count=posts_count, resources_count=resources_count, peers_count=peers_count, pending_count=pending_count, recent_posts=recent_posts, recent_resources=recent_resources, suggested_peers=suggested_peers)

@app.route('/my-peers')
def my_peers():
    user = current_user()
    if not user or user.get('role') != 'teacher':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()
    
    cursor.execute('''
        SELECT CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END as target_id
        FROM collaborators WHERE (sender_id = ? OR receiver_id = ?) AND status = 'accepted' AND sender_role = 'teacher' AND receiver_role = 'teacher'
    ''', (user['id'], user['id'], user['id']))
    rows = cursor.fetchall()
    
    active_peers = []
    for r in rows:
        cursor.execute("SELECT t.id, t.name, t.subject, p.profile_photo, p.institution_name FROM teachers t LEFT JOIN profiles p ON t.id = p.teacher_id WHERE t.id = ?", (r['target_id'],))
        peer = cursor.fetchone()
        if peer: active_peers.append(peer)

    cursor.execute('''
        SELECT c.id as request_id, t.id as teacher_id, t.name, t.subject, p.profile_photo
        FROM collaborators c JOIN teachers t ON c.sender_id = t.id
        LEFT JOIN profiles p ON t.id = p.teacher_id
        WHERE c.receiver_id = ? AND c.receiver_role = 'teacher' AND c.sender_role = 'teacher' AND c.status = 'pending'
    ''', (user['id'],))
    pending_received = cursor.fetchall()

    cursor.execute('''
        SELECT c.id as request_id, t.id as teacher_id, t.name, t.subject, p.profile_photo
        FROM collaborators c JOIN teachers t ON c.receiver_id = t.id
        LEFT JOIN profiles p ON t.id = p.teacher_id
        WHERE c.sender_id = ? AND c.sender_role = 'teacher' AND c.receiver_role = 'teacher' AND c.status = 'pending'
    ''', (user['id'],))
    pending_sent = cursor.fetchall()

    cursor.execute('''
        SELECT t.id, t.name, t.subject, p.profile_photo, p.institution_name FROM teachers t 
        LEFT JOIN profiles p ON t.id = p.teacher_id
        WHERE t.id != ? AND t.id NOT IN (
            SELECT receiver_id FROM collaborators WHERE sender_id = ? AND sender_role = 'teacher'
            UNION
            SELECT sender_id FROM collaborators WHERE receiver_id = ? AND receiver_role = 'teacher'
        ) LIMIT 10
    ''', (user['id'], user['id'], user['id']))
    suggestions = cursor.fetchall()

    connection.close() # Pass both pending lists
    return render_template('my_peers.html', user=user, active_peers=active_peers, pending_received=pending_received, pending_sent=pending_sent, suggestions=suggestions)

@app.route('/network')
def network():
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute('''
        SELECT CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END as target_id
        FROM collaborators WHERE (sender_id = ? OR receiver_id = ?) AND status = 'accepted' AND sender_role = 'institution' AND receiver_role = 'institution'
    ''', (user['id'], user['id'], user['id']))
    rows = cursor.fetchall()
    
    partners = []
    for r in rows:
        cursor.execute("SELECT id, name, type, location, logo FROM institutions WHERE id = ?", (r['target_id'],))
        partner = cursor.fetchone()
        if partner: partners.append(partner)

    cursor.execute('''
        SELECT c.id as request_id, i.id as institution_id, i.name, i.type, i.logo
        FROM collaborators c JOIN institutions i ON c.sender_id = i.id
        WHERE c.receiver_id = ? AND c.receiver_role = 'institution' AND c.sender_role = 'institution' AND c.status = 'pending'
    ''', (user['id'],))
    pending_received_inst = cursor.fetchall()

    cursor.execute('''
        SELECT c.id as request_id, i.id as institution_id, i.name, i.type, i.logo
        FROM collaborators c JOIN institutions i ON c.receiver_id = i.id
        WHERE c.sender_id = ? AND c.sender_role = 'institution' AND c.receiver_role = 'institution' AND c.status = 'pending'
    ''', (user['id'],))
    pending_sent_inst = cursor.fetchall()

    cursor.execute('''
        SELECT id, name, type, location, logo FROM institutions 
        WHERE id != ? AND id NOT IN (
            SELECT receiver_id FROM collaborators WHERE sender_id = ? AND sender_role = 'institution'
            UNION
            SELECT sender_id FROM collaborators WHERE receiver_id = ? AND receiver_role = 'institution'
        ) LIMIT 10
    ''', (user['id'], user['id'], user['id']))
    suggestions = cursor.fetchall()

    connection.close()
    return render_template('network.html', user=user, partners=partners, pending_received_inst=pending_received_inst, pending_sent_inst=pending_sent_inst, suggestions=suggestions)

@app.route('/collaborators')
def collaborators():
    user = current_user()
    if not user: return redirect(url_for('login'))
    return redirect(url_for('my_peers' if user['role'] == 'teacher' else 'network'))

@app.route('/collaborate/<int:target_id>/<string:target_role>/<string:action>')
def collaborate_action(target_id, target_role, action):
    user = current_user()
    if not user: return redirect(url_for('login'))
    
    connection = get_db()
    cursor = connection.cursor()
    
    if action == 'request':
        # Strictly enforce role matching for collaborations
        if user['role'] != target_role:
            connection.close()
            return redirect(request.referrer or url_for('feed'))
        # Prevent duplicate requests in both directions
        cursor.execute(
            '''
            SELECT id
            FROM collaborators
            WHERE (sender_id = ? AND sender_role = ? AND receiver_id = ? AND receiver_role = ?)
               OR (sender_id = ? AND sender_role = ? AND receiver_id = ? AND receiver_role = ?)
            ''',
            (user['id'], user['role'], target_id, target_role,
             target_id, target_role, user['id'], user['role'])
        )
        existing = cursor.fetchone()

        if not existing:
            cursor.execute("INSERT INTO collaborators (sender_id, sender_role, receiver_id, receiver_role) VALUES (?, ?, ?, ?)",
                           (user['id'], user['role'], target_id, target_role))
    elif action == 'accept': # target_id here is the collaboration request ID
        cursor.execute("UPDATE collaborators SET status = 'accepted' WHERE id = ?", (target_id,))
    elif action == 'decline' or action == 'cancel' or action == 'remove':
        # Using target_id as the primary key of the collaborator record for these actions
        cursor.execute("DELETE FROM collaborators WHERE id = ?", (target_id,))
    
    connection.commit()
    connection.close()
    if user['role'] == 'teacher':
        return redirect(url_for('my_peers'))
    return redirect(url_for('network'))

@app.route('/institution/profile', methods=['GET', 'POST'])
def institution_profile():
    user = current_user()
    if not user or user.get('role') != 'institution':
        return redirect(url_for('login'))

    if request.method == 'POST':
        about = request.form.get('about', '').strip()
        inst_type = request.form.get('type', '').strip()
        location = request.form.get('location', '').strip()
        logo = save_file(request.files.get('logo'), PROFILE_PHOTO_EXTENSIONS) or user['logo']

        connection = get_db()
        cursor = connection.cursor()
        cursor.execute(
            '''
            UPDATE institutions
            SET about = ?, type = ?, location = ?, logo = ?
            WHERE id = ?
            ''',
            (about, inst_type, location, logo, user['id'])
        )
        connection.commit()
        connection.close()
        return redirect(url_for('institution_dashboard'))

    return render_template('institution_profile.html', user=user)

if __name__ == '__main__':
    app.run(debug=True)
