import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'vku-super-secret-key-2024'
    # Thay đổi user, password, db_name tương ứng với MySQL của bạn
    SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:@localhost/vku_grade_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False