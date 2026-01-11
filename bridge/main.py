import os
import time
import schedule
import logging
import requests
import hashlib
import random
import string
import spotipy
import re
import shutil
from datetime import datetime, timedelta
from spotipy.oauth2 import SpotifyClientCredentials
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TPE1, TPE2, TIT2, TALB, TCMP, APIC
from unidecode import unidecode

# Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_PLAYLIST_ID = os.getenv("SPOTIFY_PLAYLIST_ID")

NAVIDROME_URL = os.getenv("NAVIDROME_URL")
NAVIDROME_USER = os.getenv("NAVIDROME_USER")
NAVIDROME_PASS = os.getenv("NAVIDROME_PASS")

SLSKD_URL = os.getenv("SLSKD_URL")
SLSKD_API_KEY = os.getenv("SLSKD_API_KEY")

# Paths
SOULSEEK_DOWNLOADS_DIR = "/downloads/_Soulseek"
DOWNLOADS_ROOT = "/downloads"
DAILY_MUSIC_DIR = "/music/Daily"
LIBRARY_INDEX_PATH = "/music/library_index.json"
WATCH_DIR = "/watch"

# --- Utils ---

def clean_string(text):
    """Remove common clutter from strings like (Radio Edit), (Ft. ...), etc."""
    if not text:
        return ""
    
    # 1. Remove text inside brackets/parentheses containing keywords
    keywords = r"\bradio\b|\bedit\b|\bmix\b|\bremix\b|\bremaster\b|\bfeat\b|\bft\.IBLE\b|\bfeature\b|\bextended\b|\bclub\b|\boriginal\b|\bvocal\b|\bversion\b"
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

def normalize_string(s):
    """Normalize string for matching: lowercase, remove special chars"""
    # Remove special characters, keep only alphanumeric and spaces
    s = re.sub(r'[^\w\s]', ' ', s.lower())
    # Replace multiple spaces with single space
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def matches_track(filename, artist, title):
    """Check if filename contains artist and title (Dual Check: As-Is & Transliterated)"""
    
    # Check 1: Direct comparison (Handles Cyrillic==Cyrillic, Latin==Latin)
    f_norm = normalize_string(filename)
    a_norm = normalize_string(artist)
    t_norm = normalize_string(title)
    
    if a_norm in f_norm and t_norm in f_norm:
        return True
        
    # Check 2: Transliterated comparison (Handles Cyrillic vs Latin, Umlauts, etc.)
    f_uni = normalize_string(unidecode(filename))
    a_uni = normalize_string(unidecode(artist))
    t_uni = normalize_string(unidecode(title))
    
    if a_uni in f_uni and t_uni in f_uni:
        return True
        
    return False

# --- Spotify & Library ---

def get_spotify_playlist_tracks(playlist_id_or_url):
    try:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        results = sp.playlist_items(playlist_id_or_url)
        tracks = results['items']
        while results['next']:
            results = sp.next(results)
            tracks.extend(results['items'])
            
        logger.info(f"Found {len(tracks)} tracks in Spotify playlist.")
        parsed_tracks = []
        for item in tracks:
            track = item['track']
            if not track: continue
            artist = track['artists'][0]['name']
            title = track['name']
            parsed_tracks.append({'artist': artist, 'title': title})
        return parsed_tracks
    except Exception as e:
        logger.error(f"Error fetching Spotify tracks: {e}")
        return []

def load_library_index():
    try:
        import json
        if not os.path.exists(LIBRARY_INDEX_PATH):
            logger.warning("Library index not found. Run scan_library.py first.")
            return {}
        
        with open(LIBRARY_INDEX_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading library index: {e}")
        return {}

# --- Slskd Operations ---

def clear_download_queue():
    """Clear all pending downloads from slskd queue"""
    try:
        headers = {'X-API-Key': SLSKD_API_KEY}
        response = requests.get(f"{SLSKD_URL}/api/v0/transfers/downloads", headers=headers)
        if response.status_code != 200:
            return

        downloads = response.json()
        cleared_count = 0

        for download in downloads:
            username = download.get('username')
            download_id = download.get('id')
            if username and download_id:
                try:
                    del_response = requests.delete(
                        f"{SLSKD_URL}/api/v0/transfers/downloads/{username}/{download_id}",
                        headers=headers
                    )
                    if del_response.status_code in [200, 204]:
                        cleared_count += 1
                except Exception:
                    pass
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} pending downloads from queue")
    except Exception as e:
        logger.error(f"Error clearing download queue: {e}")

