from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import student
from .. import db
from ..models import Class, Enrollment, Schedule, Semester
from ..utils import student_required
from sqlalchemy import and_


@student.route('/dashboard')
@login_required
@student_required
def dashboard():
    # Lấy học kỳ đang mở đăng ký (demo lấy học kỳ mới nhất)
    active_semester = Semester.query.filter_by(is_active=True).order_by(Semester.start_date.desc()).first()

    # Đếm số lớp đã đăng ký
    enrolled_count = 0
    if active_semester:
        enrolled_count = Enrollment.query.join(Class).filter(
            Enrollment.student_id == current_user.student_profile.id,
            Class.semester_id == active_semester.id
        ).count()

    return render_template('student/dashboard.html', enrolled_count=enrolled_count)


# --- ĐĂNG KÝ TÍN CHỈ ---
@student.route('/registration', methods=['GET', 'POST'])
@login_required
@student_required
def registration():
    # 1. Lấy học kỳ đang mở (Giả sử chỉ có 1 HK đang active)
    semester = Semester.query.filter_by(is_active=True).first()
    if not semester:
        flash('Hiện tại không có học kỳ nào mở đăng ký.', 'warning')
        return redirect(url_for('student.dashboard'))

    student_id = current_user.student_profile.id

    # 2. Xử lý Đăng ký
    if request.method == 'POST':
        class_id = request.form.get('class_id')
        target_class = Class.query.get(class_id)

        # A. Kiểm tra đã đăng ký chưa
        existing = Enrollment.query.filter_by(student_id=student_id, class_id=class_id).first()
        if existing:
            flash('Bạn đã đăng ký lớp này rồi!', 'warning')
            return redirect(url_for('student.registration'))

        # B. KIỂM TRA TRÙNG LỊCH (CRITICAL)
        # Lấy lịch của lớp định đăng ký
        target_schedules = target_class.schedules

        # Lấy lịch của TẤT CẢ các lớp sinh viên ĐÃ đăng ký trong học kỳ này
        current_enrollments = Enrollment.query.join(Class).filter(
            Enrollment.student_id == student_id,
            Class.semester_id == semester.id
        ).all()

        conflict_found = False

        for enrollment in current_enrollments:
            enrolled_class = enrollment.class_info
            for enrolled_sched in enrolled_class.schedules:
                for target_sched in target_schedules:
                    # Kiểm tra trùng thứ
                    if enrolled_sched.day_of_week == target_sched.day_of_week:
                        # Kiểm tra trùng tiết (Overlap)
                        if (target_sched.start_lesson < enrolled_sched.end_lesson) and \
                                (target_sched.end_lesson > enrolled_sched.start_lesson):
                            flash(
                                f'LỖI: Trùng lịch với lớp {enrolled_class.name} (Thứ {target_sched.day_of_week}, Tiết {enrolled_sched.start_lesson}-{enrolled_sched.end_lesson})',
                                'danger')
                            conflict_found = True
                            break
                if conflict_found: break
            if conflict_found: break

        if not conflict_found:
            # Nếu không trùng -> Lưu
            new_enroll = Enrollment(student_id=student_id, class_id=class_id)
            db.session.add(new_enroll)
            db.session.commit()
            flash(f'Đăng ký thành công lớp {target_class.name}', 'success')

        return redirect(url_for('student.registration'))

    # 3. Hiển thị danh sách lớp mở cho sinh viên chọn
    # Chỉ hiện các lớp thuộc học kỳ active
    available_classes = Class.query.filter_by(semester_id=semester.id).all()

    # Lấy danh sách ID các lớp đã đăng ký để disable nút bấm
    my_enrollments = [e.class_id for e in Enrollment.query.filter_by(student_id=student_id).all()]

    return render_template('student/registration.html',
                           classes=available_classes,
                           my_enrollments=my_enrollments,
                           semester=semester)


# --- THỜI KHÓA BIỂU CÁ NHÂN ---
@student.route('/schedule')
@login_required
@student_required
def schedule():
    student_id = current_user.student_profile.id
    # Lấy tất cả các lớp sinh viên đang học
    enrollments = Enrollment.query.filter_by(student_id=student_id).all()

    # Chuẩn bị dữ liệu hiển thị dạng lưới (Matrix)
    # schedule_matrix[tiết][thứ]
    schedule_data = {}

    for enroll in enrollments:
        cls = enroll.class_info
        for sch in cls.schedules:
            # Tạo key để hiển thị, ví dụ: Thứ 2, Tiết 1-3
            # Lưu ý: Đây là cách hiển thị danh sách đơn giản.
            # Để hiển thị dạng Grid (Lưới), cần xử lý phức tạp hơn ở Template.
            pass

    return render_template('student/schedule.html', enrollments=enrollments)


# Thêm vào app/student/routes.py

@student.route('/grades')
@login_required
@student_required
def view_grades():
    student_id = current_user.student_profile.id
    enrollments = Enrollment.query.filter_by(student_id=student_id).all()

    # Tính GPA tích lũy
    total_credits = 0
    total_points = 0

    for enroll in enrollments:
        if enroll.total_4 is not None:  # Chỉ tính môn đã có điểm
            credits = enroll.class_info.subject.credits
            total_points += (enroll.total_4 * credits)
            total_credits += credits

    gpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    return render_template('student/grades.html', enrollments=enrollments, gpa=gpa)