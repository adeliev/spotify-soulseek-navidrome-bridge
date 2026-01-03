import os
import json
import logging
import re
from mutagen.mp3 import MP3
from mutagen.id3 import ID3

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LIBRARY_PATHS = ["/music/Music", "/music/Музыка"]
OUTPUT_FILE = "/music/library_index.json"

def clean_string(text):
    """Remove common clutter from strings like (Radio Edit), (Ft. ...), etc."""
    if not text:
        return ""
    
    # 1. Remove text inside brackets/parentheses containing keywords
    # Use word boundaries (\b) to prevent matching parts of words (e.g. 'ver' in 'Cover')
    keywords = r"\bradio\b|\bedit\b|\bmix\b|\bremix\b|\bremaster\b|\bfeat\b|\bft\.?|\bfeature\b|\bextended\b|\bclub\b|\boriginal\b|\bvocal\b|\bversion\b"
    
    # Use hex codes to avoid backslash/bracket escaping issues
    # \x29 = )
    # \x5D = ]
    # [^\x29\x5D] means "not ) or ]"
    pattern = r'\s*[(\[][^\x29\x5D]*?(?:' + keywords + r')[^\x29\x5D]*?[)\x5D]'
    
    prev_text = None
    while text != prev_text:
        prev_text = text
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # 2. Remove trailing " - Radio Edit" etc patterns (no brackets)
    text = re.sub(r'\s*-\s*.*?(?:' + keywords + r').*?$', '', text, flags=re.IGNORECASE)

    # 3. Remove "Ft. Artist" (no brackets)
    text = re.sub(r'\s+(?:feat|ft\.|feature)\.?\s+.*$', '', text, flags=re.IGNORECASE)

    return text.strip()

def scan_library():
    logger.info("Starting library scan...")
    library_index = {}
    
    for library_path in LIBRARY_PATHS:
        if not os.path.exists(library_path):
            logger.warning(f"Path not found: {library_path}")
            continue
            
        for root, dirs, files in os.walk(library_path):
            for filename in files:
                if not filename.lower().endswith('.mp3'):
                    continue
                
                filepath = os.path.join(root, filename)
                
                try:
                    audio = MP3(filepath, ID3=ID3)
                    artist = ""
                    title = ""
                    
                    if audio.tags:
                        if 'TPE1' in audio.tags:
                            artist = str(audio.tags['TPE1'])
                        if 'TIT2' in audio.tags:
                            title = str(audio.tags['TIT2'])
                    
                    if artist and title:
                        # Clean and format
                        clean_artist = clean_string(artist)
                        clean_title = clean_string(title)
                        
                        # Remove invalid characters for the key
                        clean_artist = re.sub(r'[<>:"/\\|?*]', '', clean_artist).strip()
                        clean_title = re.sub(r'[<>:"/\\|?*]', '', clean_title).strip()
                        
                        # Create the canonical key: "Artist - Title"
                        # We use this to match against Spotify requirements
                        # Note: We store lowercase for case-insensitive matching
                        key = f"{clean_artist} - {clean_title}".lower()
                        
                        # Store the real path
                        library_index[key] = {
                            "path": filepath,
                            "original_filename": filename,
                            "canonical_name": f"{clean_artist} - {clean_title}.mp3"
                        }
                        
                except Exception as e:
                    logger.debug(f"Error reading {filepath}: {e}")
                    
    logger.info(f"Scan complete. Found {len(library_index)} unique tracks.")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(library_index, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Index saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    scan_library()