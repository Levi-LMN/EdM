#!/usr/bin/env python3
"""
Sample data injection script for Kenyan School Fee Management System
Populates the database with realistic Kenyan school data following the application logic.
"""

from flask import Flask
from models import *
from datetime import datetime, date, timedelta  # Added timedelta import
from decimal import Decimal
import random

# Initialize Flask app and database
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school_fees.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


def clear_database():
    """Clear all existing data"""
    print("🗑️  Clearing existing data...")
    with app.app_context():
        # Order matters due to foreign key constraints
        PaymentAllocation.query.delete()
        Payment.query.delete()
        FeeAssessmentLine.query.delete()
        FeeAssessment.query.delete()
        StudentService.query.delete()
        FeeRate.query.delete()
        Student.query.delete()
        Stream.query.delete()
        Class.query.delete()
        FeeItem.query.delete()
        db.session.commit()
        print("✅ Database cleared!")


def create_fee_items():
    """Create Kenyan school fee items"""
    print("💰 Creating fee items...")

    fee_items = [
        # Core fees
        FeeItem(code='TUITION', name='Tuition Fee',
                description='Basic tuition fee per term', is_optional=False),
        FeeItem(code='BOARDING', name='Boarding Fee',
                description='Accommodation fee for boarding students', is_optional=False),
        FeeItem(code='MEALS', name='Meals Fee',
                description='School meals program', is_optional=True),

        # Transport (per km)
        FeeItem(code='TRANSPORT', name='Transport Fee',
                description='School bus transport service', is_optional=True, is_per_km=True),

        # Other fees common in Kenyan schools
        FeeItem(code='UNIFORM', name='Uniform Fee',
                description='School uniform and PE kit', is_optional=True),
        FeeItem(code='BOOKS', name='Books & Stationery',
                description='Textbooks and learning materials', is_optional=True),
        FeeItem(code='ACTIVITY', name='Activity Fee',
                description='Sports, music, drama, and clubs', is_optional=True),
        FeeItem(code='EXAM', name='Examination Fee',
                description='Internal and external examination fees', is_optional=False),
        FeeItem(code='DEVELOPMENT', name='Development Fee',
                description='Infrastructure development contribution', is_optional=False),
        FeeItem(code='INSURANCE', name='Student Insurance',
                description='Medical and accident insurance cover', is_optional=True),

        # Balance brought forward (auto-created by system)
        FeeItem(code='BALANCE_BF', name='Balance B/F',
                description='Carried forward balance from previous term/year', is_optional=False)
    ]

    for item in fee_items:
        db.session.add(item)

    db.session.commit()
    print(f"✅ Created {len(fee_items)} fee items")


def create_classes_and_streams():
    """Create Kenyan secondary school classes and streams"""
    print("🏫 Creating classes and streams...")

    # Kenyan secondary school structure
    class_data = [
        {'name': 'Form 1', 'level': 'Secondary', 'streams': ['East', 'West', 'North']},
        {'name': 'Form 2', 'level': 'Secondary', 'streams': ['East', 'West', 'North']},
        {'name': 'Form 3', 'level': 'Secondary', 'streams': ['East', 'West', 'North', 'South']},
        {'name': 'Form 4', 'level': 'Secondary', 'streams': ['East', 'West', 'North', 'South']}
    ]

    classes = []
    for class_info in class_data:
        cls = Class(name=class_info['name'], level=class_info['level'])
        db.session.add(cls)
        classes.append(cls)

    db.session.flush()  # Get IDs

    # Create streams for each class
    stream_count = 0
    for i, cls in enumerate(classes):
        for stream_name in class_data[i]['streams']:
            stream = Stream(class_id=cls.id, name=stream_name)
            db.session.add(stream)
            stream_count += 1

    db.session.commit()
    print(f"✅ Created {len(classes)} classes and {stream_count} streams")
    return classes


