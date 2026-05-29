import os
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def get_real_ip():
    return request.headers.get('X-Real-IP') or request.remote_addr


limiter = Limiter(key_func=get_real_ip, storage_uri="memory://", default_limits=[])


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_todo_app_2025')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///todo.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Connectez-vous pour accéder à vos tâches.'
    login_manager.login_message_category = 'info'

    from app.routes import main
    from app.auth import auth
    app.register_blueprint(main)
    app.register_blueprint(auth)

    with app.app_context():
        db.create_all()

    return app
