# LRCLIB Lyrics Implementation

## Overview
Replaced Genius API with LRCLIB for lyrics fetching. Implemented song-only search with automatic first-result selection.

## Why LRCLIB?
- **Free** - no API key required
- **No rate limits** mentioned
- **Open source** (unlike Genius)
- **Two lyric formats:**
  - `plainLyrics` - full text lyrics
  - `syncedLyrics` - timed LRC format
- **Metadata included:** artist, track, album, duration, instrumental flag
- **3M+ lyrics available**

## API Endpoints

### Search Endpoint
```
GET https://lrclib.net/api/search?q={song_title}
```
- Returns list of matching results
- Each result includes `id`, `trackName`, `artistName`, `albumName`
- User only needs to provide song title (no artist required)

### Get Cached Endpoint
```
GET https://lrclib.net/api/get-cached?id={id}
```
- Retrieves lyrics for a specific track
- Uses cached responses for efficiency
- Faster than standard `/get` endpoint

### Response Format
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

## Implementation Details

### Module File
- **Location:** `modules/lrclib.py`
- **Replaces:** Old `lyrics.py` implementation (Genius API)
- **No new dependencies** - uses aiohttp for HTTP requests

### Command Usage
```
!lyrics <song_title>
```
Examples:
- `!lyrics "Bohemian Rhapsody"`
- `!lyrics "Imagine"`
- `!lyrics "Billie Jean"`

### Flow
1. Search API with song title → `/api/search?q={song}`
2. Take first result (automatic selection)
3. Get lyrics with `/api/get-cached?id={result_id}`
4. Display formatted lyrics

### Output Format
- Song name and artist (from search result)
- Album name (if available)
- Full lyrics from `plainLyrics`
- Optional: synced lyrics indicator from `syncedLyrics`

## Error Handling

### Error Types
1. **Search API Error** (status ≠ 200)
   - Log full error text
   - Display truncated error to user

2. **No Results Found**
   - User-friendly message
   - Log warning

3. **Missing Result ID**
   - Log error with result data
   - Display invalid format error

4. **Get API Error** (status ≠ 200)
   - Log full error text
   - Display truncated error

5. **Track Not Found**
   - User-friendly message
   - Log warning

6. **Instrumental Track**
   - Display "Instrumental Track" message
   - Log info

7. **No Lyrics Available**
   - User-friendly message
   - Log warning

8. **Network Errors**
   - Log with traceback
   - Display network error message

9. **JSON Parsing Errors**
   - Log full error
   - Display invalid API response error

### Logging
- Log all API requests with parameters
- Log selected result details (track, artist, ID)
- Log errors with full traceback (`exc_info=True`)
- Log warnings for edge cases

## Testing

### Test Cases
- ✅ Popular songs with unique titles
- ✅ Songs with multiple versions
- ✅ Instrumental tracks
- ✅ Songs not found in LRCLIB

### Test Results
All tests passed successfully with proper error handling.

## Notes
- Database has ~3M+ lyrics
- Free for commercial use
- MIT-like license (ISC)
- Auto-selection reduces user friction (no need to type artist)
- Cached endpoint improves performance
- Comprehensive logging aids debugging
