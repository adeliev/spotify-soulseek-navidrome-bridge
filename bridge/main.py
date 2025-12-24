import os
import time
import schedule
import logging
import requests
import hashlib
import random
import string
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

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

def get_spotify_tracks():
    try:
        auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        results = sp.playlist_items(SPOTIFY_PLAYLIST_ID)
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

def check_navidrome_exists(artist, title):
    try:
        # Subsonic API Authentication
        salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        token = hashlib.md5((NAVIDROME_PASS + salt).encode('utf-8')).hexdigest()
        
        params = {
            'u': NAVIDROME_USER,
            't': token,
            's': salt,
            'v': '1.16.1',
            'c': 'spotify-bridge',
            'f': 'json',
            'query': f"{artist} {title}"
        }
        
        # Search endpoint
        url = f"{NAVIDROME_URL}/rest/search3"
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'subsonic-response' in data and 'searchResult3' in data['subsonic-response']:
            results = data['subsonic-response']['searchResult3']
            if 'song' in results:
                for song in results['song']:
                    # Simple exact match check (case-insensitive)
                    if song['title'].lower() == title.lower() and song['artist'].lower() == artist.lower():
                        return True
        return False
    except Exception as e:
        logger.error(f"Error checking Navidrome: {e}")
        return False

def normalize_string(s):
    """Normalize string for matching: lowercase, remove special chars"""
    import re
    # Remove special characters, keep only alphanumeric and spaces
    s = re.sub(r'[^\w\s]', ' ', s.lower())
    # Replace multiple spaces with single space
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def matches_track(filename, artist, title):
    """Check if filename contains artist and title"""
    filename_norm = normalize_string(filename)
    artist_norm = normalize_string(artist)
    title_norm = normalize_string(title)

    # Check if both artist and title are in filename
    return artist_norm in filename_norm and title_norm in filename_norm

def search_and_download_slskd(artist, title):
    try:
        search_query = f"{artist} {title}"
        logger.info(f"Searching Slskd for: {search_query}")

        headers = {'X-API-Key': SLSKD_API_KEY}

        # 1. Initiate Search
        search_payload = {
            'searchText': search_query
        }
        init_response = requests.post(f"{SLSKD_URL}/api/v0/searches", json=search_payload, headers=headers)
        init_response.raise_for_status()
        search_id = init_response.json().get('id')

        # 2. Wait and poll for results (Soulseek network needs time)
        max_wait = 60  # Maximum 60 seconds
        check_interval = 10  # Check every 10 seconds
        waited = 0
        results = []

        while waited < max_wait:
            time.sleep(check_interval)
            waited += check_interval

            # 3. Get Results (includeResponses=true to get actual file data!)
            results_response = requests.get(
                f"{SLSKD_URL}/api/v0/searches/{search_id}?includeResponses=true",
                headers=headers
            )
            results_response.raise_for_status()
            search_data = results_response.json()

            results = search_data.get('responses', [])
            total_files = sum(len(r.get('files', [])) for r in results)

            logger.info(f"After {waited}s: {len(results)} users, {total_files} files")

            # If we got some results, stop waiting
            if len(results) > 0:
                logger.info(f"Got results after {waited} seconds, processing...")
                break

        if len(results) == 0:
            logger.warning(f"No results after {max_wait} seconds")
            return

        # 4. Find FIRST matching MP3 with 320kbps
        mp3_320_count = 0
        for user_response in results:
            for file in user_response.get('files', []):
                filename = file.get('filename', '')
                bitrate = file.get('bitRate', 0)

                # Filter for MP3 only with bitrate >= 320
                if not filename.lower().endswith('.mp3'):
                    continue

                if bitrate >= 320:
                    mp3_320_count += 1
                    logger.info(f"Checking: {filename} ({bitrate}kbps)")

                if bitrate < 320:
                    continue

                # Check if filename matches artist and title
                if not matches_track(filename, artist, title):
                    logger.info(f"  -> No match: artist or title not in filename")
                    continue

                # Found a match! Download immediately
                match_info = {
                    'username': user_response['username'],
                    'filename': file['filename'],
                    'size': file['size']
                }

                logger.info(f"  -> MATCH! Downloading from {user_response['username']}")

                # Queue Download - slskd format: POST /api/v0/transfers/downloads/{username} with array of files
                download_payload = [{
                    'filename': match_info['filename'],
                    'size': match_info['size']
                }]

                dl_response = requests.post(
                    f"{SLSKD_URL}/api/v0/transfers/downloads/{match_info['username']}",
                    json=download_payload,
                    headers=headers
                )

                if dl_response.status_code == 201 or dl_response.status_code == 200:
                    logger.info(f"Download queued successfully (status: {dl_response.status_code})")
                else:
                    logger.error(f"Failed to queue download! Status: {dl_response.status_code}, Response: {dl_response.text}")
                    continue  # Try next file

                return  # Exit immediately after first match

        logger.info(f"Found {mp3_320_count} MP3 files with 320+kbps, but none matched artist/title")

        logger.warning(f"No matching MP3 320kbps found for {artist} - {title}")

    except Exception as e:
        logger.error(f"Error with Slskd: {e}")

