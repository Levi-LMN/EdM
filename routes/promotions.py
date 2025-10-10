"""Promotion management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import desc
from models import db, Student, StudentPromotion, PromotionStatus, Class, AcademicYear

promotions_bp = Blueprint('promotions', __name__)


@promotions_bp.route('/')
@login_required
def index():
    academic_years = AcademicYear.query.order_by(desc(AcademicYear.year)).all()
    recent_promotions = StudentPromotion.query.order_by(desc(StudentPromotion.promotion_date)).limit(20).all()

    return render_template('promotions/index.html',
                           academic_years=academic_years,
                           recent_promotions=recent_promotions)


@promotions_bp.route('/bulk', methods=['GET', 'POST'])
@login_required
def bulk():
    if request.method == 'POST':
        from_class_id = int(request.form['from_class_id'])
        academic_year = int(request.form['academic_year'])
        stream_id = int(request.form['stream_id']) if request.form['stream_id'] else None

        query = Student.query.filter_by(class_id=from_class_id, is_active=True)
        if stream_id:
            query = query.filter_by(stream_id=stream_id)

        students = query.all()
        promoted_count = 0

        for student in students:
            if student.promote_to_next_class(academic_year, PromotionStatus.PROMOTED):
                promoted_count += 1

        db.session.commit()
        flash(f'Successfully promoted {promoted_count} students', 'success')
        return redirect(url_for('promotions.index'))

    classes = Class.query.all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()

    return render_template('promotions/bulk.html',
                           classes=classes,
                           current_year=current_year)


@promotions_bp.route('/individual/<int:student_id>', methods=['GET', 'POST'])
@login_required
def individual(student_id):
    student = Student.query.get_or_404(student_id)

    if request.method == 'POST':
        promotion = StudentPromotion(
            student_id=student_id,
            from_class_id=student.class_id,
            from_stream_id=student.stream_id,
            to_class_id=int(request.form['to_class_id']),
            to_stream_id=int(request.form['to_stream_id']) if request.form['to_stream_id'] else None,
            academic_year=int(request.form['academic_year']),
            status=PromotionStatus(request.form['status']),
            notes=request.form.get('notes'),
            processed_by=current_user.id
        )

        student.class_id = promotion.to_class_id
        student.stream_id = promotion.to_stream_id

        db.session.add(promotion)
        db.session.commit()

        flash('Student promotion processed successfully', 'success')
        return redirect(url_for('students.detail', student_id=student_id))

    classes = Class.query.all()
    current_year = AcademicYear.query.filter_by(is_current=True).first()

    return render_template('promotions/individual.html',
                           student=student,
                           classes=classes,
                           current_year=current_year)