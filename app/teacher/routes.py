from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import teacher
from .. import db
# Import đầy đủ các Model cần thiết
from ..models import Class, Enrollment, GradeWeight, GradeScore, AttendanceLog, Semester, Student, Subject
# Import các hàm tiện ích
from ..utils import teacher_required, calculate_gpa_vku, get_letter_grade, get_valid_class_dates


# --- 1. DASHBOARD ---
@teacher.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    teacher_id = current_user.teacher_profile.id
    # Hiển thị tất cả lớp (cả lớp cũ và mới)
    my_classes = Class.query.filter_by(teacher_id=teacher_id).order_by(Class.id.desc()).all()
    return render_template('teacher/dashboard.html', classes=my_classes)


# --- 2. LỊCH DẠY ---
@teacher.route('/schedule')
@login_required
@teacher_required
def schedule():
    teacher_id = current_user.teacher_profile.id

    # Chỉ lấy lớp thuộc Học kỳ đang hoạt động
    my_classes = Class.query.join(Semester).filter(
        Class.teacher_id == teacher_id,
        Semester.is_active == True
    ).all()

    # Logic tính ngày tháng cho tuần hiện tại
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    week_dates = {}
    for i in range(7):
        current_day = start_of_week + timedelta(days=i)
        db_day = i + 2  # Thứ 2 là 2, CN là 8
        week_dates[db_day] = current_day.strftime('%d/%m')

    return render_template('teacher/schedule.html',
                           my_classes=my_classes,
                           week_dates=week_dates,
                           today_db=today.weekday() + 2)


