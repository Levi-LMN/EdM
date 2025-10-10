"""Expense management routes"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func, desc, extract
from models import db, Expense, ExpenseCategory, PaymentMode

expenses_bp = Blueprint('expenses', __name__)


@expenses_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    category_id = request.args.get('category_id', type=int)

    query = Expense.query
    if category_id:
        query = query.filter_by(category_id=category_id)

    expenses = query.order_by(desc(Expense.expense_date)) \
        .paginate(page=page, per_page=per_page, error_out=False)

    categories = ExpenseCategory.query.filter_by(is_active=True).all()

    # Calculate statistics
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year

    base_query = Expense.query
    if category_id:
        base_query = base_query.filter_by(category_id=category_id)

    this_month_total = base_query.filter(
        extract('month', Expense.expense_date) == current_month,
        extract('year', Expense.expense_date) == current_year
    ).with_entities(func.sum(Expense.amount)).scalar() or 0

    this_year_total = base_query.filter(
        extract('year', Expense.expense_date) == current_year
    ).with_entities(func.sum(Expense.amount)).scalar() or 0

    months_passed = current_month
    average_per_month = this_year_total / months_passed if months_passed > 0 and this_year_total > 0 else 0

    total_expenses = base_query.with_entities(func.sum(Expense.amount)).scalar() or 0

    category_breakdown = db.session.query(
        ExpenseCategory.name,
        ExpenseCategory.code,
        func.sum(Expense.amount).label('total')
    ).join(Expense).filter(
        extract('month', Expense.expense_date) == current_month,
        extract('year', Expense.expense_date) == current_year
    ).group_by(ExpenseCategory.id).all()

    top_category = category_breakdown[0] if category_breakdown else None

    last_month = current_month - 1 if current_month > 1 else 12
    last_month_year = current_year if current_month > 1 else current_year - 1

    last_month_total = base_query.filter(
        extract('month', Expense.expense_date) == last_month,
        extract('year', Expense.expense_date) == last_month_year
    ).with_entities(func.sum(Expense.amount)).scalar() or 0

    if last_month_total > 0:
        month_change_percent = ((float(this_month_total) - float(last_month_total)) / float(last_month_total)) * 100
    else:
        month_change_percent = 100 if this_month_total > 0 else 0

    return render_template('expenses/list.html',
                           expenses=expenses,
                           categories=categories,
                           selected_category=category_id,
                           this_month_total=float(this_month_total),
                           average_per_month=float(average_per_month),
                           total_expenses=float(total_expenses),
                           category_breakdown=category_breakdown,
                           top_category=top_category,
                           month_change_percent=month_change_percent,
                           current_month_name=current_date.strftime('%B'),
                           current_year=current_year)


@expenses_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        expense = Expense(
            category_id=int(request.form['category_id']),
            description=request.form['description'],
            amount=Decimal(request.form['amount']),
            expense_date=datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
            payment_method=PaymentMode(request.form['payment_method']) if request.form['payment_method'] else None,
            reference_number=request.form.get('reference_number'),
            supplier_name=request.form.get('supplier_name'),
            approved_by=request.form.get('approved_by'),
            notes=request.form.get('notes'),
            created_by=current_user.id
        )

        db.session.add(expense)
        db.session.commit()
        flash('Expense recorded successfully', 'success')
        return redirect(url_for('expenses.list'))

    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    return render_template('expenses/add.html', categories=categories)


@expenses_bp.route('/category/add', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'POST':
        category = ExpenseCategory(
            name=request.form['name'],
            code=request.form['code'].upper(),
            description=request.form.get('description')
        )

        db.session.add(category)
        db.session.commit()
        flash('Expense category added successfully', 'success')
        return redirect(url_for('expenses.list'))

    return render_template('expenses/add_category.html')