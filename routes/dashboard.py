"""Dashboard routes"""
from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import desc
from models import AcademicYear, Student, Class, Vehicle, Payment

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    # Get current academic year
    current_year = AcademicYear.query.filter_by(is_current=True).first()

    # Basic statistics
    stats = {
        'total_students': Student.query.filter_by(is_active=True).count(),
        'total_classes': Class.query.count(),
        'total_vehicles': Vehicle.query.filter_by(is_active=True).count(),
        'current_year': current_year.year if current_year else 'Not Set'
    }

    # Recent payments (last 10)
    recent_payments = Payment.query.order_by(desc(Payment.created_at)).limit(10).all()

    # Students with outstanding balances
    students_with_balances = []
    students = Student.query.filter_by(is_active=True).limit(20).all()

    for student in students:
        balance = student.get_current_balance()
        if balance > 0:
            students_with_balances.append({
                'student': student,
                'balance': balance
            })

    # Sort by balance descending
    students_with_balances.sort(key=lambda x: x['balance'], reverse=True)
    students_with_balances = students_with_balances[:10]

    return render_template('dashboard.html',
                           stats=stats,
                           recent_payments=recent_payments,
                           students_with_balances=students_with_balances)