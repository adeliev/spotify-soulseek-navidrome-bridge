# Spotify-Soulseek Bridge

Automatically syncs tracks from Spotify playlists (via spotify-extract) to your local music library using Soulseek.

## Features

- 🎵 Downloads tracks from M3U playlists (Daily Mix, Release Radar)
- 🔍 Searches Soulseek network for missing tracks
- 📥 Quality filter: 320kbps+ MP3 only
- 🌍 Transliteration support (Latin ↔ Cyrillic)
- 🏷️ Updates ID3 tags while preserving album art
- 📁 Organizes files as `Artist - Title.mp3`
- 🎼 Creates NSP playlist for Navidrome

## Architecture

```
spotify-extract → data/watch/Daily.m3u → bridge → slskd → Soulseek
                                                    ↓
                                              /downloads/_Soulseek
                                                    ↓
                                              /music/Daily/
```

## Setup

```bash
# Copy example configs
cp .env.example .env
cp artist_aliases.txt.example data/artist_aliases.txt
cp slskd/config/slskd.yml.example slskd/config/slskd.yml

# Edit configs with your credentials
nano .env
nano slskd/config/slskd.yml
nano data/artist_aliases.txt

# Build and run
docker compose build
docker compose up -d
```

## Project Structure

```
spotify-soulseek-bridge/
├── bridge/
│   ├── main.py             # Main sync script
│   ├── scan_library.py     # Library index generator
│   ├── Dockerfile         # Bridge container
│   └── requirements.txt   # Python dependencies
├── slskd/
│   └── config/
│       └── slskd.yml.example  # Soulseek config template
├── data/                   # Runtime data (gitignored)
│   ├── watch/               # M3U playlists from spotify-extract
│   │   ├── Daily.m3u.processed
│   │   └── ReleaseRadar.m3u.processed
│   └── artist_aliases.txt  # Artist name aliases
├── docker-compose.yml      # Orchestration (slskd + bridge)
├── .env.example           # Environment template
└── artist_aliases.txt.example  # Aliases template
```

## Configuration Files

### .env
```
SLSKD_SLSK_USERNAME=your_soulseek_username
SLSKD_SLSK_PASSWORD=your_soulseek_password
SLSKD_API_KEY=your_api_key
```

### artist_aliases.txt
Match tracks across different alphabets:
```
Kino = Кино
Aria = Ария
```

## Utilities

### scan_library.py
Creates `library_index.json` from your music library. Used by bridge to find existing tracks.

Run manually:
```bash
python3 scan_library.py
```

Or inside container:
```bash
docker compose exec bridge python /app/scan_library.py
```

**Note**: This is a standalone utility that can be run from anywhere with proper paths.

## Usage

### Automatic sync
Bridge automatically processes M3U files from `data/watch/`.

### Manual sync via watch folder
Drop M3U or TXT files into `data/watch/`:
- M3U format: `#EXTM3U\nArtist - Title`
- TXT format: `Artist - Title` (one per line)

### Rebuild library index
```bash
docker compose exec bridge python scan_library.py
```

### View logs
```bash
docker logs spotify-soulseek-bridge -f
```

## Environment Variables

- `FORCE_SCRAPE=1` — Force scraping (not used in bridge, for spotify-extract)
- `LOG_LEVEL=INFO` — Logging verbosity

## License

MIT
