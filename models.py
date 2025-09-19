from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from decimal import Decimal

db = SQLAlchemy()


# ===========================
#  ACADEMIC TERMS
# ===========================
class AcademicTerm(db.Model):
    """Manages academic terms with start/end dates"""
    __tablename__ = "academic_terms"

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.SmallInteger, nullable=False)  # 1, 2, 3
    year = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("term", "year", name="uq_term_year"),
    )

    def __repr__(self):
        return f"<AcademicTerm Term {self.term}/{self.year}>"

    @classmethod
    def get_current_term(cls):
        """Get the current active term"""
        return cls.query.filter_by(is_current=True).first()

    @classmethod
    def get_term_by_date(cls, check_date=None):
        """Get term by date (defaults to today)"""
        if check_date is None:
            check_date = date.today()

        return cls.query.filter(
            cls.start_date <= check_date,
            cls.end_date >= check_date
        ).first()

    def is_active(self):
        """Check if this term is currently active based on dates"""
        today = date.today()
        return self.start_date <= today <= self.end_date


# ===========================
#  CLASSES & STREAMS
# ===========================
class Class(db.Model):
    """Represents an academic class (e.g. Form 1, Grade 8)."""
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # e.g. "Form 1"
    level = db.Column(db.String(30))  # e.g. "Primary", "Secondary"

    streams = db.relationship("Stream", backref="class_obj", lazy=True)

    def __repr__(self):
        return f"<Class {self.name}>"


class Stream(db.Model):
    """Represents a stream within a class (e.g. Stream A, Stream B)."""
    __tablename__ = "streams"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name = db.Column(db.String(10), nullable=False)  # e.g. "A", "B"

    __table_args__ = (db.UniqueConstraint("class_id", "name", name="uq_class_stream"),)

    def __repr__(self):
        return f"<Stream {self.class_obj.name}-{self.name}>"


