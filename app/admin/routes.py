from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import admin
from .. import db
from ..models import Semester
from ..utils import admin_required
from datetime import datetime
from ..models import User, Teacher, Student
from ..utils import generate_random_password # Import hàm mới
from sqlalchemy.exc import IntegrityError
from ..models import Subject, Class, Schedule, Semester, Teacher
from sqlalchemy import and_
from ..models import Student, Teacher, Subject, Class, User

# --- DASHBOARD ---
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Thống kê số lượng
    stats = {
        'total_students': Student.query.count(),
        'total_teachers': Teacher.query.count(),
        'total_subjects': Subject.query.count(),
        'active_classes': Class.query.filter_by(is_locked=False).count(),
        'total_users': User.query.count()
    }
    return render_template('admin/dashboard.html', stats=stats)


# --- QUẢN LÝ HỌC KỲ ---
@admin.route('/semesters', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_semesters():
    if request.method == 'POST':
        # Xử lý thêm mới học kỳ
        name = request.form.get('name')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')

        # Logic: Tắt các học kỳ khác nếu học kỳ mới được set là Active (Tạm thời để mặc định active)
        new_sem = Semester(name=name, start_date=start_date, end_date=end_date)
        db.session.add(new_sem)
        db.session.commit()
        flash('Đã thêm học kỳ mới thành công!', 'success')
        return redirect(url_for('admin.manage_semesters'))

    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    return render_template('admin/semesters.html', semesters=semesters)


@admin.route('/semesters/delete/<int:id>')
@login_required
@admin_required
def delete_semester(id):
    sem = Semester.query.get_or_404(id)
    # Kiểm tra ràng buộc: Nếu học kỳ đã có lớp học thì không được xóa (Sẽ làm kỹ hơn sau)
    db.session.delete(sem)
    db.session.commit()
    flash('Đã xóa học kỳ.', 'success')
    return redirect(url_for('admin.manage_semesters'))


@admin.route('/semesters/toggle/<int:id>')
@login_required
@admin_required
def toggle_semester(id):
    sem = Semester.query.get_or_404(id)
    sem.is_active = not sem.is_active
    db.session.commit()
    flash(f'Đã đổi trạng thái học kỳ {sem.name}', 'info')
    return redirect(url_for('admin.manage_semesters'))


# --- QUẢN LÝ GIẢNG VIÊN ---
@admin.route('/teachers', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_teachers():
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        teacher_code = request.form.get('teacher_code')
        department = request.form.get('department')

        if not email.endswith('@vku.udn.vn'):
            flash('Email phải có đuôi @vku.udn.vn', 'danger')
            return redirect(url_for('admin.manage_teachers'))

        # 1. Sinh mật khẩu
        random_pass = generate_random_password()

        try:
            # 2. Tạo User
            user = User(email=email, full_name=full_name, role='teacher')
            user.set_password(random_pass)
            db.session.add(user)
            db.session.flush()  # Để lấy user.id ngay lập tức

            # 3. Tạo Teacher Profile
            teacher = Teacher(user_id=user.id, teacher_code=teacher_code, department=department)
            db.session.add(teacher)
            db.session.commit()

            # 4. Thông báo mật khẩu (QUAN TRỌNG)
            flash(f'Đã tạo giảng viên {full_name}. Mật khẩu khởi tạo là: {random_pass}', 'password_reveal')
        except IntegrityError:
            db.session.rollback()
            flash('Lỗi: Email hoặc Mã giảng viên đã tồn tại!', 'danger')

        return redirect(url_for('admin.manage_teachers'))

    # Query danh sách giảng viên kèm thông tin user
    teachers = db.session.query(Teacher, User).join(User).all()
    return render_template('admin/teachers.html', teachers=teachers)


# --- QUẢN LÝ SINH VIÊN ---
@admin.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_students():
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        student_code = request.form.get('student_code')
        class_name = request.form.get('class_name')
        major = request.form.get('major')
        cohort = request.form.get('cohort')

        if not email.endswith('@vku.udn.vn'):
            flash('Email phải có đuôi @vku.udn.vn', 'danger')
            return redirect(url_for('admin.manage_students'))

        random_pass = generate_random_password()

        try:
            user = User(email=email, full_name=full_name, role='student')
            user.set_password(random_pass)
            db.session.add(user)
            db.session.flush()

            student = Student(
                user_id=user.id,
                student_code=student_code,
                class_name=class_name,
                major=major,
                cohort=cohort
            )
            db.session.add(student)
            db.session.commit()

            flash(f'Đã tạo sinh viên {full_name}. Mật khẩu khởi tạo là: {random_pass}', 'password_reveal')
        except IntegrityError:
            db.session.rollback()
            flash('Lỗi: Email hoặc Mã sinh viên đã tồn tại!', 'danger')

        return redirect(url_for('admin.manage_students'))

    students = db.session.query(Student, User).join(User).all()
    return render_template('admin/students.html', students=students)


# --- QUẢN LÝ HỌC PHẦN (MÔN HỌC) ---
@admin.route('/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_subjects():
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        credits = request.form.get('credits')

        # Kiểm tra mã môn trùng
        if Subject.query.filter_by(code=code).first():
            flash(f'Mã học phần {code} đã tồn tại!', 'danger')
        else:
            sub = Subject(code=code, name=name, credits=credits)
            db.session.add(sub)
            db.session.commit()
            flash('Thêm học phần thành công.', 'success')
        return redirect(url_for('admin.manage_subjects'))

    subjects = Subject.query.all()
    return render_template('admin/subjects.html', subjects=subjects)


# --- QUẢN LÝ LỚP HỌC PHẦN ---
@admin.route('/classes', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_classes():
    if request.method == 'POST':
        name = request.form.get('name')
        subject_id = request.form.get('subject_id')
        semester_id = request.form.get('semester_id')
        teacher_id = request.form.get('teacher_id')
        max_students = request.form.get('max_students')

        new_class = Class(
            name=name,
            subject_id=subject_id,
            semester_id=semester_id,
            teacher_id=teacher_id,
            max_students=max_students
        )
        db.session.add(new_class)
        db.session.commit()
        flash('Đã mở lớp học phần mới.', 'success')
        return redirect(url_for('admin.manage_classes'))

    # Load dữ liệu cho các thẻ <select>
    classes = Class.query.order_by(Class.id.desc()).all()
    subjects = Subject.query.all()
    semesters = Semester.query.filter_by(is_active=True).all()
    teachers = db.session.query(Teacher, User).join(User).all()

    return render_template('admin/classes.html',
                           classes=classes, subjects=subjects,
                           semesters=semesters, teachers=teachers)


# --- XẾP LỊCH & CHECK TRÙNG (CORE FEATURE) ---
@admin.route('/class/<int:class_id>/schedule', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_class_schedule(class_id):
    current_class = Class.query.get_or_404(class_id)

    if request.method == 'POST':
        # Xử lý thêm lịch học
        if 'add_schedule' in request.form:
            day = int(request.form.get('day_of_week'))
            start = int(request.form.get('start_lesson'))
            end = int(request.form.get('end_lesson'))
            room = request.form.get('room').strip().upper()

            # --- LOGIC KIỂM TRA TRÙNG LỊCH ---
            is_conflict = False
            conflict_msg = ""

            # Lấy tất cả lịch học trong cùng HỌC KỲ này
            # Logic: Join Schedule -> Class -> Semester
            semester_schedules = db.session.query(Schedule, Class) \
                .join(Class).filter(Class.semester_id == current_class.semester_id).all()

            for sched, cls in semester_schedules:
                # Chỉ kiểm tra nếu cùng Ngày trong tuần
                if sched.day_of_week == day:
                    # Kiểm tra trùng tiết (Overlap Logic): (StartA < EndB) and (EndA > StartB)
                    if start < sched.end_lesson and end > sched.start_lesson:

                        # 1. Trùng Giảng viên (Giảng viên này đang dạy lớp khác vào giờ này?)
                        if cls.teacher_id == current_class.teacher_id:
                            is_conflict = True
                            conflict_msg = f"Giảng viên bị trùng lịch với lớp {cls.name} (Tiết {sched.start_lesson}-{sched.end_lesson})"
                            break

                        # 2. Trùng Phòng học (Phòng này đang có lớp khác học?)
                        if sched.room == room:
                            is_conflict = True
                            conflict_msg = f"Phòng {room} đã có lớp {cls.name} học (Tiết {sched.start_lesson}-{sched.end_lesson})"
                            break

            if is_conflict:
                flash(f'KHÔNG THỂ LƯU: {conflict_msg}', 'danger')
            else:
                new_sched = Schedule(
                    class_info=current_class,
                    day_of_week=day,
                    start_lesson=start,
                    end_lesson=end,
                    room=room
                )
                db.session.add(new_sched)
                db.session.commit()
                flash('Thêm lịch học thành công!', 'success')

        # Xử lý xóa lịch
        elif 'delete_schedule' in request.form:
            sched_id = request.form.get('schedule_id')
            Schedule.query.filter_by(id=sched_id).delete()
            db.session.commit()
            flash('Đã xóa buổi học.', 'info')

        return redirect(url_for('admin.manage_class_schedule', class_id=class_id))

    return render_template('admin/class_schedule.html', current_class=current_class)