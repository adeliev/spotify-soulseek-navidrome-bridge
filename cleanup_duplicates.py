import json
import os
import re

LIBRARY_INDEX_PATH = "/Volumes/DeliRAID5/Media/Music/library_index.json"
DAILY_DIR = "/Volumes/DeliRAID5/Media/Music/Daily"

def normalize_string(s):
    """Normalize string: lowercase, remove special chars, single spaces."""
    # Remove special characters, keep only alphanumeric and spaces
    s = re.sub(r'[^\w\s]', ' ', s.lower())
    # Replace multiple spaces with single space
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def matches_track(filename, artist, title):
    """Check if filename contains artist and title (fuzzy match)."""
    filename_norm = normalize_string(filename)
    artist_norm = normalize_string(artist)
    title_norm = normalize_string(title)
    return artist_norm in filename_norm and title_norm in filename_norm

def main():
    if not os.path.exists(LIBRARY_INDEX_PATH):
        print(f"Error: Library index not found at {LIBRARY_INDEX_PATH}")
        return

    print("Loading library index...")
    with open(LIBRARY_INDEX_PATH, 'r', encoding='utf-8') as f:
        library_index = json.load(f)

    if not os.path.exists(DAILY_DIR):
        print(f"Error: Daily directory not found at {DAILY_DIR}")
        return

    files = [f for f in os.listdir(DAILY_DIR) if f.lower().endswith('.mp3')]
    print(f"Checking {len(files)} files in Daily folder against {len(library_index)} library entries...")

    deleted_count = 0

    for filename in files:
        filepath = os.path.join(DAILY_DIR, filename)

        # Parse Artist - Title from filename (Daily files are formatted as "Artist - Title.mp3")
        name_no_ext = os.path.splitext(filename)[0]

        artist_daily = ""
        title_daily = ""

        if " - " in name_no_ext:
            parts = name_no_ext.split(" - ", 1)
            artist_daily = parts[0].strip()
            title_daily = parts[1].strip()
        else:
            # Fallback if format is unexpected
            artist_daily = ""
            title_daily = name_no_ext

        daily_norm = normalize_string(name_no_ext)

        found = False
        match_path = ""

        # Check against library entries
        for key, entry in library_index.items():
            # entry['canonical_name'] is typically "Artist - Title.mp3"
            lib_canon_name = entry.get('canonical_name', '')
            lib_canon_no_ext = os.path.splitext(lib_canon_name)[0]

            # Method 1: Direct normalized filename comparison
            lib_norm = normalize_string(lib_canon_no_ext)

            if daily_norm == lib_norm:
                found = True
                match_path = entry['path']
                break

            # Method 2: Fuzzy match - Check if Daily Artist/Title exists inside Library Canonical Name
            # (Useful if Daily has slight variations but Library is definitive)
            if artist_daily and title_daily:
                if matches_track(lib_canon_name, artist_daily, title_daily):
                    found = True
                    match_path = entry['path']
                    break

            # Method 3: Reverse Fuzzy - Check if Library Artist/Title (from Key) exists in Daily Filename
            # Key is usually "artist - title" (lowercase)
            # This handles cases where Daily filename might be "Artist - Title (Radio Edit)" and Library is "Artist - Title"
            if " - " in key:
                 # key is already normalized/lowercase in index generation
                 key_parts = key.split(" - ", 1)
                 if len(key_parts) == 2:
                     key_artist = key_parts[0]
                     key_title = key_parts[1]
                     # Check if the library key components are in the daily filename
                     if key_artist in daily_norm and key_title in daily_norm:
                         found = True
                         match_path = entry['path']
                         break

        if found:
            print(f"Duplicate found: '{filename}'")
            print(f"  -> Matches Library: '{match_path}'")
            try:
                os.remove(filepath)
                print(f"  -> DELETED.")
                deleted_count += 1
            except Exception as e:
                print(f"  -> Error deleting: {e}")

    print("-" * 30)
    print(f"Cleanup finished. Deleted {deleted_count} duplicate files.")

if __name__ == "__main__":
    main()
