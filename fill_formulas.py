import requests

def get_formula(chemical_name):
    """
    Fetches the chemical formula from PubChem API given a chemical name.
    """
    try:
        # PubChem REST API endpoint for fetching molecular formula by name
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{chemical_name}/property/MolecularFormula/JSON"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            properties = data.get('PropertyTable', {}).get('Properties', [])
            if properties:
                return properties[0].get('MolecularFormula')
    except Exception as e:
        pass
    return None
