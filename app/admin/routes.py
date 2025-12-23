from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from . import admin
from .. import db
from ..models import User, Student, Teacher, Subject, Class, Semester, Schedule, Enrollment
# Import hàm check trùng lịch mới từ utils
from ..utils import admin_required, check_schedule_conflict
import unicodedata # Thêm thư viện này ở đầu file để xử lý tiếng Việt
import re
import string
import secrets  # Thư viện sinh số ngẫu nhiên an toàn
from ..models import Subject, GradeWeight




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
    # Nếu dùng server_default trong model thì logic này vẫn chạy ổn với trường hợp xem user active gần đây
    five_min_ago = now - timedelta(minutes=5)
    online_users = User.query.filter(User.last_seen >= five_min_ago).order_by(User.last_seen.desc()).all()
    return render_template('admin/active_users.html', online_users=online_users)


def generate_email_prefix(full_name):
    """
    Chuyển "Nguyễn Văn An" -> "annv"
    """
    # 1. Chuyển tiếng Việt có dấu thành không dấu
    text = unicodedata.normalize('NFD', full_name)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.replace('đ', 'd').replace('Đ', 'D')

    # 2. Tách từ và xử lý
    parts = text.lower().split()
    if not parts: return "student"

    # Tên (từ cuối cùng)
    first_name = parts[-1]

    # Họ lót (các từ đầu) -> lấy chữ cái đầu
    initials = "".join([p[0] for p in parts[:-1]])

    return f"{first_name}{initials}"


# --- 1. QUẢN LÝ SINH VIÊN ---
@admin.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_students():
    MAJORS = [
        {'code': 'GIT', 'name': 'CNTT - Kỹ sư phần mềm'},
        {'code': 'GBA', 'name': 'Quản trị kinh doanh'},
        {'code': 'GMM', 'name': 'Marketing số'},
        {'code': 'GAI', 'name': 'Trí tuệ nhân tạo'},
        {'code': 'NS', 'name': 'An toàn thông tin'},
    ]
    COHORTS = ['K20', 'K21', 'K22', 'K23', 'K24', 'K25', 'K26']

    # --- XỬ LÝ POST: THÊM SINH VIÊN ---
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        major_code = request.form.get('major_code')
        cohort = request.form.get('cohort')
        class_name = request.form.get('class_name')

        # 1. Tự động sinh Mã Sinh Viên (GIT001...)
        last_student = Student.query.filter(Student.student_code.like(f"{major_code}%")) \
            .order_by(Student.student_code.desc()).first()

        if last_student:
            try:
                last_number = int(last_student.student_code[-3:])
                new_number = last_number + 1
            except ValueError:
                new_number = 1
        else:
            new_number = 1

        new_student_code = f"{major_code}{str(new_number).zfill(3)}"

        # 2. Tự động sinh Email
        email_prefix = generate_email_prefix(full_name)
        email = f"{email_prefix}.{new_student_code.lower()}@vku.udn.vn"

        # 3. Tự động sinh Mật khẩu: [MãSV] + [5 ký tự ngẫu nhiên]
        # Ví dụ: GIT001 + aB3xZ -> GIT001aB3xZ
        random_chars = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(5))
        generated_password = f"{new_student_code}{random_chars}"

        if User.query.filter_by(email=email).first():
            flash(f'Lỗi: Email {email} đã tồn tại!', 'danger')
        else:
            # 4. Tạo User
            new_user = User(email=email, full_name=full_name, role='student')
            new_user.set_password(generated_password)  # Lưu mật khẩu đã mã hóa
            db.session.add(new_user)
            db.session.commit()

            # 5. Tạo Student
            new_student = Student(
                user_id=new_user.id,
                student_code=new_student_code,
                class_name=class_name,
                major=next((m['name'] for m in MAJORS if m['code'] == major_code), major_code),
                cohort=cohort
            )
            db.session.add(new_student)
            db.session.commit()

            # 6. THÔNG BÁO QUAN TRỌNG: Hiển thị mật khẩu ra cho Admin thấy
            # Sử dụng HTML safe trong flash message ở frontend nếu cần, hoặc format text rõ ràng
            flash_message = (
                f"✅ Đã tạo thành công!<br>"
                f"👤 SV: <b>{full_name}</b><br>"
                f"📧 Email: <b>{email}</b><br>"
                f"🔑 Mật khẩu: <b style='font-size: 1.2em; color: #d63384;'>{generated_password}</b>"
            )
            flash(flash_message, 'success')

        return redirect(url_for('admin.manage_students'))

    # --- XỬ LÝ GET (Giữ nguyên như cũ) ---
    query = Student.query.join(User)

    f_major = request.args.get('major')
    f_cohort = request.args.get('cohort')
    f_class = request.args.get('class_name')
    f_search = request.args.get('search')

    if f_major: query = query.filter(Student.major == f_major)
    if f_cohort: query = query.filter(Student.cohort == f_cohort)
    if f_class: query = query.filter(Student.class_name.contains(f_class))
    if f_search:
        query = query.filter(
            (User.full_name.contains(f_search)) |
            (Student.student_code.contains(f_search)) |
            (User.email.contains(f_search))
        )

    students = query.order_by(Student.student_code.desc()).all()
    all_majors_db = db.session.query(Student.major).distinct().all()
    all_cohorts_db = db.session.query(Student.cohort).distinct().all()

    return render_template('admin/students.html',
                           students=students,
                           all_majors=all_majors_db,
                           all_cohorts=all_cohorts_db,
                           majors_list=MAJORS,
                           cohorts_list=COHORTS)


