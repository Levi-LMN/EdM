from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from decimal import Decimal
import enum

db = SQLAlchemy()


# ===========================
#  ENUMS FOR BETTER ORGANIZATION
# ===========================
class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    PRINCIPAL = "PRINCIPAL"


class StudentType(enum.Enum):
    DAY = "DAY"
    BOARDER = "BOARDER"


class PaymentMode(enum.Enum):
    CASH = "CASH"
    MPESA = "MPESA"
    BANK = "BANK"
    CHEQUE = "CHEQUE"


class FeeScope(enum.Enum):
    UNIVERSAL = "UNIVERSAL"  # Everyone in school
    CLASS_LEVEL = "CLASS_LEVEL"  # Everyone in specific class
    STREAM_LEVEL = "STREAM_LEVEL"  # Everyone in specific stream
    INDIVIDUAL = "INDIVIDUAL"  # Manually assigned per student


class PromotionStatus(enum.Enum):
    PROMOTED = "PROMOTED"
    REPEATED = "REPEATED"
    TRANSFERRED = "TRANSFERRED"


# ===========================
#  USER AUTHENTICATION
# ===========================
class User(UserMixin, db.Model):
    """Simple user model for Google OAuth"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    profile_pic = db.Column(db.String(500))
    role = db.Column(db.Enum(UserRole), default=UserRole.ACCOUNTANT)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def __repr__(self):
        return f"<User {self.email}>"


# ===========================
#  ACADEMIC STRUCTURE
# ===========================
class AcademicYear(db.Model):
    """Track academic years"""
    __tablename__ = "academic_years"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)  # e.g., 2024
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<AcademicYear {self.year}>"


class Class(db.Model):
    """Academic classes (Form 1, Form 2, etc.)"""
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # "Form 1", "Grade 8"
    level = db.Column(db.String(20))  # "Primary", "Secondary"
    next_class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))  # For automatic promotion

    # Relationships
    next_class = db.relationship("Class", remote_side=[id])
    streams = db.relationship("Stream", back_populates="class_obj", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Class {self.name}>"


class Stream(db.Model):
    """Streams within classes (A, B, C, etc.)"""
    __tablename__ = "streams"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name = db.Column(db.String(10), nullable=False)  # "A", "B", "C"
    capacity = db.Column(db.Integer, default=40)

    # Relationships
    class_obj = db.relationship("Class", back_populates="streams")
    students = db.relationship("Student", back_populates="stream")

    __table_args__ = (db.UniqueConstraint("class_id", "name", name="unique_class_stream"),)

    def __repr__(self):
        return f"<Stream {self.class_obj.name}-{self.name}>"


# ===========================
#  TRANSPORT VEHICLES
# ===========================
class Vehicle(db.Model):
    """School transport vehicles"""
    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    registration_number = db.Column(db.String(20), unique=True, nullable=False)
    make = db.Column(db.String(50))
    model = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    driver_name = db.Column(db.String(100))
    driver_phone = db.Column(db.String(20))
    route_description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    students = db.relationship("Student", back_populates="vehicle")

    def __repr__(self):
        return f"<Vehicle {self.registration_number}>"


# ===========================
#  STUDENTS
# ===========================
class Student(db.Model):
    """Student records"""
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    admission_no = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date)

    # Current class/stream
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))

    # Student details
    student_type = db.Column(db.Enum(StudentType), nullable=False)
    parent_name = db.Column(db.String(100))
    parent_phone = db.Column(db.String(20))
    parent_email = db.Column(db.String(100))

    # Transport details (optional)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"))
    transport_distance_km = db.Column(db.Numeric(6, 2))  # Distance from school

    # Status
    is_active = db.Column(db.Boolean, default=True)
    admission_date = db.Column(db.Date, default=date.today)

    # Relationships
    class_obj = db.relationship("Class", backref="students")
    stream = db.relationship("Stream", back_populates="students")
    vehicle = db.relationship("Vehicle", back_populates="students")

    def __repr__(self):
        return f"<Student {self.admission_no} - {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_current_balance(self):
        """Get student's current balance"""
        total_fees = db.session.query(db.func.sum(FeeAssessment.amount)) \
                         .filter_by(student_id=self.id).scalar() or 0

        total_payments = db.session.query(db.func.sum(Payment.amount)) \
                             .filter_by(student_id=self.id).scalar() or 0

        return Decimal(str(total_fees)) - Decimal(str(total_payments))

    def promote_to_next_class(self, academic_year, status=PromotionStatus.PROMOTED):
        """Promote student to next class"""
        if self.class_obj.next_class:
            # Record the promotion
            promotion = StudentPromotion(
                student_id=self.id,
                from_class_id=self.class_id,
                from_stream_id=self.stream_id,
                to_class_id=self.class_obj.next_class_id,
                academic_year=academic_year,
                status=status,
                promotion_date=date.today()
            )
            db.session.add(promotion)

            # Update student's current class
            self.class_id = self.class_obj.next_class_id
            self.stream_id = None  # Reset stream, will be assigned later

            return True
        return False


