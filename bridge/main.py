import os
import time
import logging
import requests
import re
import shutil
import csv
import json
import random
import traceback
from datetime import datetime, timedelta
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, ID3NoHeaderError, TPE1, TPE2, TIT2, TALB, TCMP, TCON, TPOS, TRCK
from unidecode import unidecode

# Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SLSKD_URL = os.getenv('SLSKD_URL')
SLSKD_API_KEY = os.getenv('SLSKD_API_KEY')

# Paths
SOULSEEK_DOWNLOADS_DIR = '/downloads/_Soulseek'
DAILY_MUSIC_DIR = '/music/Daily'
RADAR_MUSIC_DIR = '/music/ReleaseRadar'
PLAYLISTS_DIR = '/music/Playlists'
LIBRARY_INDEX_PATH = '/music/library_index.json'
HISTORY_PATH = '/music/daily_history.json'
WATCH_DIR = '/app/data/watch'
ALIASES_PATH = '/app/data/artist_aliases.txt'

# Settings
TARGET_TRACKS_DAILY = 60
HISTORY_DAYS = 3
PROCESS_TIMEOUT_SECONDS = 3600  # 1 hour limit

# --- Utils ---

def repair_encoding(text):
    if not text: return ''
    try:
        if any('\u0400' <= c <= '\u04FF' for c in text): return text
        encoded = text.encode('latin-1')
        return encoded.decode('cp1251')
    except: return text

def clean_string(text):
    text = repair_encoding(text)
    if not text: return ''
    keywords = r'\bradio\b|\bedit\b|\bmix\b|\bremix\b|\bremaster\b|\bfeat\b|\bft\.?|\bfeature\b|\bextended\b|\bclub\b|\boriginal\b|\bvocal\b|\bversion\b|\blive\b'
    pattern = r'\s*[(\[][^\x29\x5D]*?(?:' + keywords + r')[^\x29\x5D]*?[)\x5D]'
    prev_text = None
    while text != prev_text:
        prev_text = text
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*-\s*.*?(?:' + keywords + r').*?$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+(?:feat|ft\.|feature)\.?\s+.*$', '', text, flags=re.IGNORECASE)
    return text.strip()