def cleanup_old_files():
    """Delete files older than 30 days from the Daily folder"""
    try:
        import os
        from datetime import datetime, timedelta

        daily_folder = "/music/Daily"
        if not os.path.exists(daily_folder):
            logger.warning(f"Daily folder does not exist: {daily_folder}")
            return

        cutoff_time = datetime.now() - timedelta(days=30)
        deleted_count = 0

        for root, dirs, files in os.walk(daily_folder):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    file_modified = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_modified < cutoff_time:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.info(f"Deleted old file: {filename}")
                except Exception as e:
                    logger.error(f"Error deleting {filepath}: {e}")

        logger.info(f"Cleanup completed. Deleted {deleted_count} files older than 30 days.")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

def organize_downloaded_files():
    """Process files from _Soulseek and move to Daily root with 'Artist - Title.mp3' format"""
    try:
        import os
        import shutil
        import re
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3

        soulseek_folder = "/music/_Soulseek"
        daily_folder = "/music/Daily"

        if not os.path.exists(soulseek_folder):
            logger.warning(f"Soulseek folder does not exist: {soulseek_folder}")
            return []

        if not os.path.exists(daily_folder):
            logger.warning(f"Daily folder does not exist: {daily_folder}")
            return []

        moved_files = []

        # Find all MP3 files in _Soulseek subdirectories
        for root, dirs, files in os.walk(soulseek_folder):
            for filename in files:
                if not filename.lower().endswith('.mp3'):
                    continue

                source_path = os.path.join(root, filename)

                # Try to get artist and title from ID3 tags
                try:
                    audio = MP3(source_path, ID3=ID3)
                    artist = None
                    title = None

                    if audio.tags:
                        # Try to get artist (TPE1)
                        if 'TPE1' in audio.tags:
                            artist = str(audio.tags['TPE1'])
                        # Try to get title (TIT2)
                        if 'TIT2' in audio.tags:
                            title = str(audio.tags['TIT2'])

                    # If we got both, create clean filename
                    if artist and title:
                        # Remove invalid filename characters
                        artist_clean = re.sub(r'[<>:"/\\|?*]', '', artist).strip()
                        title_clean = re.sub(r'[<>:"/\\|?*]', '', title).strip()
                        new_filename = f"{artist_clean} - {title_clean}.mp3"
                    else:
                        # Fallback to original filename
                        new_filename = filename

                except Exception as e:
                    logger.warning(f"Could not read tags from {filename}, using original name: {e}")
                    new_filename = filename

                dest_path = os.path.join(daily_folder, new_filename)

                # If file exists in Daily, skip (already processed)
                if os.path.exists(dest_path):
                    logger.info(f"Skipping (already exists): {new_filename}")
                    continue

                try:
                    # Copy to Daily with new name
                    shutil.copy2(source_path, dest_path)
                    moved_files.append(dest_path)
                    logger.info(f"Copied to Daily: {filename} -> {new_filename}")
                except Exception as e:
                    logger.error(f"Error copying {source_path}: {e}")

        # Clean up _Soulseek: remove all subdirectories and files
        for root, dirs, files in os.walk(soulseek_folder, topdown=False):
            # Remove files
            for filename in files:
                try:
                    filepath = os.path.join(root, filename)
                    os.remove(filepath)
                except Exception as e:
                    logger.error(f"Error removing file {filepath}: {e}")

            # Remove directories
            for dirname in dirs:
                try:
                    dirpath = os.path.join(root, dirname)
                    if os.path.exists(dirpath):
                        os.rmdir(dirpath)
                except Exception as e:
                    logger.error(f"Error removing directory {dirpath}: {e}")

        logger.info(f"Organized {len(moved_files)} files to Daily root")
        logger.info(f"Cleaned up _Soulseek folder")
        return moved_files

    except Exception as e:
        logger.error(f"Error organizing files: {e}")
        return []

