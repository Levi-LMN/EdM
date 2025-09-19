from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from decimal import Decimal
import os
import random  # Added random module
from sqlalchemy import func

# Import your models (assuming they're in models.py)
from models import (
    db, AcademicTerm, Class, Stream, Student, FeeItem, FeeRate,
    StudentService, FeeAssessment, FeeAssessmentLine, Payment, PaymentAllocation
)

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///school_fees.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize the database
db.init_app(app)


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('error.html',
                           error_code=404,
                           error_message='Page not found'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                           error_code=500,
                           error_message='Internal server error'), 500


# ===========================
# MAIN DASHBOARD
# ===========================

@app.route('/')
def dashboard():
    """Main dashboard with summary statistics"""
    current_term = AcademicTerm.get_current_term()

    # Get summary statistics
    total_students = Student.query.count()
    day_students = Student.query.filter_by(student_type='DAY').count()
    boarder_students = Student.query.filter_by(student_type='BOARDER').count()

    # Fee collection summary for current term
    if current_term:
        total_assessed = db.session.query(
            func.coalesce(func.sum(FeeAssessmentLine.amount), 0)
        ).select_from(FeeAssessmentLine) \
                             .join(FeeAssessment) \
                             .filter(FeeAssessment.term == current_term.term,
                                     FeeAssessment.year == current_term.year).scalar() or 0

        total_paid = db.session.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).filter(
            Payment.payment_date >= current_term.start_date,
            Payment.payment_date <= current_term.end_date
        ).scalar() or 0

        outstanding_balance = total_assessed - total_paid
        collection_rate = (total_paid / total_assessed * 100) if total_assessed > 0 else 0
    else:
        total_assessed = total_paid = outstanding_balance = collection_rate = 0

    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(5).all()

    return render_template('dashboard.html',
                           current_term=current_term,
                           total_students=total_students,
                           day_students=day_students,
                           boarder_students=boarder_students,
                           total_assessed=float(total_assessed),
                           total_paid=float(total_paid),
                           outstanding_balance=float(outstanding_balance),
                           collection_rate=round(collection_rate, 2),
                           recent_payments=recent_payments)


# ===========================
# ACADEMIC TERMS ROUTES
# ===========================

@app.route('/terms')
def list_terms():
    """List all academic terms"""
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc(), AcademicTerm.term.desc()).all()
    return render_template('terms/list.html', terms=terms)