# ===========================
#  FEE ITEMS & RATES
# ===========================
class FeeItem(db.Model):
    """Different types of fees (Tuition, Transport, Meals, etc.)"""
    __tablename__ = "fee_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)  # TUITION, TRANSPORT, etc.
    description = db.Column(db.Text)

    # How this fee applies
    scope = db.Column(db.Enum(FeeScope), default=FeeScope.CLASS_LEVEL)
    is_per_km = db.Column(db.Boolean, default=False)  # For transport fees
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    rates = db.relationship("FeeRate", back_populates="fee_item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FeeItem {self.code} - {self.name}>"


class FeeRate(db.Model):
    """Fee rates for different terms, classes, streams"""
    __tablename__ = "fee_rates"

    id = db.Column(db.Integer, primary_key=True)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)

    # Academic period
    term = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    year = db.Column(db.Integer, nullable=False)

    # Applicability (NULL means applies to all)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))
    student_type = db.Column(db.Enum(StudentType))  # DAY/BOARDER specific rates

    # Rate amounts
    amount = db.Column(db.Numeric(10, 2))  # Fixed amount
    rate_per_km = db.Column(db.Numeric(8, 2))  # For transport (per km)

    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    fee_item = db.relationship("FeeItem", back_populates="rates")
    class_obj = db.relationship("Class")
    stream = db.relationship("Stream")

    __table_args__ = (
        db.UniqueConstraint("fee_item_id", "term", "year", "class_id",
                            "stream_id", "student_type", name="unique_fee_rate"),
    )

    def __repr__(self):
        scope = "All"
        if self.stream:
            scope = f"{self.class_obj.name}-{self.stream.name}"
        elif self.class_obj:
            scope = self.class_obj.name

        return f"<FeeRate {self.fee_item.code} T{self.term}/{self.year} {scope}>"


# ===========================
#  INDIVIDUAL FEE ASSIGNMENTS
# ===========================
class StudentFeeAssignment(db.Model):
    """Assign specific fees to individual students"""
    __tablename__ = "student_fee_assignments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)

    # When this assignment is active
    term = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    # Custom rates (overrides standard rates)
    custom_amount = db.Column(db.Numeric(10, 2))
    custom_rate_per_km = db.Column(db.Numeric(8, 2))
    custom_distance = db.Column(db.Numeric(6, 2))  # Custom distance for this student

    is_active = db.Column(db.Boolean, default=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.Text)

    # Relationships
    student = db.relationship("Student", backref="fee_assignments")
    fee_item = db.relationship("FeeItem")
    assigned_by_user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("student_id", "fee_item_id", "term", "year",
                            name="unique_student_fee_assignment"),
    )

    def __repr__(self):
        return f"<Assignment {self.student.admission_no} - {self.fee_item.code}>"


# ===========================
#  FEE ASSESSMENTS
# ===========================
class FeeAssessment(db.Model):
    """Individual fee assessments for students per term"""
    __tablename__ = "fee_assessments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    fee_item_id = db.Column(db.Integer, db.ForeignKey("fee_items.id"), nullable=False)

    # Academic period
    term = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    # Assessment details
    description = db.Column(db.String(200))
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Calculation details (for transparency)
    base_rate = db.Column(db.Numeric(10, 2))  # The base rate used
    quantity = db.Column(db.Numeric(8, 2))  # Distance, months, etc.

    # Metadata
    assessed_date = db.Column(db.Date, default=date.today)
    assessed_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    # Relationships
    student = db.relationship("Student", backref="fee_assessments")
    fee_item = db.relationship("FeeItem")
    assessor = db.relationship("User")

    def __repr__(self):
        return f"<Assessment {self.student.admission_no} - {self.fee_item.code} T{self.term}/{self.year}>"


# ===========================
#  PAYMENTS
# ===========================
class Payment(db.Model):
    """Student payments"""
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)

    # Payment details
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, default=date.today)
    payment_mode = db.Column(db.Enum(PaymentMode), nullable=False)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)

    # Payment method specific fields
    mpesa_code = db.Column(db.String(20))
    bank_slip_number = db.Column(db.String(30))
    cheque_number = db.Column(db.String(20))

    notes = db.Column(db.Text)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship("Student", backref="payments")
    processor = db.relationship("User")
    allocations = db.relationship("PaymentAllocation", back_populates="payment",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Payment {self.receipt_number} - {self.amount}>"


class PaymentAllocation(db.Model):
    """Allocate payments to specific fee assessments"""
    __tablename__ = "payment_allocations"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    assessment_id = db.Column(db.Integer, db.ForeignKey("fee_assessments.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Relationships
    payment = db.relationship("Payment", back_populates="allocations")
    assessment = db.relationship("FeeAssessment", backref="allocations")

    def __repr__(self):
        return f"<Allocation {self.payment.receipt_number} -> {self.amount}>"


# ===========================
#  STUDENT PROMOTIONS
# ===========================
class StudentPromotion(db.Model):
    """Track student promotions and class changes"""
    __tablename__ = "student_promotions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)

    # From/To details
    from_class_id = db.Column(db.Integer, db.ForeignKey("classes.id"))
    from_stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))
    to_class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    to_stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"))

    # Promotion details
    academic_year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(PromotionStatus), default=PromotionStatus.PROMOTED)
    promotion_date = db.Column(db.Date, default=date.today)

    notes = db.Column(db.Text)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    # Relationships
    student = db.relationship("Student", backref="promotions")
    from_class = db.relationship("Class", foreign_keys=[from_class_id])
    from_stream = db.relationship("Stream", foreign_keys=[from_stream_id])
    to_class = db.relationship("Class", foreign_keys=[to_class_id])
    to_stream = db.relationship("Stream", foreign_keys=[to_stream_id])
    processor = db.relationship("User")

    def __repr__(self):
        return f"<Promotion {self.student.admission_no} - {self.status.value}>"


