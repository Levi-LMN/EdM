"""Student management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, date
from sqlalchemy import or_, desc
from models import (db, Student, StudentType, Class, Stream, Vehicle,
                   FeeAssessment, Payment, AcademicYear, get_student_balance_summary)



students_bp = Blueprint('students', __name__)


@students_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '')
    class_id = request.args.get('class_id', type=int)
    stream_id = request.args.get('stream_id', type=int)

    query = Student.query.filter_by(is_active=True)

    if search:
        query = query.filter(or_(
            Student.admission_no.contains(search),
            Student.first_name.contains(search),
            Student.last_name.contains(search)
        ))

    if class_id:
        query = query.filter_by(class_id=class_id)

    if stream_id:
        query = query.filter_by(stream_id=stream_id)

    students = query.paginate(page=page, per_page=per_page, error_out=False)
    classes = Class.query.all()
    streams = Stream.query.filter_by(class_id=class_id).all() if class_id else []

    return render_template('students/list.html',
                         students=students,
                         classes=classes,
                         streams=streams,
                         search=search,
                         selected_class=class_id,
                         selected_stream=stream_id)


@students_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        student = Student(
            admission_no=request.form['admission_no'],
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            date_of_birth=datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date() if request.form['date_of_birth'] else None,
            class_id=int(request.form['class_id']),
            stream_id=int(request.form['stream_id']) if request.form['stream_id'] else None,
            student_type=StudentType(request.form['student_type']),
            parent_name=request.form['parent_name'],
            parent_phone=request.form['parent_phone'],
            parent_email=request.form['parent_email'],
            vehicle_id=int(request.form['vehicle_id']) if request.form['vehicle_id'] else None,
            transport_distance_km=float(request.form['transport_distance_km']) if request.form['transport_distance_km'] else None
        )

        db.session.add(student)
        db.session.commit()
        flash('Student added successfully', 'success')
        return redirect(url_for('students.list'))

    classes = Class.query.all()
    vehicles = Vehicle.query.filter_by(is_active=True).all()
    return render_template('students/add.html', classes=classes, vehicles=vehicles)


@students_bp.route('/<int:student_id>')
@login_required
def detail(student_id):
    student = Student.query.get_or_404(student_id)
    balance_summary = get_student_balance_summary(student_id)

    recent_payments = Payment.query.filter_by(student_id=student_id)\
        .order_by(desc(Payment.payment_date)).limit(10).all()

    current_year = AcademicYear.query.filter_by(is_current=True).first()
    current_assessments = []
    if current_year:
        current_assessments = FeeAssessment.query.filter_by(
            student_id=student_id,
            year=current_year.year
        ).all()

    return render_template('students/detail.html',
                         student=student,
                         balance_summary=balance_summary,
                         recent_payments=recent_payments,
                         current_assessments=current_assessments)


@students_bp.route('/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit(student_id):
    student = Student.query.get_or_404(student_id)

    if request.method == 'POST':
        student.admission_no = request.form['admission_no']
        student.first_name = request.form['first_name']
        student.last_name = request.form['last_name']
        student.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date() if request.form['date_of_birth'] else None
        student.class_id = int(request.form['class_id'])
        student.stream_id = int(request.form['stream_id']) if request.form['stream_id'] else None
        student.student_type = StudentType(request.form['student_type'])
        student.parent_name = request.form['parent_name']
        student.parent_phone = request.form['parent_phone']
        student.parent_email = request.form['parent_email']
        student.vehicle_id = int(request.form['vehicle_id']) if request.form['vehicle_id'] else None
        student.transport_distance_km = float(request.form['transport_distance_km']) if request.form['transport_distance_km'] else None

        db.session.commit()
        flash('Student updated successfully', 'success')
        return redirect(url_for('students.detail', student_id=student_id))

    classes = Class.query.all()
    streams = Stream.query.filter_by(class_id=student.class_id).all()
    vehicles = Vehicle.query.filter_by(is_active=True).all()

    return render_template('students/edit.html',
                         student=student,
                         classes=classes,
                         streams=streams,
                         vehicles=vehicles)


@students_bp.route('/delete/<int:student_id>', methods=['POST'])
@login_required
def delete(student_id):
    student = Student.query.get_or_404(student_id)

    payment_count = Payment.query.filter_by(student_id=student_id).count()
    if payment_count > 0:
        flash(f'Cannot delete student - they have {payment_count} payment records', 'error')
        return redirect(url_for('students.detail', student_id=student_id))

    assessment_count = FeeAssessment.query.filter_by(student_id=student_id).count()
    if assessment_count > 0:
        flash(f'Cannot delete student - they have {assessment_count} fee assessments', 'error')
        return redirect(url_for('students.detail', student_id=student_id))

    student_name = student.full_name
    admission_no = student.admission_no

    db.session.delete(student)
    db.session.commit()
    flash(f'Student {student_name} ({admission_no}) deleted successfully', 'success')
    return redirect(url_for('students.list'))


@students_bp.route('/deactivate/<int:student_id>', methods=['POST'])
@login_required
def deactivate(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_active = False
    student.deactivation_date = date.today()
    db.session.commit()
    flash(f'Student {student.full_name} deactivated successfully', 'success')
    return redirect(url_for('students.detail', student_id=student_id))


@students_bp.route('/reactivate/<int:student_id>', methods=['POST'])
@login_required
def reactivate(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_active = True
    student.deactivation_date = None
    db.session.commit()
    flash(f'Student {student.full_name} reactivated successfully', 'success')
    return redirect(url_for('students.detail', student_id=student_id))