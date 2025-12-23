from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import teacher
from .. import db
from ..models import Class, Enrollment, AttendanceLog, Student, Subject, Semester

# Import các hàm tiện ích
from ..utils import teacher_required, calculate_gpa_vku, get_letter_grade, get_valid_class_dates


# --- 1. DASHBOARD ---
@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    teacher_id = current_user.teacher_profile.id
    # Hiển thị tất cả lớp (cả lớp cũ và mới) để xem lại lịch sử
    # Nhưng lớp cũ sẽ bị khóa (is_locked=True)
    my_classes = Class.query.filter_by(teacher_id=teacher_id).order_by(Class.id.desc()).all()
    return render_template('teacher/dashboard.html', classes=my_classes)


# --- 2. LỊCH DẠY (CHỈ HIỆN HỌC KỲ ĐANG ACTIVE) ---
@teacher.route('/schedule')
@login_required
@teacher_required
def schedule():
    teacher_id = current_user.teacher_profile.id

    # LOGIC QUAN TRỌNG: Chỉ lấy lớp thuộc Học kỳ đang hoạt động
    # Nếu học kỳ đóng, thời khóa biểu sẽ trống trơn (theo yêu cầu của bạn)
    my_classes = Class.query.join(Semester).filter(
        Class.teacher_id == teacher_id,
        Semester.is_active == True
    ).all()

    # Logic tính ngày tháng
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    week_dates = {}
    for i in range(7):
        current_day = start_of_week + timedelta(days=i)
        db_day = i + 2
        week_dates[db_day] = current_day.strftime('%d/%m')

    return render_template('teacher/schedule.html',
                           my_classes=my_classes,
                           week_dates=week_dates,
                           today_db=today.weekday() + 2)


# --- 3. ĐIỂM DANH ---
@teacher.route('/class/<int:class_id>/attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def take_attendance(class_id):
    current_class = Class.query.get_or_404(class_id)

    # 1. KIỂM TRA HỌC KỲ CÒN MỞ KHÔNG?
    if not current_class.semester.is_active:
        flash('Học kỳ đã kết thúc. Bạn không thể điểm danh được nữa.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    # 2. Kiểm tra lớp có bị khóa thủ công không?
    if current_class.is_locked:
        flash('Lớp học phần này đã bị khóa điểm.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    schedules = current_class.schedules
    if not schedules:
        flash('Lớp chưa có thời khóa biểu!', 'danger')
        return redirect(url_for('teacher.dashboard'))

    semester = current_class.semester

    sessions = []
    for sch in schedules:
        dates = get_valid_class_dates(sch, semester)
        for d in dates:
            session_info = {
                'date_obj': d,
                'value': d.strftime('%Y-%m-%d'),
                'display': f"Thứ {sch.day_of_week} - {d.strftime('%d/%m/%Y')} | Tiết {sch.start_lesson}-{sch.end_lesson} | Phòng {sch.room}"
            }
            sessions.append(session_info)

    sessions.sort(key=lambda x: x['date_obj'])
    valid_values = [s['value'] for s in sessions]
    today_str = datetime.now().strftime('%Y-%m-%d')

    if request.method == 'POST':
        selected_date_str = request.form.get('attendance_date')

        if selected_date_str not in valid_values:
            flash('Ngày chọn không hợp lệ!', 'danger')
            return redirect(url_for('teacher.take_attendance', class_id=class_id))

        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

        AttendanceLog.query.filter_by(class_id=class_id, date=selected_date).delete()

        for enroll in current_class.enrollments:
            sid = enroll.student_id
            status = request.form.get(f'status_{sid}', 'present')
            log = AttendanceLog(class_id=class_id, student_id=sid, date=selected_date, status=status)
            db.session.add(log)

        db.session.commit()
        flash(f'Đã lưu điểm danh ngày {selected_date.strftime("%d/%m/%Y")}.', 'success')
        return redirect(url_for('teacher.take_attendance', class_id=class_id))

    return render_template('teacher/attendance.html',
                           current_class=current_class,
                           sessions=sessions,
                           today_str=today_str)


# --- 4. NHẬP ĐIỂM ---
@teacher.route('/class/<int:class_id>/grades', methods=['GET', 'POST'])
@login_required
@teacher_required
def input_grades(class_id):
    current_class = Class.query.get_or_404(class_id)
    subject = current_class.subject

    # 1. KIỂM TRA QUYỀN TRUY CẬP
    if current_class.teacher_id != current_user.teacher_profile.id:
        return redirect(url_for('teacher.dashboard'))

    # 2. XỬ LÝ POST (LƯU ĐIỂM)
    if request.method == 'POST':
        # KIỂM TRA CHẶT: Nếu học kỳ đóng hoặc lớp khóa -> Không cho lưu
        if not current_class.semester.is_active or current_class.is_locked:
            flash('Lớp đã khóa hoặc học kỳ đã kết thúc. Không thể sửa điểm.', 'danger')
            return redirect(url_for('teacher.input_grades', class_id=class_id))

        for enroll in current_class.enrollments:
            sid = enroll.student_id

            # Tính điểm chuyên cần
            logs = AttendanceLog.query.filter_by(class_id=class_id, student_id=sid).all()
            current_score = 10.0
            for log in logs:
                if log.status == 'absent':
                    current_score -= 1.0
                elif log.status == 'late':
                    current_score -= 0.5
                elif log.status == 'excused':
                    current_score -= 0.5

            if current_score < 0: current_score = 0
            enroll.attendance_score = round(current_score, 1)

            # Lấy điểm từ form
            mid = request.form.get(f'mid_{sid}')
            fin = request.form.get(f'fin_{sid}')

            if mid and fin:
                enroll.midterm_score = float(mid)
                enroll.final_score = float(fin)

                w_cc = subject.weight_cc / 100
                w_gk = subject.weight_gk / 100
                w_ck = subject.weight_ck / 100

                total_10 = (enroll.attendance_score * w_cc) + \
                           (enroll.midterm_score * w_gk) + \
                           (enroll.final_score * w_ck)

                enroll.total_10 = round(total_10, 2)
                enroll.total_4 = calculate_gpa_vku(enroll.total_10)
                enroll.letter_grade = get_letter_grade(enroll.total_4)
                enroll.is_passed = (enroll.total_4 >= 1.0)

        db.session.commit()
        flash('Đã lưu bảng điểm.', 'success')
        return redirect(url_for('teacher.input_grades', class_id=class_id))

    # Logic biểu đồ (giữ nguyên)
    stats_10 = {'< 4.0': 0, '4.0 - 5.4': 0, '5.5 - 6.9': 0, '7.0 - 8.4': 0, '>= 8.5': 0}
    pass_count = 0
    fail_count = 0
    total_students = len(current_class.enrollments)
    for enroll in current_class.enrollments:
        if enroll.is_passed:
            pass_count += 1
        else:
            fail_count += 1
        if enroll.total_10 is not None:
            s = enroll.total_10
            if s < 4.0:
                stats_10['< 4.0'] += 1
            elif s < 5.5:
                stats_10['4.0 - 5.4'] += 1
            elif s < 7.0:
                stats_10['5.5 - 6.9'] += 1
            elif s < 8.5:
                stats_10['7.0 - 8.4'] += 1
            else:
                stats_10['>= 8.5'] += 1

    labels = list(stats_10.keys())
    data = list(stats_10.values())

    return render_template('teacher/grades.html',
                           current_class=current_class,
                           labels=labels, data=data,
                           pass_count=pass_count, fail_count=fail_count,
                           total_students=total_students,
                           subject=subject)