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
from flask import Response
from datetime import datetime

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
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False) # 'teacher' or 'student'
    full_name = db.Column(db.String(150), nullable=True)
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
    quantity_used = db.Column(db.Float, nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
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

# Create tables within application context
with app.app_context():
    db.create_all()
    # Auto-generate default accounts
    if User.query.count() == 0:
        teacher = User(username='teacher', password_hash=generate_password_hash('teacher123'), role='teacher')
        student = User(username='student', password_hash=generate_password_hash('student123'), role='student')
        db.session.add(teacher)
        db.session.add(student)
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- RBAC Decorators ---
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash('You must be logged in as a teacher to perform this action.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_or_teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('You must be logged in to perform this action.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password')
    user = User.query.filter(User.username.ilike(username)).first()
    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        flash(f'Logged in successfully as {user.role.capitalize()}.', 'success')
    else:
        flash('Invalid username or password.', 'danger')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/')
def dashboard():
    total_chemicals = Chemical.query.count()
    # Define "low stock" as quantity < 50 for simplicity (could be a DB field later)
    low_stock_chemicals = Chemical.query.filter(Chemical.quantity < 50).all()
    # Get the latest 5 usage logs
    recent_logs = UsageLog.query.order_by(UsageLog.date.desc()).limit(5).all()
    return render_template('dashboard.html', 
                           total_chemicals=total_chemicals, 
                           low_stock_chemicals=low_stock_chemicals,
                           recent_logs=recent_logs)

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

        if quantity_used > chemical.quantity:
            flash('Cannot use more than the available quantity!', 'danger')
            return redirect(url_for('chemical_detail', id=id))

        # Update chemical quantity
        chemical.quantity -= quantity_used
        
        # Create log entry
        new_log = UsageLog(
            chemical_id=id, user_name=user_name, 
            quantity_used=quantity_used, purpose=purpose
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
            chemical.quantity += added_quantity
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

        new_log = GlasswareLog(glassware_id=id, user_name=user_name, action=action, quantity=quantity, purpose=purpose)
        db.session.add(new_log)
        db.session.commit()
        flash('Glassware log added successfully.', 'success')
    except Exception as e:
        flash(f'Error logging glassware: {str(e)}', 'danger')
        db.session.rollback()
    return redirect(url_for('glassware_detail', id=id))

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

        new_log = EquipmentLog(equipment_id=id, user_name=user_name, action=action, purpose=purpose)
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
        writer.writerow(['Date', 'Chemical Name', 'User', 'Quantity Used', 'Purpose'])
        logs = UsageLog.query.filter(UsageLog.date.between(start, end)).order_by(UsageLog.date.desc()).all()
        for log in logs:
            writer.writerow([log.date.strftime('%Y-%m-%d %H:%M'), log.chemical.name, log.user_name, f"{log.quantity_used} {log.chemical.unit}", log.purpose])
    
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