def create_students(classes):
    """Create students with Kenyan names and realistic data"""
    print("👨‍🎓 Creating students...")

    # Common Kenyan names by ethnic groups
    kikuyu_names = {
        'first': ['Kamau', 'Wanjiku', 'Njoroge', 'Wanjiru', 'Mwangi', 'Nyambura', 'Karanja', 'Wangari'],
        'last': ['Kimani', 'Mwangi', 'Kamau', 'Wanjiku', 'Njoroge', 'Karanja', 'Gathoni', 'Mbugua']
    }

    luo_names = {
        'first': ['Otieno', 'Akinyi', 'Ochieng', 'Adhiambo', 'Omondi', 'Apiyo', 'Owino', 'Awino'],
        'last': ['Ochieng', 'Otieno', 'Omondi', 'Owino', 'Okoth', 'Odongo', 'Oloo', 'Ogola']
    }

    luhya_names = {
        'first': ['Wafula', 'Nafula', 'Wanyama', 'Nekesa', 'Barasa', 'Naliaka', 'Mukhwana', 'Simiyu'],
        'last': ['Wanyama', 'Wafula', 'Barasa', 'Mukhwana', 'Simiyu', 'Makhanu', 'Wekesa', 'Shikuku']
    }

    kamba_names = {
        'first': ['Mutua', 'Mwende', 'Kioko', 'Nduku', 'Musyoka', 'Kanini', 'Nthiwa', 'Mwikali'],
        'last': ['Mutua', 'Musyoka', 'Kioko', 'Mwende', 'Nthiwa', 'Wambua', 'Muthoka', 'Kyalo']
    }

    all_names = [kikuyu_names, luo_names, luhya_names, kamba_names]

    students = []
    admission_counter = 1001

    for cls in classes:
        streams = cls.streams

        # Create 25-40 students per class
        students_per_class = random.randint(25, 40)

        for i in range(students_per_class):
            # Choose random name set
            name_set = random.choice(all_names)
            first_name = random.choice(name_set['first'])
            last_name = random.choice(name_set['last'])

            # Assign to stream (distribute evenly)
            stream = streams[i % len(streams)] if streams else None

            # Student type distribution (70% day, 30% boarder)
            student_type = 'DAY' if random.random() < 0.7 else 'BOARDER'

            # Transport distance (only for day students, some use transport)
            transport_distance = None
            if student_type == 'DAY' and random.random() < 0.6:  # 60% of day students use transport
                transport_distance = random.randint(2, 25)  # 2-25 km from school

            # Meals plan
            if student_type == 'BOARDER':
                meals_plan = 'FULL'  # Boarders get full meals
            else:
                # Day students: 40% lunch only, 20% full, 40% none
                meals_choice = random.random()
                if meals_choice < 0.4:
                    meals_plan = 'LUNCH'
                elif meals_choice < 0.6:
                    meals_plan = 'FULL'
                else:
                    meals_plan = 'NONE'

            # Generate parent contact (Kenyan mobile format)
            parent_contact = f"0{random.choice([7, 1])}{random.randint(10000000, 99999999)}"

            student = Student(
                admission_no=f"SM/{admission_counter:04d}",
                first_name=first_name,
                last_name=last_name,
                class_id=cls.id,
                stream_id=stream.id if stream else None,
                student_type=student_type,
                parent_contact=parent_contact,
                transport_distance_km=transport_distance,
                meals_plan=meals_plan
            )

            db.session.add(student)
            students.append(student)
            admission_counter += 1

    db.session.commit()
    print(f"✅ Created {len(students)} students")
    return students


