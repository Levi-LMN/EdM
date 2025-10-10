"""Blueprint registration"""
from flask import Flask


def register_blueprints(app: Flask):
    """Register all blueprints"""
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .academic import academic_bp
    from .students import students_bp
    from .vehicles import vehicles_bp
    from .fees import fees_bp
    from .payments import payments_bp
    from .expenses import expenses_bp
    from .promotions import promotions_bp
    from .reports import reports_bp
    from .api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(academic_bp, url_prefix='/academic')
    app.register_blueprint(students_bp, url_prefix='/students')
    app.register_blueprint(vehicles_bp, url_prefix='/vehicles')
    app.register_blueprint(fees_bp, url_prefix='/fees')
    app.register_blueprint(payments_bp, url_prefix='/payments')
    app.register_blueprint(expenses_bp, url_prefix='/expenses')
    app.register_blueprint(promotions_bp, url_prefix='/promotions')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(api_bp, url_prefix='/api')