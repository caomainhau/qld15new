from . import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


# --- 1. USER & AUTHENTICATION ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)  # Bắt buộc đuôi @vku.udn.vn
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.Enum('admin', 'teacher', 'student'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    student_code = db.Column(db.String(20), unique=True, nullable=False)  # Mã SV
    class_name = db.Column(db.String(50))  # Lớp hành chính (VD: 20GIT)
    major = db.Column(db.String(100))  # Ngành
    cohort = db.Column(db.String(20))  # Khóa (VD: K20)

    enrollments = db.relationship('Enrollment', backref='student', lazy=True)


class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    teacher_code = db.Column(db.String(20), unique=True, nullable=False)
    department = db.Column(db.String(100))  # Khoa/Bộ môn

    classes = db.relationship('Class', backref='teacher', lazy=True)


# --- 2. ACADEMIC MANAGEMENT ---
class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # VD: Học kỳ 1 năm 2023-2024
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # Trạng thái HK
    registration_open = db.Column(db.Boolean, default=False)  # Mở đăng ký tín chỉ


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)  # Mã HP
    name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False)  # Số tín chỉ


class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # VD: Nhóm 1 - Lập trình Web
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    max_students = db.Column(db.Integer, default=60)
    is_locked = db.Column(db.Boolean, default=False)  # Khóa điểm

    schedules = db.relationship('Schedule', backref='class_info', lazy=True)
    enrollments = db.relationship('Enrollment', backref='class_info', lazy=True)

    # --- DÒNG QUAN TRỌNG VỪA THÊM VÀO ĐÂY ---
    subject = db.relationship('Subject', backref='classes')
    # ----------------------------------------


# --- 3. SCHEDULE (THỜI KHÓA BIỂU) ---
class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 2=Thứ 2, ..., 8=CN
    start_lesson = db.Column(db.Integer, nullable=False)  # Tiết bắt đầu (1-10)
    end_lesson = db.Column(db.Integer, nullable=False)  # Tiết kết thúc
    room = db.Column(db.String(50), nullable=False)
    is_canceled = db.Column(db.Boolean, default=False)  # Báo nghỉ


# --- 4. GRADE & ENROLLMENT (ĐIỂM SỐ) ---
class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    # Điểm thành phần (Thang 10)
    attendance_score = db.Column(db.Float, default=0)  # Chuyên cần
    midterm_score = db.Column(db.Float, nullable=True)  # Giữa kỳ
    practice_score = db.Column(db.Float, nullable=True)  # Thực hành (nếu có)
    final_score = db.Column(db.Float, nullable=True)  # Cuối kỳ

    # Điểm tổng kết
    total_10 = db.Column(db.Float, nullable=True)  # TK hệ 10
    total_4 = db.Column(db.Float, nullable=True)  # TK hệ 4 (Quy đổi)
    letter_grade = db.Column(db.String(5), nullable=True)  # Điểm chữ (A, B+, C...)

    is_passed = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('student_id', 'class_id', name='unique_enrollment'),)