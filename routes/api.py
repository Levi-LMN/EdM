"""API endpoints"""
from flask import Blueprint, jsonify, request
from flask_login import login_required
from decimal import Decimal
from sqlalchemy import or_, func
from models import (db, Student, Stream, FeeRate, FeeItem, FeeScope,
                    StudentType, FeeAssessment, PaymentAllocation)

api_bp = Blueprint('api', __name__)


@api_bp.route('/streams/<int:class_id>')
@login_required
def get_streams(class_id):
    """Get streams for a class"""
    streams = Stream.query.filter_by(class_id=class_id).all()
    return jsonify([{'id': s.id, 'name': s.name} for s in streams])


@api_bp.route('/student_search')
@login_required
def student_search():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    students = Student.query.filter(
        Student.is_active == True,
        or_(
            Student.admission_no.contains(query),
            Student.first_name.contains(query),
            Student.last_name.contains(query)
        )
    ).limit(10).all()

    return jsonify([{
        'id': s.id,
        'admission_no': s.admission_no,
        'name': s.full_name,
        'class': f"{s.class_obj.name}{'-' + s.stream.name if s.stream else ''}"
    } for s in students])


@api_bp.route('/student_balance/<int:student_id>')
@login_required
def student_balance(student_id):
    student = Student.query.get_or_404(student_id)
    balance = student.get_current_balance()

    return jsonify({
        'student_id': student_id,
        'admission_no': student.admission_no,
        'name': student.full_name,
        'balance': float(balance)
    })


@api_bp.route('/get_standard_rate', methods=['POST'])
@login_required
def get_standard_rate():
    """Get standard rate information for a fee item"""
    try:
        fee_item_id = int(request.form['fee_item_id'])
        term = int(request.form['term'])
        year = int(request.form['year'])
        student_id = int(request.form['student_id'])

        student = Student.query.get_or_404(student_id)
        fee_item = FeeItem.query.get_or_404(fee_item_id)

        rate = None
        scope_description = ""

        if fee_item.scope == FeeScope.UNIVERSAL:
            rate = FeeRate.query.filter_by(
                fee_item_id=fee_item_id,
                term=term,
                year=year,
                class_id=None,
                stream_id=None,
                is_active=True
            ).first()
            scope_description = "All students"

        elif fee_item.scope == FeeScope.STREAM_LEVEL and student.stream_id:
            rate = FeeRate.query.filter_by(
                fee_item_id=fee_item_id,
                term=term,
                year=year,
                stream_id=student.stream_id,
                student_type=student.student_type,
                is_active=True
            ).first()

            if not rate:
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item_id,
                    term=term,
                    year=year,
                    stream_id=student.stream_id,
                    student_type=None,
                    is_active=True
                ).first()

            scope_description = f"{student.class_obj.name}-{student.stream.name}"

        elif fee_item.scope == FeeScope.CLASS_LEVEL:
            rate = FeeRate.query.filter_by(
                fee_item_id=fee_item_id,
                term=term,
                year=year,
                class_id=student.class_id,
                student_type=student.student_type,
                is_active=True
            ).first()

            if not rate:
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item_id,
                    term=term,
                    year=year,
                    class_id=student.class_id,
                    student_type=None,
                    is_active=True
                ).first()

            scope_description = student.class_obj.name

        if rate:
            rate_info = {
                'amount': f"KSh {rate.amount:,.2f}" if rate.amount else None,
                'rate_per_km': f"KSh {rate.rate_per_km:,.2f}" if rate.rate_per_km else None,
                'scope_description': scope_description,
                'student_distance': float(student.transport_distance_km) if student.transport_distance_km else None,
                'calculated_amount': None
            }

            if rate.rate_per_km and student.transport_distance_km:
                calculated = float(rate.rate_per_km * student.transport_distance_km)
                rate_info['calculated_amount'] = f"KSh {calculated:,.2f}"

            return jsonify({'success': True, 'rate': rate_info})
        else:
            return jsonify({'success': False, 'message': 'No standard rate found'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})