# ===========================
#  STUDENTS
# ===========================
class Student(db.Model):
    """Holds student bio data and financial attributes."""
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    admission_no = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))

    student_type = db.Column(db.Enum("DAY", "BOARDER", name="student_type"), nullable=False)
    parent_contact = db.Column(db.String(100))
    transport_distance_km = db.Column(db.Numeric(7, 2))  # NULL if no transport
    meals_plan = db.Column(
        db.Enum("NONE", "LUNCH", "FULL", name="meals_plan"),
        default="NONE",
        nullable=False
    )

    class_obj = db.relationship("Class", backref=db.backref("students", lazy=True))
    stream = db.relationship("Stream", backref=db.backref("students", lazy=True))

    def __repr__(self):
        return f"<Student {self.admission_no} - {self.first_name} {self.last_name}>"

    def get_balance_for_term(self, term=None, year=None, as_of_date=None):
        """
        Calculate student's balance for a specific term/year or as of a date.
        Returns a dictionary with balance details.
        """
        if term is None or year is None:
            if as_of_date:
                current_term = AcademicTerm.get_term_by_date(as_of_date)
            else:
                current_term = AcademicTerm.get_current_term()

            if not current_term:
                return {
                    'total_assessed': Decimal('0.00'),
                    'total_paid': Decimal('0.00'),
                    'balance': Decimal('0.00'),
                    'term': None,
                    'year': None,
                    'error': 'No active term found'
                }

            term = current_term.term
            year = current_term.year

        # Get all assessments up to and including the specified term
        assessments_query = FeeAssessment.query.filter(
            FeeAssessment.student_id == self.id,
            db.or_(
                FeeAssessment.year < year,
                db.and_(
                    FeeAssessment.year == year,
                    FeeAssessment.term <= term
                )
            )
        )

        # Calculate total assessed amount
        total_assessed = db.session.query(
            db.func.coalesce(db.func.sum(FeeAssessmentLine.amount), 0)
        ).select_from(FeeAssessmentLine) \
                             .join(FeeAssessment) \
                             .filter(FeeAssessment.id.in_(
            assessments_query.with_entities(FeeAssessment.id)
        )).scalar() or Decimal('0.00')

        # Calculate total payments - FIXED: More inclusive payment calculation
        if as_of_date:
            payment_filter_date = as_of_date
        else:
            # Instead of using term end date, use today's date to include all payments made so far
            payment_filter_date = date.today()

            # Alternative: If you want to respect term boundaries, but include some buffer:
            # term_obj = AcademicTerm.query.filter_by(term=term, year=year).first()
            # if term_obj and term_obj.end_date < date.today():
            #     # If term has ended, use today's date to include post-term payments
            #     payment_filter_date = date.today()
            # else:
            #     # If term is ongoing, use term end date
            #     payment_filter_date = term_obj.end_date if term_obj else date.today()

        total_paid = db.session.query(
            db.func.coalesce(db.func.sum(Payment.amount), 0)
        ).filter(
            Payment.student_id == self.id,
            Payment.payment_date <= payment_filter_date
        ).scalar() or Decimal('0.00')

        balance = total_assessed - total_paid

        return {
            'total_assessed': Decimal(str(total_assessed)),
            'total_paid': Decimal(str(total_paid)),
            'balance': balance,
            'term': term,
            'year': year,
            'term_obj': AcademicTerm.query.filter_by(term=term, year=year).first()
        }

    def get_current_balance(self):
        """Get current balance as of today"""
        return self.get_balance_for_term()

    def get_balance_history(self, from_year=None):
        """Get balance history by term"""
        if from_year is None:
            from_year = datetime.now().year - 1

        # Get all terms from the specified year onwards
        terms = AcademicTerm.query.filter(
            AcademicTerm.year >= from_year
        ).order_by(AcademicTerm.year, AcademicTerm.term).all()

        balance_history = []
        for term_obj in terms:
            balance_info = self.get_balance_for_term(term_obj.term, term_obj.year)
            balance_info['term_obj'] = term_obj
            balance_history.append(balance_info)

        return balance_history

    def get_outstanding_fee_lines(self, term=None, year=None):
        """Get detailed breakdown of outstanding fee lines"""
        if term is None or year is None:
            current_term = AcademicTerm.get_current_term()
            if current_term:
                term = current_term.term
                year = current_term.year

        # Get all assessment lines up to the specified term with outstanding amounts
        outstanding_query = db.session.query(
            FeeAssessmentLine,
            FeeAssessment,
            FeeItem,
            (FeeAssessmentLine.amount -
             db.func.coalesce(
                 db.session.query(db.func.sum(PaymentAllocation.amount))
                 .filter(PaymentAllocation.assessment_line_id == FeeAssessmentLine.id)
                 .correlate(FeeAssessmentLine)
                 .scalar_subquery(),
                 0
             )).label('outstanding_amount')
        ).join(FeeAssessment, FeeAssessment.id == FeeAssessmentLine.assessment_id) \
            .join(FeeItem, FeeItem.id == FeeAssessmentLine.fee_item_id) \
            .filter(
            FeeAssessment.student_id == self.id,
            db.or_(
                FeeAssessment.year < year,
                db.and_(
                    FeeAssessment.year == year,
                    FeeAssessment.term <= term
                )
            )
        ).order_by(FeeAssessment.year, FeeAssessment.term)

        outstanding_lines = []
        for line, assessment, fee_item, outstanding_amount in outstanding_query:
            if outstanding_amount > 0:
                outstanding_lines.append({
                    'line_id': line.id,
                    'fee_item': fee_item.name,
                    'fee_code': fee_item.code,
                    'description': line.description,
                    'assessed_amount': line.amount,
                    'outstanding_amount': Decimal(str(outstanding_amount)),
                    'term': assessment.term,
                    'year': assessment.year,
                    'assessment_date': assessment.assessed_at
                })

        return outstanding_lines


# ===========================
#  FEE ITEMS & RATES
# ===========================
class FeeItem(db.Model):
    """Lookup table for types of fees (e.g. Tuition, Boarding, Meals, Transport)."""
    __tablename__ = "fee_items"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)  # e.g. TUITION
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_optional = db.Column(db.Boolean, default=False)  # Meals/Transport are optional
    is_per_km = db.Column(db.Boolean, default=False)  # True if charged per km (Transport)

    def __repr__(self):
        return f"<FeeItem {self.code}>"