def search_and_download_slskd(artist, title):
    try:
        search_query = f"{artist} {title}"
        logger.info(f"Searching Slskd for: {search_query}")

        headers = {'X-API-Key': SLSKD_API_KEY}

        # 1. Initiate Search
        search_payload = {'searchText': search_query}
        init_response = requests.post(f"{SLSKD_URL}/api/v0/searches", json=search_payload, headers=headers)
        init_response.raise_for_status()
        search_id = init_response.json().get('id')

        # 2. Wait and poll for results
        max_wait = 45 # Reduced wait time slightly
        check_interval = 5
        waited = 0
        results = []

        while waited < max_wait:
            time.sleep(check_interval)
            waited += check_interval

            results_response = requests.get(
                f"{SLSKD_URL}/api/v0/searches/{search_id}?includeResponses=true",
                headers=headers
            )
            results_response.raise_for_status()
            search_data = results_response.json()
            results = search_data.get('responses', [])
            
            if len(results) > 0:
                break

        if len(results) == 0:
            logger.warning(f"No results after {max_wait} seconds")
            return False

        # 3. Find FIRST matching MP3 with 320kbps
        for user_response in results:
            for file in user_response.get('files', []):
                filename = file.get('filename', '')
                bitrate = file.get('bitRate', 0)

                if not filename.lower().endswith('.mp3'): continue
                if bitrate < 320: continue
                
                # Loose check first
                if not matches_track(filename, artist, title):
                    continue

                # Found a match!
                match_info = {
                    'username': user_response['username'],
                    'filename': file['filename'],
                    'size': file['size']
                }

                logger.info(f"  -> MATCH! Downloading from {user_response['username']}")

                download_payload = [{
                    'filename': match_info['filename'],
                    'size': match_info['size']
                }]

                dl_response = requests.post(
                    f"{SLSKD_URL}/api/v0/transfers/downloads/{match_info['username']}",
                    json=download_payload,
                    headers=headers
                )

                if dl_response.status_code in [200, 201]:
                    return True
                else:
                    logger.error(f"Failed to queue download! Status: {dl_response.status_code}")
                    continue 

        logger.warning(f"No matching MP3 320kbps found for {artist} - {title}")
        return False

    except Exception as e:
        logger.error(f"Error with Slskd: {e}")
        return False

# --- File Organization ---

def cleanup_soulseek_dir():
    """Clean up _Soulseek folder completely"""
    if not os.path.exists(SOULSEEK_DOWNLOADS_DIR):
        return

    for root, dirs, files in os.walk(SOULSEEK_DOWNLOADS_DIR, topdown=False):
        for filename in files:
            try:
                os.remove(os.path.join(root, filename))
            except Exception: pass
        for dirname in dirs:
            try:
                os.rmdir(os.path.join(root, dirname))
            except Exception: pass
    
    logger.info("Cleaned up _Soulseek folder")

