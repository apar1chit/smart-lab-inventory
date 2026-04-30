import requests
import urllib.parse
from functools import lru_cache

# Curated File Names on Wikimedia Commons for 100% accuracy on standard items
STANDARD_FILES = {
    "beaker": "File:Beaker_hg.jpg",
    "erlenmeyer flask": "File:Erlenmeyer_flask_hg.jpg",
    "test tube": "File:Test_tube_01.jpg",
    "pipette": "File:Pipettes.jpg",
    "burette": "File:Burette_titration.jpg",
    "petri dish": "File:Petri_dish.jpg",
    "graduated cylinder": "File:Graduated_cylinder.jpg",
    "volumetric flask": "File:Volumetric_flask.jpg",
    "watch glass": "File:Watch_glass.JPG",
    "crucible": "File:Porcelain_crucible.jpg",
    "funnel": "File:Glass_funnel.jpg",
    "stirring rod": "File:Stirring_rod.jpg",
    "microscope": "File:Optical_microscope_nikon_alphaphot.jpg",
    "centrifuge": "File:Eppendorf_centrifuge_5417_C.jpg"
}

# The absolute final fallback if even the dynamic search fails
FALLBACK_ICON = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiM0YTU1NjgiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNOSAzdjhoNi02LTZ6TTUgMjFsNy0xMiA3IDEyaC0xNHoiLz48L3N2Zz4="

@lru_cache(maxsize=128)
def get_wikimedia_url(file_title, width=150):
    """
    Fetches the direct thumbnail URL for a Wikimedia File title at a specific width.
    This significantly boosts page loading speed by reducing resolution.
    """
    try:
        url = (
            "https://commons.wikimedia.org/w/api.php?"
            "action=query&prop=imageinfo&iiprop=url&"
            f"iiurlwidth={width}&"
            f"titles={urllib.parse.quote(file_title)}&format=json"
        )
        headers = {'User-Agent': 'SmartLabInventory/1.0 (lab-admin@example.com)'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            pages = data.get('query', {}).get('pages', {})
            for page_id in pages:
                if 'imageinfo' in pages[page_id]:
                    # Use 'thumburl' for optimized resolution
                    info = pages[page_id]['imageinfo'][0]
                    return info.get('thumburl') or info.get('url')
    except:
        pass
    return None

@lru_cache(maxsize=128)
def search_wikimedia_dynamic(name, suffix="", width=150):
    """Performs a dynamic search on Wikimedia Commons and returns an optimized thumbnail."""
    try:
        search_query = f"{name}{suffix}"
        encoded_query = urllib.parse.quote(search_query)
        url = (
            "https://commons.wikimedia.org/w/api.php?"
            "action=query&generator=search&"
            f"gsrsearch={encoded_query}&gsrnamespace=6&"
            f"prop=imageinfo&iiprop=url&iiurlwidth={width}&gsrlimit=1&format=json"
        )
        headers = {'User-Agent': 'SmartLabInventory/1.0 (lab-admin@example.com)'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            pages = data.get('query', {}).get('pages', {})
            for page_id in pages:
                if 'imageinfo' in pages[page_id]:
                    info = pages[page_id]['imageinfo'][0]
                    return info.get('thumburl') or info.get('url')
    except:
        pass
    return None

@lru_cache(maxsize=128)
def get_lab_item_image(name, suffix=" laboratory", width=150):
    """
    Finds a direct, high-quality, and OPTIMIZED image URL for a lab item.
    Uses a multi-stage approach for maximum robustness.
    """
    clean_name = name.lower().strip()
    
    # 1. Stage 1: Curated Filenames (Highest Accuracy)
    target_file = None
    if clean_name in STANDARD_FILES:
        target_file = STANDARD_FILES[clean_name]
    else:
        for key, filename in STANDARD_FILES.items():
            if key in clean_name:
                target_file = filename
                break
    
    if target_file:
        url = get_wikimedia_url(target_file, width=width)
        if url: return url

    # 2. Stage 2: Specific Search (The provided suffix, e.g., " laboratory")
    url = search_wikimedia_dynamic(name, suffix, width=width)
    if url: return url

    # 3. Stage 3: Broad Search (Just the name, often best for natural products)
    url = search_wikimedia_dynamic(name, "", width=width)
    if url: return url

    # 4. Final Stage: Very Broad Search (First part of the name only)
    if " " in name:
        broad_name = name.split(" ")[0]
        url = search_wikimedia_dynamic(broad_name, "", width=width)
        if url: return url

    # Final Fallback
    return FALLBACK_ICON
