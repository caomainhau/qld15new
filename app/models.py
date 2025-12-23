from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash


# --- 1. USER & AUTHENTICATION ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    # Role khớp với ENUM trong SQL
    role = db.Column(db.Enum('admin', 'teacher', 'student'), nullable=False)

    # Sử dụng server_default để khớp với 'DEFAULT current_timestamp()' trong SQL
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    last_seen = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # Quan hệ 1-1
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
    class_name = db.Column(db.String(50))
    major = db.Column(db.String(100))
    cohort = db.Column(db.String(20))

    enrollments = db.relationship('Enrollment', backref='student', lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='student', lazy=True)


class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    teacher_code = db.Column(db.String(20), unique=True, nullable=False)
    department = db.Column(db.String(100))

    classes = db.relationship('Class', backref='teacher', lazy=True)


# --- 2. ACADEMIC MANAGEMENT ---
class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    registration_open = db.Column(db.Boolean, default=False)

    classes = db.relationship('Class', backref='semester', lazy=True)


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    credits = db.Column(db.Integer, nullable=False)

    # Quan hệ 1-nhiều với Cấu hình điểm
    # VD: Môn Python có [Chuyên cần(10%), Giữa kỳ(30%), Cuối kỳ(60%)]
    grade_weights = db.relationship('GradeWeight', backref='subject', lazy=True, cascade="all, delete-orphan")

    classes = db.relationship('Class', backref='subject', lazy=True)


class GradeWeight(db.Model):
    """Bảng cấu hình cột điểm cho từng môn"""
    __tablename__ = 'grade_weights'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)

    name = db.Column(db.String(50), nullable=False)  # VD: "Bài tập lớn", "Thực hành"
    weight_percent = db.Column(db.Integer, nullable=False)  # VD: 20 (tức là 20%)
    order_index = db.Column(db.Integer, default=1)  # Để sắp xếp cột nào đứng trước

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)

    max_students = db.Column(db.Integer, default=60)
    is_locked = db.Column(db.Boolean, default=False)

    # QUAN TRỌNG: cascade='all, delete-orphan' để xử lý xóa lịch khi xóa lớp
    schedules = db.relationship('Schedule', backref='class_info', lazy=True, cascade="all, delete-orphan")
    enrollments = db.relationship('Enrollment', backref='class_info', lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='class_info', lazy=True)


# --- 3. SCHEDULE & ATTENDANCE ---
class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_lesson = db.Column(db.Integer, nullable=False)
    end_lesson = db.Column(db.Integer, nullable=False)
    room = db.Column(db.String(50), nullable=False)
    is_canceled = db.Column(db.Boolean, default=False)


class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, server_default=func.current_date())
    status = db.Column(db.String(20), default='present')


# --- 4. GRADE & ENROLLMENT ---
class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    scores = db.relationship('GradeScore', backref='enrollment', lazy=True, cascade="all, delete-orphan")

    total_10 = db.Column(db.Float, nullable=True)
    total_4 = db.Column(db.Float, nullable=True)
    letter_grade = db.Column(db.String(5), nullable=True)
    is_passed = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('student_id', 'class_id', name='unique_enrollment'),)


class GradeScore(db.Model):
    """Bảng lưu điểm thực tế của sinh viên"""
    __tablename__ = 'grade_scores'
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollments.id'), nullable=False)

    # Điểm này thuộc về cột điểm nào (VD: Điểm này là của cột "Giữa kỳ")
    grade_weight_id = db.Column(db.Integer, db.ForeignKey('grade_weights.id'), nullable=False)
    weight_config = db.relationship('GradeWeight', backref='scores')
    value = db.Column(db.Float, nullable=True)  # Giá trị điểm (VD: 8.5)