def organize_daily_files(expected_tracks=[]):
    """Process files from _Soulseek and move to Daily root with 'Artist - Title.mp3' format"""
    if not os.path.exists(SOULSEEK_DOWNLOADS_DIR) or not os.path.exists(DAILY_MUSIC_DIR):
        return []

    moved_files = []

    for root, dirs, files in os.walk(SOULSEEK_DOWNLOADS_DIR):
        for filename in files:
            if not filename.lower().endswith('.mp3'): continue

            source_path = os.path.join(root, filename)
            
            # Default: use filename as base
            artist_candidate = ""
            title_candidate = ""
            
            try:
                audio = MP3(source_path, ID3=ID3)
                if audio.tags:
                    if 'TPE1' in audio.tags: artist_candidate = str(audio.tags['TPE1'])
                    if 'TIT2' in audio.tags: title_candidate = str(audio.tags['TIT2'])
            except Exception: pass
            
            matched_track = None
            
            # Check using ID3 tags first
            if artist_candidate and title_candidate:
                for track in expected_tracks:
                    if track['artist'].lower() in artist_candidate.lower() and \
                       track['title'].lower() in title_candidate.lower():
                        matched_track = track
                        break
            
            # If no match, check using filename
            if not matched_track:
                for track in expected_tracks:
                    if matches_track(filename, track['artist'], track['title']):
                        matched_track = track
                        break
            
            if matched_track:
                final_artist = matched_track['artist']
                final_title = matched_track['title']
            else:
                logger.info(f"No Spotify match for {filename}, heuristic cleaning")
                if artist_candidate and title_candidate:
                    final_artist = clean_string(artist_candidate)
                    final_title = clean_string(title_candidate)
                else:
                    base = os.path.splitext(filename)[0]
                    if " - " in base:
                        parts = base.split(" - ", 1)
                        final_artist = clean_string(parts[0])
                        final_title = clean_string(parts[1])
                    else:
                        final_artist = "Unknown"
                        final_title = clean_string(base)

            # Sanitize filename
            final_artist = re.sub(r'[<>:"/\\|?*]', '', final_artist).strip()
            final_title = re.sub(r'[<>:"/\\|?*]', '', final_title).strip()
            new_filename = f"{final_artist} - {final_title}.mp3"
            dest_path = os.path.join(DAILY_MUSIC_DIR, new_filename)

            if os.path.exists(dest_path):
                continue

            try:
                shutil.copy2(source_path, dest_path)
                moved_files.append(dest_path)
                logger.info(f"Copied to Daily: {filename} -> {new_filename}")
            except Exception as e:
                logger.error(f"Error copying {source_path}: {e}")

    cleanup_soulseek_dir()
    return moved_files

def move_raw_files(destination_folder):
    """Move all files from _Soulseek to destination WITHOUT renaming"""
    if not os.path.exists(SOULSEEK_DOWNLOADS_DIR):
        return
    
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    moved_count = 0
    for root, dirs, files in os.walk(SOULSEEK_DOWNLOADS_DIR):
        for filename in files:
            source_path = os.path.join(root, filename)
            dest_path = os.path.join(destination_folder, filename)
            
            # Avoid overwriting
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(filename)
                dest_path = os.path.join(destination_folder, f"{base}_{int(time.time())}{ext}")

            try:
                shutil.move(source_path, dest_path)
                moved_count += 1
            except Exception as e:
                logger.error(f"Error moving {filename}: {e}")

    cleanup_soulseek_dir()
    logger.info(f"Moved {moved_count} raw files to {destination_folder}")

