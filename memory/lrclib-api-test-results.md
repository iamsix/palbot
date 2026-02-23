# LRCLIB API Test Results

## API Requirements
**CRITICAL:** API requires BOTH `track_name` AND `artist_name` parameters
- ❌ ERROR: `missing field track_name` (only artist)
- ❌ ERROR: `missing field artist_name` (only track)
- ✅ SUCCESS: Both parameters present

## Test Cases

### 1. Successful Song Search ✅
**Query:** `artist_name=Queen&track_name=Bohemian+Rhapsody`
- Status: 200
- Returns full lyrics with synced version
- Database: 3M+ tracks

### 2. Not Found (404) ✅
**Query:** `artist_name=Unknown+Artist&track_name=This+Song+Does+Not+Exist`
- Status: 404
- Response: `{"message":"Failed to find specified track","name":"TrackNotFound","statusCode":404}`

### 3. Instrumental Track ✅
**Query:** `artist_name=John+Lennon&track_name=Imagine`
- Status: 200
- `instrumental: false` (song has lyrics)
- Note: Need to find actual instrumental for test

## API Response Structure

### Successful Response (200)
```json
{
  "id": 19079,
  "name": "Bohemian Rhapsody",
  "trackName": "Bohemian Rhapsody",
  "artistName": "Queen",
  "albumName": "Stone Cold Classics",
  "duration": 355,
  "instrumental": false,
  "plainLyrics": "Full text lyrics",
  "syncedLyrics": "[00:00.15] Line 1\n[00:07.13] Line 2..."
}
```

### Error Response (404)
```json
{
  "message": "Failed to find specified track",
  "name": "TrackNotFound",
  "statusCode": 404
}
```

## Key Fields

| Field | Type | Description |
|------|------|-------------|
| `id` | integer | Unique track identifier |
| `name` | string | Full song name |
| `trackName` | string | Track name only |
| `artistName` | string | Artist name |
| `albumName` | string | Album name |
| `duration` | integer | Duration in seconds |
| `instrumental` | boolean | True if instrumental (no lyrics) |
| `plainLyrics` | string | Full lyrics text |
| `syncedLyrics` | string | LRC format synced lyrics |

## Implementation Notes

1. **Required parameters:** Both `artist_name` AND `track_name` must be provided
2. **Error handling:** Check HTTP status, return user-friendly message if 404
3. **Instrumental detection:** Skip if `instrumental: true`
4. **No API key required** - free to use
5. **Response format:** JSON from GET request
6. **Base URL:** `https://lrclib.net/api/get`
