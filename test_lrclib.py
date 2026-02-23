#!/usr/bin/env python3
"""
Test script for LRCLIB lyrics module
"""
import sys
import asyncio
from urllib.parse import quote

async def test_lrclib_api():
    """Test the LRCLIB API directly"""
    from aiohttp import ClientSession

    async with ClientSession() as session:
        # Test 1: Successful search
        print("Test 1: Successful search - Bohemian Rhapsody - Queen")
        params = {
            "artist_name": "Queen",
            "track_name": "Bohemian Rhapsody"
        }
        
        async with session.get("https://lrclib.net/api/get", params=params) as resp:
            data = await resp.json()
            if "message" in data:
                print(f"  ❌ Error: {data['message']}")
            else:
                print(f"  ✅ Found: {data['trackName']} by {data['artistName']}")
                print(f"  Duration: {data['duration']}s")
                print(f"  Instrumental: {data['instrumental']}")
                print(f"  Lyrics length: {len(data['plainLyrics'])} chars")

        # Test 2: Not found
        print("\nTest 2: Not found - Unknown Song - Unknown Artist")
        params = {
            "artist_name": "Unknown Artist",
            "track_name": "This Song Does Not Exist"
        }
        
        async with session.get("https://lrclib.net/api/get", params=params) as resp:
            data = await resp.json()
            if "message" in data and data["message"] == "Failed to find specified track":
                print(f"  ✅ Correctly returned 404: {data['message']}")
            else:
                print(f"  ⚠️  Unexpected response")

        # Test 3: Alternative format
        print("\nTest 3: Alternative format - Billie Jean - Michael Jackson")
        params = {
            "artist_name": "Michael Jackson",
            "track_name": "Billie Jean"
        }
        
        async with session.get("https://lrclib.net/api/get", params=params) as resp:
            data = await resp.json()
            if "message" in data:
                print(f"  ❌ Error: {data['message']}")
            else:
                print(f"  ✅ Found: {data['trackName']} by {data['artistName']}")
                print(f"  Album: {data['albumName']}")

        # Test 4: Check response structure
        print("\nTest 4: Response structure validation")
        params = {
            "artist_name": "John Lennon",
            "track_name": "Imagine"
        }
        
        async with session.get("https://lrclib.net/api/get", params=params) as resp:
            data = await resp.json()
            
            required_fields = ['id', 'trackName', 'artistName', 'plainLyrics', 'syncedLyrics', 'duration', 'instrumental']
            all_present = all(field in data for field in required_fields)
            
            if all_present:
                print(f"  ✅ All required fields present")
                print(f"  Synced lyrics available: {bool(data['syncedLyrics'])}")
                print(f"  Synced lyrics length: {len(data['syncedLyrics'])} chars")
            else:
                print(f"  ❌ Missing fields: {[f for f in required_fields if f not in data]}")

async def test_command_parsing():
    """Test command parsing logic"""
    print("\n" + "="*50)
    print("Command Parsing Tests")
    print("="*50)
    
    test_cases = [
        ("Bohemian Rhapsody - Queen", "Bohemian Rhapsody", "Queen"),
        ("Billie Jean Michael Jackson", "Billie Jean", "Michael Jackson"),
        ("Imagine John Lennon", "Imagine", "John Lennon"),
    ]
    
    for query, expected_song, expected_artist in test_cases:
        parts = query.split('-')
        song = parts[0].strip() if len(parts) > 0 else ""
        artist = parts[1].strip() if len(parts) > 1 else ""
        
        if song == expected_song and artist == expected_artist:
            print(f"  ✅ '{query}' → song='{song}', artist='{artist}'")
        else:
            print(f"  ❌ '{query}' → song='{song}', artist='{artist}' (expected: song='{expected_song}', artist='{expected_artist}')")

if __name__ == "__main__":
    print("LRCLIB Lyrics Module Tests")
    print("=" * 50)
    
    asyncio.run(test_lrclib_api())
    test_command_parsing()
    
    print("\n" + "="*50)
    print("All tests completed!")