def update_id3_tags():
    """Update ID3 tags: set Album Artist to 'Various Artists' and Album to 'Daily Mix'"""
    try:
        import os
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TPE2, TALB, TPE1

        daily_folder = "/music/Daily"
        if not os.path.exists(daily_folder):
            return

        album_name = "Daily Mix"
        updated_count = 0

        # Process only MP3 files in root directory
        for filename in os.listdir(daily_folder):
            if not filename.lower().endswith('.mp3'):
                continue

            filepath = os.path.join(daily_folder, filename)

            try:
                audio = MP3(filepath, ID3=ID3)

                # Add ID3 tag if it doesn't exist
                if audio.tags is None:
                    audio.add_tags()

                # Set Album Artist to "Various Artists"
                audio.tags.add(TPE2(encoding=3, text="Various Artists"))

                # Set Album name
                audio.tags.add(TALB(encoding=3, text=album_name))

                audio.save()
                updated_count += 1
                logger.info(f"Updated tags: {filename}")

            except Exception as e:
                logger.error(f"Error updating tags for {filename}: {e}")

        logger.info(f"Updated ID3 tags for {updated_count} files")

    except Exception as e:
        logger.error(f"Error updating ID3 tags: {e}")

def create_playlist():
    """Create M3U playlist for Navidrome"""
    try:
        import os

        daily_folder = "/music/Daily"
        if not os.path.exists(daily_folder):
            return

        playlist_name = "Daily Mix.m3u"
        playlist_path = os.path.join(daily_folder, playlist_name)

        # Collect all MP3 files
        mp3_files = []
        for filename in sorted(os.listdir(daily_folder)):
            if filename.lower().endswith('.mp3'):
                mp3_files.append(filename)

        if not mp3_files:
            logger.info("No MP3 files found for playlist")
            return

        # Create M3U playlist
        with open(playlist_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for filename in mp3_files:
                # Write relative path for portability
                f.write(f"{filename}\n")

        logger.info(f"Created playlist: {playlist_name} with {len(mp3_files)} tracks")

    except Exception as e:
        logger.error(f"Error creating playlist: {e}")

def clear_download_queue():
    """Clear all pending downloads from slskd queue"""
    try:
        headers = {'X-API-Key': SLSKD_API_KEY}

        # Get all downloads
        response = requests.get(f"{SLSKD_URL}/api/v0/transfers/downloads", headers=headers)

        if response.status_code != 200:
            logger.warning(f"Could not get downloads list: {response.status_code}")
            return

        downloads = response.json()
        cleared_count = 0

        # Cancel each download
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
                except Exception as e:
                    logger.error(f"Error clearing download {download_id}: {e}")

        logger.info(f"Cleared {cleared_count} pending downloads from queue")

    except Exception as e:
        logger.error(f"Error clearing download queue: {e}")

def job():
    import time
    from datetime import datetime, timedelta

    logger.info("Starting Sync Job...")

    # Set timeout: 30 minutes
    start_time = datetime.now()
    timeout_minutes = 30
    timeout_time = start_time + timedelta(minutes=timeout_minutes)

    tracks = get_spotify_tracks()
    processed_count = 0
    timeout_reached = False

    for track in tracks:
        # Check if timeout reached
        if datetime.now() >= timeout_time:
            logger.warning(f"Timeout reached ({timeout_minutes} minutes). Stopping search and processing remaining files.")
            timeout_reached = True
            break

        exists = check_navidrome_exists(track['artist'], track['title'])
        if exists:
            logger.info(f"Skipping (Exists): {track['artist']} - {track['title']}")
        else:
            logger.info(f"Missing: {track['artist']} - {track['title']}")
            search_and_download_slskd(track['artist'], track['title'])
            processed_count += 1

    elapsed = (datetime.now() - start_time).total_seconds() / 60
    logger.info(f"Sync Job Completed. Processed {processed_count} tracks in {elapsed:.1f} minutes.")

    if timeout_reached:
        logger.info("Clearing download queue due to timeout...")
        clear_download_queue()

    # Post-processing
    logger.info("Starting post-processing...")

    # Wait a bit for downloads to complete
    time.sleep(10)

    # Organize files (move to Daily with Artist - Title format)
    organize_downloaded_files()

    # Update ID3 tags to Various Artists
    update_id3_tags()

    # Create playlist for Navidrome (includes all files in Daily)
    create_playlist()

    # Clean up old files (30+ days)
    cleanup_old_files()

    logger.info("Post-processing completed.")

if __name__ == "__main__":
    logger.info("Bridge Service Started.")
    
    # Run once on startup
    job()
    
    # Schedule every 6 hours
    schedule.every(6).hours.do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(1)
