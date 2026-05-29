from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db, limiter
from app.models import User
from urllib.parse import urlparse

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc != '':
                next_page = None
            return redirect(next_page or url_for('main.index'))
        flash('Email ou mot de passe incorrect.', 'error')

    return render_template('login.html')


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('Tous les champs sont requis.', 'error')
        elif len(password) < 8:
            flash('Le mot de passe doit faire au moins 8 caractères.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'error')
        elif User.query.filter_by(username=username).first():
            flash("Ce nom d'utilisateur est déjà pris.", 'error')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            return redirect(url_for('main.index'))

    return render_template('register.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
