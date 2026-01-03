from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import secrets
import string
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from flask import send_file
import csv

#git testing(sujal)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dayflow-secret-key-2025')

# PostgreSQL Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.environ.get('DB_USER', 'postgres')}:"
    f"{os.environ.get('DB_PASSWORD', '8511')}@"
    f"{os.environ.get('DB_HOST', 'localhost')}:"
    f"{os.environ.get('DB_PORT', 5432)}/"
    f"{os.environ.get('DB_NAME', 'dayflow')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ======================== DATABASE MODELS ========================
class Leave(db.Model):
    __tablename__ = 'leaves'

    id = db.Column(db.Integer, primary_key=True)
    
    # Relationships to User (defined as string 'User' so it works before User class exists)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester = db.relationship('User', foreign_keys=[user_id], backref='my_leaves')

    leave_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(50), default='Pending')
    
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approver = db.relationship('User', foreign_keys=[approved_by])
    
    number_of_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(db.Model):
    """User model for Admin, HR Officer, Payroll Officer, and Employees"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    
    # --- CHANGED: Split Name for new Signup ---
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    
    # --- Authentication ---
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False) # Renamed to match your signup logic
    
    # --- Contact ---
    phone = db.Column(db.String(20))
    
    # --- Job Details ---
    role = db.Column(db.String(50), default='employee')  
    department = db.Column(db.String(100))
    job_position = db.Column(db.String(100))
    job_title = db.Column(db.String(100))
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # --- Contract & Location ---
    employment_type = db.Column(db.String(50))  # Full-time, Part-time
    contract_type = db.Column(db.String(50))    # Permanent, Contract
    work_address = db.Column(db.String(255))
    work_location = db.Column(db.String(100))
    time_zone = db.Column(db.String(50))
    
    # --- Payroll ---
    wage_type = db.Column(db.String(50))        # Fixed Wage, Hourly
    wage = db.Column(db.Float)                 # Monthly/Hourly wage
    basic_salary = db.Column(db.Float)
    
    # --- Shifts ---
    working_hours = db.Column(db.String(50))   # e.g., "40 hours/week"
    shift_time = db.Column(db.String(100))     # e.g., "9:00 AM - 6:00 PM"
    
    # --- Personal Info ---
    date_of_joining = db.Column(db.Date)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    nationality = db.Column(db.String(100))
    
    # --- Emergency Contact ---
    emergency_contact_name = db.Column(db.String(255))
    emergency_contact_relation = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    
    # --- System Fields ---
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Relationships ---
    # Note: Ensure 'Leave', 'Payslip', 'Attendance' models are defined in your file
    leaves = db.relationship('Leave', backref='employee', lazy=True, foreign_keys='[Leave.user_id]', cascade='save-update')
    payslips = db.relationship('Payslip', backref='employee', lazy=True, cascade='save-update')
    attendances = db.relationship('Attendance', backref='employee', lazy=True, cascade='save-update')

    # --- HELPER: Makes 'user.full_name' work in templates ---
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    # --- Password Methods ---
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Attendance(db.Model):
    """Attendance tracking model"""
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    attendance_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    
    # Changed to DateTime to make math easier (e.g., 9:00 AM to 5:00 PM)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    
    status = db.Column(db.String(50))  # Present, Absent, Late
    working_hours = db.Column(db.Float)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Ensure one record per user per day
    __table_args__ = (db.UniqueConstraint('user_id', 'attendance_date', name='uq_user_date'),)



class LeaveBalance(db.Model):
    """Leave balance tracking"""
    __tablename__ = 'leave_balance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)
    total_days = db.Column(db.Integer)
    used_days = db.Column(db.Integer, default=0)
    remaining_days = db.Column(db.Integer)
    year = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'leave_type', 'year', name='uq_user_leave_year'),)

class Payslip(db.Model):
    """Payslip model"""
    __tablename__ = 'payslips'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payroll_month = db.Column(db.Date, nullable=False)
    basic_salary = db.Column(db.Float)
    hra = db.Column(db.Float)  # House Rent Allowance
    da = db.Column(db.Float)   # Dearness Allowance
    gross_earnings = db.Column(db.Float)
    pf = db.Column(db.Float)   # Provident Fund
    income_tax = db.Column(db.Float)
    professional_tax = db.Column(db.Float)
    net_salary = db.Column(db.Float)
    status = db.Column(db.String(50), default='Draft')  # Draft, Processed
    processed_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'payroll_month', name='uq_user_month'),)

class SalaryAdjustment(db.Model):
    """Salary adjustment history"""
    __tablename__ = 'salary_adjustments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adjustment_date = db.Column(db.Date, nullable=False)
    old_salary = db.Column(db.Float)
    new_salary = db.Column(db.Float)
    reason = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # FIX: Add backref=False or custom backref names
    employee = db.relationship('User', foreign_keys=[user_id], backref='adjusted_salaries')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_adjustments')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Badge(db.Model):
    """Badges and awards model"""
    __tablename__ = 'badges'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_name = db.Column(db.String(100))
    badge_description = db.Column(db.Text)
    awarded_date = db.Column(db.Date)
    awarded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Certification(db.Model):
    """Employee certifications"""
    __tablename__ = 'certifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    certification_name = db.Column(db.String(255))
    issuing_organization = db.Column(db.String(255))
    issue_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date)
    credential_id = db.Column(db.String(100))
    credential_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    """Reports storage"""
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50))  # Attendance, Payroll, Employee, Leave, Overtime, Performance
    report_data = db.Column(db.JSON)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

# ======================== UTILITY FUNCTIONS ========================



def generate_temp_password(length=12):
    """Generate secure temporary password"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$') for _ in range(length))

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """Decorator for role-based access"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = User.query.get(session.get('user_id'))
            
            # Fix 1: Handle case sensitivity and list wrapping
            # Flatten roles if a list was passed accidentally (e.g. ['admin'])
            required_roles = []
            for r in roles:
                if isinstance(r, list):
                    required_roles.extend([x.lower() for x in r])
                else:
                    required_roles.append(r.lower())
            
            # Fix 2: Check role (case-insensitive)
            if not user or user.role.lower() not in required_roles:
                # Fix 3: Remove ', 403' so the browser follows the redirect properly
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('login'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ======================== ROUTES ========================

@app.route('/')
def index():
    return redirect(url_for('login'))

# --- Authentication Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 1. Get EMAIL and PASSWORD from the form (not login_id)
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 2. Query user by EMAIL
        user = User.query.filter_by(email=email, is_active=True).first()
        
        # 3. Verify User and Password
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['user_name'] = user.full_name # Store name for the dashboard
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid email or password")
            
    return render_template('login.html')

# Add this to app.py

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # 1. Get data matching your HTML form exactly
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        role = request.form.get('role')

        # 2. Check if email already exists
        if User.query.filter_by(email=email).first():
            return render_template('signup.html', error="Email already exists")

        # 3. Create User (Removing the Confirm Password check)
        new_user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role=role.lower() if role else 'employee', # Safety check: default to employee if empty
            created_at=datetime.now()
        )

        db.session.add(new_user)
        db.session.commit()

        # Success!
        return redirect(url_for('login', success="Account created! Please login."))

    return render_template('signup.html')

@app.route('/register')
def register():
    """Redirect to signup page"""
    return redirect(url_for('signup'))

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('login'))

# --- Dashboard Routes ---

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session.get('user_id'))
    today = datetime.now().date()
    
    # Total Employees
    total_employees = User.query.filter_by(role='EMPLOYEE', is_active=True).count()
    
    # Attendance Rate (percentage of present today)
    total_present_today = Attendance.query.filter_by(attendance_date=today, status='Present').count()
    total_employees_active = User.query.filter_by(is_active=True).count()
    attendance_rate = round((total_present_today / total_employees_active * 100) if total_employees_active > 0 else 0)
    
    # Pending Leaves
    pending_leaves = Leave.query.filter_by(status='Pending').count()
    
    # Total Payroll (sum of all net salaries for current month)
    current_month = today.replace(day=1)
    total_payroll = db.session.query(db.func.sum(Payslip.net_salary)).filter_by(payroll_month=current_month).scalar() or 0
    total_payroll = round(total_payroll / 100000, 1)  # Convert to Lakhs
    
    # Today's Attendance (for logged-in employee)
    today_attendance = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
    
    # Leave Balance
    leave_balance = LeaveBalance.query.filter_by(user_id=user.id, year=today.year).all()
    
    # Recent Payslips
    recent_payslips = Payslip.query.filter_by(user_id=user.id).order_by(Payslip.payroll_month.desc()).limit(3).all()
    
    return render_template('dashboard.html', 
                         user=user,
                         total_employees=total_employees,
                         attendance_rate=attendance_rate,
                         pending_leaves=pending_leaves,
                         total_payroll=total_payroll,
                         today_attendance=today_attendance,
                         leave_balance=leave_balance,
                         recent_payslips=recent_payslips)



def init_db():
    """Create all database tables"""
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