@app.route('/terms/new', methods=['GET', 'POST'])
def create_term():
    """Create a new academic term"""
    if request.method == 'POST':
        try:
            # If this term is set as current, unset all others
            if request.form.get('is_current'):
                AcademicTerm.query.update({'is_current': False})

            term = AcademicTerm(
                term=int(request.form['term']),
                year=int(request.form['year']),
                start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
                is_current=bool(request.form.get('is_current'))
            )

            db.session.add(term)
            db.session.commit()
            flash('Term created successfully!', 'success')
            return redirect(url_for('list_terms'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating term: {str(e)}', 'error')

    return render_template('terms/form.html')


@app.route('/terms/<int:term_id>/set_current', methods=['POST'])
def set_current_term(term_id):
    """Set a term as the current active term"""
    try:
        AcademicTerm.query.update({'is_current': False})
        term = AcademicTerm.query.get_or_404(term_id)
        term.is_current = True
        db.session.commit()
        flash('Current term updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating current term: {str(e)}', 'error')

    return redirect(url_for('list_terms'))


# ===========================
# CLASSES AND STREAMS ROUTES
# ===========================

@app.route('/classes')
def list_classes():
    """List all classes with their streams"""
    classes = Class.query.all()
    return render_template('classes/list.html', classes=classes)


@app.route('/classes/new', methods=['GET', 'POST'])
def create_class():
    """Create a new class"""
    if request.method == 'POST':
        try:
            cls = Class(
                name=request.form['name'],
                level=request.form.get('level')
            )
            db.session.add(cls)
            db.session.commit()
            flash('Class created successfully!', 'success')
            return redirect(url_for('list_classes'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating class: {str(e)}', 'error')

    return render_template('classes/form.html')


@app.route('/classes/<int:class_id>/streams/new', methods=['GET', 'POST'])
def create_stream(class_id):
    """Create a new stream for a class"""
    cls = Class.query.get_or_404(class_id)

    if request.method == 'POST':
        try:
            stream = Stream(
                class_id=class_id,
                name=request.form['name']
            )
            db.session.add(stream)
            db.session.commit()
            flash('Stream created successfully!', 'success')
            return redirect(url_for('list_classes'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating stream: {str(e)}', 'error')

    return render_template('classes/stream_form.html', cls=cls)


# ===========================
# STUDENTS ROUTES
# ===========================

@app.route('/students')
def list_students():
    """List all students with filtering options and pagination"""
    # Get filter parameters
    class_id = request.args.get('class_id', type=int)
    stream_id = request.args.get('stream_id', type=int)
    student_type = request.args.get('student_type')
    search = request.args.get('search', '').strip()

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    # Validate per_page
    if per_page not in [10, 25, 50, 100]:
        per_page = 25

    # Build query
    query = Student.query.join(Class).outerjoin(Stream)

    # Apply filters
    if class_id:
        query = query.filter(Student.class_id == class_id)
    if stream_id:
        query = query.filter(Student.stream_id == stream_id)
    if student_type:
        query = query.filter(Student.student_type == student_type)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Student.first_name.ilike(search_pattern),
                Student.last_name.ilike(search_pattern),
                Student.admission_no.ilike(search_pattern)
            )
        )

    # Apply ordering and pagination
    students = query.order_by(Student.first_name, Student.last_name).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # Get all classes for filter dropdown
    classes = Class.query.order_by(Class.name).all()

    # Prepare filter values for template
    filters = {
        'class_id': class_id,
        'stream_id': stream_id,
        'student_type': student_type,
        'search': search,
        'per_page': per_page
    }

    # Remove None values from filters for URL generation
    clean_filters = {k: v for k, v in filters.items() if v is not None and v != ''}

    return render_template('students/list.html',
                           students=students,
                           classes=classes,
                           filters=clean_filters)

@app.route('/students/new', methods=['GET', 'POST'])
def create_student():
    """Create a new student"""
    if request.method == 'POST':
        try:
            student = Student(
                admission_no=request.form['admission_no'],
                first_name=request.form['first_name'],
                last_name=request.form['last_name'],
                class_id=int(request.form['class_id']),
                stream_id=int(request.form['stream_id']) if request.form.get('stream_id') else None,
                student_type=request.form['student_type'],
                parent_contact=request.form.get('parent_contact'),
                transport_distance_km=Decimal(str(request.form['transport_distance_km']))
                if request.form.get('transport_distance_km') else None,
                meals_plan=request.form.get('meals_plan', 'NONE')
            )

            db.session.add(student)
            db.session.commit()
            flash('Student created successfully!', 'success')
            return redirect(url_for('list_students'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating student: {str(e)}', 'error')

    classes = Class.query.all()
    return render_template('students/form.html', classes=classes)


@app.route('/students/<int:student_id>')
def view_student(student_id):
    """View student details with balance information"""
    student = Student.query.get_or_404(student_id)
    balance_info = student.get_current_balance()
    outstanding_lines = student.get_outstanding_fee_lines()
    recent_payments = Payment.query.filter_by(student_id=student_id) \
        .order_by(Payment.payment_date.desc()).limit(5).all()

    return render_template('students/detail.html',
                           student=student,
                           balance_info=balance_info,
                           outstanding_lines=outstanding_lines,
                           recent_payments=recent_payments)


@app.route('/students/<int:student_id>/balance')
def student_balance_detail(student_id):
    """Detailed balance information for a student"""
    student = Student.query.get_or_404(student_id)
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)

    if term and year:
        balance_info = student.get_balance_for_term(term, year)
    else:
        balance_info = student.get_current_balance()

    outstanding_lines = student.get_outstanding_fee_lines(term, year)
    balance_history = student.get_balance_history()

    return render_template('students/balance.html',
                           student=student,
                           balance_info=balance_info,
                           outstanding_lines=outstanding_lines,
                           balance_history=balance_history)


# ===========================
# FEE ITEMS AND RATES ROUTES
# ===========================

@app.route('/fee_items')
def list_fee_items():
    """List all fee items"""
    fee_items = FeeItem.query.all()
    return render_template('fees/items_list.html', fee_items=fee_items)


@app.route('/fee_items/new', methods=['GET', 'POST'])
def create_fee_item():
    """Create a new fee item"""
    if request.method == 'POST':
        try:
            fee_item = FeeItem(
                code=request.form['code'].upper(),
                name=request.form['name'],
                description=request.form.get('description'),
                is_optional=bool(request.form.get('is_optional')),
                is_per_km=bool(request.form.get('is_per_km'))
            )

            db.session.add(fee_item)
            db.session.commit()
            flash('Fee item created successfully!', 'success')
            return redirect(url_for('list_fee_items'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating fee item: {str(e)}', 'error')

    return render_template('fees/item_form.html')


@app.route('/fee_rates')
def list_fee_rates():
    """List fee rates with filtering"""
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)
    class_id = request.args.get('class_id', type=int)

    query = FeeRate.query.join(FeeItem).join(Class).outerjoin(Stream)

    if term:
        query = query.filter(FeeRate.term == term)
    if year:
        query = query.filter(FeeRate.year == year)
    if class_id:
        query = query.filter(FeeRate.class_id == class_id)

    rates = query.order_by(FeeRate.year.desc(), FeeRate.term.desc()).all()
    classes = Class.query.all()
    fee_items = FeeItem.query.all()
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc()).all()

    return render_template('fees/rates_list.html',
                           rates=rates,
                           classes=classes,
                           fee_items=fee_items,
                           terms=terms,
                           filters={
                               'term': term,
                               'year': year,
                               'class_id': class_id
                           })


@app.route('/fee_rates/new', methods=['GET', 'POST'])
def create_fee_rate():
    """Create a new fee rate"""
    if request.method == 'POST':
        try:
            fee_rate = FeeRate(
                fee_item_id=int(request.form['fee_item_id']),
                class_id=int(request.form['class_id']),
                stream_id=int(request.form['stream_id']) if request.form.get('stream_id') else None,
                student_type=request.form.get('student_type') or None,
                term=int(request.form['term']),
                year=int(request.form['year']),
                amount=Decimal(str(request.form['amount'])) if request.form.get('amount') else None,
                rate_per_km=Decimal(str(request.form['rate_per_km'])) if request.form.get('rate_per_km') else None
            )

            db.session.add(fee_rate)
            db.session.commit()
            flash('Fee rate created successfully!', 'success')
            return redirect(url_for('list_fee_rates'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating fee rate: {str(e)}', 'error')

    classes = Class.query.all()
    fee_items = FeeItem.query.all()
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc()).all()

    return render_template('fees/rate_form.html',
                           classes=classes,
                           fee_items=fee_items,
                           terms=terms)


# ===========================
# FEE ASSESSMENTS ROUTES
# ===========================

@app.route('/assessments')
def list_assessments():
    """List fee assessments"""
    student_id = request.args.get('student_id', type=int)
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)

    query = FeeAssessment.query.join(Student)

    if student_id:
        query = query.filter(FeeAssessment.student_id == student_id)
    if term:
        query = query.filter(FeeAssessment.term == term)
    if year:
        query = query.filter(FeeAssessment.year == year)

    assessments = query.order_by(FeeAssessment.assessed_at.desc()).all()
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc()).all()

    return render_template('assessments/list.html',
                           assessments=assessments,
                           terms=terms,
                           filters={
                               'student_id': student_id,
                               'term': term,
                               'year': year
                           })


@app.route('/assessments/<int:assessment_id>')
def view_assessment(assessment_id):
    """View detailed assessment information"""
    assessment = FeeAssessment.query.get_or_404(assessment_id)
    return render_template('assessments/detail.html', assessment=assessment)


@app.route('/assessments/bulk', methods=['GET', 'POST'])
def bulk_create_assessments():
    """Create assessments for multiple students"""
    if request.method == 'POST':
        try:
            term = int(request.form['term'])
            year = int(request.form['year'])
            class_id = int(request.form['class_id']) if request.form.get('class_id') else None
            stream_id = int(request.form['stream_id']) if request.form.get('stream_id') else None

            # Get students to assess
            query = Student.query
            if class_id:
                query = query.filter(Student.class_id == class_id)
            if stream_id:
                query = query.filter(Student.stream_id == stream_id)

            students = query.all()
            created_count = 0

            for student in students:
                # Check if assessment already exists
                existing = FeeAssessment.query.filter_by(
                    student_id=student.id,
                    term=term,
                    year=year
                ).first()

                if existing:
                    continue

                # Create assessment
                assessment = FeeAssessment(
                    student_id=student.id,
                    term=term,
                    year=year
                )
                db.session.add(assessment)
                db.session.flush()

                # Generate fee lines
                fee_lines = generate_fee_lines_for_student(student, term, year)

                for line_data in fee_lines:
                    line = FeeAssessmentLine(
                        assessment_id=assessment.id,
                        fee_item_id=line_data['fee_item_id'],
                        description=line_data['description'],
                        amount=line_data['amount']
                    )
                    db.session.add(line)

                created_count += 1

            db.session.commit()
            flash(f'Created {created_count} assessments successfully!', 'success')
            return redirect(url_for('list_assessments'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating assessments: {str(e)}', 'error')

    classes = Class.query.all()
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc()).all()

    return render_template('assessments/bulk_form.html',
                           classes=classes,
                           terms=terms)


def generate_fee_lines_for_student(student, term, year):
    """Generate fee lines for a student based on rates and services"""
    lines = []

    # Get applicable fee rates
    rates_query = FeeRate.query.filter(
        FeeRate.term == term,
        FeeRate.year == year,
        FeeRate.class_id == student.class_id
    ).filter(
        db.or_(
            FeeRate.stream_id.is_(None),
            FeeRate.stream_id == student.stream_id
        )
    ).filter(
        db.or_(
            FeeRate.student_type.is_(None),
            FeeRate.student_type == student.student_type
        )
    )

    for rate in rates_query:
        if rate.fee_item.is_per_km and student.transport_distance_km:
            amount = rate.rate_per_km * student.transport_distance_km
            description = f"Transport - {student.transport_distance_km}km @ {rate.rate_per_km}/km"
        elif rate.amount:
            amount = rate.amount
            description = f"{rate.fee_item.name} - Term {term} {year}"
        else:
            continue

        lines.append({
            'fee_item_id': rate.fee_item_id,
            'description': description,
            'amount': amount
        })

    return lines


# ===========================
# PAYMENTS ROUTES
# ===========================

@app.route('/payments')
def list_payments():
    """List payments with filtering"""
    student_id = request.args.get('student_id', type=int)
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    query = Payment.query.join(Student)

    if student_id:
        query = query.filter(Payment.student_id == student_id)
    if from_date:
        query = query.filter(Payment.payment_date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(Payment.payment_date <= datetime.strptime(to_date, '%Y-%m-%d').date())

    payments = query.order_by(Payment.payment_date.desc()).all()

    return render_template('payments/list.html',
                           payments=payments,
                           filters={
                               'student_id': student_id,
                               'from_date': from_date,
                               'to_date': to_date
                           })


from datetime import date, datetime
from decimal import Decimal

@app.route('/payments/new', methods=['GET', 'POST'])
def create_payment():
    """Create a new payment"""
    student_id = request.args.get('student_id', type=int)
    student = Student.query.get(student_id) if student_id else None

    if request.method == 'POST':
        try:
            payment = Payment(
                student_id=int(request.form['student_id']),
                payment_date=datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date(),
                amount=Decimal(str(request.form['amount'])),
                mode=request.form['mode'],
                receipt_no=request.form['receipt_no'],
                note=request.form.get('note')
            )

            db.session.add(payment)
            db.session.commit()
            flash('Payment recorded successfully!', 'success')
            return redirect(url_for('view_payment', payment_id=payment.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error recording payment: {str(e)}', 'error')

    # Generate receipt number
    today = date.today()
    date_str = today.strftime('%Y%m%d')
    today_payments = Payment.query.filter(Payment.payment_date == today).count()
    receipt_no = f"RCP-{date_str}-{today_payments + 1:04d}"

    return render_template(
        'payments/form.html',
        student=student,
        receipt_no=receipt_no,
        today=today.isoformat()  # ✅ Pass this for Jinja to use
    )


@app.route('/payments/<int:payment_id>')
def view_payment(payment_id):
    """View payment details"""
    payment = Payment.query.get_or_404(payment_id)
    return render_template('payments/detail.html', payment=payment)


# ===========================
# REPORTS ROUTES
# ===========================

@app.route('/reports')
def reports_menu():
    """Reports menu page"""
    return render_template('reports/menu.html')


@app.route('/reports/fee_collection')
def fee_collection_report():
    """Fee collection report"""
    term = request.args.get('term', type=int)
    year = request.args.get('year', type=int)
    class_id = request.args.get('class_id', type=int)

    # Set defaults if not provided
    if not term or not year:
        current_term = AcademicTerm.get_current_term()
        if current_term:
            term = term or current_term.term
            year = year or current_term.year

    report_data = []
    summary = {}

    if term and year:
        # Generate report data
        assessment_query = db.session.query(
            Student.id.label('student_id'),
            Student.admission_no,
            Student.first_name,
            Student.last_name,
            Class.name.label('class_name'),
            Stream.name.label('stream_name'),
            func.sum(FeeAssessmentLine.amount).label('total_assessed')
        ).select_from(Student) \
            .join(Class) \
            .outerjoin(Stream) \
            .join(FeeAssessment) \
            .join(FeeAssessmentLine) \
            .filter(FeeAssessment.term == term, FeeAssessment.year == year)

        if class_id:
            assessment_query = assessment_query.filter(Student.class_id == class_id)

        assessment_results = assessment_query.group_by(
            Student.id, Student.admission_no, Student.first_name,
            Student.last_name, Class.name, Stream.name
        ).all()

        # Get payments
        student_ids = [result.student_id for result in assessment_results]
        term_obj = AcademicTerm.query.filter_by(term=term, year=year).first()

        payment_query = db.session.query(
            Payment.student_id,
            func.sum(Payment.amount).label('total_paid')
        ).filter(Payment.student_id.in_(student_ids))

        if term_obj:
            payment_query = payment_query.filter(
                Payment.payment_date >= term_obj.start_date,
                Payment.payment_date <= term_obj.end_date
            )

        payment_results = {
            p.student_id: p.total_paid for p in payment_query.group_by(Payment.student_id).all()
        }

        # Combine results
        for assessment in assessment_results:
            total_paid = float(payment_results.get(assessment.student_id, 0))
            total_assessed = float(assessment.total_assessed)
            balance = total_assessed - total_paid

            report_data.append({
                'student_id': assessment.student_id,
                'admission_no': assessment.admission_no,
                'student_name': f"{assessment.first_name} {assessment.last_name}",
                'class': assessment.class_name,
                'stream': assessment.stream_name,
                'total_assessed': total_assessed,
                'total_paid': total_paid,
                'balance': balance,
                'collection_percentage': round((total_paid / total_assessed * 100) if total_assessed > 0 else 0, 2)
            })

        summary = {
            'total_students': len(report_data),
            'total_assessed': sum(item['total_assessed'] for item in report_data),
            'total_paid': sum(item['total_paid'] for item in report_data),
            'total_outstanding': sum(item['balance'] for item in report_data),
        }

        if summary['total_assessed'] > 0:
            summary['overall_collection_rate'] = round(
                summary['total_paid'] / summary['total_assessed'] * 100, 2
            )
        else:
            summary['overall_collection_rate'] = 0

    classes = Class.query.all()
    terms = AcademicTerm.query.order_by(AcademicTerm.year.desc()).all()

    return render_template('reports/fee_collection.html',
                           report_data=report_data,
                           summary=summary,
                           classes=classes,
                           terms=terms,
                           filters={
                               'term': term,
                               'year': year,
                               'class_id': class_id
                           })


@app.route('/reports/outstanding_fees')
def outstanding_fees_report():
    """Outstanding fees report"""
    min_balance = request.args.get('min_balance', type=float, default=0)
    class_id = request.args.get('class_id', type=int)

    students_query = Student.query.join(Class).outerjoin(Stream)

    if class_id:
        students_query = students_query.filter(Student.class_id == class_id)

    students = students_query.all()
    outstanding_students = []

    for student in students:
        balance_info = student.get_current_balance()
        balance = float(balance_info['balance'])

        if balance > min_balance:
            outstanding_lines = student.get_outstanding_fee_lines()

            outstanding_students.append({
                'student_id': student.id,
                'admission_no': student.admission_no,
                'student_name': f"{student.first_name} {student.last_name}",
                'class': student.class_obj.name,
                'stream': student.stream.name if student.stream else None,
                'parent_contact': student.parent_contact,
                'total_assessed': float(balance_info['total_assessed']),
                'total_paid': float(balance_info['total_paid']),
                'outstanding_balance': balance,
                'outstanding_lines_count': len(outstanding_lines),
                'oldest_outstanding_date': min([
                    line['assessment_date'] for line in outstanding_lines
                ]).isoformat() if outstanding_lines else None
            })

    outstanding_students.sort(key=lambda x: x['outstanding_balance'], reverse=True)

    summary = {
        'total_students_with_balance': len(outstanding_students),
        'total_outstanding_amount': sum(s['outstanding_balance'] for s in outstanding_students),
        'average_outstanding': (
            sum(s['outstanding_balance'] for s in outstanding_students) / len(outstanding_students)
            if outstanding_students else 0
        )
    }

    classes = Class.query.all()

    return render_template('reports/outstanding_fees.html',
                           outstanding_students=outstanding_students,
                           summary=summary,
                           classes=classes,
                           filters={
                               'min_balance': min_balance,
                               'class_id': class_id
                           })


# ===========================
# UTILITY ROUTES
# ===========================

@app.route('/search/students')
def search_students():
    """Search students by name or admission number for AJAX requests"""
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', type=int, default=10)

    if not query:
        return jsonify([])

    search_pattern = f"%{query}%"
    students = Student.query.filter(
        db.or_(
            Student.first_name.ilike(search_pattern),
            Student.last_name.ilike(search_pattern),
            Student.admission_no.ilike(search_pattern)
        )
    ).limit(limit).all()

    return jsonify([{
        'id': student.id,
        'admission_no': student.admission_no,
        'name': f"{student.first_name} {student.last_name}",
        'class': student.class_obj.name,
        'stream': student.stream.name if student.stream else None,
        'current_balance': float(student.get_current_balance()['balance'])
    } for student in students])


@app.route('/get_streams/<int:class_id>')
def get_streams(class_id):
    """Get streams for a class (AJAX endpoint)"""
    streams = Stream.query.filter_by(class_id=class_id).all()
    return jsonify([{
        'id': stream.id,
        'name': stream.name
    } for stream in streams])


# ===========================
# DATABASE INITIALIZATION
# ===========================




@app.route('/initialize_db', methods=['GET', 'POST'])
def initialize_database():
    """Initialize database with realistic Kenyan primary school data"""
    if request.method == 'POST':
        try:
            # Create all tables
            db.create_all()

            # Check if data already exists
            if Class.query.first():
                flash('Database already initialized!', 'warning')
                return redirect(url_for('dashboard'))

            # ===========================
            # CREATE ACADEMIC TERMS
            # ===========================
            current_year = datetime.now().year

            # Create academic terms for current and next year
            terms_data = [
                # Current year terms
                {
                    'term': 1, 'year': current_year,
                    'start_date': date(current_year, 1, 8),
                    'end_date': date(current_year, 4, 5),
                    'is_current': False
                },
                {
                    'term': 2, 'year': current_year,
                    'start_date': date(current_year, 5, 6),
                    'end_date': date(current_year, 8, 9),
                    'is_current': True  # Current term
                },
                {
                    'term': 3, 'year': current_year,
                    'start_date': date(current_year, 9, 2),
                    'end_date': date(current_year, 11, 22),
                    'is_current': False
                },
                # Next year terms
                {
                    'term': 1, 'year': current_year + 1,
                    'start_date': date(current_year + 1, 1, 7),
                    'end_date': date(current_year + 1, 4, 4),
                    'is_current': False
                }
            ]

            for term_data in terms_data:
                term = AcademicTerm(**term_data)
                db.session.add(term)

            # ===========================
            # CREATE CLASSES (CBC PRIMARY GRADES)
            # ===========================
            classes_data = [
                {'name': 'Pre-Primary 1', 'level': 'Pre-Primary'},
                {'name': 'Pre-Primary 2', 'level': 'Pre-Primary'},
                {'name': 'Grade 1', 'level': 'Primary'},
                {'name': 'Grade 2', 'level': 'Primary'},
                {'name': 'Grade 3', 'level': 'Primary'},
                {'name': 'Grade 4', 'level': 'Primary'},
                {'name': 'Grade 5', 'level': 'Primary'},
                {'name': 'Grade 6', 'level': 'Primary'}
            ]

            class_objects = {}
            for class_data in classes_data:
                cls = Class(**class_data)
                db.session.add(cls)
                db.session.flush()
                class_objects[class_data['name']] = cls

            # ===========================
            # CREATE STREAMS
            # ===========================
            stream_objects = {}
            # Create streams for each class (A, B for smaller grades, A, B, C for higher grades)
            for class_name, cls in class_objects.items():
                if class_name in ['Pre-Primary 1', 'Pre-Primary 2']:
                    stream_names = ['Lions', 'Eagles']  # Fun names for pre-primary
                elif class_name in ['Grade 1', 'Grade 2']:
                    stream_names = ['A', 'B']
                else:
                    stream_names = ['A', 'B', 'C']

                for stream_name in stream_names:
                    stream = Stream(class_id=cls.id, name=stream_name)
                    db.session.add(stream)
                    db.session.flush()
                    stream_objects[f"{class_name}_{stream_name}"] = stream

            # ===========================
            # CREATE FEE ITEMS (KENYAN PRIMARY SCHOOL CONTEXT)
            # ===========================
            fee_items_data = [
                {
                    'code': 'TUITION',
                    'name': 'Tuition Fee',
                    'description': 'Basic tuition and instruction fees',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'ADMISSION',
                    'name': 'Admission Fee',
                    'description': 'One-time admission and registration fee',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'DEVELOPMENT',
                    'name': 'Development Fee',
                    'description': 'School infrastructure development fund',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'LUNCH',
                    'name': 'Lunch Program',
                    'description': 'School feeding program - lunch meals',
                    'is_optional': True,
                    'is_per_km': False
                },
                {
                    'code': 'TRANSPORT',
                    'name': 'School Transport',
                    'description': 'School bus transport service',
                    'is_optional': True,
                    'is_per_km': True
                },
                {
                    'code': 'UNIFORM',
                    'name': 'School Uniform',
                    'description': 'School uniform and PE kit',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'BOOKS',
                    'name': 'Books & Stationery',
                    'description': 'Textbooks, exercise books and stationery',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'ACTIVITIES',
                    'name': 'Co-curricular Activities',
                    'description': 'Sports, music, drama and other activities',
                    'is_optional': False,
                    'is_per_km': False
                },
                {
                    'code': 'MEDICAL',
                    'name': 'Medical Cover',
                    'description': 'Basic medical insurance and first aid',
                    'is_optional': True,
                    'is_per_km': False
                },
                {
                    'code': 'EXAMS',
                    'name': 'Examination Fees',
                    'description': 'Internal and external examination fees',
                    'is_optional': False,
                    'is_per_km': False
                }
            ]

            fee_item_objects = {}
            for fee_data in fee_items_data:
                fee_item = FeeItem(**fee_data)
                db.session.add(fee_item)
                db.session.flush()
                fee_item_objects[fee_data['code']] = fee_item

            # ===========================
            # CREATE FEE RATES (REALISTIC KENYAN AMOUNTS)
            # ===========================
            # Fee structure based on Kenyan primary school standards
            fee_rates_structure = {
                'Pre-Primary 1': {
                    'TUITION': {'amount': 15000, 'student_type': None},
                    'ADMISSION': {'amount': 5000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 2000, 'student_type': None},
                    'LUNCH': {'amount': 8000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 50, 'student_type': None},
                    'UNIFORM': {'amount': 3000, 'student_type': None},
                    'BOOKS': {'amount': 2500, 'student_type': None},
                    'ACTIVITIES': {'amount': 1500, 'student_type': None},
                    'MEDICAL': {'amount': 1000, 'student_type': None}
                },
                'Pre-Primary 2': {
                    'TUITION': {'amount': 16000, 'student_type': None},
                    'ADMISSION': {'amount': 5000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 2000, 'student_type': None},
                    'LUNCH': {'amount': 8000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 50, 'student_type': None},
                    'UNIFORM': {'amount': 3200, 'student_type': None},
                    'BOOKS': {'amount': 2800, 'student_type': None},
                    'ACTIVITIES': {'amount': 1500, 'student_type': None},
                    'MEDICAL': {'amount': 1000, 'student_type': None}
                },
                'Grade 1': {
                    'TUITION': {'amount': 18000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 2500, 'student_type': None},
                    'LUNCH': {'amount': 9000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 60, 'student_type': None},
                    'UNIFORM': {'amount': 3500, 'student_type': None},
                    'BOOKS': {'amount': 3500, 'student_type': None},
                    'ACTIVITIES': {'amount': 2000, 'student_type': None},
                    'MEDICAL': {'amount': 1200, 'student_type': None},
                    'EXAMS': {'amount': 500, 'student_type': None}
                },
                'Grade 2': {
                    'TUITION': {'amount': 19000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 2500, 'student_type': None},
                    'LUNCH': {'amount': 9500, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 60, 'student_type': None},
                    'UNIFORM': {'amount': 3500, 'student_type': None},
                    'BOOKS': {'amount': 3800, 'student_type': None},
                    'ACTIVITIES': {'amount': 2000, 'student_type': None},
                    'MEDICAL': {'amount': 1200, 'student_type': None},
                    'EXAMS': {'amount': 800, 'student_type': None}
                },
                'Grade 3': {
                    'TUITION': {'amount': 20000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 3000, 'student_type': None},
                    'LUNCH': {'amount': 10000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 70, 'student_type': None},
                    'UNIFORM': {'amount': 3800, 'student_type': None},
                    'BOOKS': {'amount': 4200, 'student_type': None},
                    'ACTIVITIES': {'amount': 2500, 'student_type': None},
                    'MEDICAL': {'amount': 1500, 'student_type': None},
                    'EXAMS': {'amount': 1000, 'student_type': None}
                },
                'Grade 4': {
                    'TUITION': {'amount': 22000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 3000, 'student_type': None},
                    'LUNCH': {'amount': 10500, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 70, 'student_type': None},
                    'UNIFORM': {'amount': 4000, 'student_type': None},
                    'BOOKS': {'amount': 4800, 'student_type': None},
                    'ACTIVITIES': {'amount': 2500, 'student_type': None},
                    'MEDICAL': {'amount': 1500, 'student_type': None},
                    'EXAMS': {'amount': 1200, 'student_type': None}
                },
                'Grade 5': {
                    'TUITION': {'amount': 24000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 3500, 'student_type': None},
                    'LUNCH': {'amount': 11000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 80, 'student_type': None},
                    'UNIFORM': {'amount': 4200, 'student_type': None},
                    'BOOKS': {'amount': 5200, 'student_type': None},
                    'ACTIVITIES': {'amount': 3000, 'student_type': None},
                    'MEDICAL': {'amount': 1800, 'student_type': None},
                    'EXAMS': {'amount': 1500, 'student_type': None}
                },
                'Grade 6': {
                    'TUITION': {'amount': 26000, 'student_type': None},
                    'DEVELOPMENT': {'amount': 3500, 'student_type': None},
                    'LUNCH': {'amount': 12000, 'student_type': None},
                    'TRANSPORT': {'rate_per_km': 80, 'student_type': None},
                    'UNIFORM': {'amount': 4500, 'student_type': None},
                    'BOOKS': {'amount': 5800, 'student_type': None},
                    'ACTIVITIES': {'amount': 3000, 'student_type': None},
                    'MEDICAL': {'amount': 2000, 'student_type': None},
                    'EXAMS': {'amount': 2000, 'student_type': None}  # Higher due to end of primary assessment
                }
            }

            # Create fee rates for current term
            current_term_obj = AcademicTerm.query.filter_by(is_current=True).first()

            for class_name, fees in fee_rates_structure.items():
                class_obj = class_objects.get(class_name)
                if not class_obj:
                    continue

                for fee_code, rate_info in fees.items():
                    fee_item = fee_item_objects.get(fee_code)
                    if not fee_item:
                        continue

                    fee_rate = FeeRate(
                        fee_item_id=fee_item.id,
                        class_id=class_obj.id,
                        stream_id=None,  # Apply to all streams
                        student_type=rate_info.get('student_type'),
                        term=current_term_obj.term,
                        year=current_term_obj.year,
                        amount=Decimal(str(rate_info.get('amount', 0))) if rate_info.get('amount') else None,
                        rate_per_km=Decimal(str(rate_info.get('rate_per_km', 0))) if rate_info.get(
                            'rate_per_km') else None
                    )
                    db.session.add(fee_rate)

            # ===========================
            # CREATE REALISTIC STUDENTS (FIXED NAME GENERATION)
            # ===========================
            import random

            # Expanded Kenyan names to avoid duplicates
            kenyan_first_names_male = [
                'Amani', 'Baraka', 'Chege', 'Daudi', 'Emmanuel', 'Francis', 'George', 'Hassan',
                'Ibrahim', 'James', 'Kevin', 'Leonard', 'Moses', 'Nicholas', 'Oscar', 'Peter',
                'Robert', 'Samuel', 'Tony', 'Victor', 'William', 'Xavier', 'Yusuf', 'Zuberi',
                'Allan', 'Brian', 'Charles', 'Dennis', 'Edwin', 'Felix', 'Gilbert', 'Henry',
                'Isaac', 'Joseph', 'Kennedy', 'Lucas', 'Martin', 'Nathan', 'Oliver', 'Patrick',
                'Quinton', 'Richard', 'Stephen', 'Thomas', 'Ulysses', 'Vincent', 'Walter', 'Zachary',
                'Anthony', 'Benedict', 'Collins', 'Daniel', 'Eric', 'Frederick', 'Geoffrey', 'Harrison',
                'Ian', 'Jackson', 'Kyle', 'Lawrence', 'Michael', 'Norman', 'Owen', 'Philip'
            ]

            kenyan_first_names_female = [
                'Aisha', 'Beatrice', 'Caroline', 'Diana', 'Esther', 'Faith', 'Grace', 'Hannah',
                'Irene', 'Jane', 'Khadija', 'Lucy', 'Mary', 'Nancy', 'Olive', 'Patience',
                'Queen', 'Ruth', 'Sarah', 'Teresa', 'Upendo', 'Violet', 'Wanjiku', 'Yvonne',
                'Agnes', 'Betty', 'Catherine', 'Doreen', 'Elizabeth', 'Florence', 'Gladys', 'Helen',
                'Isabella', 'Joyce', 'Karen', 'Linda', 'Margaret', 'Naomi', 'Olivia', 'Priscilla',
                'Rachel', 'Susan', 'Tabitha', 'Ursula', 'Victoria', 'Winnie', 'Yolanda', 'Zipporah',
                'Alice', 'Brenda', 'Clara', 'Deborah', 'Eva', 'Felicia', 'Gloria', 'Hilda',
                'Ivy', 'Jacinta', 'Kate', 'Lydia', 'Monica', 'Nicole', 'Ophelia', 'Pauline'
            ]

            kenyan_last_names = [
                'Kipchoge', 'Wanjiku', 'Mwangi', 'Otieno', 'Kamau', 'Njoroge', 'Ochieng',
                'Mutua', 'Kiptoo', 'Waweru', 'Kimani', 'Owino', 'Kiprotich', 'Githiomi',
                'Omondi', 'Karanja', 'Anyango', 'Chepkwony', 'Macharia', 'Akinyi', 'Korir',
                'Githinji', 'Odongo', 'Cheruiyot', 'Wainaina', 'Awino', 'Rotich', 'Kiambu',
                'Akello', 'Kirui', 'Mbugua', 'Adhiambo', 'Lagat', 'Waithaka', 'Atieno',
                'Sang', 'Ngugi', 'Nekesa', 'Too', 'Mburu', 'Were', 'Kigen', 'Ndungu',
                'Chebii', 'Muriuki', 'Auma', 'Keter', 'Maina', 'Obiero', 'Rono', 'Waigwa',
                'Chebet', 'Mwenda', 'Apiyo', 'Lagat', 'Njenga', 'Ocholla', 'Rutto', 'Wahome',
                'Cheptoo', 'Mweu', 'Awuor', 'Kemboi', 'Njeri', 'Ogola', 'Sigei', 'Wanjala',
                'Jelagat', 'Mwikali', 'Ongayo', 'Kibet', 'Njoki', 'Ondiek', 'Tanui', 'Wanjau'
            ]

            # Create a pool of unique name combinations
            all_first_names = kenyan_first_names_male + kenyan_first_names_female

            # Generate unique name combinations (more than we need)
            unique_name_combinations = []
            used_combinations = set()

            # Generate combinations ensuring uniqueness
            max_attempts = len(all_first_names) * len(kenyan_last_names)
            attempts = 0

            while len(
                    unique_name_combinations) < 500 and attempts < max_attempts:  # Generate up to 500 unique combinations
                first_name = random.choice(all_first_names)
                last_name = random.choice(kenyan_last_names)
                combination = (first_name, last_name)

                if combination not in used_combinations:
                    used_combinations.add(combination)
                    unique_name_combinations.append(combination)

                attempts += 1

            # Shuffle the combinations
            random.shuffle(unique_name_combinations)

            student_counter = 1
            students_created = []
            name_index = 0  # Index to track unique name usage

            for class_name, class_obj in class_objects.items():
                # Realistic student distribution per class
                if 'Pre-Primary' in class_name:
                    students_per_stream = random.randint(15, 22)  # Smaller classes for young kids
                elif class_name in ['Grade 1', 'Grade 2']:
                    students_per_stream = random.randint(25, 32)  # Standard primary class size
                else:
                    students_per_stream = random.randint(28, 35)  # Larger classes for older grades

                # Get streams for this class
                class_streams = [s for key, s in stream_objects.items() if key.startswith(class_name)]

                for stream in class_streams:
                    for i in range(students_per_stream):
                        # Ensure we don't run out of unique names
                        if name_index >= len(unique_name_combinations):
                            # If we run out, generate more combinations on the fly
                            while True:
                                first_name = random.choice(all_first_names)
                                last_name = random.choice(kenyan_last_names)
                                combination = (first_name, last_name)

                                if combination not in used_combinations:
                                    used_combinations.add(combination)
                                    unique_name_combinations.append(combination)
                                    break

                        # Get unique name combination
                        first_name, last_name = unique_name_combinations[name_index]
                        name_index += 1

                        # Generate admission number (format: year/class/stream/number)
                        admission_no = f"{current_year}/{class_obj.id}/{stream.id}/{student_counter:03d}"

                        # All primary students are day students (realistic for Kenyan context)
                        student_type = 'DAY'

                        # Transport distance - realistic distribution
                        transport_distance = None
                        if random.random() < 0.65:  # 65% of students use transport
                            # Most students live within 10km, but some come from further
                            if random.random() < 0.8:  # 80% live within 10km
                                transport_distance = Decimal(str(round(random.uniform(1.5, 10), 1)))
                            else:  # 20% live further away
                                transport_distance = Decimal(str(round(random.uniform(10.1, 20), 1)))

                        # Meal plan - most students take lunch
                        meals_plan = 'LUNCH' if random.random() < 0.85 else 'NONE'  # 85% take lunch

                        # Generate realistic Kenyan phone number
                        phone_prefixes = ['0701', '0702', '0703', '0704', '0705', '0706', '0707', '0708', '0709',
                                          '0710', '0711', '0712', '0713', '0714', '0715', '0716', '0717', '0718',
                                          '0719', '0720', '0721', '0722', '0723', '0724', '0725', '0726', '0727',
                                          '0728', '0729', '0733', '0734', '0735', '0736', '0737', '0738', '0739']
                        parent_contact = f"{random.choice(phone_prefixes)}{random.randint(100000, 999999)}"

                        student = Student(
                            admission_no=admission_no,
                            first_name=first_name,
                            last_name=last_name,
                            class_id=class_obj.id,
                            stream_id=stream.id,
                            student_type=student_type,
                            parent_contact=parent_contact,
                            transport_distance_km=transport_distance,
                            meals_plan=meals_plan
                        )

                        db.session.add(student)
                        db.session.flush()
                        students_created.append(student)
                        student_counter += 1

            # ===========================
            # CREATE FEE ASSESSMENTS FOR ALL STUDENTS
            # ===========================
            assessments_created = 0

            # Create assessments for ALL students to maintain data consistency
            for student in students_created:
                # Create assessment for current term
                assessment = FeeAssessment(
                    student_id=student.id,
                    term=current_term_obj.term,
                    year=current_term_obj.year,
                    assessed_at=datetime.utcnow() - timedelta(days=random.randint(1, 30))
                )
                db.session.add(assessment)
                db.session.flush()

                # Generate fee lines based on student's class and attributes
                fee_lines = generate_fee_lines_for_student(student, current_term_obj.term, current_term_obj.year)

                for line_data in fee_lines:
                    line = FeeAssessmentLine(
                        assessment_id=assessment.id,
                        fee_item_id=line_data['fee_item_id'],
                        description=line_data['description'],
                        amount=Decimal(str(line_data['amount']))
                    )
                    db.session.add(line)

                assessments_created += 1

            # ===========================
            # CREATE REALISTIC PAYMENTS
            # ===========================
            payments_created = 0

            # Create payments for about 75% of students (realistic collection rate)
            paying_students = random.sample(students_created, int(len(students_created) * 0.75))

            for student in paying_students:
                # Get student's total assessment
                balance_info = student.get_current_balance()
                total_assessed = float(balance_info['total_assessed'])

                if total_assessed > 0:
                    # Realistic payment patterns
                    payment_percentage = random.choices(
                        [0.3, 0.5, 0.7, 0.85, 1.0],  # Payment percentages
                        weights=[10, 20, 30, 25, 15],  # Weights (fewer full payments)
                        k=1
                    )[0]

                    # Number of payment installments
                    if payment_percentage >= 0.8:
                        num_payments = random.randint(1, 2)  # Full payers make fewer payments
                    else:
                        num_payments = random.randint(1, 4)  # Partial payers spread payments

                    total_to_pay = total_assessed * payment_percentage
                    remaining_amount = total_to_pay

                    for payment_num in range(num_payments):
                        if payment_num == num_payments - 1:
                            # Last payment gets remaining amount
                            payment_amount = remaining_amount
                        else:
                            # Split payment (but not equally - first payments often larger)
                            if payment_num == 0:
                                payment_amount = remaining_amount * random.uniform(0.4, 0.7)  # First payment 40-70%
                            else:
                                payment_amount = remaining_amount * random.uniform(0.3, 0.6)

                            payment_amount = min(payment_amount, remaining_amount)

                        if payment_amount <= 100:  # Skip very small payments
                            continue

                        # Realistic payment dates - spread over term
                        if payment_num == 0:
                            days_ago = random.randint(5, 45)  # First payment within first 6 weeks
                        else:
                            days_ago = random.randint(1, max(1, 45 - payment_num * 10))

                        payment_date = date.today() - timedelta(days=days_ago)

                        # Generate receipt number
                        date_str = payment_date.strftime('%Y%m%d')
                        receipt_no = f"RCP-{date_str}-{payments_created + 1:04d}"

                        # Payment mode - realistic for Kenya (M-Pesa dominance)
                        payment_modes = ['MPESA', 'MPESA', 'MPESA', 'MPESA', 'BANK', 'CASH']
                        mode = random.choice(payment_modes)

                        payment = Payment(
                            student_id=student.id,
                            payment_date=payment_date,
                            amount=Decimal(str(round(payment_amount, 2))),
                            mode=mode,
                            receipt_no=receipt_no,
                            note=f"Installment {payment_num + 1} of {num_payments}" if num_payments > 1 else None
                        )

                        db.session.add(payment)
                        payments_created += 1
                        remaining_amount -= payment_amount

                        if remaining_amount <= 0:
                            break

            # Commit all changes
            db.session.commit()

            flash(f'''Database initialized successfully with realistic Kenyan Primary School data!

                         ✅ CREATED:
                         • {len(classes_data)} Classes (Pre-Primary to Grade 6)
                         • {len(stream_objects)} Streams with proper distribution
                         • {len(fee_items_data)} Fee Items (Kenyan context)
                         • {len(students_created)} Students with UNIQUE names
                         • {assessments_created} Fee Assessments (100% coverage)
                         • {payments_created} Realistic Payments (75% students, varied amounts)
                         • Academic terms for {current_year} and {current_year + 1}

                         📊 STUDENT DISTRIBUTION:
                         • Pre-Primary: 15-22 students per stream
                         • Grade 1-2: 25-32 students per stream  
                         • Grade 3-6: 28-35 students per stream

                         💰 REALISTIC PAYMENT PATTERNS:
                         • 75% of students have made payments
                         • Payment rates: 30%-100% of fees
                         • Multiple installments for partial payers
                         • M-Pesa dominant payment method

                         🎯 All data now follows proper school logic!''', 'success')

            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error initializing database: {str(e)}', 'error')

    return render_template('admin/initialize_db.html')


def generate_fee_lines_for_student(student, term, year):
    """
    Generate fee lines for a student based on their class, services, and applicable rates.
    Enhanced for Kenyan primary school context.
    """
    lines = []

    # Get applicable fee rates for the student
    rates_query = FeeRate.query.join(FeeItem).filter(
        FeeRate.term == term,
        FeeRate.year == year,
        FeeRate.class_id == student.class_id
    ).filter(
        db.or_(
            FeeRate.stream_id.is_(None),
            FeeRate.stream_id == student.stream_id
        )
    ).filter(
        db.or_(
            FeeRate.student_type.is_(None),
            FeeRate.student_type == student.student_type
        )
    )

    for rate in rates_query:
        fee_item = rate.fee_item

        # Skip optional services based on student preferences
        if fee_item.code == 'LUNCH' and student.meals_plan == 'NONE':
            continue
        elif fee_item.code == 'TRANSPORT' and not student.transport_distance_km:
            continue
        elif fee_item.code == 'MEDICAL' and random.random() < 0.3:  # 30% skip medical
            continue

        # Calculate amount
        if fee_item.is_per_km and student.transport_distance_km:
            amount = rate.rate_per_km * student.transport_distance_km
            description = f"{fee_item.name} - {student.transport_distance_km}km @ KES {rate.rate_per_km}/km - Term {term} {year}"
        elif rate.amount:
            amount = rate.amount
            description = f"{fee_item.name} - {student.class_obj.name} - Term {term} {year}"
        else:
            continue

        lines.append({
            'fee_item_id': rate.fee_item_id,
            'description': description,
            'amount': float(amount)
        })

    return lines

# ===========================
# API ENDPOINTS (for backward compatibility)
# ===========================

@app.route('/api/students/search')
def api_search_students():
    """API endpoint for student search"""
    return search_students()


@app.route('/api/generate_receipt_number')
def api_generate_receipt_number():
    """API endpoint to generate receipt number"""
    today = date.today()
    date_str = today.strftime('%Y%m%d')
    today_payments = Payment.query.filter(Payment.payment_date == today).count()
    receipt_no = f"RCP-{date_str}-{today_payments + 1:04d}"

    # Ensure uniqueness
    while Payment.query.filter_by(receipt_no=receipt_no).first():
        today_payments += 1
        receipt_no = f"RCP-{date_str}-{today_payments + 1:04d}"

    return jsonify({'receipt_number': receipt_no})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True, host='0.0.0.0', port=5000)