def update_daily_tags():
    """Update tags for ALL files in Daily folder, preserving modification time and Album Art"""
    if not os.path.exists(DAILY_MUSIC_DIR): return
    
    for filename in os.listdir(DAILY_MUSIC_DIR):
        if not filename.lower().endswith('.mp3'): continue
        filepath = os.path.join(DAILY_MUSIC_DIR, filename)
        
        try:
            # Preserve original mtime
            stat = os.stat(filepath)
            original_atime = stat.st_atime
            original_mtime = stat.st_mtime

            base = os.path.splitext(filename)[0]
            
            # Extract artist and title
            if " - " in base:
                parts = base.split(" - ", 1)
                final_artist = parts[0].strip()
                final_title = parts[1].strip()
            else:
                final_artist = "Unknown"
                final_title = base.strip()

            audio = MP3(filepath, ID3=ID3)
            
            # Ensure tags exist
            if audio.tags is None:
                try:
                    audio.add_tags()
                except Exception:
                    pass
            
            if audio.tags is None:
                logger.warning(f"Could not initialize tags for {filename}")
                continue

            # 1. Backup Album Art (APIC)
            apic_frames = audio.tags.getall("APIC")
            
            # 2. Clear all tags
            audio.tags.clear()
            
            # 3. Restore Album Art
            for frame in apic_frames:
                audio.tags.add(frame)

            # 4. Set New Tags
            audio.tags.add(TPE1(encoding=3, text=final_artist)) # Artist
            audio.tags.add(TIT2(encoding=3, text=final_title))  # Title
            audio.tags.add(TALB(encoding=3, text="Daily Mix"))  # Album
            audio.tags.add(TPE2(encoding=3, text="Various Artists")) # Album Artist
            audio.tags.add(TCMP(encoding=3, text="1")) # Compilation Flag
            
            audio.save()
            
            # Restore mtime
            os.utime(filepath, (original_atime, original_mtime))
            
        except Exception as e:
            logger.error(f"Error updating tags for {filepath}: {e}")