# ... (các import secrets, string, unicodedata đã có từ trước)

# --- 2. QUẢN LÝ GIẢNG VIÊN ---
@admin.route('/teachers', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_teachers():
    # Danh sách các Khoa tại VKU (Cố định để chọn cho chuẩn)
    DEPARTMENTS = [
        "Khoa Khoa học máy tính",
        "Khoa Kỹ thuật máy tính & Điện tử",
        "Khoa Kinh tế số & TMĐT",
        "Khoa Khoa học cơ bản",
        "Trung tâm Học liệu & Truyền thông"
    ]

    # --- XỬ LÝ POST: THÊM GIẢNG VIÊN ---
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        department = request.form.get('department')

        # 1. Tự động sinh Mã Giảng Viên (GV001, GV002...)
        # Tìm mã lớn nhất hiện tại
        last_teacher = Teacher.query.filter(Teacher.teacher_code.like("GV%")) \
            .order_by(Teacher.id.desc()).first()

        if last_teacher:
            try:
                # Giả sử mã là GV001 -> lấy 001
                last_number = int(last_teacher.teacher_code[2:])
                new_number = last_number + 1
            except ValueError:
                new_number = 1
        else:
            new_number = 1

        # Tạo mã mới (GV + 3 số)
        new_teacher_code = f"GV{str(new_number).zfill(3)}"

        # 2. Tự động sinh Email
        # VD: giangnv.gv001@vku.udn.vn
        email_prefix = generate_email_prefix(full_name)
        email = f"{email_prefix}.{new_teacher_code.lower()}@vku.udn.vn"

        # 3. Sinh mật khẩu ngẫu nhiên
        random_chars = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
        generated_password = f"{new_teacher_code}@{random_chars}"

        # 4. Kiểm tra trùng email
        if User.query.filter_by(email=email).first():
            flash(f'Lỗi: Email {email} đã tồn tại!', 'danger')
        else:
            # Tạo User
            new_user = User(email=email, full_name=full_name, role='teacher')
            new_user.set_password(generated_password)
            db.session.add(new_user)
            db.session.commit()

            # Tạo Teacher Profile
            new_teacher = Teacher(
                user_id=new_user.id,
                teacher_code=new_teacher_code,
                department=department
            )
            db.session.add(new_teacher)
            db.session.commit()

            # Thông báo kèm mật khẩu
            flash_message = (
                f"✅ Đã thêm Giảng viên thành công!<br>"
                f"👤 GV: <b>{full_name}</b><br>"
                f"🆔 Mã GV: <b>{new_teacher_code}</b><br>"
                f"📧 Email: <b>{email}</b><br>"
                f"🔑 Mật khẩu: <b style='font-size: 1.2em; color: #d63384;'>{generated_password}</b>"
            )
            flash(flash_message, 'success')

        return redirect(url_for('admin.manage_teachers'))

    # --- XỬ LÝ GET: LỌC & HIỂN THỊ ---
    query = Teacher.query.join(User)

    f_dept = request.args.get('department')
    f_search = request.args.get('search')

    if f_dept:
        query = query.filter(Teacher.department == f_dept)

    if f_search:
        query = query.filter(
            (User.full_name.contains(f_search)) |
            (Teacher.teacher_code.contains(f_search)) |
            (User.email.contains(f_search))
        )

    teachers = query.order_by(Teacher.teacher_code.asc()).all()

    # Lấy danh sách khoa thực tế trong DB để làm bộ lọc (nếu muốn lọc theo dữ liệu cũ)
    # Hoặc dùng list DEPARTMENTS cố định cũng được. Ở đây tôi dùng DB distinct.
    db_departments = db.session.query(Teacher.department).distinct().all()

    return render_template('admin/teachers.html',
                           teachers=teachers,
                           departments=db_departments,
                           dept_list=DEPARTMENTS)  # Truyền list cố định cho Modal


# --- HÀM HỖ TRỢ: SINH MÃ HỌC PHẦN TỰ ĐỘNG ---
def generate_subject_code(name):
    """
    Input: "Lập trình Python Nâng cao"
    Output: "LTPNC25" (Nếu năm là 2025)
    """
    # 1. Xử lý tiếng Việt (Bỏ dấu)
    text = unicodedata.normalize('NFD', name)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # 2. Lấy chữ cái đầu của từng từ (Viết hoa)
    words = text.upper().split()
    initials = "".join([w[0] for w in words if w.isalnum()])

    # 3. Lấy 2 số cuối của năm hiện tại
    current_year = datetime.now().strftime("%y")  # VD: 2025 -> "25"

    return f"{initials}{current_year}"

# --- 3. QUẢN LÝ MÔN HỌC ---
@admin.route('/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_subjects():
    # --- XỬ LÝ POST: THÊM MÔN HỌC ---
    if request.method == 'POST':
        # Không lấy code từ form nữa
        name = request.form.get('name')
        credits = request.form.get('credits')

        # Lấy cấu trúc điểm động
        col_names = request.form.getlist('col_names[]')
        col_weights = request.form.getlist('col_weights[]')

        # Validate tổng %
        total_weight = sum([int(w) for w in col_weights if w.isdigit()])

        if total_weight != 100:
            flash(f'Tổng tỷ lệ phần trăm phải bằng 100% (Hiện tại: {total_weight}%)', 'danger')
        else:
            # --- LOGIC TỰ ĐỘNG SINH MÃ ---
            base_code = generate_subject_code(name)  # VD: LTW25
            final_code = base_code

            # Kiểm tra trùng lặp. Nếu trùng "LTW25", thử "LTW25A", "LTW25B"...
            while Subject.query.filter_by(code=final_code).first():
                random_char = secrets.choice(string.ascii_uppercase)  # A-Z
                final_code = f"{base_code}{random_char}"

            # --- LƯU VÀO DB ---
            new_sub = Subject(code=final_code, name=name, credits=credits)
            db.session.add(new_sub)
            db.session.commit()

            # Lưu cấu trúc điểm
            for i in range(len(col_names)):
                gw = GradeWeight(
                    subject_id=new_sub.id,
                    name=col_names[i],
                    weight_percent=int(col_weights[i]),
                    order_index=i + 1
                )
                db.session.add(gw)

            db.session.commit()
            flash(f'Đã thêm môn: {name} (Mã: {final_code})', 'success')

        return redirect(url_for('admin.manage_subjects'))

    # --- XỬ LÝ GET: LỌC MÔN THEO KỲ ---
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    active_semester = Semester.query.filter_by(is_active=True).order_by(Semester.start_date.desc()).first()

    # Logic xác định kỳ cần lọc
    # 1. Nếu người dùng chọn trên giao diện (?semester_id=...)
    semester_id_str = request.args.get('semester_id')

    selected_semester = None
    query = Subject.query

    if semester_id_str == 'all':
        # Trường hợp xem "Tất cả danh mục" (Kho môn học)
        subjects = query.order_by(Subject.code.asc()).all()

    elif semester_id_str:
        # Trường hợp người dùng chọn 1 kỳ cụ thể
        try:
            sem_id = int(semester_id_str)
            selected_semester = Semester.query.get(sem_id)
            # Chỉ lấy các môn CÓ MỞ LỚP trong kỳ này (Join với Class)
            subjects = query.join(Class).filter(Class.semester_id == sem_id).distinct().all()
        except ValueError:
            subjects = []

    else:
        # Trường hợp mặc định (Vừa vào trang): Hiển thị theo KỲ HIỆN TẠI
        if active_semester:
            selected_semester = active_semester
            subjects = query.join(Class).filter(Class.semester_id == active_semester.id).distinct().all()
        else:
            # Nếu không có kỳ nào active, hiện tất cả
            subjects = query.order_by(Subject.code.asc()).all()

    return render_template('admin/subjects.html',
                           subjects=subjects,
                           semesters=semesters,
                           selected_semester=selected_semester,
                           is_all=(semester_id_str == 'all'))

# =======================================================
# 4. QUẢN LÝ LỚP HỌC PHẦN & API AJAX (QUAN TRỌNG)
# =======================================================

# API 1: Lấy số nhóm tiếp theo (Tự động đặt tên lớp)
@admin.route('/api/get_next_group', methods=['GET'])
@login_required
def get_next_group():
    subject_id = request.args.get('subject_id')
    semester_id = request.args.get('semester_id')

    if not subject_id or not semester_id:
        return jsonify({'next_group': '01'})

    count = Class.query.filter_by(subject_id=subject_id, semester_id=semester_id).count()
    next_number = str(count + 1).zfill(2)
    return jsonify({'next_group': next_number})


# API 2: Lấy danh sách lịch học của 1 lớp
@admin.route('/api/schedule/get/<int:class_id>', methods=['GET'])
@login_required
def get_class_schedule(class_id):
    schedules = Schedule.query.filter_by(class_id=class_id, is_canceled=False).order_by(Schedule.day_of_week,
                                                                                        Schedule.start_lesson).all()
    data = []
    for s in schedules:
        data.append({
            'id': s.id,
            'day': s.day_of_week,
            'start': s.start_lesson,
            'end': s.end_lesson,
            'room': s.room
        })
    return jsonify(data)


# API 3: Thêm lịch học mới (Có check trùng)
@admin.route('/api/schedule/add', methods=['POST'])
@login_required
def add_schedule():
    data = request.json
    try:
        class_id = int(data.get('class_id'))
        day = int(data.get('day'))
        start = int(data.get('start'))
        count = int(data.get('count'))
        room = data.get('room')
        end = start + count - 1
    except (ValueError, TypeError):
        return jsonify({'success': False, 'msg': 'Dữ liệu không hợp lệ!'})

    cls = Class.query.get(class_id)
    if not cls:
        return jsonify({'success': False, 'msg': 'Lớp học không tồn tại!'})

    # Gọi hàm check trùng từ utils.py
    # Hàm trả về True nếu có trùng
    is_conflict = check_schedule_conflict(class_id, day, start, end, room, cls.semester_id)

    if is_conflict:
        return jsonify({'success': False, 'msg': f'TRÙNG LỊCH: Phòng {room} hoặc Giảng viên đã bận vào thời gian này!'})

    # Nếu không trùng -> Lưu
    new_sch = Schedule(class_id=class_id, day_of_week=day, start_lesson=start, end_lesson=end, room=room)
    db.session.add(new_sch)
    db.session.commit()

    return jsonify({'success': True, 'msg': 'Thêm lịch thành công!'})


# API 4: Xóa lịch học
@admin.route('/api/schedule/delete', methods=['POST'])
@login_required
def delete_schedule():
    data = request.json
    sch_id = data.get('schedule_id')
    schedule = Schedule.query.get(sch_id)
    if schedule:
        db.session.delete(schedule)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'msg': 'Không tìm thấy lịch trình'})


