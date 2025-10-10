"""Flask extensions initialization"""
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from models import db

# Initialize extensions
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

oauth = OAuth()