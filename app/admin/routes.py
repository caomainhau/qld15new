from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import admin
from .. import db
from ..models import User, Student, Teacher, Subject, Class, Semester, Schedule, Enrollment
from ..utils import admin_required, check_schedule_conflict


# --- DASHBOARD ---
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_students': Student.query.count(),
        'total_teachers': Teacher.query.count(),
        'total_classes': Class.query.count(),
        'active_semesters': Semester.query.filter_by(is_active=True).count()
    }
    return render_template('admin/dashboard.html', stats=stats)


# --- THEO DÕI NGƯỜI DÙNG ONLINE ---
@admin.route('/active_users')
@login_required
@admin_required
def active_users():
    now = datetime.utcnow()
    five_min_ago = now - timedelta(minutes=5)
    online_users = User.query.filter(User.last_seen >= five_min_ago).order_by(User.last_seen.desc()).all()
    return render_template('admin/active_users.html', online_users=online_users)


# --- 1. QUẢN LÝ SINH VIÊN ---
@admin.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_students():
    query = Student.query
    f_major = request.args.get('major')
    f_cohort = request.args.get('cohort')
    f_class = request.args.get('class_name')

    if f_major: query = query.filter(Student.major == f_major)
    if f_cohort: query = query.filter(Student.cohort == f_cohort)
    if f_class: query = query.filter(Student.class_name.contains(f_class))

    students = query.all()
    all_majors = db.session.query(Student.major).distinct().all()
    all_cohorts = db.session.query(Student.cohort).distinct().all()

    return render_template('admin/students.html', students=students, all_majors=all_majors, all_cohorts=all_cohorts)


