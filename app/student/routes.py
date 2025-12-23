from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import and_
from . import student
from .. import db
# Import gọn gàng, không lặp lại
from ..models import Class, Enrollment, Schedule, Semester, GradeWeight, GradeScore
from ..utils import student_required, check_schedule_conflict


# --- DASHBOARD ---
@student.route('/dashboard')
@login_required
@student_required
def dashboard():
    # Lấy học kỳ đang mở (active) mới nhất
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
    semester = Semester.query.filter_by(is_active=True).order_by(Semester.start_date.desc()).first()

    if not semester:
        flash('Hiện tại không có học kỳ nào mở đăng ký.', 'warning')
        return redirect(url_for('student.dashboard'))

    student_id = current_user.student_profile.id

    if request.method == 'POST':
        class_id = request.form.get('class_id')
        target_class = Class.query.get(class_id)

        if not target_class:
            flash('Lớp học không tồn tại.', 'danger')
            return redirect(url_for('student.registration'))

        # A. Kiểm tra đã đăng ký chưa
        existing = Enrollment.query.filter_by(student_id=student_id, class_id=class_id).first()
        if existing:
            flash(f'Bạn đã đăng ký lớp {target_class.name} rồi!', 'warning')
            return redirect(url_for('student.registration'))

        # B. Kiểm tra sĩ số
        current_count = len(target_class.enrollments)
        if current_count >= target_class.max_students:
            flash('Lớp đã đầy sĩ số!', 'danger')
            return redirect(url_for('student.registration'))

        # C. KIỂM TRA TRÙNG LỊCH
        current_enrollments = Enrollment.query.join(Class).filter(
            Enrollment.student_id == student_id,
            Class.semester_id == semester.id
        ).all()

        target_schedules = target_class.schedules
        conflict_found = False

        for enrollment in current_enrollments:
            enrolled_class = enrollment.class_info
            for enrolled_sched in enrolled_class.schedules:
                for target_sched in target_schedules:
                    if enrolled_sched.day_of_week == target_sched.day_of_week:
                        if (target_sched.start_lesson <= enrolled_sched.end_lesson) and \
                                (target_sched.end_lesson >= enrolled_sched.start_lesson):
                            flash(f'LỖI: Trùng lịch với lớp "{enrolled_class.name}"', 'danger')
                            conflict_found = True
                            break
                if conflict_found: break
            if conflict_found: break

        # D. LƯU ĐĂNG KÝ VÀ TỰ ĐỘNG GÁN ĐIỂM CHUYÊN CẦN
        if not conflict_found:
            # 1. Tạo Enrollment
            new_enroll = Enrollment(student_id=student_id, class_id=class_id)
            db.session.add(new_enroll)
            db.session.commit()  # Commit để có ID

            # 2. Tìm cột điểm "Chuyên cần" (nếu có)
            attendance_weight = GradeWeight.query.filter_by(
                subject_id=target_class.subject_id,
                name="Chuyên cần"
            ).first()

            # 3. Gán điểm 10 mặc định
            if attendance_weight:
                init_score = GradeScore(
                    enrollment_id=new_enroll.id,
                    grade_weight_id=attendance_weight.id,
                    value=10.0
                )
                db.session.add(init_score)
                db.session.commit()

            flash(f'Đăng ký thành công lớp: {target_class.name}', 'success')

        return redirect(url_for('student.registration'))

    # GET: Hiển thị danh sách lớp
    available_classes = Class.query.filter_by(semester_id=semester.id, is_locked=False).all()
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

    all_semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    semester_id = request.args.get('semester_id', type=int)

    current_semester = None
    if semester_id:
        current_semester = Semester.query.get(semester_id)
    else:
        current_semester = Semester.query.filter_by(is_active=True).order_by(Semester.start_date.desc()).first()
        if not current_semester and all_semesters:
            current_semester = all_semesters[0]

    enrollments = []
    if current_semester:
        enrollments = Enrollment.query.join(Class).filter(
            Enrollment.student_id == student_id,
            Class.semester_id == current_semester.id
        ).all()

    return render_template('student/schedule.html',
                           enrollments=enrollments,
                           semesters=all_semesters,
                           current_semester=current_semester)


# --- XEM ĐIỂM (CẬP NHẬT: XỬ LÝ ĐIỂM ĐỘNG) ---
@student.route('/grades')
@login_required
@student_required
def view_grades():
    student_id = current_user.student_profile.id

    enrollments = Enrollment.query.filter_by(student_id=student_id) \
        .join(Class).join(Semester) \
        .order_by(Semester.start_date.desc()).all()

    transcript_data = []
    total_accumulated_points = 0
    total_accumulated_credits = 0
    temp_group = {}

    for enroll in enrollments:
        sem_id = enroll.class_info.semester_id

        if sem_id not in temp_group:
            temp_group[sem_id] = {
                'semester': enroll.class_info.semester,
                'enrollments': [],
                'term_points': 0,
                'term_credits': 0
            }

        # --- PHẦN QUAN TRỌNG: LẤY CHI TIẾT ĐIỂM (CC, GK, CK...) ---
        detail_scores = []
        # enroll.scores là quan hệ 1-nhiều sang bảng GradeScore
        for score in enroll.scores:
            detail_scores.append({
                # Cần đảm bảo model GradeScore có backref='weight_config' sang GradeWeight
                'name': score.weight_config.name,
                'val': score.value,
                'percent': score.weight_config.weight_percent
            })

        # Sắp xếp theo % trọng số (hoặc theo order_index nếu bạn join thêm)
        detail_scores.sort(key=lambda x: x['percent'])

        # Gán vào thuộc tính tạm để Template sử dụng
        enroll.detail_scores_display = detail_scores
        # -----------------------------------------------------------

        temp_group[sem_id]['enrollments'].append(enroll)

        if enroll.total_4 is not None:
            credits = enroll.class_info.subject.credits
            points = enroll.total_4 * credits
            temp_group[sem_id]['term_points'] += points
            temp_group[sem_id]['term_credits'] += credits
            total_accumulated_points += points
            total_accumulated_credits += credits

    for sem_id, data in temp_group.items():
        term_gpa = 0.0
        if data['term_credits'] > 0:
            term_gpa = round(data['term_points'] / data['term_credits'], 2)

        transcript_data.append({
            'semester': data['semester'],
            'enrollments': data['enrollments'],
            'term_gpa': term_gpa,
            'term_credits': data['term_credits']
        })

    transcript_data.sort(key=lambda x: x['semester'].start_date, reverse=True)

    cumulative_gpa = 0.0
    if total_accumulated_credits > 0:
        cumulative_gpa = round(total_accumulated_points / total_accumulated_credits, 2)

    return render_template('student/grades.html',
                           transcript=transcript_data,
                           cumulative_gpa=cumulative_gpa,
                           total_credits=total_accumulated_credits)