def normalize_string(s):
    if not s: return ''
    s = re.sub(r'[^\w\s]', ' ', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def matches_track(filename, artist, title):
    filename = repair_encoding(filename)
    f_norm = normalize_string(filename)
    a_norm = normalize_string(artist)
    t_norm = normalize_string(title)
    if a_norm in f_norm and t_norm in f_norm: return True
    f_uni = normalize_string(unidecode(filename))
    a_uni = normalize_string(unidecode(artist))
    t_uni = normalize_string(unidecode(title))
    if a_uni in f_uni and t_uni in f_uni: return True
    return False

def load_history():
    if not os.path.exists(HISTORY_PATH): return {}
    try:
        with open(HISTORY_PATH, 'r') as f:
            data = json.load(f)
            return {k: datetime.fromisoformat(v) for k, v in data.items()} if data else {}
    except: return {}

def save_history(history):
    if history is None: return
    try:
        cutoff = datetime.now() - timedelta(days=HISTORY_DAYS)
        clean_hist = {k: v for k, v in history.items() if v > cutoff}
        with open(HISTORY_PATH, 'w') as f:
            json.dump({k: v.isoformat() for k, v in clean_hist.items()}, f)
    except: pass

def load_library_index():
    if not os.path.exists(LIBRARY_INDEX_PATH): return {}
    try:
        with open(LIBRARY_INDEX_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if data else {}
    except: return {}

def load_aliases():
    if not os.path.exists(ALIASES_PATH): return {}
    try:
        with open(ALIASES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if data else {}
    except: return {}

def get_artist_name(artist, aliases):
    if aliases is None or not isinstance(aliases, dict): return artist
    return aliases[artist] if artist in aliases else artist

# --- Slskd ---

def search_and_download_slskd(artist, title):
    try:
        search_query = artist + ' ' + title
        headers = {'X-API-Key': SLSKD_API_KEY}
        init_response = requests.post(SLSKD_URL + '/api/v0/searches', json={'searchText': search_query}, headers=headers)
        search_id = init_response.json().get('id')
        waited = 0
        while waited < 45:
            time.sleep(5)
            waited += 5
            res_obj = requests.get(SLSKD_URL + '/api/v0/searches/' + search_id + '?includeResponses=true', headers=headers)
            results = res_obj.json().get('responses', [])
            if results: break
        if not results: return False
        for user_res in results:
            for file in user_res.get('files', []):
                if not file.get('filename', '').lower().endswith('.mp3'): continue
                if file.get('bitRate', 0) < 320: continue
                if not matches_track(file['filename'], artist, title): continue
                dl_payload = [{'filename': file['filename'], 'size': file['size']}]
                username = user_res['username']
                requests.post(SLSKD_URL + '/api/v0/transfers/downloads/' + username, json=dl_payload, headers=headers)
                logger.info('Queued: ' + artist + ' - ' + title)
                return True
        return False
    except: return False

def get_active_downloads_count():
    try:
        headers = {'X-API-Key': SLSKD_API_KEY}
        resp = requests.get(SLSKD_URL + '/api/v0/transfers/downloads', headers=headers)
        if resp.status_code == 200:
            dls = resp.json()
            if not dls: return 0
            active = [d for d in dls if d.get('state') not in ['Completed', 'Succeeded', 'Errored']]
            return len(active)
    except: pass
    return 0

def clear_slskd_queues():
    logger.info('Forcefully clearing slskd queues...')
    try:
        headers = {'X-API-Key': SLSKD_API_KEY}
        # Clear downloads
        resp = requests.get(SLSKD_URL + '/api/v0/transfers/downloads', headers=headers)
        if resp.status_code == 200:
            dls = resp.json()
            if dls:
                for dl in dls:
                    if dl.get('state') in ['Queued', 'Requested', 'Initializing', 'Downloading']:
                        user = dl.get('username')
                        requests.delete(f"{SLSKD_URL}/api/v0/transfers/downloads/{user}", headers=headers)
        
        # Clear searches
        resp = requests.get(SLSKD_URL + '/api/v0/searches', headers=headers)
        if resp.status_code == 200:
            searches = resp.json()
            if searches:
                for s in searches:
                    sid = s.get('id')
                    requests.delete(f"{SLSKD_URL}/api/v0/searches/{sid}", headers=headers)
        logger.info('Slskd queues cleared')
    except Exception as e:
        logger.error(f'Failed to clear slskd queues: {e}')

# --- File Operations ---

def organize_files(expected_tracks, target_dir):
    if not os.path.exists(SOULSEEK_DOWNLOADS_DIR): return
    if not os.path.exists(target_dir): os.makedirs(target_dir)
    for root, _, files in os.walk(SOULSEEK_DOWNLOADS_DIR):
        for f in files:
            if not f.lower().endswith('.mp3'): continue
            src = os.path.join(root, f)
            matched = next((t for t in expected_tracks if matches_track(f, t['artist'], t['title'])), None)
            if not matched:
                try:
                    audio = MP3(src, ID3=ID3)
                    if audio.tags:
                        tag_artist = repair_encoding(str(audio.tags.get('TPE1', '')))
                        tag_title = repair_encoding(str(audio.tags.get('TIT2', '')))
                        if tag_artist and tag_title:
                            matched = next((t for t in expected_tracks if matches_track(tag_artist + ' ' + tag_title, t['artist'], t['title'])), None)
                except: pass
            if matched:
                a, tit = matched['artist'], matched['title']
            else:
                for t in expected_tracks:
                    if normalize_string(t['title']) in normalize_string(f):
                        matched, a, tit = t, t['artist'], t['title']
                        break
                if not matched: a, tit = 'Unknown', os.path.splitext(f)[0]
            a_safe, t_safe = re.sub(r'[<>:"/\\|?*]', '', a).strip(), re.sub(r'[<>:"/\\|?*]', '', tit).strip()
            dest = os.path.join(target_dir, a_safe + ' - ' + t_safe + '.mp3')
            try:
                if not os.path.exists(dest): shutil.copy2(src, dest)
            except: pass

# --- Tag Polishing ---

def parse_filename(filename):
    name_no_ext = os.path.splitext(filename)[0]
    if " - " in name_no_ext:
        parts = name_no_ext.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return None, None

def polish_tags(filepath, is_downloaded):
    try:
        audio = MP3(filepath)
    except: return False

    if audio.tags is None: return False
    modified = False

    # 1. Delete track/disc
    for tag in ['TRCK', 'TPOS']:
        if tag in audio.tags:
            del audio.tags[tag]
            modified = True

    tag_artist = repair_encoding(str(audio.tags.get('TPE1', '')))
    tag_title = repair_encoding(str(audio.tags.get('TIT2', '')))

    if not tag_artist or not tag_title:
        f_artist, f_title = parse_filename(os.path.basename(filepath))
        if f_artist and f_title:
            if not tag_artist:
                audio.tags['TPE1'] = TPE1(encoding=3, text=clean_string(f_artist))
                modified = True
            if not tag_title:
                audio.tags['TIT2'] = TIT2(encoding=3, text=clean_string(f_title))
                modified = True

    if 'TALB' not in audio.tags or not audio.tags['TALB']:
        album_name = "Release Radar" if "ReleaseRadar" in filepath else "Daily Mix"
        audio.tags['TALB'] = TALB(encoding=3, text=album_name)
        modified = True

    if is_downloaded:
        if 'TPE2' not in audio.tags:
            audio.tags['TPE2'] = TPE2(encoding=3, text='Various Artists')
            modified = True
        if 'TCMP' not in audio.tags:
            audio.tags['TCMP'] = TCMP(encoding=3, text='1')
            modified = True

    if 'TCON' in audio.tags and audio.tags['TCON']:
        genres = str(audio.tags['TCON'])
        if ';' in genres:
            audio.tags['TCON'] = TCON(encoding=3, text=genres.replace(';', ','))
            modified = True

    if modified: audio.save()
    return modified

def polish_directory(directory, is_downloaded=True):
    if not os.path.exists(directory): return
    files = [f for f in os.listdir(directory) if f.lower().endswith('.mp3')]
    logger.info(f"Polishing {len(files)} files in {directory}...")
    count = 0
    for filename in files:
        try:
            if polish_tags(os.path.join(directory, filename), is_downloaded): count += 1
        except: pass
    logger.info(f"Updated {count} files")

# --- Core Processing ---

def process_file(file_path):
    process_start_time = datetime.now()
    filename = os.path.basename(file_path)
    logger.info(f'--- STARTING PROCESS: {filename} ---')
    
    is_radar = 'Release Radar' in filename or 'Release_Radar' in filename or 'ReleaseRadar' in filename
    is_daily = 'Daily' in filename or 'all_tracks.csv' in filename
    target_dir = RADAR_MUSIC_DIR if is_radar else DAILY_MUSIC_DIR
    
    try:
        # 1. Parse tracks
        tracks = []
        if filename.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('artist') and row.get('title'):
                        tracks.append({'artist': row['artist'], 'title': row['title']})
        else:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    line = re.sub(r'\.(mp3|flac|wav|m4a)$', '', line, flags=re.IGNORECASE)
                    if ' - ' in line:
                        a, t = line.split(' - ', 1)
                        tracks.append({'artist': a.strip(), 'title': t.strip()})
                    else:
                        tracks.append({'artist': 'Unknown', 'title': line.strip()})
        
        if not tracks: return
        if is_daily and len(tracks) > TARGET_TRACKS_DAILY:
            random.shuffle(tracks)
            tracks = tracks[:TARGET_TRACKS_DAILY]

        # 2. Filter
        history = load_history()
        aliases = load_aliases()
        lib_idx = load_library_index()
        
        to_download, lib_matches = [], []
        for t in tracks:
            art = get_artist_name(t['artist'], aliases)
            a_cl, t_cl = re.sub(r'[<>:"/\\|?*]', '', clean_string(art)).strip(), re.sub(r'[<>:"/\\|?*]', '', clean_string(t['title'])).strip()
            lookup = (a_cl + ' - ' + t_cl).lower()
            
            if lookup in history:
                history[lookup] = datetime.now()
                continue
            
            history[lookup] = datetime.now()
            if lookup in lib_idx:
                lib_matches.append(lib_idx[lookup]['path'])
                continue
            if is_daily and os.path.exists(os.path.join(DAILY_MUSIC_DIR, a_cl + ' - ' + t_cl + '.mp3')):
                continue
            to_download.append({'artist': art, 'title': t['title']})

        logger.info(f'To download: {len(to_download)}, In library: {len(lib_matches)}')

        # 3. Queue downloads
        for t in to_download:
            search_and_download_slskd(t['artist'], t['title'])
            time.sleep(2) # Faster queueing

        # 4. Wait loop (Max 1 hour total)
        logger.info(f'Entering download wait loop (Limit: {PROCESS_TIMEOUT_SECONDS}s)')
        while (datetime.now() - process_start_time).total_seconds() < PROCESS_TIMEOUT_SECONDS:
            organize_files(to_download, target_dir)
            active = get_active_downloads_count()
            if active == 0:
                logger.info('All downloads finished early.')
                break
            logger.info(f'Still downloading: {active} files remaining... Time elapsed: {int((datetime.now()-process_start_time).total_seconds())}s')
            time.sleep(60)

        # 5. Guaranteed Finalization
        logger.info('Starting guaranteed finalization phase...')
        clear_slskd_queues()
        
        # Move anything that just finished
        organize_files(to_download, target_dir)
        
        # Polish tags
        polish_directory(target_dir, is_downloaded=True)
        
        # Cleanup Daily
        if is_daily:
            current_files = os.listdir(DAILY_MUSIC_DIR) if os.path.exists(DAILY_MUSIC_DIR) else []
            if len(current_files) > 10:
                keep_now = set()
                for t in tracks:
                    art = get_artist_name(t['artist'], aliases)
                    a_cl, t_cl = re.sub(r'[<>:"/\\|?*]', '', clean_string(art)).strip(), re.sub(r'[<>:"/\\|?*]', '', clean_string(t['title'])).strip()
                    keep_now.add(a_cl + ' - ' + t_cl + '.mp3')
                for f in current_files:
                    if f.lower().endswith('.mp3') and f not in keep_now:
                        try: os.remove(os.path.join(DAILY_MUSIC_DIR, f))
                        except: pass
        
        # Cleanup Radar (7 days)
        if is_radar:
            cutoff = time.time() - (7 * 86400)
            for f in os.listdir(RADAR_MUSIC_DIR):
                f_path = os.path.join(RADAR_MUSIC_DIR, f)
                if os.path.getmtime(f_path) < cutoff:
                    try: os.remove(f_path)
                    except: pass

        # Update NSP
        if is_daily:
            nsp_path = os.path.join(PLAYLISTS_DIR, 'Daily Mix.nsp')
            if os.path.exists(nsp_path):
                try:
                    with open(nsp_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if not data: data = {"name": "Daily Mix", "any": [], "sort": "random"}
                    new_any = [{"startsWith": {"filepath": "Daily/"}}]
                    for lp in lib_matches:
                        new_any.append({"is": {"filepath": lp.replace('/music/', '')}})
                    data['any'] = new_any
                    with open(nsp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.info('NSP updated')
                except: pass

        save_history(history)
        
        # Clean Soulseek folder
        if os.path.exists(SOULSEEK_DOWNLOADS_DIR):
            for item in os.listdir(SOULSEEK_DOWNLOADS_DIR):
                path = os.path.join(SOULSEEK_DOWNLOADS_DIR, item)
                try:
                    if os.path.isfile(path): os.remove(path)
                    else: shutil.rmtree(path)
                except: pass

        logger.info(f'--- PROCESS FINISHED: {filename} ---')
    except Exception as e:
        logger.error(f"FATAL error in process_file: {e}")
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    logger.info('Bridge Watcher Started (CSV/M3U/TXT support)')
    while True:
        try:
            valid = ('.csv', '.m3u', '.m3u8', '.txt')
            files = [f for f in os.listdir(WATCH_DIR) if f.lower().endswith(valid) and not f.endswith('.processed')]
            for f in files:
                f_path = os.path.join(WATCH_DIR, f)
                process_file(f_path)
                try: os.rename(f_path, f_path + '.processed')
                except: pass
        except Exception as e:
            logger.error(f"Watcher loop error: {e}")
        time.sleep(30)
