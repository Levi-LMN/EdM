"""Academic management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from datetime import datetime
from sqlalchemy import desc
from models import db, Class, Stream, AcademicYear, Student, FeeAssessment, FeeRate, StudentPromotion

academic_bp = Blueprint('academic', __name__)


@academic_bp.route('/')
@login_required
def index():
    classes = Class.query.all()
    academic_years = AcademicYear.query.order_by(desc(AcademicYear.year)).all()
    return render_template('academic/index.html', classes=classes, academic_years=academic_years)


@academic_bp.route('/class/add', methods=['GET', 'POST'])
@login_required
def add_class():
    if request.method == 'POST':
        class_obj = Class(
            name=request.form['name'],
            level=request.form['level'],
            next_class_id=request.form['next_class_id'] if request.form['next_class_id'] else None
        )
        db.session.add(class_obj)
        db.session.commit()
        flash('Class added successfully', 'success')
        return redirect(url_for('academic.index'))

    classes = Class.query.all()
    return render_template('academic/add_class.html', classes=classes)


@academic_bp.route('/class/edit/<int:class_id>', methods=['GET', 'POST'])
@login_required
def edit_class(class_id):
    class_obj = Class.query.get_or_404(class_id)

    if request.method == 'POST':
        class_obj.name = request.form['name']
        class_obj.level = request.form['level']
        class_obj.next_class_id = request.form['next_class_id'] if request.form['next_class_id'] else None

        db.session.commit()
        flash('Class updated successfully', 'success')
        return redirect(url_for('academic.index'))

    classes = Class.query.filter(Class.id != class_id).all()
    return render_template('academic/edit_class.html', class_obj=class_obj, classes=classes)


@academic_bp.route('/class/delete/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    class_obj = Class.query.get_or_404(class_id)

    student_count = Student.query.filter_by(class_id=class_id, is_active=True).count()
    if student_count > 0:
        flash(f'Cannot delete class {class_obj.name} - it has {student_count} active students', 'error')
        return redirect(url_for('academic.index'))

    stream_count = Stream.query.filter_by(class_id=class_id).count()
    if stream_count > 0:
        flash(f'Cannot delete class {class_obj.name} - it has {stream_count} streams', 'error')
        return redirect(url_for('academic.index'))

    referencing_classes = Class.query.filter_by(next_class_id=class_id).all()
    if referencing_classes:
        class_names = ', '.join([c.name for c in referencing_classes])
        flash(f'Cannot delete - it is set as next class for: {class_names}', 'error')
        return redirect(url_for('academic.index'))

    db.session.delete(class_obj)
    db.session.commit()
    flash(f'Class {class_obj.name} deleted successfully', 'success')
    return redirect(url_for('academic.index'))


@academic_bp.route('/stream/add/<int:class_id>', methods=['GET', 'POST'])
@login_required
def add_stream(class_id):
    class_obj = Class.query.get_or_404(class_id)

    if request.method == 'POST':
        stream = Stream(
            class_id=class_id,
            name=request.form['name'],
            capacity=int(request.form['capacity']) if request.form['capacity'] else 40
        )
        db.session.add(stream)
        db.session.commit()
        flash('Stream added successfully', 'success')
        return redirect(url_for('academic.index'))

    return render_template('academic/add_stream.html', class_obj=class_obj)


@academic_bp.route('/stream/edit/<int:stream_id>', methods=['GET', 'POST'])
@login_required
def edit_stream(stream_id):
    stream = Stream.query.get_or_404(stream_id)

    if request.method == 'POST':
        stream.name = request.form['name']
        stream.capacity = int(request.form['capacity']) if request.form['capacity'] else 40

        db.session.commit()
        flash('Stream updated successfully', 'success')
        return redirect(url_for('academic.index'))

    return render_template('academic/edit_stream.html', stream=stream)


@academic_bp.route('/stream/delete/<int:stream_id>', methods=['POST'])
@login_required
def delete_stream(stream_id):
    stream = Stream.query.get_or_404(stream_id)

    student_count = Student.query.filter_by(stream_id=stream_id, is_active=True).count()
    if student_count > 0:
        flash(f'Cannot delete stream - it has {student_count} active students', 'error')
        return redirect(url_for('academic.index'))

    class_name = stream.class_obj.name
    stream_name = stream.name

    db.session.delete(stream)
    db.session.commit()
    flash(f'Stream {class_name}-{stream_name} deleted successfully', 'success')
    return redirect(url_for('academic.index'))


@academic_bp.route('/year/add', methods=['GET', 'POST'])
@login_required
def add_year():
    if request.method == 'POST':
        year = AcademicYear(
            year=int(request.form['year']),
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
            is_current=bool(request.form.get('is_current'))
        )

        if year.is_current:
            AcademicYear.query.update({'is_current': False})

        db.session.add(year)
        db.session.commit()
        flash('Academic year added successfully', 'success')
        return redirect(url_for('academic.index'))

    return render_template('academic/add_year.html')


@academic_bp.route('/year/edit/<int:year_id>', methods=['GET', 'POST'])
@login_required
def edit_year(year_id):
    academic_year = AcademicYear.query.get_or_404(year_id)

    if request.method == 'POST':
        academic_year.year = int(request.form['year'])
        academic_year.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        academic_year.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()

        is_current = bool(request.form.get('is_current'))
        if is_current and not academic_year.is_current:
            AcademicYear.query.update({'is_current': False})
            academic_year.is_current = True
        elif not is_current and academic_year.is_current:
            academic_year.is_current = False

        db.session.commit()
        flash('Academic year updated successfully', 'success')
        return redirect(url_for('academic.index'))

    return render_template('academic/edit_year.html', academic_year=academic_year)


@academic_bp.route('/year/delete/<int:year_id>', methods=['POST'])
@login_required
def delete_year(year_id):
    academic_year = AcademicYear.query.get_or_404(year_id)

    assessment_count = FeeAssessment.query.filter_by(year=academic_year.year).count()
    if assessment_count > 0:
        flash(f'Cannot delete - it has {assessment_count} fee assessments', 'error')
        return redirect(url_for('academic.index'))

    rate_count = FeeRate.query.filter_by(year=academic_year.year).count()
    if rate_count > 0:
        flash(f'Cannot delete - it has {rate_count} fee rates', 'error')
        return redirect(url_for('academic.index'))

    promotion_count = StudentPromotion.query.filter_by(academic_year=academic_year.year).count()
    if promotion_count > 0:
        flash(f'Cannot delete - it has {promotion_count} student promotions', 'error')
        return redirect(url_for('academic.index'))

    year_value = academic_year.year
    db.session.delete(academic_year)
    db.session.commit()
    flash(f'Academic year {year_value} deleted successfully', 'success')
    return redirect(url_for('academic.index'))