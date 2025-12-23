from . import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# --- 1. USER & AUTHENTICATION ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.Enum('admin', 'teacher', 'student'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    # Quan hệ
    student_profile = db.relationship('Student', backref='user', uselist=False)
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    student_code = db.Column(db.String(20), unique=True, nullable=False)
    class_name = db.Column(db.String(50))  # Lớp hành chính (VD: 20GIT)
    major = db.Column(db.String(100))  # Ngành/Khoa (VD: CNTT)
    cohort = db.Column(db.String(20))  # Khóa (VD: K20)

    enrollments = db.relationship('Enrollment', backref='student', lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='student', lazy=True)


class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    teacher_code = db.Column(db.String(20), unique=True, nullable=False)
    department = db.Column(db.String(100))  # Khoa/Bộ môn (VD: Khoa học máy tính)

    classes = db.relationship('Class', backref='teacher', lazy=True)


# --- 2. ACADEMIC MANAGEMENT ---
class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # True: Đang học, False: Đã kết thúc
    registration_open = db.Column(db.Boolean, default=False)

    classes = db.relationship('Class', backref='semester', lazy=True)


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False)

    # Trọng số điểm
    weight_cc = db.Column(db.Integer, default=10)
    weight_gk = db.Column(db.Integer, default=30)
    weight_ck = db.Column(db.Integer, default=60)

    classes = db.relationship('Class', backref='subject', lazy=True)


class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Tên lớp học phần (VD: Nhóm 1 - Lập trình mạng)

    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)

    max_students = db.Column(db.Integer, default=60)
    is_locked = db.Column(db.Boolean, default=False)  # True: Đã chốt điểm

    schedules = db.relationship('Schedule', backref='class_info', lazy=True)
    enrollments = db.relationship('Enrollment', backref='class_info', lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='class_info', lazy=True)


# --- 3. SCHEDULE & ATTENDANCE ---
class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 2=Thứ 2...
    start_lesson = db.Column(db.Integer, nullable=False)
    end_lesson = db.Column(db.Integer, nullable=False)
    room = db.Column(db.String(50), nullable=False)
    is_canceled = db.Column(db.Boolean, default=False)


class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='present')


# --- 4. GRADE & ENROLLMENT ---
class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    attendance_score = db.Column(db.Float, default=0)
    midterm_score = db.Column(db.Float, nullable=True)
    practice_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)

    total_10 = db.Column(db.Float, nullable=True)
    total_4 = db.Column(db.Float, nullable=True)
    letter_grade = db.Column(db.String(5), nullable=True)
    is_passed = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('student_id', 'class_id', name='unique_enrollment'),)