# ===========================
#  EXPENSES
# ===========================
class ExpenseCategory(db.Model):
    """Categories for school expenses"""
    __tablename__ = "expense_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


class Expense(db.Model):
    """School expenses"""
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=False)

    # Expense details
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    expense_date = db.Column(db.Date, default=date.today)

    # Payment details
    payment_method = db.Column(db.Enum(PaymentMode))
    reference_number = db.Column(db.String(50))
    supplier_name = db.Column(db.String(200))

    # Approval
    approved_by = db.Column(db.String(100))
    notes = db.Column(db.Text)

    # Metadata
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    category = db.relationship("ExpenseCategory", backref="expenses")
    creator = db.relationship("User", backref="expenses_created")

    def __repr__(self):
        return f"<Expense {self.description[:30]}... - {self.amount}>"


# ===========================
#  UTILITY FUNCTIONS
# ===========================
def generate_fee_assessments(term, year, class_id=None, stream_id=None, student_id=None):
    """Generate fee assessments for students based on their applicable fees"""

    # Determine which students to assess
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
        # Get all applicable fee items for this student
        applicable_fees = get_applicable_fees_for_student(student, term, year)

        for fee_item, rate_info in applicable_fees:
            # Check if assessment already exists
            existing = FeeAssessment.query.filter_by(
                student_id=student.id,
                fee_item_id=fee_item.id,
                term=term,
                year=year
            ).first()

            if existing:
                continue  # Skip if already assessed

            # Calculate amount
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


def get_applicable_fees_for_student(student, term, year):
    """Get all fee items applicable to a specific student"""
    applicable_fees = []

    # Get all active fee items
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
        else:
            # Look for standard rates
            if fee_item.scope == FeeScope.UNIVERSAL:
                # Universal fees apply to everyone
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

            elif fee_item.scope == FeeScope.STREAM_LEVEL:
                # Stream-specific rates
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    stream_id=student.stream_id,
                    student_type=student.student_type,
                    is_active=True
                ).first()

                if not rate:
                    # Fall back to stream without student type
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
                # Class-level rates
                rate = FeeRate.query.filter_by(
                    fee_item_id=fee_item.id,
                    term=term,
                    year=year,
                    class_id=student.class_id,
                    student_type=student.student_type,
                    is_active=True
                ).first()

                if not rate:
                    # Fall back to class without student type
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


def get_student_balance_summary(student_id):
    """Get comprehensive balance summary for a student"""
    student = Student.query.get_or_404(student_id)

    # Get all assessments
    assessments = db.session.query(
        FeeAssessment.term,
        FeeAssessment.year,
        db.func.sum(FeeAssessment.amount).label('total_assessed')
    ).filter_by(student_id=student_id) \
        .group_by(FeeAssessment.term, FeeAssessment.year) \
        .all()

    # Get all payments
    total_payments = db.session.query(db.func.sum(Payment.amount)) \
                         .filter_by(student_id=student_id).scalar() or 0

    # Calculate balances per term
    term_balances = []
    total_assessed = 0

    for assessment in assessments:
        assessed_amount = float(assessment.total_assessed)
        total_assessed += assessed_amount

        # Get payments allocated to this term
        allocated_payments = db.session.query(db.func.sum(PaymentAllocation.amount)) \
                                 .join(FeeAssessment) \
                                 .filter(FeeAssessment.student_id == student_id,
                                         FeeAssessment.term == assessment.term,
                                         FeeAssessment.year == assessment.year) \
                                 .scalar() or 0

        balance = assessed_amount - float(allocated_payments)

        term_balances.append({
            'term': assessment.term,
            'year': assessment.year,
            'assessed': assessed_amount,
            'paid': float(allocated_payments),
            'balance': balance
        })

    return {
        'student': student,
        'term_balances': term_balances,
        'total_assessed': total_assessed,
        'total_payments': float(total_payments),
        'overall_balance': total_assessed - float(total_payments)
    }