# --- 3. ĐIỂM DANH (GIỮ NGUYÊN LOGIC CŨ) ---
@teacher.route('/class/<int:class_id>/attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def take_attendance(class_id):
    current_class = Class.query.get_or_404(class_id)

    # Validate quyền và trạng thái lớp
    if current_class.teacher_id != current_user.teacher_profile.id:
        flash('Bạn không có quyền truy cập lớp này.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    if not current_class.semester.is_active:
        flash('Học kỳ đã kết thúc.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    if current_class.is_locked:
        flash('Lớp học phần này đã bị khóa điểm.', 'warning')
        return redirect(url_for('teacher.dashboard'))

    schedules = current_class.schedules
    if not schedules:
        flash('Lớp chưa có thời khóa biểu!', 'danger')
        return redirect(url_for('teacher.dashboard'))

    # Chuẩn bị danh sách các buổi học để hiển thị dropdown
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

    # XỬ LÝ POST: LƯU ĐIỂM DANH
    if request.method == 'POST':
        selected_date_str = request.form.get('attendance_date')

        if selected_date_str not in valid_values:
            flash('Ngày chọn không hợp lệ hoặc không có lịch học!', 'danger')
            return redirect(url_for('teacher.take_attendance', class_id=class_id))

        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

        # Xóa log cũ của ngày hôm đó để lưu mới (tránh trùng lặp)
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


# --- 4. NHẬP ĐIỂM (ĐÃ SỬA CHO CẤU TRÚC ĐỘNG) ---
@teacher.route('/class/<int:class_id>/grades', methods=['GET', 'POST'])
@login_required
@teacher_required
def input_grades(class_id):
    current_class = Class.query.get_or_404(class_id)

    # 1. Kiểm tra quyền
    if current_class.teacher_id != current_user.teacher_profile.id:
        return redirect(url_for('teacher.dashboard'))

    # 2. Lấy cấu hình cột điểm của môn học này
    weights = GradeWeight.query.filter_by(subject_id=current_class.subject_id) \
        .order_by(GradeWeight.order_index).all()

    # 3. XỬ LÝ POST (LƯU ĐIỂM)
    if request.method == 'POST':
        if not current_class.semester.is_active or current_class.is_locked:
            flash('Lớp đã khóa hoặc học kỳ đã kết thúc.', 'danger')
            return redirect(url_for('teacher.input_grades', class_id=class_id))

        # Duyệt qua từng sinh viên
        for enroll in current_class.enrollments:
            sid = enroll.student_id

            # --- TỰ ĐỘNG TÍNH ĐIỂM CHUYÊN CẦN TỪ LOG (NẾU CÓ CỘT NÀY) ---
            # Tìm xem môn này có cột nào tên là "Chuyên cần" không
            att_weight = next((w for w in weights if w.name.lower() == "chuyên cần"), None)

            if att_weight:
                # Tính toán điểm dựa trên log
                logs = AttendanceLog.query.filter_by(class_id=class_id, student_id=sid).all()
                calc_score = 10.0
                for log in logs:
                    if log.status == 'absent':
                        calc_score -= 1.0  # Vắng trừ 1
                    elif log.status == 'late':
                        calc_score -= 0.5  # Muộn trừ 0.5
                    elif log.status == 'excused':
                        calc_score -= 0.5  # Có phép trừ 0.5 (tùy quy chế)

                if calc_score < 0: calc_score = 0

                # Lưu vào bảng GradeScore
                att_score_record = GradeScore.query.filter_by(enrollment_id=enroll.id,
                                                              grade_weight_id=att_weight.id).first()
                if not att_score_record:
                    att_score_record = GradeScore(enrollment_id=enroll.id, grade_weight_id=att_weight.id)
                    db.session.add(att_score_record)
                att_score_record.value = calc_score

            # --- LƯU CÁC CỘT ĐIỂM KHÁC TỪ FORM ---
            total_subject_score = 0
            total_percent = 0

            for w in weights:
                # Nếu là Chuyên cần thì đã tính ở trên rồi, nhưng vẫn lấy từ form nếu muốn cho phép sửa tay
                # Ở đây tôi ưu tiên lấy từ form nếu người dùng nhập, nếu không nhập thì giữ nguyên logic tính toán

                input_name = f"score_{enroll.id}_{w.id}"  # VD: score_101_5
                val_str = request.form.get(input_name)

                # Tìm bản ghi điểm trong DB
                score_record = GradeScore.query.filter_by(enrollment_id=enroll.id, grade_weight_id=w.id).first()
                if not score_record:
                    score_record = GradeScore(enrollment_id=enroll.id, grade_weight_id=w.id)
                    db.session.add(score_record)

                # Nếu là chuyên cần và form trống => dùng điểm tự tính (đã gán ở trên).
                # Nếu form có dữ liệu => dùng dữ liệu form (ghi đè)
                if val_str is not None and val_str.strip() != '':
                    try:
                        score_record.value = float(val_str)
                    except ValueError:
                        pass  # Giữ nguyên giá trị cũ nếu nhập sai

                # --- CỘNG DỒN TÍNH TỔNG KẾT ---
                if score_record.value is not None:
                    total_subject_score += score_record.value * (w.weight_percent / 100)
                    total_percent += w.weight_percent

            # --- TÍNH TỔNG KẾT (Chỉ tính khi tổng trọng số cấu hình là 100%) ---
            # Hoặc logic: Tính dựa trên các cột đã có điểm
            enroll.total_10 = round(total_subject_score, 2)
            enroll.total_4 = calculate_gpa_vku(enroll.total_10)
            enroll.letter_grade = get_letter_grade(enroll.total_4)
            enroll.is_passed = (enroll.total_4 >= 1.0)

        db.session.commit()
        flash('Đã lưu bảng điểm thành công.', 'success')
        return redirect(url_for('teacher.input_grades', class_id=class_id))

    # --- CHUẨN BỊ DỮ LIỆU HIỂN THỊ (GET) ---

    # 1. Map điểm để hiển thị ra bảng: scores_map[(enroll_id, weight_id)] = value
    scores_map = {}
    all_scores = GradeScore.query.join(Enrollment).filter(Enrollment.class_id == class_id).all()
    for s in all_scores:
        scores_map[(s.enrollment_id, s.grade_weight_id)] = s.value

    # 2. Logic biểu đồ thống kê
    stats_10 = {'< 4.0': 0, '4.0 - 5.4': 0, '5.5 - 6.9': 0, '7.0 - 8.4': 0, '>= 8.5': 0}
    pass_count = 0
    fail_count = 0
    total_students = len(current_class.enrollments)

    for enroll in current_class.enrollments:
        if enroll.total_10 is not None:
            s = enroll.total_10
            if enroll.is_passed:
                pass_count += 1
            else:
                fail_count += 1

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
                           # Lưu ý: Bạn cần update file html này theo code Frontend tôi gửi ở turn trước
                           cls=current_class,  # Tôi đổi biến current_class thành cls cho ngắn gọn trong template mới
                           current_class=current_class,  # Truyền cả 2 tên để tương thích template cũ/mới
                           weights=weights,
                           scores_map=scores_map,
                           labels=labels, data=data,
                           pass_count=pass_count, fail_count=fail_count,
                           total_students=total_students)