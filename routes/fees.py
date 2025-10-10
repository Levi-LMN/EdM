"""Fee management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from decimal import Decimal
from sqlalchemy import func
from models import (db, FeeItem, FeeRate, FeeScope, StudentType, Class, Stream,
                    AcademicYear, Student, FeeAssessment, StudentFeeAssignment,
                    PaymentAllocation)
from utils import generate_fee_assessments, get_applicable_fees_for_student, calculate_fee_amount

fees_bp = Blueprint('fees', __name__)


@fees_bp.route('/')
@login_required
def index():
    term = request.args.get('term', 1, type=int)
    year = request.args.get('year', type=int)

    current_year = AcademicYear.query.filter_by(is_current=True).first()

    if not year and current_year:
        year = current_year.year
    elif not year:
        year = 2025

    fee_items = FeeItem.query.all()

    current_rates = []
    if term and year:
        current_rates = FeeRate.query.filter_by(
            term=term,
            year=year,
            is_active=True
        ).all()

    classes = Class.query.all()

    return render_template('fees/index.html',
                           fee_items=fee_items,
                           current_rates=current_rates,
                           current_year=current_year,
                           classes=classes)


@fees_bp.route('/item/add', methods=['GET', 'POST'])
@login_required
def add_item():
    if request.method == 'POST':
        fee_item = FeeItem(
            name=request.form['name'],
            code=request.form['code'].upper(),
            description=request.form['description'],
            scope=FeeScope(request.form['scope']),
            is_per_km=bool(request.form.get('is_per_km'))
        )

        db.session.add(fee_item)
        db.session.commit()
        flash('Fee item added successfully', 'success')
        return redirect(url_for('fees.index'))

    return render_template('fees/add_item.html')


@fees_bp.route('/item/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    fee_item = FeeItem.query.get_or_404(item_id)

    existing_rates_count = FeeRate.query.filter_by(fee_item_id=item_id).count()
    usage_stats = None

    if existing_rates_count > 0:
        total_assessments = FeeAssessment.query.filter_by(fee_item_id=item_id).count()
        total_assignments = StudentFeeAssignment.query.filter_by(fee_item_id=item_id).count()
        total_revenue = db.session.query(func.sum(FeeAssessment.amount)).filter_by(fee_item_id=item_id).scalar() or 0

        usage_stats = {
            'total_rates': existing_rates_count,
            'total_assessments': total_assessments,
            'total_assignments': total_assignments,
            'total_revenue': total_revenue
        }

    if request.method == 'POST':
        fee_item.name = request.form['name']
        fee_item.code = request.form['code'].upper()
        fee_item.description = request.form['description']
        fee_item.scope = FeeScope(request.form['scope'])
        fee_item.is_per_km = bool(request.form.get('is_per_km'))

        db.session.commit()
        flash('Fee item updated successfully', 'success')
        return redirect(url_for('fees.index'))

    return render_template('fees/edit_item.html',
                           fee_item=fee_item,
                           existing_rates_count=existing_rates_count,
                           usage_stats=usage_stats)


@fees_bp.route('/item/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    fee_item = FeeItem.query.get_or_404(item_id)

    assessment_count = FeeAssessment.query.filter_by(fee_item_id=item_id).count()
    if assessment_count > 0:
        flash(f'Cannot delete fee item - it has {assessment_count} assessments', 'error')
        return redirect(url_for('fees.index'))

    rate_count = FeeRate.query.filter_by(fee_item_id=item_id).count()
    if rate_count > 0:
        flash(f'Cannot delete fee item - it has {rate_count} fee rates', 'error')
        return redirect(url_for('fees.index'))

    fee_item_name = fee_item.name
    db.session.delete(fee_item)
    db.session.commit()
    flash(f'Fee item {fee_item_name} deleted successfully', 'success')
    return redirect(url_for('fees.index'))


@fees_bp.route('/rate/add', methods=['GET', 'POST'])
@login_required
def add_rate():
    if request.method == 'POST':
        rate = FeeRate(
            fee_item_id=int(request.form['fee_item_id']),
            term=int(request.form['term']),
            year=int(request.form['year']),
            class_id=int(request.form['class_id']) if request.form.get('class_id') else None,
            stream_id=int(request.form['stream_id']) if request.form.get('stream_id') else None,
            student_type=StudentType(request.form['student_type']) if request.form.get('student_type') else None,
            amount=Decimal(request.form['amount']) if request.form.get('amount') else None,
            rate_per_km=Decimal(request.form['rate_per_km']) if request.form.get('rate_per_km') else None
        )

        db.session.add(rate)
        db.session.commit()
        flash('Fee rate added successfully', 'success')
        return redirect(url_for('fees.index'))

    fee_items = FeeItem.query.filter_by(is_active=True).all()
    classes = Class.query.all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()

    return render_template('fees/add_rate.html',
                           fee_items=fee_items,
                           classes=classes,
                           current_year=current_year)


@fees_bp.route('/rate/edit/<int:rate_id>', methods=['GET', 'POST'])
@login_required
def edit_rate(rate_id):
    fee_rate = FeeRate.query.get_or_404(rate_id)

    existing_assessments_count = FeeAssessment.query.filter_by(fee_item_id=fee_rate.fee_item_id).count()

    usage_stats = None
    assessments_with_rate = db.session.query(FeeAssessment) \
        .filter_by(fee_item_id=fee_rate.fee_item_id) \
        .filter_by(term=fee_rate.term, year=fee_rate.year).all()

    if assessments_with_rate:
        students_affected = len(set(a.student_id for a in assessments_with_rate))
        total_amount = sum(a.amount for a in assessments_with_rate)

        usage_stats = {
            'assessments_count': len(assessments_with_rate),
            'students_affected': students_affected,
            'total_amount': total_amount
        }

    if request.method == 'POST':
        fee_rate.fee_item_id = int(request.form['fee_item_id'])
        fee_rate.term = int(request.form['term'])
        fee_rate.year = int(request.form['year'])
        fee_rate.class_id = int(request.form['class_id']) if request.form['class_id'] else None
        fee_rate.stream_id = int(request.form['stream_id']) if request.form['stream_id'] else None
        fee_rate.student_type = StudentType(request.form['student_type']) if request.form['student_type'] else None
        fee_rate.amount = Decimal(request.form['amount']) if request.form['amount'] else None
        fee_rate.rate_per_km = Decimal(request.form['rate_per_km']) if request.form['rate_per_km'] else None
        fee_rate.is_active = bool(request.form.get('is_active'))

        db.session.commit()
        flash('Fee rate updated successfully', 'success')
        return redirect(url_for('fees.index'))

    fee_items = FeeItem.query.filter_by(is_active=True).all()
    classes = Class.query.all()

    return render_template('fees/edit_rate.html',
                           fee_rate=fee_rate,
                           fee_items=fee_items,
                           classes=classes,
                           existing_assessments_count=existing_assessments_count,
                           usage_stats=usage_stats)


@fees_bp.route('/rate/delete/<int:rate_id>', methods=['POST'])
@login_required
def delete_rate(rate_id):
    fee_rate = FeeRate.query.get_or_404(rate_id)

    assessment_count = db.session.query(FeeAssessment) \
        .filter_by(fee_item_id=fee_rate.fee_item_id) \
        .filter_by(term=fee_rate.term, year=fee_rate.year).count()

    if assessment_count > 0:
        flash(f'Cannot delete fee rate - it has been used in {assessment_count} assessments', 'error')
        return redirect(url_for('fees.index'))

    fee_item_name = fee_rate.fee_item.name
    term_year = f"Term {fee_rate.term}/{fee_rate.year}"

    db.session.delete(fee_rate)
    db.session.commit()
    flash(f'Fee rate for {fee_item_name} ({term_year}) deleted successfully', 'success')
    return redirect(url_for('fees.index'))


@fees_bp.route('/assess', methods=['GET', 'POST'])
@login_required
def assess():
    """Enhanced assess fees with preview functionality"""
    if request.method == 'POST':
        if request.form.get('preview'):
            return handle_fee_assessment_preview()
        else:
            term = int(request.form['term'])
            year = int(request.form['year'])
            assessment_scope = request.form.get('assessment_scope', 'all')

            class_id = None
            stream_id = None
            student_id = None

            if assessment_scope == 'class':
                class_id = int(request.form['class_id']) if request.form.get('class_id') else None
            elif assessment_scope == 'stream':
                class_id = int(request.form['class_id']) if request.form.get('class_id') else None
                stream_id = int(request.form['stream_id']) if request.form.get('stream_id') else None
            elif assessment_scope == 'individual':
                student_id = int(request.form['student_id']) if request.form.get('student_id') else None

            dry_run = bool(request.form.get('dry_run'))
            force_regenerate = bool(request.form.get('force_regenerate'))

            if not dry_run:
                assessments_created = generate_fee_assessments(
                    term=term,
                    year=year,
                    class_id=class_id,
                    stream_id=stream_id,
                    student_id=student_id,
                    force_regenerate=force_regenerate
                )

                if force_regenerate:
                    flash(f'Regenerated {assessments_created} fee assessments', 'success')
                else:
                    flash(f'Generated {assessments_created} fee assessments', 'success')
            else:
                flash('Dry run completed - no assessments were created', 'info')

            return redirect(url_for('fees.index'))

    classes = Class.query.all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()

    return render_template('fees/assess.html',
                           classes=classes,
                           current_year=current_year)


def handle_fee_assessment_preview():
    """Handle preview request for fee assessments"""
    try:
        term = int(request.form['term'])
        year = int(request.form['year'])
        assessment_scope = request.form.get('assessment_scope', 'all')
        skip_existing = bool(request.form.get('skip_existing'))
        include_transport = bool(request.form.get('include_transport'))

        query = Student.query.filter_by(is_active=True)

        if assessment_scope == 'class' and request.form.get('class_id'):
            query = query.filter_by(class_id=int(request.form['class_id']))
        elif assessment_scope == 'stream' and request.form.get('stream_id'):
            query = query.filter_by(stream_id=int(request.form['stream_id']))
        elif assessment_scope == 'individual' and request.form.get('student_id'):
            query = query.filter_by(id=int(request.form['student_id']))

        students = query.all()

        preview_data = {
            'students_count': len(students),
            'assessments_count': 0,
            'total_amount': 'KSh 0.00',
            'skipped_count': 0,
            'fee_breakdown': [],
            'warnings': []
        }

        total_amount = Decimal('0')
        fee_totals = {}

        for student in students:
            if skip_existing:
                existing = FeeAssessment.query.filter_by(
                    student_id=student.id,
                    term=term,
                    year=year
                ).first()

                if existing:
                    preview_data['skipped_count'] += 1
                    continue

            applicable_fees = get_applicable_fees_for_student(student, term, year)

            for fee_item, rate_info in applicable_fees:
                if not include_transport and fee_item.code == 'TRANSPORT':
                    continue

                amount = calculate_fee_amount(student, fee_item, rate_info)

                if amount > 0:
                    preview_data['assessments_count'] += 1
                    total_amount += amount

                    if fee_item.code not in fee_totals:
                        fee_totals[fee_item.code] = {
                            'name': fee_item.name,
                            'code': fee_item.code,
                            'students_count': 0,
                            'amount': Decimal('0')
                        }

                    fee_totals[fee_item.code]['students_count'] += 1
                    fee_totals[fee_item.code]['amount'] += amount

        for code, data in fee_totals.items():
            preview_data['fee_breakdown'].append({
                'code': data['code'],
                'name': data['name'],
                'students_count': data['students_count'],
                'amount': f"KSh {data['amount']:,.2f}"
            })

        preview_data['total_amount'] = f"KSh {total_amount:,.2f}"

        if preview_data['assessments_count'] == 0:
            preview_data['warnings'].append('No new assessments will be created')

        if not include_transport:
            transport_students = sum(1 for s in students if s.vehicle_id)
            if transport_students > 0:
                preview_data['warnings'].append(
                    f'{transport_students} students have transport but fees are excluded')

        return jsonify({'success': True, 'data': preview_data})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Preview failed: {str(e)}'})