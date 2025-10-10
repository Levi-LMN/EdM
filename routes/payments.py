"""Payment management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func, desc, or_
from models import (db, Payment, PaymentMode, PaymentAllocation, Student,
                    FeeAssessment, UserRole)
from utils import amount_to_words
from io import BytesIO
from reportlab.lib.pagesizes import A5
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.graphics.shapes import Drawing, Circle, String

payments_bp = Blueprint('payments', __name__)


@payments_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '')
    payment_mode = request.args.get('payment_mode', '')
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')

    query = Payment.query

    if search:
        query = query.join(Student).filter(or_(
            Payment.receipt_number.contains(search),
            Student.admission_no.contains(search),
            Student.first_name.contains(search),
            Student.last_name.contains(search)
        ))

    if payment_mode:
        query = query.filter_by(payment_mode=PaymentMode(payment_mode))

    if from_date:
        query = query.filter(Payment.payment_date >= datetime.strptime(from_date, '%Y-%m-%d').date())

    if to_date:
        query = query.filter(Payment.payment_date <= datetime.strptime(to_date, '%Y-%m-%d').date())

    payments = query.order_by(desc(Payment.created_at)) \
        .paginate(page=page, per_page=per_page, error_out=False)

    return render_template('payments/list.html', payments=payments, search=search)


@payments_bp.route('/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add(student_id):
    student = Student.query.get_or_404(student_id)

    if request.method == 'POST':
        last_receipt = Payment.query.order_by(desc(Payment.id)).first()
        receipt_no = f"RCT{(last_receipt.id + 1):06d}" if last_receipt else "RCT000001"

        payment = Payment(
            student_id=student_id,
            amount=Decimal(request.form['amount']),
            payment_date=datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date(),
            payment_mode=PaymentMode(request.form['payment_mode']),
            receipt_number=receipt_no,
            mpesa_code=request.form.get('mpesa_code'),
            bank_slip_number=request.form.get('bank_slip_number'),
            cheque_number=request.form.get('cheque_number'),
            notes=request.form.get('notes'),
            processed_by=current_user.id
        )

        db.session.add(payment)
        db.session.commit()

        flash(f'Payment {receipt_no} recorded successfully', 'success')
        return redirect(url_for('payments.allocate', payment_id=payment.id))

    outstanding_assessments = []
    assessments = FeeAssessment.query.filter_by(student_id=student_id).all()

    for assessment in assessments:
        paid_amount = db.session.query(func.sum(PaymentAllocation.amount)) \
                          .filter_by(assessment_id=assessment.id).scalar() or Decimal('0')

        outstanding = assessment.amount - paid_amount

        if outstanding > 0:
            outstanding_assessments.append({
                'assessment': assessment,
                'outstanding': outstanding
            })

    return render_template('payments/add.html',
                           student=student,
                           outstanding_assessments=outstanding_assessments,
                           today_date=date.today().isoformat())


@payments_bp.route('/<int:payment_id>/allocate', methods=['GET', 'POST'])
@login_required
def allocate(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if request.method == 'POST':
        try:
            allocation_inputs = request.form.getlist('allocations')
            total_allocated = Decimal('0')
            allocations_to_create = []

            for allocation_data in allocation_inputs:
                if not allocation_data or not allocation_data.strip():
                    continue

                if ':' not in allocation_data:
                    continue

                try:
                    parts = allocation_data.split(':')
                    if len(parts) != 2:
                        continue

                    assessment_id = int(parts[0])
                    amount = Decimal(parts[1])

                    if amount <= 0:
                        continue

                    assessment = FeeAssessment.query.get(assessment_id)
                    if not assessment or assessment.student_id != payment.student_id:
                        flash(f'Invalid assessment ID: {assessment_id}', 'error')
                        continue

                    already_allocated = db.session.query(func.sum(PaymentAllocation.amount)) \
                                            .filter_by(assessment_id=assessment_id).scalar() or Decimal('0')
                    outstanding = assessment.amount - already_allocated

                    if amount > outstanding:
                        flash(f'Amount for {assessment.fee_item.name} exceeds outstanding balance', 'warning')
                        amount = outstanding

                    allocations_to_create.append({
                        'assessment_id': assessment_id,
                        'amount': amount
                    })
                    total_allocated += amount

                except (ValueError, TypeError):
                    continue

            if total_allocated > payment.amount:
                flash('Total allocation exceeds payment amount', 'error')
                db.session.rollback()
            elif total_allocated == 0:
                flash('No valid allocations provided', 'warning')
            else:
                for alloc_data in allocations_to_create:
                    allocation = PaymentAllocation(
                        payment_id=payment_id,
                        assessment_id=alloc_data['assessment_id'],
                        amount=alloc_data['amount']
                    )
                    db.session.add(allocation)

                db.session.commit()
                flash(f'Payment allocated successfully. Total: KSh {total_allocated:,.2f}', 'success')
                return redirect(url_for('students.detail', student_id=payment.student_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error allocating payment: {str(e)}', 'error')

    outstanding_assessments = db.session.query(
        FeeAssessment,
        (FeeAssessment.amount - func.coalesce(func.sum(PaymentAllocation.amount), 0)).label('outstanding')
    ).filter_by(student_id=payment.student_id) \
        .outerjoin(PaymentAllocation) \
        .group_by(FeeAssessment.id) \
        .having(func.coalesce(func.sum(PaymentAllocation.amount), 0) < FeeAssessment.amount) \
        .all()

    return render_template('payments/allocate.html',
                           payment=payment,
                           outstanding_assessments=outstanding_assessments)


@payments_bp.route('/<int:payment_id>')
@login_required
def detail(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    total_assessed = db.session.query(func.sum(FeeAssessment.amount)) \
                         .filter_by(student_id=payment.student.id).scalar() or Decimal('0')

    total_paid = db.session.query(func.sum(PaymentAllocation.amount)) \
                     .join(FeeAssessment) \
                     .filter(FeeAssessment.student_id == payment.student.id).scalar() or Decimal('0')

    current_balance = Decimal(str(total_assessed)) - Decimal(str(total_paid))

    return render_template('payments/receipt.html',
                           payment=payment,
                           amount_to_words=amount_to_words,
                           total_assessed=total_assessed,
                           total_paid=total_paid,
                           current_balance=current_balance)


@payments_bp.route('/<int:payment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if request.method == 'POST':
        try:
            old_amount = payment.amount
            old_date = payment.payment_date
            old_mode = payment.payment_mode.value

            payment.amount = Decimal(request.form['amount'])
            payment.payment_date = datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date()
            payment.payment_mode = PaymentMode(request.form['payment_mode'])

            payment.mpesa_code = request.form.get('mpesa_code') if payment.payment_mode == PaymentMode.MPESA else None
            payment.bank_slip_number = request.form.get(
                'bank_slip_number') if payment.payment_mode == PaymentMode.BANK else None
            payment.cheque_number = request.form.get(
                'cheque_number') if payment.payment_mode == PaymentMode.CHEQUE else None

            edit_reason = request.form.get('edit_reason', '')
            existing_notes = payment.notes or ''
            audit_note = f"\n\n[EDITED on {datetime.now().strftime('%Y-%m-%d %H:%M')} by {current_user.name}]\nReason: {edit_reason}\nChanges: Amount {old_amount} -> {payment.amount}, Date {old_date} -> {payment.payment_date}, Mode {old_mode} -> {payment.payment_mode.value}"
            payment.notes = existing_notes + audit_note

            db.session.commit()

            flash(f'Payment {payment.receipt_number} updated successfully', 'success')
            return redirect(url_for('payments.detail', payment_id=payment_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating payment: {str(e)}', 'error')

    return render_template('payments/edit.html', payment=payment)


@payments_bp.route('/<int:payment_id>/delete', methods=['POST'])
@login_required
def delete(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if payment.allocations:
        flash('Cannot delete payment - it has allocations. Remove allocations first.', 'error')
        return redirect(url_for('payments.detail', payment_id=payment_id))

    if current_user.role != UserRole.ADMIN:
        flash('Only administrators can delete payment records', 'error')
        return redirect(url_for('payments.detail', payment_id=payment_id))

    try:
        receipt_number = payment.receipt_number
        student_id = payment.student_id

        db.session.delete(payment)
        db.session.commit()

        flash(f'Payment {receipt_number} deleted successfully', 'success')
        return redirect(url_for('students.detail', student_id=student_id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting payment: {str(e)}', 'error')
        return redirect(url_for('payments.detail', payment_id=payment_id))


@payments_bp.route('/<int:payment_id>/print')
@login_required
def print_receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    total_assessed = db.session.query(func.sum(FeeAssessment.amount)) \
                         .filter_by(student_id=payment.student.id).scalar() or Decimal('0')

    total_paid = db.session.query(func.sum(PaymentAllocation.amount)) \
                     .join(FeeAssessment) \
                     .filter(FeeAssessment.student_id == payment.student.id).scalar() or Decimal('0')

    current_balance = Decimal(str(total_assessed)) - Decimal(str(total_paid))

    return render_template('payments/print_receipt.html',
                           payment=payment,
                           amount_to_words=amount_to_words,
                           total_assessed=total_assessed,
                           total_paid=total_paid,
                           current_balance=current_balance)


@payments_bp.route('/<int:payment_id>/download-pdf')
@login_required
def download_pdf(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    try:
        pdf_buffer = generate_receipt_pdf(payment)

        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=Receipt_{payment.receipt_number}.pdf'

        return response
    except Exception as e:
        flash(f'Error generating PDF: {str(e)}', 'error')
        return redirect(url_for('payments.detail', payment_id=payment_id))


def generate_receipt_pdf(payment):
    """Generate PDF receipt"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
                            rightMargin=10 * mm, leftMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm)

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    school_name_style = ParagraphStyle(
        'SchoolName',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=3,
        fontName='Helvetica-Bold'
    )

    # Add school header
    elements.append(Paragraph("ST LUKE MOGOBICH ACADEMY", school_name_style))
    elements.append(Spacer(1, 5 * mm))

    # Receipt details
    receipt_data = [
        ['Receipt No:', payment.receipt_number, 'Date:', payment.payment_date.strftime('%d/%m/%Y')],
        ['Student:', payment.student.full_name, 'Adm:', payment.student.admission_no],
        ['Amount:', f"KSh {payment.amount:,.2f}", '', '']
    ]

    receipt_table = Table(receipt_data, colWidths=[30 * mm, 40 * mm, 20 * mm, 30 * mm])
    receipt_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(receipt_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer