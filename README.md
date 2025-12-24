# Spotify-Soulseek Bridge

Automatically sync your Spotify playlist to your local music library using Soulseek. This bridge service searches for and downloads missing tracks from your Spotify playlist via the Soulseek network, organizing them for use with Navidrome or other music servers.

## Features

- 🎵 **Automatic Sync**: Syncs Spotify playlist every 6 hours
- 🔍 **Smart Search**: Only searches for tracks missing from your Navidrome library
- 📥 **Quality Filter**: Downloads only MP3 files with 320kbps or higher bitrate
- 🎯 **Intelligent Matching**: Flexible artist and title matching in filenames
- 📁 **Clean Organization**:
  - Downloads to temporary folder (`_Soulseek`)
  - Processes and moves to final destination (`Daily`)
  - Renames files to `Artist - Title.mp3` format
  - Updates ID3 tags (Album Artist: "Various Artists", Album: "Daily Mix")
- 🎼 **Playlist Generation**: Creates M3U playlist for Navidrome
- ⏰ **Auto-cleanup**: Removes files older than 30 days
- ⏱️ **Timeout Protection**: 30-minute execution limit to prevent excessive runtime

## Architecture

```
┌─────────────┐
│   Spotify   │
│  Playlist   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│     Spotify-Soulseek Bridge         │
│  ┌───────────────────────────────┐  │
│  │  1. Fetch playlist tracks     │  │
│  │  2. Check Navidrome library   │  │
│  │  3. Search Soulseek network   │  │
│  │  4. Download missing tracks   │  │
│  │  5. Organize & tag files      │  │
│  │  6. Create M3U playlist       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│        File Organization            │
│                                     │
│  _Soulseek/  →  Daily/              │
│  (temporary)    (permanent)         │
│                                     │
│  subdirs/       Artist - Title.mp3  │
│  files.mp3      (Various Artists)   │
│                 Daily Mix.m3u       │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  Navidrome  │
│    Server   │
└─────────────┘
```

## Prerequisites

- Docker and Docker Compose
- Spotify Developer Account (for API access)
- Navidrome music server (optional, for library checking)
- Soulseek account

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/spotify-soulseek-bridge.git
   cd spotify-soulseek-bridge
   ```

2. **Create configuration files**

   Copy the example files:
   ```bash
   cp .env.example .env
   cp slskd/config/slskd.yml.example slskd/config/slskd.yml
   ```

3. **Configure environment variables**

   Edit `.env` with your credentials:
   ```bash
   # Spotify API (get from https://developer.spotify.com/dashboard)
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_PLAYLIST_ID=spotify:playlist:your_playlist_id

   # Navidrome
   NAVIDROME_USER=your_username
   NAVIDROME_PASS=your_password

   # Soulseek
   SLSKD_SLSK_USERNAME=your_soulseek_username
   SLSKD_SLSK_PASSWORD=your_soulseek_password

   # Slskd API Key (must match slskd.yml)
   SLSKD_API_KEY=your_api_key
   ```

4. **Configure slskd**

   Edit `slskd/config/slskd.yml`:
   ```yaml
   web:
     authentication:
       api_keys:
         bridge:
           key: your_api_key  # Must match .env
           role: administrator
   soulseek:
     username: your_soulseek_username
     password: your_soulseek_password
   ```

5. **Set up directories**

   Update `docker-compose.yml` with your music paths:
   ```yaml
   volumes:
     - /path/to/your/music/_Soulseek:/app/downloads  # Temporary download folder
     - /path/to/your/music:/music  # Music library root
   ```

   Your music folder should contain:
   - `_Soulseek/` - Temporary downloads (auto-cleaned)
   - `Daily/` - Final organized files

6. **Start the services**
   ```bash
   docker compose up -d
   ```

## How It Works

### Sync Cycle (Every 6 Hours)

1. **Fetch Tracks**: Retrieves up to 50 tracks from your Spotify playlist
2. **Check Library**: Queries Navidrome to skip tracks you already have
3. **Search & Download** (30-minute timeout):
   - Searches Soulseek for missing tracks
   - Downloads first matching MP3 file ≥320kbps
   - Saves to `_Soulseek/` with original folder structure
4. **Post-Processing**:
   - Extracts artist/title from ID3 tags
   - Renames to `Artist - Title.mp3` format
   - Moves to `Daily/` folder (flat structure)
   - Updates ID3 tags: Album Artist = "Various Artists", Album = "Daily Mix"
   - Creates/updates `Daily Mix.m3u` playlist with all files
   - Cleans up `_Soulseek/` folder
   - Removes files older than 30 days from `Daily/`

### File Processing Example

```
Before:
_Soulseek/
  ├── Album Name (2024)/
  │   └── 01 - Song Title.mp3
  └── Various/
      └── track.mp3

After:
Daily/
  ├── Artist Name - Song Title.mp3
  ├── Another Artist - Track Name.mp3
  └── Daily Mix.m3u

_Soulseek/
  (empty - cleaned up)
```

## Configuration

### Timeout Settings

The script has a 30-minute timeout to prevent excessive runtime. Adjust in `bridge/main.py`:

```python
timeout_minutes = 30  # Change this value
```

### Cleanup Period

Files are kept for 30 days by default. Adjust in `bridge/main.py`:

```python
cutoff_time = datetime.now() - timedelta(days=30)  # Change days
```

### Sync Schedule

Default is every 6 hours. Adjust in `bridge/main.py`:

```python
schedule.every(6).hours.do(job)  # Change interval
```

## Monitoring

View logs:
```bash
# Bridge service logs
docker logs spotify-soulseek-bridge -f

# Slskd logs
docker logs slskd -f
```

Check download status:
- Open http://localhost:5030 in your browser
- Login with your Soulseek credentials
- Navigate to Downloads section

## Troubleshooting

### No downloads happening
1. Check slskd is connected: `docker logs slskd | grep "Logged in"`
2. Verify API key matches between `.env` and `slskd.yml`
3. Check search results: `docker logs spotify-soulseek-bridge | grep "Got.*responses"`

### Files not organizing
1. Ensure music folder is mounted read-write (no `:ro` flag)
2. Check post-processing logs: `docker logs spotify-soulseek-bridge | grep "Organized"`

### Authentication errors
- 401 Unauthorized: API key mismatch
- 404 Not Found: Incorrect API endpoint
- Check headers: `X-API-Key` must be set correctly

## Docker Compose Services

- **slskd**: Soulseek client with web UI
  - Web UI: http://localhost:5030
  - Handles search and download operations

- **bridge**: Python sync service
  - Runs every 6 hours
  - Manages the sync workflow

## Network Architecture

```
bridge ──API──> slskd ──Soulseek──> Network
  │
  └──API──> navidrome (library check)
```

## File Permissions

The bridge service needs read-write access to:
- `/music/_Soulseek/` - For cleaning up downloads
- `/music/Daily/` - For organizing files and updating tags

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - See LICENSE file for details

## Credits

- [slskd](https://github.com/slskd/slskd) - Soulseek client
- [Spotipy](https://github.com/spotipy-dev/spotipy) - Spotify API library
- [Mutagen](https://github.com/quodlibet/mutagen) - Audio metadata library

## Disclaimer

This tool is for personal use only. Ensure you comply with copyright laws in your jurisdiction. The authors are not responsible for any misuse of this software.