class FeeRate(db.Model):
    """Holds per-term, per-class, per-stream fee amounts."""
    __tablename__ = "fee_rates"

    id = db.Column(db.Integer, primary_key=True)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))
    student_type = db.Column(db.Enum("DAY", "BOARDER", name="rate_student_type"))

    term = db.Column(db.SmallInteger, nullable=False)  # 1, 2, 3
    year = db.Column(db.Integer, nullable=False)

    amount = db.Column(db.Numeric(12, 2))  # Flat fee (Tuition/Boarding/Meals)
    rate_per_km = db.Column(db.Numeric(8, 2))  # Transport fee per km (if applicable)

    fee_item = db.relationship("FeeItem", backref="rates")
    class_obj = db.relationship("Class", backref="fee_rates")
    stream = db.relationship("Stream", backref="fee_rates")

    __table_args__ = (
        db.UniqueConstraint(
            "fee_item_id", "class_id", "stream_id", "student_type", "term", "year",
            name="uq_fee_rate"
        ),
    )

    def __repr__(self):
        return f"<FeeRate {self.fee_item.code}-{self.class_obj.name}-T{self.term}-{self.year}>"


# ===========================
#  STUDENT SERVICES (OPTIONAL)
# ===========================
class StudentService(db.Model):
    """Tracks optional services (Transport, Meals) with custom rates or distance."""
    __tablename__ = "student_services"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)
    custom_rate = db.Column(db.Numeric(12, 2))
    distance_km = db.Column(db.Numeric(7, 2))
    active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)

    student = db.relationship("Student", backref="services")
    fee_item = db.relationship("FeeItem", backref="student_services")

    def __repr__(self):
        return f"<StudentService {self.student.admission_no}-{self.fee_item.code}>"


# ===========================
#  FEE ASSESSMENTS (INVOICES)
# ===========================
class FeeAssessment(db.Model):
    """Represents an invoice for a student for a given term & year."""
    __tablename__ = "fee_assessments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    term = db.Column(db.SmallInteger, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    assessed_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", backref="assessments")

    def total_amount(self):
        return sum(line.amount for line in self.lines)

    def __repr__(self):
        return f"<Assessment {self.student.admission_no} T{self.term}/{self.year}>"


class FeeAssessmentLine(db.Model):
    """Line items for a student's invoice (Tuition, Meals, Transport, etc.)."""
    __tablename__ = "fee_assessment_lines"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("fee_assessments.id"), nullable=False)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    assessment = db.relationship("FeeAssessment", backref=db.backref("lines", lazy=True))
    fee_item = db.relationship("FeeItem")

    def __repr__(self):
        return f"<AssessmentLine {self.fee_item.code}: {self.amount}>"


# ===========================
#  PAYMENTS & ALLOCATIONS
# ===========================
class Payment(db.Model):
    """Stores payments received from parents/guardians."""
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    payment_date = db.Column(db.Date, default=date.today)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    mode = db.Column(db.Enum("CASH", "MPESA", "BANK", "CHEQUE", name="payment_mode"), nullable=False)
    receipt_no = db.Column(db.String(80), unique=True, nullable=False)
    note = db.Column(db.Text)

    student = db.relationship("Student", backref="payments")

    def __repr__(self):
        return f"<Payment {self.receipt_no} - {self.amount}>"


class PaymentAllocation(db.Model):
    """Allocates part of a payment to a specific fee line (supports partial payments)."""
    __tablename__ = "payment_allocations"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    assessment_line_id = db.Column(db.Integer, db.ForeignKey("fee_assessment_lines.id"))
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"))
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    payment = db.relationship("Payment", backref=db.backref("allocations", cascade="all, delete"))
    assessment_line = db.relationship("FeeAssessmentLine")
    fee_item = db.relationship("FeeItem")

    def __repr__(self):
        return f"<PaymentAllocation {self.amount}>"