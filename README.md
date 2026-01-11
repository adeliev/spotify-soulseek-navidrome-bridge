# Spotify-Soulseek-Navidrome Bridge

**[English](#english)** | **[Русский](#русский)**

---

## English

Automatically sync your Spotify playlist to your local music library using Soulseek. This bridge service searches for and downloads missing tracks from your Spotify playlist via the Soulseek network, organizing them for use with Navidrome or other music servers.

### Features

- 🎵 **Automatic Sync**: Syncs Spotify playlist every 6 hours
- 🔍 **Smart Search**: Only searches for tracks missing from your Navidrome library
- 📥 **Quality Filter**: Downloads only MP3 files with 320kbps or higher bitrate
- 🎯 **Intelligent Matching**:
  - Dual-check track matching (direct + transliterated)
  - Supports Cyrillic, Latin, and mixed character sets
  - Flexible artist and title matching in filenames
- 🌍 **Transliteration Support**: Matches tracks across different alphabets (e.g., Russian ↔ English)
- 📁 **Clean Organization**:
  - Downloads to temporary folder (`_Soulseek`)
  - Processes and moves to final destination (`Daily`)
  - Renames files to `Artist - Title.mp3` format
  - Removes clutter: "(Radio Edit)", "Ft.", remixes, etc.
  - Updates ID3 tags while preserving album art
- 🎼 **Playlist Generation**: Creates M3U playlist for Navidrome
- 📂 **Watch Folder**: Process custom playlists manually via `/watch` folder
- 🧹 **Smart Cleanup**:
  - Automatic duplicate detection using library index
  - Removes files older than 30 days
  - Included `cleanup_duplicates.py` utility
- ⏱️ **Timeout Protection**: 30-minute execution limit to prevent excessive runtime

### Architecture

```
┌─────────────┐           ┌─────────────┐
│   Spotify   │           │    Watch    │
│  Playlist   │           │   Folder    │
└──────┬──────┘           └──────┬──────┘
       │                         │
       └──────────┬──────────────┘
                  ▼
┌──────────────────────────────────────────┐
│      Spotify-Soulseek Bridge             │
│  ┌────────────────────────────────────┐  │
│  │  1. Fetch playlist tracks          │  │
│  │  2. Check local library index      │  │
│  │  3. Search Soulseek network        │  │
│  │  4. Download missing tracks        │  │
│  │  5. Organize & tag files           │  │
│  │  6. Remove duplicates              │  │
│  │  7. Create M3U playlist            │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         File Organization                │
│                                          │
│  /downloads/_Soulseek/  →  /music/Daily/ │
│       (temporary)           (permanent)  │
│                                          │
│  user/subdirs/          Artist - Title.mp3│
│  orig_name.mp3          (cleaned tags)   │
│                         Daily Mix.m3u    │
└──────────────────────────────────────────┘
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

   Update `docker-compose.yml` with your paths:
   ```yaml
   volumes:
     # slskd service
     - /path/to/downloads/_Soulseek:/app/downloads  # Temporary download folder

     # bridge service
     - /path/to/music:/music          # Music library root
     - /path/to/downloads:/downloads  # Downloads folder (includes _Soulseek)
     - ./watch:/watch                 # Watch folder for manual playlists
   ```

   Required folder structure:
   - `/downloads/_Soulseek/` - Temporary downloads (auto-cleaned)
   - `/music/Daily/` - Final organized files
   - `/music/library_index.json` - Library index (generated by scan script)
   - `./watch/` - Place manual playlists here (.txt files with Spotify URLs)

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
- [Unidecode](https://github.com/avian2/unidecode) - Transliteration library

## Disclaimer

This tool is for personal use only. Ensure you comply with copyright laws in your jurisdiction. The authors are not responsible for any misuse of this software.

---

## Русский

Автоматическая синхронизация вашего Spotify плейлиста с локальной музыкальной библиотекой через Soulseek. Этот сервис-мост ищет и скачивает недостающие треки из вашего Spotify плейлиста через сеть Soulseek, организуя их для использования с Navidrome или другими музыкальными серверами.

### Возможности

- 🎵 **Автоматическая синхронизация**: Синхронизация Spotify плейлиста каждые 6 часов
- 🔍 **Умный поиск**: Ищет только треки, отсутствующие в вашей библиотеке Navidrome
- 📥 **Фильтр качества**: Скачивает только MP3 файлы с битрейтом 320kbps и выше
- 🎯 **Интеллектуальное сопоставление**:
  - Двойная проверка треков (прямое + транслитерированное совпадение)
  - Поддержка кириллицы, латиницы и смешанных наборов символов
  - Гибкое сопоставление исполнителя и названия в именах файлов
- 🌍 **Поддержка транслитерации**: Находит треки в разных алфавитах (например, русский ↔ английский)
- 📁 **Чистая организация**:
  - Скачивание во временную папку (`_Soulseek`)
  - Обработка и перемещение в конечную папку (`Daily`)
  - Переименование файлов в формат `Исполнитель - Название.mp3`
  - Удаление мусора: "(Radio Edit)", "Ft.", ремиксы и т.д.
  - Обновление ID3 тегов с сохранением обложек
- 🎼 **Генерация плейлистов**: Создание M3U плейлиста для Navidrome
- 📂 **Watch-папка**: Обработка пользовательских плейлистов через папку `/watch`
- 🧹 **Умная очистка**:
  - Автоматическое обнаружение дубликатов через индекс библиотеки
  - Удаление файлов старше 30 дней
  - Включена утилита `cleanup_duplicates.py`
- ⏱️ **Защита от зависания**: 30-минутный лимит выполнения

### Архитектура

```
┌─────────────┐           ┌─────────────┐
│   Spotify   │           │    Watch    │
│  Плейлист   │           │    Папка    │
└──────┬──────┘           └──────┬──────┘
       │                         │
       └──────────┬──────────────┘
                  ▼
┌──────────────────────────────────────────┐
│      Spotify-Soulseek Bridge             │
│  ┌────────────────────────────────────┐  │
│  │  1. Получение треков плейлиста     │  │
│  │  2. Проверка локального индекса    │  │
│  │  3. Поиск в сети Soulseek          │  │
│  │  4. Загрузка недостающих треков    │  │
│  │  5. Организация и тегирование      │  │
│  │  6. Удаление дубликатов            │  │
│  │  7. Создание M3U плейлиста         │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         Организация файлов               │
│                                          │
│  /downloads/_Soulseek/  →  /music/Daily/ │
│       (временная)           (постоянная) │
│                                          │
│  user/subdirs/       Исполнитель - Название.mp3│
│  orig_name.mp3          (очищенные теги) │
│                         Daily Mix.m3u    │
└──────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  Navidrome  │
│    Сервер   │
└─────────────┘
```

### Требования

- Docker и Docker Compose
- Аккаунт Spotify Developer (для доступа к API)
- Музыкальный сервер Navidrome (опционально, для проверки библиотеки)
- Аккаунт Soulseek

### Установка

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/adeliev/spotify-soulseek-navidrome-bridge.git
   cd spotify-soulseek-navidrome-bridge
   ```

2. **Создайте конфигурационные файлы**

   Скопируйте примеры файлов:
   ```bash
   cp .env.example .env
   cp slskd/config/slskd.yml.example slskd/config/slskd.yml
   ```

3. **Настройте переменные окружения**

   Отредактируйте `.env` с вашими данными:
   ```bash
   # Spotify API (получите на https://developer.spotify.com/dashboard)
   SPOTIFY_CLIENT_ID=ваш_client_id
   SPOTIFY_CLIENT_SECRET=ваш_client_secret
   SPOTIFY_PLAYLIST_ID=spotify:playlist:ваш_playlist_id

   # Navidrome
   NAVIDROME_USER=ваш_логин
   NAVIDROME_PASS=ваш_пароль

   # Soulseek
   SLSKD_SLSK_USERNAME=ваш_soulseek_логин
   SLSKD_SLSK_PASSWORD=ваш_soulseek_пароль

   # Slskd API Key (должен совпадать с slskd.yml)
   SLSKD_API_KEY=ваш_api_key
   ```

4. **Настройте slskd**

   Отредактируйте `slskd/config/slskd.yml`:
   ```yaml
   web:
     authentication:
       api_keys:
         bridge:
           key: ваш_api_key  # Должен совпадать с .env
           role: administrator
   soulseek:
     username: ваш_soulseek_логин
     password: ваш_soulseek_пароль
   ```

5. **Настройте директории**

   Обновите `docker-compose.yml` с вашими путями:
   ```yaml
   volumes:
     # Сервис slskd
     - /путь/к/downloads/_Soulseek:/app/downloads  # Временная папка загрузок

     # Сервис bridge
     - /путь/к/music:/music          # Корень музыкальной библиотеки
     - /путь/к/downloads:/downloads  # Папка загрузок (включает _Soulseek)
     - ./watch:/watch                # Watch-папка для ручных плейлистов
   ```

   Требуемая структура папок:
   - `/downloads/_Soulseek/` - Временные загрузки (автоматически очищается)
   - `/music/Daily/` - Финальные организованные файлы
   - `/music/library_index.json` - Индекс библиотеки (создается скриптом сканирования)
   - `./watch/` - Сюда помещайте ручные плейлисты (.txt файлы со Spotify URL)

6. **Запустите сервисы**
   ```bash
   docker compose up -d
   ```

### Как это работает

#### Цикл синхронизации (каждые 6 часов)

1. **Получение треков**: Загружает до 50 треков из вашего Spotify плейлиста
2. **Проверка библиотеки**: Проверяет индекс библиотеки, чтобы пропустить имеющиеся треки
3. **Поиск и загрузка** (таймаут 30 минут):
   - Ищет недостающие треки в Soulseek
   - Скачивает первый подходящий MP3 файл ≥320kbps
   - Сохраняет в `_Soulseek/` с оригинальной структурой папок
4. **Пост-обработка**:
   - Извлекает исполнителя/название из ID3 тегов
   - Переименовывает в формат `Исполнитель - Название.mp3`
   - Перемещает в папку `Daily/` (плоская структура)
   - Обновляет ID3 теги: Album Artist = "Various Artists", Album = "Daily Mix"
   - Создает/обновляет плейлист `Daily Mix.m3u` со всеми файлами
   - Очищает папку `_Soulseek/`
   - Удаляет файлы старше 30 дней из `Daily/`

#### Пример обработки файлов

```
До:
/downloads/_Soulseek/
  ├── Название альбома (2024)/
  │   └── 01 - Название песни.mp3
  └── Various/
      └── track.mp3

После:
/music/Daily/
  ├── Имя исполнителя - Название песни.mp3
  ├── Другой исполнитель - Название трека.mp3
  └── Daily Mix.m3u

/downloads/_Soulseek/
  (пусто - очищено)
```

### Утилиты

#### cleanup_duplicates.py

Утилита для поиска и удаления дубликатов в папке Daily:

```bash
# Запустите на хосте (вне Docker)
python3 cleanup_duplicates.py
```

Скрипт:
- Сравнивает файлы в Daily с индексом библиотеки
- Использует нормализацию строк и транслитерацию
- Удаляет дубликаты, уже существующие в основной библиотеке

### Конфигурация

#### Настройки таймаута

Скрипт имеет 30-минутный таймаут. Измените в `bridge/main.py`:

```python
timeout_minutes = 30  # Измените это значение
```

#### Период очистки

Файлы хранятся 30 дней по умолчанию. Измените в `bridge/main.py`:

```python
cutoff_time = datetime.now() - timedelta(days=30)  # Измените дни
```

#### Расписание синхронизации

По умолчанию каждые 6 часов. Измените в `bridge/main.py`:

```python
schedule.every(6).hours.do(job)  # Измените интервал
```

### Мониторинг

Просмотр логов:
```bash
# Логи сервиса bridge
docker logs spotify-soulseek-bridge -f

# Логи slskd
docker logs slskd -f
```

Проверка статуса загрузок:
- Откройте http://localhost:5030 в браузере
- Войдите с вашими Soulseek данными
- Перейдите в раздел Downloads

### Решение проблем

#### Загрузки не начинаются
1. Проверьте подключение slskd: `docker logs slskd | grep "Logged in"`
2. Убедитесь, что API ключ совпадает в `.env` и `slskd.yml`
3. Проверьте результаты поиска: `docker logs spotify-soulseek-bridge | grep "Got.*responses"`

#### Файлы не организуются
1. Убедитесь, что папка music смонтирована с правами на запись (без флага `:ro`)
2. Проверьте логи пост-обработки: `docker logs spotify-soulseek-bridge | grep "Organized"`

#### Ошибки аутентификации
- 401 Unauthorized: Несовпадение API ключа
- 404 Not Found: Неправильный API endpoint
- Проверьте заголовки: `X-API-Key` должен быть установлен корректно

### Docker Compose сервисы

- **slskd**: Soulseek клиент с веб-интерфейсом
  - Веб-интерфейс: http://localhost:5030
  - Обрабатывает поиск и загрузку

- **bridge**: Python сервис синхронизации
  - Запускается каждые 6 часов
  - Управляет рабочим процессом синхронизации

### Сетевая архитектура

```
bridge ──API──> slskd ──Soulseek──> Сеть
  │
  └──API──> navidrome (проверка библиотеки)
```

### Права доступа к файлам

Сервису bridge требуется доступ на чтение-запись к:
- `/downloads/_Soulseek/` - Для очистки загрузок
- `/music/Daily/` - Для организации файлов и обновления тегов

### Участие в разработке

Вклад приветствуется! Не стесняйтесь отправлять Pull Request.

### Лицензия

MIT License - См. файл LICENSE для деталей

### Благодарности

- [slskd](https://github.com/slskd/slskd) - Soulseek клиент
- [Spotipy](https://github.com/spotipy-dev/spotipy) - Библиотека Spotify API
- [Mutagen](https://github.com/quodlibet/mutagen) - Библиотека для работы с аудио метаданными
- [Unidecode](https://github.com/avian2/unidecode) - Библиотека транслитерации

### Отказ от ответственности

Этот инструмент предназначен только для личного использования. Убедитесь, что вы соблюдаете законы об авторском праве в вашей юрисдикции. Авторы не несут ответственности за любое неправомерное использование этого программного обеспечения.
