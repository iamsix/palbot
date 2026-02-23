# LRCLIB Lyrics Implementation

## Overview
Replaced Genius API with LRCLIB for lyrics fetching.

## Why LRCLIB?
- **Free** - no API key required
- **No rate limits** mentioned
- **Open source** (unlike Genius)
- **Two lyric formats:**
  - `plainLyrics` - full text lyrics
  - `syncedLyrics` - timed LRC format
- **Metadata included:** artist, track, album, duration, instrumental flag
- **Endpoint:** `https://lrclib.net/api/get`

## API Endpoint
```
GET https://lrclib.net/api/get?artist_name={artist}&track_name={track}
```

## Response Format
```json
{
  "id": 13781,
  "name": "Hey Jude",
  "trackName": "Hey Jude",
  "artistName": "The Beatles",
  "albumName": "The Beatles 1967-1970 (The Blue Album)",
  "duration": 431,
  "instrumental": false,
  "plainLyrics": "Full lyrics text here...",
  "syncedLyrics": "[00:00.35] First line\n[00:06.74] Second line..."
}
```

## Implementation Plan

### 1. Create new module file
- File: `modules/lrclib.py`
- Replace old `lyrics.py` (removed)

### 2. Dependencies
No new dependencies needed - uses aiohttp for HTTP requests

### 3. Command Usage
```
!lyrics <song> - <artist>
!lyrics <search query>
```

### 4. Output Format
- Song name and artist
- Full lyrics from `plainLyrics`
- Optional: synced lyrics from `syncedLyrics`
- Link to LRCLIB page (optional)

### 5. Error Handling
- No lyrics found: "Could not find lyrics"
- Instrumental tracks: skip or show message
- API errors: return error message

## Testing
Tested with:
- "Hey Jude" - The Beatles
- "Creep" - Radiohead

Both returned complete lyrics successfully.

## Notes
- Database has ~3M+ lyrics
- Free for commercial use
- MIT-like license (ISC)
