from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import teacher
from .. import db
from ..models import Class, Enrollment, Schedule
from ..utils import teacher_required, calculate_gpa_vku, get_letter_grade


# --- 1. DASHBOARD ---
@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    teacher_id = current_user.teacher_profile.id
    my_classes = Class.query.filter_by(teacher_id=teacher_id).all()
    return render_template('teacher/dashboard.html', classes=my_classes)


# --- 2. XEM LỊCH DẠY ---
@teacher.route('/schedule')
@login_required
@teacher_required
def schedule():
    teacher_id = current_user.teacher_profile.id
    my_classes = Class.query.filter_by(teacher_id=teacher_id).all()
    return render_template('teacher/schedule.html', my_classes=my_classes)


# --- 3. NHẬP ĐIỂM & THỐNG KÊ (LOGIC MỚI) ---
@teacher.route('/class/<int:class_id>/grades', methods=['GET', 'POST'])
@login_required
@teacher_required
def input_grades(class_id):
    current_class = Class.query.get_or_404(class_id)

    if current_class.teacher_id != current_user.teacher_profile.id:
        flash('Bạn không có quyền truy cập lớp này!', 'danger')
        return redirect(url_for('teacher.dashboard'))

    if request.method == 'POST':
        for enroll in current_class.enrollments:
            sid = str(enroll.student_id)
            att = request.form.get(f'att_{sid}')
            mid = request.form.get(f'mid_{sid}')
            fin = request.form.get(f'fin_{sid}')

            if att and mid and fin:
                enroll.attendance_score = float(att)
                enroll.midterm_score = float(mid)
                enroll.final_score = float(fin)

                # Tính tổng kết thang 10
                total_10 = (enroll.attendance_score * 0.1) + \
                           (enroll.midterm_score * 0.3) + \
                           (enroll.final_score * 0.6)
                enroll.total_10 = round(total_10, 2)

                # Quy đổi và xét đạt
                enroll.total_4 = calculate_gpa_vku(enroll.total_10)
                enroll.letter_grade = get_letter_grade(enroll.total_4)
                enroll.is_passed = (enroll.total_4 >= 1.0)

        db.session.commit()
        flash('Đã lưu bảng điểm thành công!', 'success')
        return redirect(url_for('teacher.input_grades', class_id=class_id))

    # --- LOGIC THỐNG KÊ PHỔ ĐIỂM THANG 10 ---
    stats_10 = {
        '< 4.0': 0,
        '4.0 - 5.4': 0,
        '5.5 - 6.9': 0,
        '7.0 - 8.4': 0,
        '>= 8.5': 0
    }

    pass_count = 0
    fail_count = 0
    total_students = len(current_class.enrollments)

    for enroll in current_class.enrollments:
        # Thống kê Đạt/Trượt
        if enroll.is_passed:
            pass_count += 1
        else:
            fail_count += 1

        # Thống kê Phổ điểm thang 10
        if enroll.total_10 is not None:
            score = enroll.total_10
            if score < 4.0:
                stats_10['< 4.0'] += 1
            elif score < 5.5:
                stats_10['4.0 - 5.4'] += 1
            elif score < 7.0:
                stats_10['5.5 - 6.9'] += 1
            elif score < 8.5:
                stats_10['7.0 - 8.4'] += 1
            else:
                stats_10['>= 8.5'] += 1

    # Chuẩn bị dữ liệu gửi sang HTML
    labels = list(stats_10.keys())
    data = list(stats_10.values())

    return render_template('teacher/grades.html',
                           current_class=current_class,
                           labels=labels,
                           data=data,
                           pass_count=pass_count,
                           fail_count=fail_count,
                           total_students=total_students)