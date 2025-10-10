"""Main Flask application"""
from flask import Flask, render_template
from datetime import date, datetime
from decimal import Decimal
from config import config
from extensions import db, login_manager, oauth
from models import User, UserRole, StudentType, PaymentMode, FeeScope, PromotionStatus, ExpenseCategory, FeeItem
from routes import register_blueprints


def create_app(config_name='default'):
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)

    # Register blueprints
    register_blueprints(app)

    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Template globals
    @app.context_processor
    def inject_enums():
        return {
            'StudentType': StudentType,
            'UserRole': UserRole,
            'PaymentMode': PaymentMode,
            'FeeScope': FeeScope,
            'PromotionStatus': PromotionStatus
        }

    # Template filters
    @app.template_filter('currency')
    def currency_filter(amount):
        if amount is None:
            return "KSh 0.00"
        return f"KSh {amount:,.2f}"

    @app.template_filter('percentage')
    def percentage_filter(value):
        if value is None:
            return "0%"
        return f"{value:.1f}%"

    @app.template_filter('amount_to_words')
    def amount_to_words_filter(amount):
        from utils import amount_to_words
        return amount_to_words(amount)

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app


def init_database(app):
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()

        # Create default expense categories
        if not ExpenseCategory.query.first():
            default_categories = [
                ('ADMIN', 'Administration'),
                ('MAINT', 'Maintenance'),
                ('UTIL', 'Utilities'),
                ('TRANS', 'Transport'),
                ('FOOD', 'Food & Catering'),
                ('SUPP', 'Supplies'),
                ('OTHER', 'Other')
            ]

            for code, name in default_categories:
                category = ExpenseCategory(code=code, name=name)
                db.session.add(category)

            db.session.commit()

        # Create default fee items
        if not FeeItem.query.first():
            from models import FeeScope
            default_fees = [
                ('TUITION', 'Tuition Fee', FeeScope.CLASS_LEVEL, False),
                ('BOARDING', 'Boarding Fee', FeeScope.CLASS_LEVEL, False),
                ('TRANSPORT', 'Transport Fee', FeeScope.INDIVIDUAL, True),
                ('MEALS', 'Meals Fee', FeeScope.CLASS_LEVEL, False),
                ('UNIFORM', 'Uniform Fee', FeeScope.UNIVERSAL, False),
                ('BOOKS', 'Books & Materials', FeeScope.CLASS_LEVEL, False),
                ('ACTIVITY', 'Activity Fee', FeeScope.UNIVERSAL, False),
                ('SWIMMING', 'Swimming Fee', FeeScope.INDIVIDUAL, False),
                ('EXAM', 'Examination Fee', FeeScope.CLASS_LEVEL, False)
            ]

            for code, name, scope, is_per_km in default_fees:
                fee = FeeItem(code=code, name=name, scope=scope, is_per_km=is_per_km)
                db.session.add(fee)

            db.session.commit()

        # Create default admin user
        if not User.query.first():
            admin_user = User(
                email='admin@school.com',
                name='System Administrator',
                role=UserRole.ADMIN,
                is_active=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created: admin@school.com")



if __name__ == '__main__':
    app = create_app('development')
    init_database(app)
    app.run(debug=True)
