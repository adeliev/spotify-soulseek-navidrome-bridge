import os
import time
import logging
import requests
import re
import shutil
import csv
import json
import random
from datetime import datetime, timedelta
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TPE1, TPE2, TIT2, TALB, TCMP
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
            return {k: datetime.fromisoformat(v) for k, v in data.items()}
    except: return {}

def save_history(history):
    try:
        cutoff = datetime.now() - timedelta(days=30)
        clean_hist = {k: v for k, v in history.items() if v > cutoff}
        with open(HISTORY_PATH, 'w') as f:
            json.dump({k: v.isoformat() for k, v in clean_hist.items()}, f)
    except: pass

def load_library_index():
    if not os.path.exists(LIBRARY_INDEX_PATH): return {}
    try:
        with open(LIBRARY_INDEX_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def load_aliases():
    if not os.path.exists(ALIASES_PATH): return {}
    try:
        with open(ALIASES_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def get_artist_name(artist, aliases):
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
            active = [d for d in dls if d.get('state') not in ['Completed', 'Succeeded', 'Errored']]
            return len(active)
    except: pass
    return 0

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

def wait_and_organize(expected_tracks, target_dir, max_wait_mins=30):
    logger.info('Waiting for downloads to complete...')
    start_time = datetime.now()
    while (datetime.now() - start_time).total_seconds() < max_wait_mins * 60:
        time.sleep(60)
        organize_files(expected_tracks, target_dir)
        active_count = get_active_downloads_count()
        if active_count == 0:
            logger.info('Downloads finished.')
            break
        logger.info('Still downloading: ' + str(active_count) + ' files remaining...')
    
    if os.path.exists(SOULSEEK_DOWNLOADS_DIR):
        for item in os.listdir(SOULSEEK_DOWNLOADS_DIR):
            item_path = os.path.join(SOULSEEK_DOWNLOADS_DIR, item)
            try:
                if os.path.isfile(item_path): os.remove(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path)
            except: pass

def update_nsp_playlist(name, folder_prefix, library_paths):
    if not os.path.exists(PLAYLISTS_DIR): os.makedirs(PLAYLISTS_DIR)
    rules = []
    if folder_prefix: rules.append({'startsWith': {'filepath': folder_prefix}})
    for p in library_paths: rules.append({'is': {'filepath': p.replace('/music/', '')}})
    with open(os.path.join(PLAYLISTS_DIR, name + '.nsp'), 'w') as f:
        json.dump({'name': name, 'any': rules, 'sort': 'random'}, f, indent=2)

# --- Core Processing ---

def process_file(file_path):
    filename = os.path.basename(file_path)
    logger.info('Processing: ' + filename)
    
    is_radar = 'Release Radar' in filename or 'Release_Radar' in filename
    is_daily = 'Daily Mix' in filename or 'Daily_Mix' in filename or 'all_tracks.csv' in filename
    
    target_dir = RADAR_MUSIC_DIR if is_radar else DAILY_MUSIC_DIR
    playlist_name = 'Release Radar' if is_radar else 'Daily Mix'
    folder_prefix = 'ReleaseRadar/' if is_radar else 'Daily/'
    
    tracks = []
    try:
        if filename.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('artist') and row.get('title'):
                        tracks.append({'artist': row['artist'], 'title': row['title']})
        elif filename.endswith('.m3u') or filename.endswith('.m3u8') or filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    
                    # Remove .mp3 or .flac if present
                    line = re.sub(r'\.(mp3|flac|wav|m4a)$', '', line, flags=re.IGNORECASE)
                    
                    if ' - ' in line:
                        a, t = line.split(' - ', 1)
                        tracks.append({'artist': a.strip(), 'title': t.strip()})
                    else:
                        # Fallback for lines without ' - '
                        tracks.append({'artist': 'Unknown', 'title': line.strip()})
            logger.info('Found ' + str(len(tracks)) + ' tracks in ' + filename)
        elif filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if ' - ' in line:
                        a, t = line.split(' - ', 1)
                        tracks.append({'artist': a.strip(), 'title': t.strip()})
    except Exception as e:
        logger.error('Error reading file: ' + str(e))
        return

    if not tracks: return

    history, aliases, lib_idx = load_history(), load_aliases(), load_library_index()
    cutoff = datetime.now() - timedelta(days=HISTORY_DAYS)
    
    if is_radar:
        if os.path.exists(RADAR_MUSIC_DIR): shutil.rmtree(RADAR_MUSIC_DIR)
        os.makedirs(RADAR_MUSIC_DIR)

    if is_daily and len(tracks) > 60:
        random.shuffle(tracks)
        tracks = tracks[:60]

    to_download, lib_matches = [], []
    for t in tracks:
        art, tit = get_artist_name(t['artist'], aliases), t['title']
        a_cl, t_cl = re.sub(r'[<>:"/\\|?*]', '', clean_string(art)).strip(), re.sub(r'[<>:"/\\|?*]', '', clean_string(tit)).strip()
        lookup = (a_cl + ' - ' + t_cl).lower()
        
        if lookup in lib_idx:
            lib_matches.append(lib_idx[lookup]['path'])
            if is_daily: history[lookup] = datetime.now()
            continue
        if is_daily and os.path.exists(os.path.join(DAILY_MUSIC_DIR, a_cl + ' - ' + t_cl + '.mp3')):
            history[lookup] = datetime.now()
            continue
        if is_daily and lookup in history and history[lookup] > cutoff: continue
        to_download.append({'artist': art, 'title': tit})

    dl_count = 0
    for t in to_download:
        if search_and_download_slskd(t['artist'], t['title']):
            dl_count += 1
            if is_daily: history[(t['artist'] + ' - ' + t['title']).lower()] = datetime.now()
            time.sleep(5)
    
    if dl_count > 0: wait_and_organize(to_download, target_dir)
    
    if is_daily:
        current_files = os.listdir(DAILY_MUSIC_DIR) if os.path.exists(DAILY_MUSIC_DIR) else []
        if len(current_files) > 10:
            keep_now = set()
            for t in tracks:
                art, tit = get_artist_name(t['artist'], aliases), t['title']
                a_cl, t_cl = re.sub(r'[<>:"/\\|?*]', '', clean_string(art)).strip(), re.sub(r'[<>:"/\\|?*]', '', clean_string(tit)).strip()
                keep_now.add(a_cl + ' - ' + t_cl + '.mp3')
            for f in current_files:
                if f.lower().endswith('.mp3') and f not in keep_now:
                    try: os.remove(os.path.join(DAILY_MUSIC_DIR, f))
                    except: pass

    save_history(history)
    update_nsp_playlist(playlist_name, folder_prefix, lib_matches)
    logger.info('Done processing: ' + filename)

if __name__ == '__main__':
    logger.info('Bridge Watcher Started (CSV/M3U/TXT support)')
    while True:
        valid_extensions = ('.csv', '.m3u', '.m3u8', '.txt')
        files = [f for f in os.listdir(WATCH_DIR) if f.lower().endswith(valid_extensions) and not f.endswith('.processed')]
        for f in files:
            file_path = os.path.join(WATCH_DIR, f)
            try:
                process_file(file_path)
                os.rename(file_path, file_path + '.processed')
            except Exception as e:
                logger.error('Error: ' + str(e))
        time.sleep(30)