def create_fee_rates():
    """Create realistic Kenyan school fee rates"""
    print("💳 Creating fee rates...")

    current_year = datetime.now().year
    classes = Class.query.all()
    fee_items = {item.code: item for item in FeeItem.query.all()}

    # Kenyan school fee structure (in KES)
    fee_structure = {
        'Form 1': {
            'TUITION': {'DAY': 15000, 'BOARDER': 25000},
            'BOARDING': {'BOARDER': 20000},  # Only boarders
            'MEALS': {'DAY': 8000, 'BOARDER': 0},  # Day students meals, boarders included in boarding
            'UNIFORM': 4500,
            'BOOKS': 3500,
            'ACTIVITY': 2000,
            'EXAM': 1500,
            'DEVELOPMENT': 3000,
            'INSURANCE': 1200,
            'TRANSPORT': 50  # Per km rate
        },
        'Form 2': {
            'TUITION': {'DAY': 16000, 'BOARDER': 26000},
            'BOARDING': {'BOARDER': 21000},
            'MEALS': {'DAY': 8500, 'BOARDER': 0},
            'UNIFORM': 3000,  # Less uniform needed
            'BOOKS': 4000,
            'ACTIVITY': 2000,
            'EXAM': 1500,
            'DEVELOPMENT': 3000,
            'INSURANCE': 1200,
            'TRANSPORT': 50
        },
        'Form 3': {
            'TUITION': {'DAY': 17000, 'BOARDER': 27000},
            'BOARDING': {'BOARDER': 22000},
            'MEALS': {'DAY': 9000, 'BOARDER': 0},
            'UNIFORM': 2000,
            'BOOKS': 5000,  # More books for Form 3
            'ACTIVITY': 2500,
            'EXAM': 2000,  # Mock exams
            'DEVELOPMENT': 3000,
            'INSURANCE': 1200,
            'TRANSPORT': 50
        },
        'Form 4': {
            'TUITION': {'DAY': 18000, 'BOARDER': 28000},
            'BOARDING': {'BOARDER': 23000},
            'MEALS': {'DAY': 9500, 'BOARDER': 0},
            'UNIFORM': 1500,
            'BOOKS': 4000,
            'ACTIVITY': 3000,
            'EXAM': 3500,  # KCSE exam fees
            'DEVELOPMENT': 3000,
            'INSURANCE': 1200,
            'TRANSPORT': 50
        }
    }

    rate_count = 0

    for cls in classes:
        class_rates = fee_structure[cls.name]

        # Create rates for 3 terms
        for term in [1, 2, 3]:
            for fee_code, rate_info in class_rates.items():
                fee_item = fee_items[fee_code]

                if fee_code == 'TRANSPORT':
                    # Transport is per km
                    rate = FeeRate(
                        fee_item_id=fee_item.id,
                        class_id=cls.id,
                        term=term,
                        year=current_year,
                        rate_per_km=rate_info
                    )
                    db.session.add(rate)
                    rate_count += 1

                elif isinstance(rate_info, dict):
                    # Different rates for DAY/BOARDER
                    for student_type, amount in rate_info.items():
                        if amount > 0:  # Only create if amount > 0
                            rate = FeeRate(
                                fee_item_id=fee_item.id,
                                class_id=cls.id,
                                student_type=student_type,
                                term=term,
                                year=current_year,
                                amount=amount
                            )
                            db.session.add(rate)
                            rate_count += 1
                else:
                    # Flat rate for all students
                    rate = FeeRate(
                        fee_item_id=fee_item.id,
                        class_id=cls.id,
                        term=term,
                        year=current_year,
                        amount=rate_info
                    )
                    db.session.add(rate)
                    rate_count += 1

    db.session.commit()
    print(f"✅ Created {rate_count} fee rates")


def generate_fee_assessments(students):
    """Generate fee assessments for students"""
    print("📊 Generating fee assessments...")

    current_year = datetime.now().year
    terms = [1, 2, 3]

    assessments_created = 0

    for student in students:
        for term in terms:
            # Skip some assessments randomly to simulate real scenarios
            if random.random() < 0.05:  # 5% chance to skip
                continue

            assessment = FeeAssessment(
                student_id=student.id,
                term=term,
                year=current_year
            )
            db.session.add(assessment)
            db.session.flush()  # Get ID

            # Generate fee lines using the same logic as the app
            fee_lines = calculate_student_fees_sample(student, term, current_year)

            for fee_item_id, amount, description in fee_lines:
                line = FeeAssessmentLine(
                    assessment_id=assessment.id,
                    fee_item_id=fee_item_id,
                    amount=amount,
                    description=description
                )
                db.session.add(line)

            assessments_created += 1

    db.session.commit()
    print(f"✅ Generated {assessments_created} fee assessments")


def calculate_student_fees_sample(student, term, year):
    """Calculate fees for a student (similar to app logic)"""
    fee_lines = []

    # Get applicable fee rates
    rates = FeeRate.query.filter_by(
        class_id=student.class_id,
        term=term,
        year=year
    ).filter(
        (FeeRate.stream_id == student.stream_id) |
        (FeeRate.stream_id.is_(None))
    ).filter(
        (FeeRate.student_type == student.student_type) |
        (FeeRate.student_type.is_(None))
    ).all()

    for rate in rates:
        fee_item = rate.fee_item

        # Skip optional fees based on student settings
        if fee_item.is_optional:
            if fee_item.code == 'TRANSPORT' and not student.transport_distance_km:
                continue
            if fee_item.code == 'MEALS' and student.meals_plan == 'NONE':
                continue
            if fee_item.code == 'BOARDING' and student.student_type == 'DAY':
                continue

        # Calculate amount
        if fee_item.is_per_km and student.transport_distance_km:
            amount = rate.rate_per_km * student.transport_distance_km
            description = f"{fee_item.name} - {student.transport_distance_km}km @ KES {rate.rate_per_km}/km"
        else:
            amount = rate.amount or 0
            description = fee_item.name

        if amount > 0:
            fee_lines.append((fee_item.id, amount, description))

    return fee_lines


