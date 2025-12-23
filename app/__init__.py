from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from config import Config
from datetime import datetime

# Khởi tạo các extension
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # --- IMPORT MODEL USER (QUAN TRỌNG: Để tránh lỗi NameError) ---
    from .models import User

    # --- CẤU HÌNH LOGIN MANAGER ---
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- TÍNH NĂNG: CẬP NHẬT THỜI GIAN HOẠT ĐỘNG (LAST SEEN) ---
    @app.before_request
    def update_last_seen():
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

    # --- ĐĂNG KÝ BLUEPRINTS ---
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    from .teacher import teacher as teacher_blueprint
    app.register_blueprint(teacher_blueprint, url_prefix='/teacher')

    from .student import student as student_blueprint
    app.register_blueprint(student_blueprint, url_prefix='/student')

    # --- ROUTE MẶC ĐỊNH (REDIRECT THEO ROLE) ---
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            elif current_user.role == 'student':
                return redirect(url_for('student.dashboard'))
        return redirect(url_for('auth.login'))

    # Tạo Database nếu chưa có
    with app.app_context():
        db.create_all()

    return app