def create_daily_playlist(library_files=[]):
    if not os.path.exists(DAILY_MUSIC_DIR): return
    playlist_path = os.path.join(DAILY_MUSIC_DIR, "Daily Mix.m3u")
    
    daily_files = sorted([f for f in os.listdir(DAILY_MUSIC_DIR) if f.lower().endswith('.mp3')])
    if not daily_files and not library_files: return

    with open(playlist_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for path in library_files: f.write(f"{path}\n")
        for filename in daily_files: f.write(f"{filename}\n")

def cleanup_old_daily_files():
    if not os.path.exists(DAILY_MUSIC_DIR): return
    cutoff = datetime.now() - timedelta(days=7)
    for filename in os.listdir(DAILY_MUSIC_DIR):
        filepath = os.path.join(DAILY_MUSIC_DIR, filename)
        try:
            if os.path.isfile(filepath) and filename.endswith('.mp3'):
                if datetime.fromtimestamp(os.path.getmtime(filepath)) < cutoff:
                    os.remove(filepath)
        except Exception: pass

# --- Jobs ---

def job_daily_sync():
    logger.info("Starting Daily Sync Job...")
    library_index = load_library_index()
    library_matches = []
    
    # Scan Daily folder for existing tracks
    daily_existing = []
    if os.path.exists(DAILY_MUSIC_DIR):
        daily_existing = [f for f in os.listdir(DAILY_MUSIC_DIR) if f.lower().endswith('.mp3')]
    
    tracks = get_spotify_playlist_tracks(SPOTIFY_PLAYLIST_ID)
    tracks_to_download = []

    for track in tracks:
        a = re.sub(r'[<>:"/\\|?*]', '', clean_string(track['artist'])).strip()
        t = re.sub(r'[<>:"/\\|?*]', '', clean_string(track['title'])).strip()
        lookup_key = f"{a} - {t}".lower()
        
        # 1. Check Daily Folder (Priority: Filename Match)
        found_in_daily = False
        for daily_file in daily_existing:
            if matches_track(daily_file, track['artist'], track['title']):
                found_in_daily = True
                break
        
        if found_in_daily:
            # Already in Daily.
            continue

        # 2. Check Library (Exact Match)
        if lookup_key in library_index:
            library_matches.append(library_index[lookup_key]['path'])
            continue

        # 3. Check Library (Fuzzy Match)
        found_fuzzy = False
        for entry in library_index.values():
            if matches_track(entry['canonical_name'], track['artist'], track['title']):
                library_matches.append(entry['path'])
                found_fuzzy = True
                break
        
        if found_fuzzy:
            continue
            
        # 4. Not found anywhere -> Download
        tracks_to_download.append(track)

    # Download limit to prevent huge queues
    processed_count = 0
    for track in tracks_to_download:
        # Simple timeout protection for the job loop
        if processed_count > 50: 
            logger.info("Daily limit reached (50 tracks). Stopping.")
            break
            
        logger.info(f"Missing in library: {track['artist']} - {track['title']}")
        if search_and_download_slskd(track['artist'], track['title']):
             # Wait a bit between searches
             time.sleep(5)
        processed_count += 1

    # Wait for downloads to finish if we downloaded anything
    if processed_count > 0:
        logger.info("Waiting for downloads (60s)...")
        time.sleep(60)
        # Organize only if we actually downloaded something
        organize_daily_files(tracks_to_download)
    
    # Force update tags on ALL files in Daily (ensures consistency for old & new)
    update_daily_tags()
    
    # Always recreate playlist
    create_daily_playlist(library_matches)
    cleanup_old_daily_files()
    
    logger.info("Daily Sync Job Completed.")

def process_watch_folder():
    """Check watch folder for .txt or .m3u files"""
    if not os.path.exists(WATCH_DIR):
        return

    for filename in os.listdir(WATCH_DIR):
        if filename.endswith(".processed"):
            continue

        filepath = os.path.join(WATCH_DIR, filename)
        playlist_name = os.path.splitext(filename)[0]
        destination_dir = os.path.join(DOWNLOADS_ROOT, playlist_name)
        
        tracks = []
        is_valid = False

        if filename.endswith(".txt"):
            try:
                with open(filepath, 'r') as f:
                    content = f.read().strip()
                    # Expecting Spotify URI or URL
                    if "spotify" in content:
                        logger.info(f"Found Spotify link in {filename}: {content}")
                        tracks = get_spotify_playlist_tracks(content)
                        is_valid = True
            except Exception as e:
                logger.error(f"Error reading {filename}: {e}")

        elif filename.endswith(".m3u") or filename.endswith(".m3u8"):
            try:
                logger.info(f"Processing M3U playlist: {filename}")
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#EXTINF"):
                            # #EXTINF:123,Artist - Title
                            parts = line.split(",", 1)
                            if len(parts) > 1:
                                meta = parts[1]
                                if " - " in meta:
                                    a, t = meta.split(" - ", 1)
                                    tracks.append({'artist': a.strip(), 'title': t.strip()})
                        elif not line.startswith("#") and line:
                            # Try to guess from filename path
                            base = os.path.basename(line)
                            base = os.path.splitext(base)[0]
                            if " - " in base:
                                a, t = base.split(" - ", 1)
                                tracks.append({'artist': a.strip(), 'title': t.strip()})
                if tracks:
                    is_valid = True
            except Exception as e:
                logger.error(f"Error reading M3U {filename}: {e}")

        if is_valid and tracks:
            logger.info(f"Starting manual download for '{playlist_name}' ({len(tracks)} tracks)")
            
            # Ensure destination exists
            if not os.path.exists(destination_dir):
                os.makedirs(destination_dir)

            for track in tracks:
                logger.info(f"Manual Download: {track['artist']} - {track['title']}")
                search_and_download_slskd(track['artist'], track['title'])
                # Small delay between searches
                time.sleep(2)
            
            # Allow time for last downloads
            logger.info("Waiting for downloads to complete...")
            time.sleep(20)
            
            # Move files
            move_raw_files(destination_dir)
            
            # Mark processed
            try:
                os.rename(filepath, filepath + ".processed")
                logger.info(f"Finished processing {filename}")
            except Exception as e:
                logger.error(f"Error marking {filename} as processed: {e}")

if __name__ == "__main__":
    logger.info("Bridge Service Started with Manual Watch Support.")
    
    # Run Daily Sync on startup
    job_daily_sync()
    
    # Schedule Daily Sync every day at 05:00
    schedule.every().day.at("05:00").do(job_daily_sync)
    
    # Main loop
    while True:
        # Check watch folder frequently (every 10 seconds)
        try:
            process_watch_folder()
        except Exception as e:
            logger.error(f"Error in watch loop: {e}")
            
        schedule.run_pending()
        time.sleep(10)