# Route chính: Quản lý lớp
# app/admin/routes.py

@admin.route('/classes', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_classes():
    # --- XỬ LÝ POST: TẠO LỚP MỚI ---
    if request.method == 'POST':
        name = request.form.get('name')
        subject_id = request.form.get('subject_id')
        semester_id = request.form.get('semester_id')
        teacher_id = request.form.get('teacher_id')
        max_students = request.form.get('max_students')

        sem_check = Semester.query.get(semester_id)
        if not sem_check.is_active:
            flash('Học kỳ đã kết thúc hoặc bị khóa, không thể tạo lớp!', 'danger')
        else:
            new_class = Class(
                name=name,
                subject_id=subject_id,
                semester_id=semester_id,
                teacher_id=teacher_id,
                max_students=max_students
            )
            db.session.add(new_class)
            db.session.commit()
            flash(f'Thêm lớp "{name}" thành công.', 'success')
        return redirect(url_for('admin.manage_classes'))

    # --- XỬ LÝ GET: LỌC VÀ HIỂN THỊ ---
    query = Class.query.join(Subject).join(Teacher).join(Semester)

    # 1. Lấy thông tin từ URL
    f_sem = request.args.get('semester_id')
    f_dept = request.args.get('department')
    f_sub = request.args.get('subject_id')
    f_teacher = request.args.get('teacher_id')

    # 2. Logic "Tự động hiển thị kỳ hiện tại"
    # Nếu không có tham số semester_id trên URL (tức là mới vào trang)
    if f_sem is None:
        active_sem = Semester.query.filter_by(is_active=True).order_by(Semester.start_date.desc()).first()
        if active_sem:
            f_sem = active_sem.id  # Tự động set ID kỳ hiện tại để lọc

    # 3. Áp dụng các bộ lọc
    if f_sem: query = query.filter(Class.semester_id == f_sem)
    if f_dept: query = query.filter(Teacher.department == f_dept)
    if f_sub: query = query.filter(Class.subject_id == f_sub)
    if f_teacher: query = query.filter(Class.teacher_id == f_teacher)

    classes = query.order_by(Class.id.desc()).all()

    # 4. Lấy dữ liệu cho các Select box
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    teachers = Teacher.query.join(User).order_by(User.full_name).all()
    subjects = Subject.query.order_by(Subject.name).all()
    departments = db.session.query(Teacher.department).distinct().all()

    # Truyền thêm current_filter_sem để Frontend biết đang lọc theo kỳ nào
    return render_template('admin/classes.html',
                           classes=classes,
                           semesters=semesters,
                           teachers=teachers,
                           subjects=subjects,
                           departments=departments,
                           current_filter_sem=int(f_sem) if f_sem else None)


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
        # Nếu còn sinh viên chưa có điểm tổng kết (total_10 is None)
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


# --- 6. TẠO USER (DỰ PHÒNG) ---
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