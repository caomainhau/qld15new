# --- SỬA LẦN 1: Thêm redirect, url_for vào dòng import ---
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Import models để tạo bảng
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Đăng ký Blueprints
    # Lưu ý: Tôi đã thêm url_prefix='/auth' để đường dẫn rõ ràng hơn (/auth/login)
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    from .student import student as student_blueprint
    app.register_blueprint(student_blueprint, url_prefix='/student')

    from .teacher import teacher as teacher_blueprint
    app.register_blueprint(teacher_blueprint, url_prefix='/teacher')

    # --- SỬA LẦN 2: Thêm đoạn này để xử lý trang chủ (/) ---
    @app.route('/')
    def index():
        # Khi vào trang chủ, tự động chuyển hướng sang trang đăng nhập
        return redirect(url_for('auth.login'))
    # -------------------------------------------------------

    # Tạo bảng trong DB nếu chưa có
    with app.app_context():
        db.create_all()

    return app