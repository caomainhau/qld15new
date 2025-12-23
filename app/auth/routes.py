from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from ..models import User
from .. import db
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user


@auth.route('/login', methods=['GET', 'POST'])
def login():
    # Nếu đã đăng nhập thì chuyển hướng luôn
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))  # Chúng ta sẽ tạo route này sau
        elif current_user.role == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        # 1. Kiểm tra đuôi email VKU
        if not email.endswith('@vku.udn.vn'):
            flash('Vui lòng sử dụng email nhà trường (@vku.udn.vn)', 'danger')
            return render_template('auth/login.html')

        # 2. Kiểm tra User trong DB
        user = User.query.filter_by(email=email).first()

        # 3. Kiểm tra mật khẩu hash
        if not user or not user.check_password(password):
            flash('Email hoặc mật khẩu không chính xác.', 'danger')
            return redirect(url_for('auth.login'))

        # 4. Đăng nhập thành công
        login_user(user, remember=remember)

        # Chuyển hướng theo Role
        if user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user.role == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        else:
            return redirect(url_for('student.dashboard'))

    return render_template('auth/login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # 1. Kiểm tra mật khẩu cũ
        if not current_user.check_password(current_password):
            flash('Mật khẩu hiện tại không đúng.', 'danger')
            return redirect(url_for('auth.change_password'))

        # 2. Kiểm tra xác nhận mật khẩu
        if new_password != confirm_password:
            flash('Mật khẩu xác nhận không khớp.', 'danger')
            return redirect(url_for('auth.change_password'))

        # 3. Đổi mật khẩu
        current_user.set_password(new_password)
        db.session.commit()
        flash('Đổi mật khẩu thành công! Vui lòng đăng nhập lại.', 'success')
        return redirect(url_for('auth.logout'))

    return render_template('auth/change_password.html')