def create_payments(students):
    """Create realistic payment records"""
    print("💰 Creating payment records...")

    payment_modes = ['MPESA', 'BANK', 'CASH', 'CHEQUE']
    receipt_counter = 1001

    payments_created = 0

    for student in students:
        # Each student makes 2-5 payments randomly
        num_payments = random.randint(2, 5)

        for i in range(num_payments):
            # Payment amount (random between 5000-50000 KES)
            amount = random.randint(5000, 50000)

            # Payment date (random in the last 6 months)
            days_ago = random.randint(1, 180)
            payment_date = date.today() - timedelta(days=days_ago)  # Fixed: use timedelta directly

            # Payment mode weighted towards MPESA (very common in Kenya)
            mode_weights = [0.6, 0.25, 0.1, 0.05]  # MPESA, BANK, CASH, CHEQUE
            mode = random.choices(payment_modes, weights=mode_weights)[0]

            # Generate receipt number based on mode
            if mode == 'MPESA':
                receipt_no = f"MP{receipt_counter:06d}"
            elif mode == 'BANK':
                receipt_no = f"BK{receipt_counter:06d}"
            elif mode == 'CASH':
                receipt_no = f"CSH{receipt_counter:04d}"
            else:  # CHEQUE
                receipt_no = f"CHQ{receipt_counter:04d}"

            note = f"Payment from parent via {mode}"

            payment = Payment(
                student_id=student.id,
                amount=amount,
                mode=mode,
                receipt_no=receipt_no,
                note=note,
                payment_date=payment_date
            )

            db.session.add(payment)
            payments_created += 1
            receipt_counter += 1

    db.session.commit()
    print(f"✅ Created {payments_created} payment records")


def create_payment_allocations():
    """Allocate payments to fee lines (simplified version)"""
    print("🔄 Creating payment allocations...")

    payments = Payment.query.all()
    allocations_created = 0

    for payment in payments:
        # Get student's assessment lines
        assessment_lines = db.session.query(FeeAssessmentLine) \
            .join(FeeAssessment) \
            .filter(FeeAssessment.student_id == payment.student_id) \
            .limit(3).all()  # Allocate to first 3 lines

        remaining_amount = payment.amount

        for line in assessment_lines:
            if remaining_amount <= 0:
                break

            # Allocate partial or full amount
            allocation_amount = min(remaining_amount, line.amount)

            allocation = PaymentAllocation(
                payment_id=payment.id,
                assessment_line_id=line.id,
                fee_item_id=line.fee_item_id,
                amount=allocation_amount
            )

            db.session.add(allocation)
            remaining_amount -= allocation_amount
            allocations_created += 1

    db.session.commit()
    print(f"✅ Created {allocations_created} payment allocations")


def main():
    """Main function to populate the database"""
    print("🏫 KENYAN SCHOOL FEE MANAGEMENT SYSTEM - DATA INJECTION")
    print("=" * 60)

    with app.app_context():
        # Create tables if they don't exist
        db.create_all()

        # Clear existing data
        clear_database()

        # Populate data in logical order
        create_fee_items()
        classes = create_classes_and_streams()
        students = create_students(classes)
        create_fee_rates()
        generate_fee_assessments(students)
        create_payments(students)
        create_payment_allocations()

        print("\n" + "=" * 60)
        print("✅ DATABASE POPULATION COMPLETE!")
        print("\n📊 SUMMARY:")
        print(f"   📚 Classes: {Class.query.count()}")
        print(f"   📝 Streams: {Stream.query.count()}")
        print(f"   👨‍🎓 Students: {Student.query.count()}")
        print(f"   💰 Fee Items: {FeeItem.query.count()}")
        print(f"   💳 Fee Rates: {FeeRate.query.count()}")
        print(f"   📊 Assessments: {FeeAssessment.query.count()}")
        print(f"   💰 Payments: {Payment.query.count()}")
        print(f"   🔄 Allocations: {PaymentAllocation.query.count()}")
        print("\n🎉 Your school fee management system is now ready with realistic Kenyan data!")


if __name__ == "__main__":
    main()