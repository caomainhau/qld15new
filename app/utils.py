from functools import wraps
from flask import abort
from flask_login import current_user
import string
import secrets

# Decorator yêu cầu quyền Admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403) # Lỗi 403: Forbidden
        return f(*args, **kwargs)
    return decorated_function

# Decorator yêu cầu quyền Giảng viên
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Decorator yêu cầu quyền Sinh viên
def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def generate_random_password(length=10):
    """Sinh mật khẩu ngẫu nhiên gồm chữ và số"""
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password


# ... (các code cũ)

def calculate_gpa_vku(score_10):
    """
    Quy đổi điểm thang 10 sang thang 4 theo quy chế VKU
    """
    if score_10 is None: return 0.0

    s = float(score_10)
    if s >= 8.5:
        return 4.0
    elif 8.0 <= s < 8.5:
        return 3.7
    elif 7.0 <= s < 8.0:
        return 3.0 + (s - 7.0) * 0.25
    elif 6.5 <= s < 7.0:
        return 2.5
    elif 5.5 <= s < 6.5:
        return 2.0
    elif 4.0 <= s < 5.5:
        return 1.0
    else:
        return 0.0


def get_letter_grade(score_4):
    """Quy đổi sang điểm chữ để hiển thị"""
    if score_4 >= 4.0: return 'A'
    if score_4 >= 3.7: return 'A-'
    if score_4 >= 3.5: return 'B+'
    if score_4 >= 3.0: return 'B'
    if score_4 >= 2.5: return 'C+'
    if score_4 >= 2.0: return 'C'
    if score_4 >= 1.0: return 'D'
    return 'F'