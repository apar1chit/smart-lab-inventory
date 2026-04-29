from app import app, db, Chemical

def get_suggested_unit(name):
    name = name.lower()
    liquids = [
        'acid', 'ethanol', 'methanol', 'acetone', 'chloroform', 'ether', 
        'water', 'solution', 'soln', 'peroxide', 'formaldehyde', 'benzene',
        'toluene', 'xylene', 'alcohol', 'reagent', 'indicator', 'liquid'
    ]
    
    # Exceptions that are commonly solids even if they contain 'acid' in name (less common in school labs but possible)
    # But usually, if it says 'Acid' in a lab context, it's a solution or liquid.
    
    for l in liquids:
        if l in name:
            return 'mL'
    return 'g'

with app.app_context():
    chemicals = Chemical.query.all()
    count = 0
    for chem in chemicals:
        old_unit = chem.unit
        new_unit = get_suggested_unit(chem.name)
        if old_unit != new_unit:
            chem.unit = new_unit
            print(f"Updated {chem.name}: {old_unit} -> {new_unit}")
            count += 1
    
    db.session.commit()
    print(f"Standardization complete. Updated {count} chemicals.")
