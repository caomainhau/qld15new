from functools import wraps
from flask import abort
from flask_login import current_user
import string
import secrets
from datetime import timedelta

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


def get_valid_class_dates(schedule, semester):
    """
    Trả về danh sách các ngày cụ thể (dd/mm/yyyy) mà lớp này có lịch học
    trong khoảng thời gian của học kỳ.
    schedule.day_of_week: 2 (Thứ 2) -> 8 (CN)
    """
    valid_dates = []

    # Python weekday(): 0=Thứ 2, 1=Thứ 3, ..., 6=CN
    # DB của mình: 2=Thứ 2, ..., 8=CN. => Cần trừ đi 2 để khớp với Python
    target_weekday = schedule.day_of_week - 2

    current_date = semester.start_date
    while current_date <= semester.end_date:
        if current_date.weekday() == target_weekday:
            valid_dates.append(current_date)
        current_date += timedelta(days=1)

    return valid_dates


def check_schedule_conflict(new_class_id, day, start, end, room, semester_id):
    """
    Kiểm tra trùng lịch: Cùng phòng, cùng thứ, giao nhau về tiết học
    """
    from .models import Schedule, Class

    # Lấy tất cả lịch trong học kỳ này
    existing_schedules = Schedule.query.join(Class).filter(
        Class.semester_id == semester_id,
        Schedule.day_of_week == day,
        Schedule.room == room,
        Schedule.is_canceled == False
    ).all()

    for sch in existing_schedules:
        # Bỏ qua chính nó (trường hợp update)
        if sch.class_id == new_class_id:
            continue

        # Kiểm tra giao nhau: (StartA < EndB) and (EndA > StartB)
        if (start <= sch.end_lesson) and (end >= sch.start_lesson):
            return sch  # Trả về lịch bị trùng

    return None