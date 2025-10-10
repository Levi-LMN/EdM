"""Utility functions"""
from decimal import Decimal
from sqlalchemy import func
from models import (
    FeeItem, FeeRate, FeeScope, FeeAssessment, StudentFeeAssignment,
    PaymentAllocation, db
)


def amount_to_words(amount):
    """Convert amount to words for receipt"""
    amount = float(amount)
    shillings = int(amount)
    cents = int((amount - shillings) * 100)

    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    teens = ['Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen',
             'Nineteen']

    def convert_below_thousand(n):
        if n == 0:
            return ''
        elif n < 10:
            return ones[n]
        elif n < 20:
            return teens[n - 10]
        elif n < 100:
            return tens[n // 10] + (' ' + ones[n % 10] if n % 10 != 0 else '')
        else:
            return ones[n // 100] + ' Hundred' + (' ' + convert_below_thousand(n % 100) if n % 100 != 0 else '')

    if shillings == 0:
        words = 'Zero'
    else:
        words = ''
        if shillings >= 1000000:
            words += convert_below_thousand(shillings // 1000000) + ' Million '
            shillings %= 1000000
        if shillings >= 1000:
            words += convert_below_thousand(shillings // 1000) + ' Thousand '
            shillings %= 1000
        if shillings > 0:
            words += convert_below_thousand(shillings)
        words = words.strip()

    if cents > 0:
        words += ' and ' + convert_below_thousand(cents) + ' Cents'

    return words


def get_applicable_fees_for_student(student, term, year):
    """Get all fee items applicable to a specific student"""
    applicable_fees = []
    fee_items = FeeItem.query.filter_by(is_active=True).all()

    for fee_item in fee_items:
        rate_info = None

        # Check for individual assignment first
        individual_assignment = StudentFeeAssignment.query.filter_by(
            student_id=student.id,
            fee_item_id=fee_item.id,
            term=term,
            year=year,
            is_active=True
        ).first()

        if individual_assignment:
            if individual_assignment.custom_amount:
                rate_info = {
                    'source': 'individual',
                    'base_rate': individual_assignment.custom_amount,
                    'quantity': 1
                }
            elif fee_item.is_per_km and individual_assignment.custom_rate_per_km:
                distance = individual_assignment.custom_distance or student.transport_distance_km
                if distance:
                    rate_info = {
                        'source': 'individual_per_km',
                        'base_rate': individual_assignment.custom_rate_per_km,
                        'quantity': distance
                    }

        # If no individual assignment found, look for standard rates
        if not rate_info:
            if fee_item.scope == FeeScope.UNIVERSAL or fee_item.scope == FeeScope.INDIVIDUAL:
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    class_id=None,
                    stream_id=None,
                    is_active=True
                ).first()

                if rate:
                    rate_info = get_rate_info(rate, student, fee_item)
                    if fee_item.code == 'TRANSPORT' and not student.vehicle_id:
                        rate_info = None

            elif fee_item.scope == FeeScope.STREAM_LEVEL and student.stream_id:
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    stream_id=student.stream_id,
                    student_type=student.student_type,
                    is_active=True
                ).first()

                if not rate:
                    rate = FeeRate.query.filter_by(
                        fee_item_id=fee_item.id,
                        term=term,
                        year=year,
                        stream_id=student.stream_id,
                        student_type=None,
                        is_active=True
                    ).first()

                if rate:
                    rate_info = get_rate_info(rate, student, fee_item)

            elif fee_item.scope == FeeScope.CLASS_LEVEL:
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    class_id=student.class_id,
                    student_type=student.student_type,
                    is_active=True
                ).first()

                if not rate:
                    rate = FeeRate.query.filter_by(
                        fee_item_id=fee_item.id,
                        term=term,
                        year=year,
                        class_id=student.class_id,
                        student_type=None,
                        is_active=True
                    ).first()

                if rate:
                    rate_info = get_rate_info(rate, student, fee_item)

        if rate_info:
            applicable_fees.append((fee_item, rate_info))

    return applicable_fees


def get_rate_info(fee_rate, student, fee_item):
    """Extract rate information for calculation"""
    if fee_item.is_per_km and student.transport_distance_km and fee_rate.rate_per_km:
        return {
            'source': 'standard_per_km',
            'base_rate': fee_rate.rate_per_km,
            'quantity': student.transport_distance_km
        }
    elif fee_rate.amount:
        return {
            'source': 'standard_fixed',
            'base_rate': fee_rate.amount,
            'quantity': 1
        }
    return None


def calculate_fee_amount(student, fee_item, rate_info):
    """Calculate the actual fee amount"""
    base_rate = rate_info.get('base_rate', 0)
    quantity = rate_info.get('quantity', 1)
    return Decimal(str(base_rate)) * Decimal(str(quantity))


def generate_fee_assessments(term, year, class_id=None, stream_id=None, student_id=None, force_regenerate=False):
    """Generate fee assessments for students based on their applicable fees"""
    from models import Student

    query = Student.query.filter_by(is_active=True)

    if student_id:
        query = query.filter_by(id=student_id)
    elif stream_id:
        query = query.filter_by(stream_id=stream_id)
    elif class_id:
        query = query.filter_by(class_id=class_id)

    students = query.all()
    assessments_created = 0

    for student in students:
        applicable_fees = get_applicable_fees_for_student(student, term, year)

        for fee_item, rate_info in applicable_fees:
            existing = FeeAssessment.query.filter_by(
                student_id=student.id,
                fee_item_id=fee_item.id,
                term=term,
                year=year
            ).first()

            if existing:
                if not force_regenerate:
                    continue
                else:
                    db.session.delete(existing)
                    db.session.flush()

            amount = calculate_fee_amount(student, fee_item, rate_info)

            if amount > 0:
                assessment = FeeAssessment(
                    student_id=student.id,
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    description=f"{fee_item.name} - Term {term} {year}",
                    amount=amount,
                    base_rate=rate_info.get('base_rate'),
                    quantity=rate_info.get('quantity', 1)
                )

                db.session.add(assessment)
                assessments_created += 1

    db.session.commit()
    return assessments_created