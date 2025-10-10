"""Application configuration"""
import os
import secrets


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///school_fees.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth configuration
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}