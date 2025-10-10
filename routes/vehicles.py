"""Vehicle management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from decimal import Decimal
from models import db, Vehicle, Student, FeeItem, FeeRate, AcademicYear

vehicles_bp = Blueprint('vehicles', __name__)


@vehicles_bp.route('/')
@login_required
def list():
    vehicles = Vehicle.query.all()
    return render_template('vehicles/list.html', vehicles=vehicles)


@vehicles_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        vehicle = Vehicle(
            registration_number=request.form['registration_number'],
            make=request.form['make'],
            model=request.form['model'],
            capacity=int(request.form['capacity']) if request.form['capacity'] else None,
            driver_name=request.form['driver_name'],
            driver_phone=request.form['driver_phone'],
            route_description=request.form['route_description']
        )

        db.session.add(vehicle)
        db.session.commit()
        flash('Vehicle added successfully', 'success')
        return redirect(url_for('vehicles.list'))

    return render_template('vehicles/add.html')


@vehicles_bp.route('/<int:vehicle_id>')
@login_required
def detail(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    students = Student.query.filter_by(vehicle_id=vehicle_id, is_active=True).all()

    total_revenue = 0
    for student in students:
        if student.transport_distance_km:
            current_year = AcademicYear.query.filter_by(is_current=True).first()
            if current_year:
                transport_fee = FeeItem.query.filter_by(code='TRANSPORT').first()
                if transport_fee:
                    rate = FeeRate.query.filter_by(
                        fee_item_id=transport_fee.id,
                        year=current_year.year
                    ).first()
                    if rate and rate.rate_per_km:
                        total_revenue += float(student.transport_distance_km * rate.rate_per_km * 3)

    return render_template('vehicles/detail.html',
                           vehicle=vehicle,
                           students=students,
                           total_revenue=total_revenue)