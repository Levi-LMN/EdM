"""Authentication routes"""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from models import db, User, UserRole
from extensions import oauth

auth_bp = Blueprint('auth', __name__)

# Configure Google OAuth
google = oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('auth/login.html')


@auth_bp.route('/login')
def login():
    redirect_uri = url_for('auth.auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/callback')
def auth_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')

    if user_info:
        user = User.query.filter_by(email=user_info['email']).first()

        if not user:
            user = User(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info['name'],
                profile_pic=user_info.get('picture'),
                role=UserRole.ACCOUNTANT
            )
            db.session.add(user)
            db.session.commit()

        user.last_login = datetime.utcnow()
        db.session.commit()

        login_user(user)
        return redirect(url_for('dashboard.dashboard'))

    flash('Authentication failed', 'error')
    return redirect(url_for('auth.index'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.index'))