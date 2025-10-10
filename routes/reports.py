"""Reporting routes"""
from flask import Blueprint, render_template, request
from flask_login import login_required
from decimal import Decimal
from sqlalchemy import func, desc
from models import (db, Student, Class, FeeAssessment, Payment, PaymentAllocation,
                    Vehicle, FeeItem, FeeRate, AcademicYear, get_student_balance_summary)

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/class_summary')
@login_required
def class_summary():
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)
    class_id = request.args.get('class_id', type=int)

    current_year = AcademicYear.query.filter_by(is_current=True).first()
    if not term and current_year:
        year = current_year.year
        term = 1

    classes = Class.query.all()
    summary_data = []

    target_classes = [Class.query.get(class_id)] if class_id else classes

    for cls in target_classes:
        if not cls:
            continue

        students = Student.query.filter_by(class_id=cls.id, is_active=True).all()

        class_summary = {
            'class': cls,
            'total_students': len(students),
            'total_assessed': 0,
            'total_paid': 0,
            'outstanding': 0,
            'streams': {}
        }

        for student in students:
            assessments = FeeAssessment.query.filter_by(
                student_id=student.id,
                term=term,
                year=year
            ).all() if term and year else []

            student_assessed = sum(a.amount for a in assessments)

            student_paid = db.session.query(func.sum(PaymentAllocation.amount)) \
                               .join(FeeAssessment) \
                               .filter(FeeAssessment.student_id == student.id,
                                       FeeAssessment.term == term,
                                       FeeAssessment.year == year) \
                               .scalar() or 0

            class_summary['total_assessed'] += student_assessed
            class_summary['total_paid'] += student_paid

            stream_key = student.stream.name if student.stream else 'No Stream'
            if stream_key not in class_summary['streams']:
                class_summary['streams'][stream_key] = {
                    'students': 0, 'assessed': 0, 'paid': 0
                }

            class_summary['streams'][stream_key]['students'] += 1
            class_summary['streams'][stream_key]['assessed'] += student_assessed
            class_summary['streams'][stream_key]['paid'] += student_paid

        class_summary['outstanding'] = class_summary['total_assessed'] - class_summary['total_paid']
        summary_data.append(class_summary)

    return render_template('reports/class_summary.html',
                           summary_data=summary_data,
                           classes=classes,
                           selected_class=class_id,
                           term=term,
                           year=year)


@reports_bp.route('/student_statement/<int:student_id>')
@login_required
def student_statement(student_id):
    student = Student.query.get_or_404(student_id)
    balance_summary = get_student_balance_summary(student_id)

    assessments = FeeAssessment.query.filter_by(student_id=student_id) \
        .order_by(FeeAssessment.year, FeeAssessment.term) \
        .all()

    payments = Payment.query.filter_by(student_id=student_id) \
        .order_by(Payment.payment_date) \
        .all()

    return render_template('reports/student_statement.html',
                           student=student,
                           balance_summary=balance_summary,
                           assessments=assessments,
                           payments=payments)


@reports_bp.route('/outstanding_fees')
@login_required
def outstanding_fees():
    class_id = request.args.get('class_id', type=int)

    query = Student.query.filter_by(is_active=True)
    if class_id:
        query = query.filter_by(class_id=class_id)

    students_with_outstanding = []

    for student in query.all():
        balance = student.get_current_balance()
        if balance > 0:
            students_with_outstanding.append({
                'student': student,
                'balance': balance
            })

    students_with_outstanding.sort(key=lambda x: x['balance'], reverse=True)

    classes = Class.query.all()

    return render_template('reports/outstanding_fees.html',
                           students_with_outstanding=students_with_outstanding,
                           classes=classes,
                           selected_class=class_id)


@reports_bp.route('/vehicle_revenue')
@login_required
def vehicle_revenue():
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)

    current_year = AcademicYear.query.filter_by(is_current=True).first()
    if not term and current_year:
        year = current_year.year
        term = 1

    vehicles = Vehicle.query.filter_by(is_active=True).all()
    vehicle_data = []

    transport_fee = FeeItem.query.filter_by(code='TRANSPORT', is_active=True).first()

    rate = None
    if transport_fee and term and year:
        rate = FeeRate.query.filter_by(
            fee_item_id=transport_fee.id,
            term=term,
            year=year,
            is_active=True
        ).first()

    for vehicle in vehicles:
        students = Student.query.filter_by(
            vehicle_id=vehicle.id,
            is_active=True
        ).all()

        vehicle_summary = {
            'vehicle': vehicle,
            'total_students': len(students),
            'total_distance': sum(float(s.transport_distance_km or 0) for s in students),
            'total_assessed': Decimal('0'),
            'total_paid': Decimal('0'),
            'total_balance': Decimal('0'),
            'students': []
        }

        for student in students:
            if not student.transport_distance_km:
                continue

            assessed_amount = Decimal('0')
            if rate and rate.rate_per_km:
                assessed_amount = Decimal(str(student.transport_distance_km)) * rate.rate_per_km

            paid_amount = Decimal('0')
            if transport_fee and term and year:
                transport_assessments = FeeAssessment.query.filter_by(
                    student_id=student.id,
                    fee_item_id=transport_fee.id,
                    term=term,
                    year=year
                ).all()

                for assessment in transport_assessments:
                    allocated = db.session.query(func.sum(PaymentAllocation.amount)) \
                                    .filter_by(assessment_id=assessment.id) \
                                    .scalar() or 0
                    paid_amount += Decimal(str(allocated))

            balance = assessed_amount - paid_amount

            vehicle_summary['total_assessed'] += assessed_amount
            vehicle_summary['total_paid'] += paid_amount
            vehicle_summary['total_balance'] += balance

            vehicle_summary['students'].append({
                'student': student,
                'distance': float(student.transport_distance_km),
                'assessed': assessed_amount,
                'paid': paid_amount,
                'balance': balance
            })

        vehicle_data.append(vehicle_summary)

    totals = {
        'vehicles': len(vehicle_data),
        'students': sum(v['total_students'] for v in vehicle_data),
        'distance': sum(v['total_distance'] for v in vehicle_data),
        'assessed': sum(v['total_assessed'] for v in vehicle_data),
        'paid': sum(v['total_paid'] for v in vehicle_data),
        'balance': sum(v['total_balance'] for v in vehicle_data)
    }

    return render_template('reports/vehicle_revenue.html',
                           vehicle_data=vehicle_data,
                           totals=totals,
                           term=term,
                           year=year,
                           rate=rate,
                           transport_fee=transport_fee)