# --- 2. QUẢN LÝ GIẢNG VIÊN ---
@admin.route('/teachers', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_teachers():
    # XỬ LÝ POST: THÊM GIẢNG VIÊN
    if request.method == 'POST':
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        teacher_code = request.form.get('teacher_code')
        department = request.form.get('department')

        if User.query.filter_by(email=email).first():
            flash(f'Email {email} đã tồn tại!', 'danger')
        elif Teacher.query.filter_by(teacher_code=teacher_code).first():
            flash(f'Mã GV {teacher_code} đã tồn tại!', 'danger')
        else:
            new_user = User(email=email, full_name=full_name, role='teacher')
            new_user.set_password('123456')
            db.session.add(new_user)
            db.session.commit()

            new_teacher = Teacher(user_id=new_user.id, teacher_code=teacher_code, department=department)
            db.session.add(new_teacher)
            db.session.commit()
            flash(f'Đã thêm GV {full_name}.', 'success')
        return redirect(url_for('admin.manage_teachers'))

    # XỬ LÝ GET: LỌC VÀ HIỂN THỊ
    query = Teacher.query
    department = request.args.get('department')
    if department:
        query = query.filter(Teacher.department == department)

    teachers = query.all()
    departments = db.session.query(Teacher.department).distinct().all()

    return render_template('admin/teachers.html', teachers=teachers, departments=departments)


# --- 3. QUẢN LÝ MÔN HỌC ---
@admin.route('/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_subjects():
    if request.method == 'POST':
        code = request.form.get('code')
        name = request.form.get('name')
        credits = request.form.get('credits')
        w_cc = int(request.form.get('weight_cc', 10))
        w_gk = int(request.form.get('weight_gk', 30))
        w_ck = int(request.form.get('weight_ck', 60))

        if (w_cc + w_gk + w_ck) != 100:
            flash('Tổng tỷ lệ % phải bằng 100!', 'danger')
        elif Subject.query.filter_by(code=code).first():
            flash(f'Mã {code} đã tồn tại!', 'danger')
        else:
            sub = Subject(code=code, name=name, credits=credits, weight_cc=w_cc, weight_gk=w_gk, weight_ck=w_ck)
            db.session.add(sub)
            db.session.commit()
            flash('Thêm môn học thành công.', 'success')
        return redirect(url_for('admin.manage_subjects'))

    subjects = Subject.query.all()
    return render_template('admin/subjects.html', subjects=subjects)


# --- 4. API & QUẢN LÝ LỚP HỌC PHẦN ---

# [NEW] API Lấy số nhóm tiếp theo (cho JS gọi)
@admin.route('/api/get_next_group', methods=['GET'])
@login_required
def get_next_group():
    subject_id = request.args.get('subject_id')
    semester_id = request.args.get('semester_id')

    if not subject_id or not semester_id:
        return jsonify({'next_group': '01'})

    # Đếm số lớp hiện có của môn này trong học kỳ này
    count = Class.query.filter_by(subject_id=subject_id, semester_id=semester_id).count()

    # Format thành chuỗi 2 chữ số: 1 -> "01", 10 -> "10"
    next_number = str(count + 1).zfill(2)

    return jsonify({'next_group': next_number})


@admin.route('/classes', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_classes():
    query = Class.query.join(Subject).join(Teacher).join(Semester)

    f_sem = request.args.get('semester_id')
    f_dept = request.args.get('department')
    f_sub = request.args.get('subject_id')
    f_teacher = request.args.get('teacher_id')

    if f_sem: query = query.filter(Class.semester_id == f_sem)
    if f_dept: query = query.filter(Teacher.department == f_dept)
    if f_sub: query = query.filter(Class.subject_id == f_sub)
    if f_teacher: query = query.filter(Class.teacher_id == f_teacher)

    classes = query.all()
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    teachers = Teacher.query.all()
    subjects = Subject.query.all()
    departments = db.session.query(Teacher.department).distinct().all()

    if request.method == 'POST':
        name = request.form.get('name')
        subject_id = request.form.get('subject_id')
        semester_id = request.form.get('semester_id')
        teacher_id = request.form.get('teacher_id')
        max_students = request.form.get('max_students')

        sem_check = Semester.query.get(semester_id)
        if not sem_check.is_active:
            flash('Học kỳ đã kết thúc, không thể tạo lớp!', 'danger')
        else:
            new_class = Class(name=name, subject_id=subject_id, semester_id=semester_id, teacher_id=teacher_id,
                              max_students=max_students)
            db.session.add(new_class)
            db.session.commit()
            flash(f'Thêm lớp "{name}" thành công.', 'success')
        return redirect(url_for('admin.manage_classes'))

    return render_template('admin/classes.html', classes=classes, semesters=semesters, teachers=teachers,
                           subjects=subjects, departments=departments)


# --- 5. QUẢN LÝ HỌC KỲ ---
@admin.route('/semesters', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_semesters():
    if request.method == 'POST':
        name = request.form.get('name')
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        new_sem = Semester(name=name, start_date=datetime.strptime(start, '%Y-%m-%d'),
                           end_date=datetime.strptime(end, '%Y-%m-%d'), is_active=True)
        db.session.add(new_sem)
        db.session.commit()
        flash('Tạo học kỳ thành công.', 'success')
        return redirect(url_for('admin.manage_semesters'))

    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    return render_template('admin/semesters.html', semesters=semesters)


@admin.route('/semester/<int:id>/close', methods=['POST'])
@login_required
@admin_required
def close_semester(id):
    semester = Semester.query.get_or_404(id)
    unfinished_classes = []

    for cls in semester.classes:
        if not cls.enrollments: continue
        incomplete_count = Enrollment.query.filter_by(class_id=cls.id, total_10=None).count()
        if incomplete_count > 0:
            unfinished_classes.append(f"{cls.name} ({incomplete_count} SV chưa điểm)")

    if unfinished_classes:
        flash(f'KHÔNG THỂ KẾT THÚC! Lớp chưa đủ điểm: {", ".join(unfinished_classes)}', 'danger')
    else:
        semester.is_active = False
        for cls in semester.classes:
            cls.is_locked = True
        db.session.commit()
        flash(f'Đã kết thúc học kỳ {semester.name}.', 'success')
    return redirect(url_for('admin.manage_semesters'))


# --- 6. THỜI KHÓA BIỂU ---
@admin.route('/timetable', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_timetable():
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    current_semester_id = request.args.get('semester_id', type=int)
    if not current_semester_id and semesters:
        current_semester_id = semesters[0].id

    today_python = datetime.now().weekday()
    default_day_db = today_python + 2
    selected_day = request.args.get('day', default_day_db, type=int)

    if request.method == 'POST':
        current_sem_obj = Semester.query.get(current_semester_id)
        if not current_sem_obj.is_active:
            flash('Học kỳ đã đóng, không thể xếp lịch!', 'danger')
        else:
            class_id = request.form.get('class_id')
            day = int(request.form.get('day'))
            start = int(request.form.get('start'))
            count = int(request.form.get('count'))
            room = request.form.get('room')
            end = start + count - 1

            conflict = check_schedule_conflict(class_id, day, start, end, room, current_semester_id)
            if conflict:
                flash(f'LỖI: Phòng {room} trùng lịch.', 'danger')
            else:
                new_sch = Schedule(class_id=class_id, day_of_week=day, start_lesson=start, end_lesson=end, room=room)
                db.session.add(new_sch)
                db.session.commit()
                flash('Thêm lịch thành công!', 'success')
        return redirect(url_for('admin.manage_timetable', semester_id=current_semester_id, day=day))

    daily_schedules = Schedule.query.join(Class).filter(Class.semester_id == current_semester_id,
                                                        Schedule.day_of_week == selected_day,
                                                        Schedule.is_canceled == False).order_by(
        Schedule.start_lesson.asc()).all()
    active_classes = Class.query.filter_by(semester_id=current_semester_id, is_locked=False).all()

    return render_template('admin/timetable.html', schedules=daily_schedules, semesters=semesters,
                           current_semester_id=current_semester_id, classes=active_classes, selected_day=selected_day)


# --- 7. TẠO USER CHUNG (DỰ PHÒNG) ---
@admin.route('/create_user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        role = request.form.get('role')

        if User.query.filter_by(email=email).first():
            flash('Email đã tồn tại!', 'danger')
        else:
            new_user = User(email=email, full_name=full_name, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            if role == 'student':
                student_code = request.form.get('student_code')
                class_name = request.form.get('class_name')
                major = request.form.get('major')
                cohort = request.form.get('cohort')
                new_student = Student(user_id=new_user.id, student_code=student_code, class_name=class_name,
                                      major=major, cohort=cohort)
                db.session.add(new_student)

            elif role == 'teacher':
                teacher_code = request.form.get('teacher_code')
                department = request.form.get('department')
                new_teacher = Teacher(user_id=new_user.id, teacher_code=teacher_code, department=department)
                db.session.add(new_teacher)

            db.session.commit()
            flash('Tạo tài khoản thành công.', 'success')
        return redirect(url_for('admin.create_user'))
    return render_template('admin/create_user.html')