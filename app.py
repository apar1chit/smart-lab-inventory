import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from lab_images import get_lab_item_image
import csv
import io
from flask import Response, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func
app = Flask(__name__)
# Production Config: Use environment variables if available
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-12345')
# Stick to SQLite for the simplest "free" hosting setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    # Note: Use .lower() when setting or querying usernames to maintain consistency
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False) # 'teacher', 'student', or 'developer'
    full_name = db.Column(db.String(150), nullable=True)
    roll_number = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
class Chemical(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    formula = db.Column(db.String(100), nullable=False)
    cas_number = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Float, nullable=False, default=0.0)
    unit = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    hazard_category = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(50), default='Chemicals') # New: Chemicals, Reagents, Indicators, Miscellaneous
    logs = db.relationship('UsageLog', backref='chemical', lazy=True, cascade="all, delete-orphan")

class UsageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chemical_id = db.Column(db.Integer, db.ForeignKey('chemical.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50), nullable=False, default='Usage') # Usage, Restock, Adjustment
    quantity_change = db.Column(db.Float, nullable=False) # Positive for restock, negative for usage
    purpose = db.Column(db.String(255), nullable=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Glassware(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    condition = db.Column(db.String(50), nullable=False) # Good, Damaged, etc.
    logs = db.relationship('GlasswareLog', backref='glassware', lazy=True, cascade="all, delete-orphan")

class GlasswareLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    glassware_id = db.Column(db.Integer, db.ForeignKey('glassware.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50), nullable=False) # Checked Out, Returned, Broken
    quantity = db.Column(db.Integer, nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), nullable=False) # Available, In Use, Maintenance
    logs = db.relationship('EquipmentLog', backref='equipment', lazy=True, cascade="all, delete-orphan")

class EquipmentLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50), nullable=False) # Started Using, Finished Using, Maintenance
    purpose = db.Column(db.String(255), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class DashboardConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False) # 'teacher', 'student', 'developer'
    card_id = db.Column(db.String(100), nullable=False)
    is_visible = db.Column(db.Boolean, default=True)
    position = db.Column(db.Integer, nullable=False)

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_safety = db.Column(db.Boolean, default=False)

# Create tables within application context
with app.app_context():
    db.create_all()
    # Auto-generate default accounts
    if User.query.count() == 0:
        teacher = User(username='teacher', password_hash=generate_password_hash('teacher123'), role='teacher')
        student = User(username='student', password_hash=generate_password_hash('student123'), role='student')
        dev = User(username='kartik', password_hash=generate_password_hash('kartik@lab'), role='developer')
        db.session.add(teacher)
        db.session.add(student)
        db.session.add(dev)
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- RBAC Decorators ---
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['teacher', 'developer']:
            flash('You must be logged in as a teacher or developer to perform this action.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_or_teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['student', 'teacher', 'developer']:
            flash('Access denied.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def developer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'developer':
            flash('Access Restricted: Developer Mode only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username'].lower()
    password = request.form['password']
    user = User.query.filter(func.lower(User.username) == username).first()
    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        flash(f'Logged in successfully as {user.role.capitalize()}.', 'success')
    else:
        flash('Invalid username or password.', 'danger')
    return redirect(url_for('profile') if user and user.role in ['student', 'developer'] else url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/profile')
@login_required
def profile():
    # Fetch all activity for the current user (case-insensitive username match)
    username_lower = current_user.username.lower()
    chemical_logs = UsageLog.query.filter(func.lower(UsageLog.user_name) == username_lower).order_by(UsageLog.date.desc()).all()
    glassware_logs = GlasswareLog.query.filter(func.lower(UsageLog.user_name) == username_lower).order_by(GlasswareLog.date.desc()).all()
    equipment_logs = EquipmentLog.query.filter(func.lower(UsageLog.user_name) == username_lower).order_by(EquipmentLog.date.desc()).all()
    
    # Calculate stats
    total_sessions = len(chemical_logs) + len(glassware_logs) + len(equipment_logs)
    
    # Get most used chemicals for this user
    user_most_used = db.session.query(
        Chemical.name, func.count(UsageLog.id)
    ).join(UsageLog).filter(func.lower(UsageLog.user_name) == username_lower).group_by(Chemical.name).order_by(func.count(UsageLog.id).desc()).limit(3).all()
    
    # Merge and sort all logs for the timeline
    all_logs = []
    for log in chemical_logs[:10]: all_logs.append({'type': 'chemical', 'data': log})
    for log in glassware_logs[:10]: all_logs.append({'type': 'glassware', 'data': log})
    for log in equipment_logs[:10]: all_logs.append({'type': 'equipment', 'data': log})
    
    # Sort by date
    all_logs.sort(key=lambda x: x['data'].date, reverse=True)
    all_logs = all_logs[:15] # Keep top 15
    
    return render_template('profile.html', 
                           all_logs=all_logs,
                           chemical_logs=chemical_logs,
                           glassware_logs=glassware_logs,
                           equipment_logs=equipment_logs,
                           total_sessions=total_sessions,
                           user_most_used=user_most_used)

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        current_user.full_name = request.form.get('full_name')
        current_user.email = request.form.get('email')
        current_user.phone = request.form.get('phone')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating profile: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('profile'))

@app.route('/')
def dashboard():
    total_chemicals = Chemical.query.count()
    low_stock_chemicals = Chemical.query.filter(Chemical.quantity < 50).all()
    recent_logs = UsageLog.query.order_by(UsageLog.date.desc()).limit(5).all()

    # --- New Analytical Data ---

    # 1. Upcoming Expiries (next 30 days)
    thirty_days_from_now = datetime.utcnow().date() + timedelta(days=30)
    expiring_soon = Chemical.query.filter(
        Chemical.expiry_date.between(datetime.utcnow().date(), thirty_days_from_now)
    ).order_by(Chemical.expiry_date.asc()).all()

    # 2. Equipment Utilization
    equip_stats = db.session.query(Equipment.status, func.count(Equipment.id)).group_by(Equipment.status).all()
    equip_utilization = {status: count for status, count in equip_stats}

    # 3. Most Used Items (Chemicals) - Top 5 by number of logs in last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    most_used_chems = db.session.query(
        Chemical.name, func.count(UsageLog.id).label('usage_count')
    ).join(UsageLog).filter(UsageLog.date >= thirty_days_ago).group_by(Chemical.name).order_by(func.count(UsageLog.id).desc()).limit(5).all()

    # 4. Monthly Consumption (Combined Stock Change) - Last 6 months
    consumption_data = db.session.query(
        func.strftime('%Y-%m', UsageLog.date).label('month'),
        func.abs(func.sum(UsageLog.quantity_change)).label('total_consumption')
    ).filter(UsageLog.quantity_change < 0).group_by('month').order_by('month').limit(6).all()
    
    chart_labels = [d[0] for d in consumption_data]
    chart_values = [float(d[1]) for d in consumption_data]

    # 5. Dashboard Configuration
    role = current_user.role if current_user.is_authenticated else 'student'
    all_possible_cards = [
        'announcements', 'quick_actions', 'stats_row', 'consumption_chart', 
        'equipment_utilization', 'low_stock', 'recent_usage', 'expiring_soon', 'most_used'
    ]
    if role in ['teacher', 'developer']:
        all_possible_cards.append('export_logs')
    
    configs = DashboardConfig.query.filter_by(role=role).order_by(DashboardConfig.position).all()
    existing_card_ids = [c.card_id for c in configs]
    
    # Sync missing cards (especially if new features are added)
    missing_cards = [cid for cid in all_possible_cards if cid not in existing_card_ids]
    if missing_cards:
        max_pos = max([c.position for c in configs]) if configs else 0
        for i, card_id in enumerate(missing_cards):
            new_conf = DashboardConfig(role=role, card_id=card_id, position=max_pos + i + 1, is_visible=True)
            db.session.add(new_conf)
        db.session.commit()
        configs = DashboardConfig.query.filter_by(role=role).order_by(DashboardConfig.position).all()

    return render_template('dashboard.html', 
                           total_chemicals=total_chemicals, 
                           low_stock_chemicals=low_stock_chemicals,
                           recent_logs=recent_logs,
                           expiring_soon=expiring_soon,
                           equip_utilization=equip_utilization,
                           most_used_chems=most_used_chems,
                           chart_labels=chart_labels,
                           chart_values=chart_values,
                           dashboard_configs=configs,
                           now_date=datetime.utcnow().date(),
                           announcements=Announcement.query.order_by(Announcement.date.desc()).limit(3).all())

@app.route('/announcement/add', methods=['POST'])
@teacher_required
def add_announcement():
    content = request.form.get('content')
    is_safety = 'is_safety' in request.form
    if content:
        new_ann = Announcement(content=content, author=current_user.username, is_safety=is_safety)
        db.session.add(new_ann)
        db.session.commit()
        flash('Announcement posted!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/announcement/<int:id>/delete', methods=['POST'])
@teacher_required
def delete_announcement(id):
    ann = Announcement.query.get_or_404(id)
    db.session.delete(ann)
    db.session.commit()
    flash('Announcement removed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/api/dashboard/config', methods=['POST'])
@login_required
def save_dashboard_config():
    if current_user.role not in ['teacher', 'developer']:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    role_to_edit = data.get('role', current_user.role)
    new_configs = data.get('configs', [])

    try:
        # Clear existing configs for this role
        DashboardConfig.query.filter_by(role=role_to_edit).delete()
        
        for i, conf in enumerate(new_configs):
            new_conf = DashboardConfig(
                role=role_to_edit,
                card_id=conf['card_id'],
                is_visible=conf['is_visible'],
                position=i
            )
            db.session.add(new_conf)
        
        db.session.commit()
        return jsonify({'message': 'Configuration saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/chemicals')
def chemicals():
    search_query = request.args.get('search', '')
    if search_query:
        # Case insensitive search on name or formula
        chemicals_list = Chemical.query.filter(
            db.or_(
                Chemical.name.ilike(f'%{search_query}%'),
                Chemical.formula.ilike(f'%{search_query}%')
            )
        ).all()
    else:
        chemicals_list = Chemical.query.all()
    
    # Group chemicals by category
    grouped_chemicals = {}
    for chem in chemicals_list:
        cat = chem.category or 'Chemicals'
        if cat not in grouped_chemicals:
            grouped_chemicals[cat] = []
        grouped_chemicals[cat].append(chem)
        
    return render_template('chemicals.html', grouped_chemicals=grouped_chemicals, search_query=search_query)

@app.route('/chemicals/add', methods=['GET', 'POST'])
@teacher_required
def add_chemical():
    if request.method == 'POST':
        try:
            name = request.form['name']
            formula = request.form['formula']
            cas_number = request.form.get('cas_number')
            quantity = float(request.form['quantity'])
            unit = request.form['unit']
            location = request.form['location']
            category = request.form.get('category', 'Chemicals')
            expiry_date_str = request.form.get('expiry_date')
            hazard_category = request.form.get('hazard_category')

            expiry_date = None
            if expiry_date_str:
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()

            from fill_formulas import get_formula
            if not formula or formula.strip() == "TBD":
                fetched_formula = get_formula(name)
                formula = fetched_formula if fetched_formula else name

            new_chem = Chemical(
                name=name, formula=formula, cas_number=cas_number, 
                quantity=quantity, unit=unit, location=location, 
                expiry_date=expiry_date, hazard_category=hazard_category,
                category=category
            )
            db.session.add(new_chem)
            db.session.flush() # Get ID for log

            # Create initial stock log
            initial_log = UsageLog(
                chemical_id=new_chem.id, 
                user_name=current_user.username.lower(),
                action='Initial Addition',
                quantity_change=quantity,
                purpose='Opening Stock'
            )
            db.session.add(initial_log)
            db.session.commit()
            flash('Chemical added successfully!', 'success')
            return redirect(url_for('chemicals'))
        except Exception as e:
            flash(f'Error adding chemical: {str(e)}', 'danger')
            db.session.rollback()

    # Pass existing chemical names for autocomplete
    existing_chemicals = [c.name for c in Chemical.query.with_entities(Chemical.name).distinct().all()]
    return render_template('add_chemical.html', existing_chemicals=existing_chemicals)

@app.route('/chemicals/<int:id>')
def chemical_detail(id):
    chemical = Chemical.query.get_or_404(id)
    # Get a robust fallback image from Wikimedia for natural products/mixtures
    # Using 500px for optimized speed in detail view
    fallback_image = get_lab_item_image(chemical.name, suffix=" plant specimen", width=500)
    # Get logs ordered by date descending
    logs = UsageLog.query.filter_by(chemical_id=id).order_by(UsageLog.date.desc()).all()
    return render_template('chemical_detail.html', chemical=chemical, logs=logs, fallback_image=fallback_image)

@app.route('/chemicals/<int:id>/log_usage', methods=['POST'])
@student_or_teacher_required
def log_usage(id):
    chemical = Chemical.query.get_or_404(id)
    try:
        user_name = request.form['user_name']
        quantity_used = float(request.form['quantity_used'])
        purpose = request.form['purpose']

        if quantity_used <= 0:
            flash('Quantity used must be greater than zero.', 'warning')
            return redirect(url_for('chemical_detail', id=id))

        # Atomic update to prevent race conditions
        # We deduction only if quantity is still sufficient
        result = db.session.query(Chemical).filter(
            Chemical.id == id, 
            Chemical.quantity >= quantity_used
        ).update({"quantity": Chemical.quantity - quantity_used}, synchronize_session='fetch')
        
        if result == 0:
            flash('Error: Stock might have changed or is insufficient. Please refresh and try again.', 'danger')
            db.session.rollback()
            return redirect(url_for('chemical_detail', id=id))

        # Create ledger entry
        new_log = UsageLog(
            chemical_id=id, 
            user_name=user_name.lower(), 
            action='Usage',
            quantity_change=-quantity_used, 
            purpose=purpose
        )
        db.session.add(new_log)
        db.session.commit()
        flash('Usage logged successfully.', 'success')
    except Exception as e:
        flash(f'Error logging usage: {str(e)}', 'danger')
        db.session.rollback()

    return redirect(url_for('chemical_detail', id=id))

@app.route('/chemicals/<int:id>/delete', methods=['POST'])
@teacher_required
def delete_chemical(id):
    chemical = Chemical.query.get_or_404(id)
    db.session.delete(chemical)
    db.session.commit()
    flash(f'Chemical "{chemical.name}" deleted successfully.', 'info')
    return redirect(url_for('chemicals'))

@app.route('/chemicals/<int:id>/edit', methods=['GET', 'POST'])
@teacher_required
def edit_chemical(id):
    chemical = Chemical.query.get_or_404(id)
    if request.method == 'POST':
        try:
            chemical.name = request.form['name']
            chemical.formula = request.form['formula']
            chemical.cas_number = request.form.get('cas_number')
            chemical.location = request.form['location']
            chemical.unit = request.form['unit']
            chemical.category = request.form.get('category', 'Chemicals')
            chemical.hazard_category = request.form.get('hazard_category')
            
            expiry_date_str = request.form.get('expiry_date')
            if expiry_date_str:
                chemical.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            
            db.session.commit()
            flash('Chemical updated successfully!', 'success')
            return redirect(url_for('chemical_detail', id=id))
        except Exception as e:
            flash(f'Error updating chemical: {str(e)}', 'danger')
            db.session.rollback()
            
    return render_template('edit_chemical.html', chemical=chemical)

@app.route('/chemicals/<int:id>/add_stock', methods=['POST'])
@teacher_required
def add_stock(id):
    chemical = Chemical.query.get_or_404(id)
    try:
        added_quantity = float(request.form['added_quantity'])
        if added_quantity <= 0:
            flash('Added quantity must be greater than zero.', 'warning')
        else:
            # Atomic update for restock
            db.session.query(Chemical).filter(Chemical.id == id).update(
                {"quantity": Chemical.quantity + added_quantity}, 
                synchronize_session='fetch'
            )
            
            # Create restock log
            restock_log = UsageLog(
                chemical_id=id,
                user_name=current_user.username.lower(),
                action='Restock',
                quantity_change=added_quantity,
                purpose='Manual Restock'
            )
            db.session.add(restock_log)
            db.session.commit()
            flash(f'Successfully added {added_quantity} {chemical.unit} to stock.', 'success')
    except Exception as e:
        flash(f'Error adding stock: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('chemical_detail', id=id))


@app.route('/glassware', methods=['GET', 'POST'])
def glassware():
    if request.method == 'POST':
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('You must be a teacher to add glassware.', 'danger')
            return redirect(url_for('glassware'))
            
        name = request.form['name']
        quantity = int(request.form['quantity'])
        condition = request.form['condition']
        
        new_glass = Glassware(name=name, quantity=quantity, condition=condition)
        db.session.add(new_glass)
        db.session.commit()
        flash('Glassware added successfully.', 'success')
        return redirect(url_for('glassware'))
            
    items = Glassware.query.all()
    for item in items:
        item.image_url = get_lab_item_image(item.name, width=300)
    standard_glassware = ["Beaker", "Erlenmeyer Flask", "Test Tube", "Pipette", "Burette", "Petri Dish", "Graduated Cylinder", "Volumetric Flask", "Watch Glass", "Crucible", "Funnel", "Stirring Rod"]
    return render_template('glassware.html', items=items, standard_glassware=standard_glassware)

@app.route('/glassware/<int:id>/delete', methods=['POST'])
@teacher_required
def delete_glassware(id):
    item = Glassware.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash(f'Glassware "{item.name}" deleted.', 'info')
    return redirect(url_for('glassware'))

@app.route('/glassware/<int:id>/edit', methods=['GET', 'POST'])
@teacher_required
def edit_glassware(id):
    item = Glassware.query.get_or_404(id)
    if request.method == 'POST':
        try:
            item.name = request.form['name']
            item.quantity = float(request.form['quantity'])
            item.condition = request.form['condition']
            db.session.commit()
            flash('Glassware updated.', 'success')
            return redirect(url_for('glassware_detail', id=id))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('edit_glassware.html', item=item)

@app.route('/glassware/<int:id>')
def glassware_detail(id):
    item = Glassware.query.get_or_404(id)
    # Using 500px for detail view
    item.image_url = get_lab_item_image(item.name, width=500)
    logs = GlasswareLog.query.filter_by(glassware_id=id).order_by(GlasswareLog.date.desc()).all()
    return render_template('glassware_detail.html', item=item, logs=logs)

@app.route('/glassware/<int:id>/log_usage', methods=['POST'])
@student_or_teacher_required
def log_glassware_usage(id):
    item = Glassware.query.get_or_404(id)
    try:
        user_name = request.form['user_name']
        action = request.form['action']
        quantity = int(request.form['quantity'])
        purpose = request.form['purpose']

        # Adjust quantity based on action
        if action == 'Checked Out':
            if quantity > item.quantity:
                flash('Cannot check out more than available quantity!', 'danger')
                return redirect(url_for('glassware_detail', id=id))
            item.quantity -= quantity
        elif action == 'Returned':
            item.quantity += quantity
        elif action == 'Broken':
            # Broken items just leave the system or reduce available stock if they were already in stock
            # We assume they break it while using it, so it's already deducted from available stock. 
            pass

        new_log = GlasswareLog(glassware_id=id, user_name=user_name.lower(), action=action, quantity=quantity, purpose=purpose)
        db.session.add(new_log)
        db.session.commit()
        flash('Glassware log added successfully.', 'success')
    except Exception as e:
        flash(f'Error logging glassware: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('glassware_detail', id=id))

@app.route('/bulk_update', methods=['GET', 'POST'])
@teacher_required
def bulk_update():
    if request.method == 'POST':
        try:
            # Handle Chemicals
            chem_ids = request.form.getlist('chemical_ids')
            for cid in chem_ids:
                chem = Chemical.query.get(int(cid))
                new_qty = float(request.form.get(f'qty_chem_{cid}'))
                new_loc = request.form.get(f'loc_chem_{cid}')
                
                changed = False
                if new_qty != chem.quantity:
                    diff = new_qty - chem.quantity
                    chem.quantity = new_qty
                    changed = True
                
                if new_loc != chem.location:
                    chem.location = new_loc
                    changed = True
                
                new_unit = request.form.get(f'unit_chem_{cid}')
                if new_unit != chem.unit:
                    chem.unit = new_unit
                    changed = True
                
                if changed:
                    # Log the adjustment (both qty and location)
                    log = UsageLog(
                        chemical_id=chem.id,
                        user_name=current_user.username.lower(),
                        action='Adjustment',
                        quantity_change=new_qty - chem.quantity if 'diff' not in locals() else diff,
                        purpose=f'Bulk Stock Take ({new_loc})'
                    )
                    db.session.add(log)
            
            db.session.commit()
            flash('Inventory updated successfully!', 'success')
            return redirect(url_for('chemicals'))
        except Exception as e:
            flash(f'Error during bulk update: {str(e)}', 'danger')
            db.session.rollback()
            
    chemicals = Chemical.query.order_by(Chemical.name).all()
    return render_template('bulk_update.html', chemicals=chemicals)

@app.route('/equipment', methods=['GET', 'POST'])
def equipment():
    if request.method == 'POST':
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('You must be a teacher to add equipment.', 'danger')
            return redirect(url_for('equipment'))
            
        name = request.form['name']
        status = request.form['status']
        
        new_equip = Equipment(name=name, status=status)
        db.session.add(new_equip)
        db.session.commit()
        flash('Equipment added successfully.', 'success')
        return redirect(url_for('equipment'))
        
    items = Equipment.query.all()
    for item in items:
        item.image_url = get_lab_item_image(item.name, width=300)
    standard_equipment = ["Microscope", "Centrifuge", "Bunsen Burner", "Spectrophotometer", "Hot Plate", "Magnetic Stirrer", "Analytical Balance", "pH Meter", "Incubator", "Autoclave", "Fume Hood", "Water Bath"]
    return render_template('equipment.html', items=items, standard_equipment=standard_equipment)

@app.route('/equipment/<int:id>')
def equipment_detail(id):
    item = Equipment.query.get_or_404(id)
    # Using 500px for detail view
    item.image_url = get_lab_item_image(item.name, width=500)
    logs = EquipmentLog.query.filter_by(equipment_id=id).order_by(EquipmentLog.date.desc()).all()
    return render_template('equipment_detail.html', item=item, logs=logs)

@app.route('/equipment/<int:id>/log_usage', methods=['POST'])
@student_or_teacher_required
def log_equipment_usage(id):
    item = Equipment.query.get_or_404(id)
    try:
        user_name = request.form['user_name']
        action = request.form['action']
        purpose = request.form['purpose']

        if action == 'Started Using':
            item.status = 'In Use'
        elif action == 'Finished Using':
            item.status = 'Available'
        elif action == 'Reported Issue':
            item.status = 'Maintenance'

        new_log = EquipmentLog(equipment_id=id, user_name=user_name.lower(), action=action, purpose=purpose)
        db.session.add(new_log)
        db.session.commit()
        flash('Equipment log added successfully.', 'success')
    except Exception as e:
        flash(f'Error logging equipment: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('equipment_detail', id=id))

@app.route('/equipment/<int:id>/delete', methods=['POST'])
@teacher_required
def delete_equipment(id):
    item = Equipment.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash(f'Equipment "{item.name}" deleted.', 'info')
    return redirect(url_for('equipment'))

@app.route('/equipment/<int:id>/edit', methods=['GET', 'POST'])
@teacher_required
def edit_equipment(id):
    item = Equipment.query.get_or_404(id)
    if request.method == 'POST':
        try:
            item.name = request.form['name']
            item.status = request.form['status']
            db.session.commit()
            flash('Equipment updated.', 'success')
            return redirect(url_for('equipment_detail', id=id))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            db.session.rollback()
    return render_template('edit_equipment.html', item=item)

@app.route('/export/logs', methods=['POST'])
@teacher_required
def export_logs():
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    log_type = request.form.get('log_type')
    
    # Convert string dates to datetime objects
    start = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.min
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.max
    # Set end to the very end of the day
    end = end.replace(hour=23, minute=59, second=59)

    output = io.StringIO()
    writer = csv.writer(output)
    
    if log_type == 'chemicals':
        writer.writerow(['Date', 'Chemical Name', 'User', 'Action', 'Change', 'Unit', 'Purpose'])
        logs = UsageLog.query.filter(UsageLog.date.between(start, end)).order_by(UsageLog.date.desc()).all()
        for log in logs:
            writer.writerow([
                log.date.strftime('%Y-%m-%d %H:%M'), 
                log.chemical.name, 
                log.user_name, 
                log.action,
                log.quantity_change,
                log.chemical.unit,
                log.purpose
            ])
    
    elif log_type == 'glassware':
        writer.writerow(['Date', 'Glassware Name', 'User', 'Action', 'Quantity', 'Purpose'])
        logs = GlasswareLog.query.filter(GlasswareLog.date.between(start, end)).order_by(GlasswareLog.date.desc()).all()
        for log in logs:
            writer.writerow([log.date.strftime('%Y-%m-%d %H:%M'), log.glassware.name, log.user_name, log.action, log.quantity, log.purpose])
            
    elif log_type == 'equipment':
        writer.writerow(['Date', 'Equipment Name', 'User', 'Action', 'Usage Duration (min)', 'Purpose'])
        logs = EquipmentLog.query.filter(EquipmentLog.date.between(start, end)).order_by(EquipmentLog.date.desc()).all()
        for log in logs:
            writer.writerow([log.date.strftime('%Y-%m-%d %H:%M'), log.equipment.name, log.user_name, log.action, log.usage_duration or 'N/A', log.purpose])

    output.seek(0)
    filename = f"lab_logs_{log_type}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route('/developer/dashboard')
@developer_required
def developer_dashboard():
    users = User.query.all()
    chemical_logs = UsageLog.query.order_by(UsageLog.date.desc()).all()
    glassware_logs = GlasswareLog.query.order_by(GlasswareLog.date.desc()).all()
    equipment_logs = EquipmentLog.query.order_by(EquipmentLog.date.desc()).all()
    return render_template('developer_dashboard.html', 
                           users=users, 
                           chemical_logs=chemical_logs,
                           glassware_logs=glassware_logs,
                           equipment_logs=equipment_logs)

@app.route('/developer/user/add', methods=['POST'])
@developer_required
def dev_add_user():
    username = request.form['username'].lower()
    password = request.form['password']
    role = request.form['role']
    if User.query.filter_by(username=username).first():
        flash('Username already exists!', 'danger')
    else:
        new_user = User(username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(new_user)
        db.session.commit()
        flash(f'User {username} added.', 'success')
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/user/<int:id>/edit', methods=['POST'])
@developer_required
def dev_edit_user(id):
    user = User.query.get_or_404(id)
    new_password = request.form.get('password')
    new_role = request.form.get('role')
    full_name = request.form.get('full_name')
    roll_number = request.form.get('roll_number')
    email = request.form.get('email')
    phone = request.form.get('phone')
    
    if new_password:
        user.password_hash = generate_password_hash(new_password)
    if new_role:
        user.role = new_role
    
    user.full_name = full_name
    user.roll_number = roll_number
    user.email = email
    user.phone = phone
    db.session.commit()
    flash(f'User {user.username} updated.', 'success')
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/user/<int:id>/delete', methods=['POST'])
@developer_required
def dev_delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Cannot delete yourself!', 'danger')
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'User {user.username} deleted.', 'info')
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/logs/reset', methods=['POST'])
@developer_required
def dev_reset_logs():
    UsageLog.query.delete()
    GlasswareLog.query.delete()
    EquipmentLog.query.delete()
    db.session.commit()
    flash('All inventory logs have been reset.', 'warning')
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/log/<type>/<int:id>/delete', methods=['POST'])
@developer_required
def dev_delete_log(type, id):
    if type == 'chemical':
        log = UsageLog.query.get_or_404(id)
    elif type == 'glassware':
        log = GlasswareLog.query.get_or_404(id)
    else:
        log = EquipmentLog.query.get_or_404(id)
    
    db.session.delete(log)
    db.session.commit()
    flash('Log entry deleted.', 'info')
    return redirect(url_for('developer_dashboard'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
