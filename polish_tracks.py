#!/usr/bin/env python3
"""Polish MP3 tags in Daily and ReleaseRadar folders."""

import os
import re
import logging
from datetime import datetime
from mutagen.mp3 import MP3, ID3
from mutagen.id3 import TPE1, TPE2, TIT2, TALB, TCMP, TCOM, TCON, APIC
from mutagen.id3 import ID3NoHeaderError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
DAILY_DIR = "/music/Daily"
RADAR_DIR = "/music/ReleaseRadar"

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

def parse_filename(filename):
    """Parse Artist - Title from filename."""
    name_no_ext = os.path.splitext(filename)[0]
    if " - " in name_no_ext:
        parts = name_no_ext.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return None, None

def polish_tags(filepath, is_downloaded):
    """Polish MP3 tags according to requirements."""
    try:
        audio = MP3(filepath)
    except ID3NoHeaderError:
        logger.warning(f"No ID3 tags in {os.path.basename(filepath)}")
        return False

    modified = False

    # 1. Delete track and discnumber tags
    if 'TRCK' in audio.tags:
        del audio.tags['TRCK']
        modified = True
    if 'TPOS' in audio.tags:
        del audio.tags['TPOS']
        modified = True

    # Get current artist and title from tags
    tag_artist = repair_encoding(str(audio.tags.get('TPE1', '')))
    tag_title = repair_encoding(str(audio.tags.get('TIT2', '')))

    # 2. If tags missing, try to parse from filename
    if not tag_artist or not tag_title:
        filename_artist, filename_title = parse_filename(os.path.basename(filepath))
        if filename_artist and filename_title:
            if not tag_artist:
                audio.tags['TPE1'] = TPE1(encoding=3, text=clean_string(filename_artist))
                modified = True
                logger.info(f"Added artist from filename: {filename_artist}")
            if not tag_title:
                audio.tags['TIT2'] = TIT2(encoding=3, text=clean_string(filename_title))
                modified = True
                logger.info(f"Added title from filename: {filename_title}")

    # 4. If no album tag, add "Daily Mix"
    if 'TALB' not in audio.tags or not audio.tags['TALB']:
        album_name = "Release Radar" if "/ReleaseRadar/" in filepath else "Daily Mix"
        audio.tags['TALB'] = TALB(encoding=3, text=album_name)
        modified = True
        logger.info(f"Added album: {album_name}")

    # 5. For downloaded tracks: add albumartist = Various Artists and compilation = 1
    if is_downloaded:
        if 'TPE2' not in audio.tags or not audio.tags['TPE2']:
            audio.tags['TPE2'] = TPE2(encoding=3, text='Various Artists')
            modified = True
            logger.info(f"Added album artist: Various Artists")
        if 'TCMP' not in audio.tags or not audio.tags['TCMP']:
            audio.tags['TCMP'] = TCMP(encoding=3, text='1')
            modified = True
            logger.info(f"Set compilation = 1")

    # 6. Fix genres: split with commas
    if 'TCON' in audio.tags and audio.tags['TCON']:
        genres = str(audio.tags['TCON'])
        # Replace semicolons with comma + space
        if ';' in genres:
            new_genres = ', '.join(g.strip() for g in genres.split(';'))
            if new_genres != genres:
                audio.tags['TCON'] = TCON(encoding=3, text=new_genres)
                modified = True
                logger.info(f"Fixed genres: {genres} => {new_genres}")

    # 3. Preserve album art (already preserved by mutagen on save)
    # Just ensure we save the file

    if modified:
        audio.save()
        logger.info(f"Updated tags: {os.path.basename(filepath)}")

    return modified

def process_directory(directory, is_downloaded=True):
    """Process all MP3 files in directory."""
    if not os.path.exists(directory):
        logger.warning(f"Directory not found: {directory}")
        return

    files = [f for f in os.listdir(directory) if f.lower().endswith('.mp3')]
    logger.info(f"Processing {len(files)} files in {directory}...")

    updated_count = 0
    for filename in files:
        filepath = os.path.join(directory, filename)
        if polish_tags(filepath, is_downloaded):
            updated_count += 1

    logger.info(f"Updated {updated_count} files in {directory}")
    return updated_count

def main():
    logger.info("=" * 50)
    logger.info("MP3 Tag Polisher")
    logger.info("=" * 50)

    total_updated = 0

    # Process Daily folder (downloaded tracks)
    total_updated += process_directory(DAILY_DIR, is_downloaded=True)

    # Process ReleaseRadar folder (downloaded tracks)
    total_updated += process_directory(RADAR_DIR, is_downloaded=True)

    logger.info("=" * 50)
    logger.info(f"Total files updated: {total_updated}")
    logger.info("=" * 50)

if __name__ == "__main__":
    main()
