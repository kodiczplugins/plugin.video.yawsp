#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import xml.etree.ElementTree as ET

# Try to load dotenv if available, otherwise use manual env vars
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("dotenv not available - please set environment variables manually or create .env file")

try:
    from urllib import urlencode
    from urllib2 import urlopen, Request, HTTPError
except ImportError:
    from urllib.parse import urlencode
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError

import re
import requests
import hashlib
from md5crypt import md5crypt

# Production API settings (copied from yawsp.py)
BASE = 'https://webshare.cz'
API = BASE + '/api/'
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
HEADERS = {'User-Agent': UA, 'Referer': BASE}
REALM = ':Webshare:'

# Create session like production code
_session = requests.Session()
_session.headers.update(HEADERS)

# Copy the business logic functions from series_manager.py
def _normalize(text):
    """Normalize text for comparisons."""
    # Replace non-word characters (including underscore) with spaces and
    # convert to lower case for easier matching.
    return re.sub(r'[\W_]+', ' ', text).strip().lower()

def _is_series_match(filename, series_name):
    """Check if filename contains the series name with flexible matching."""
    norm_fn = _normalize(filename)
    norm_sn = _normalize(series_name)
    
    # Split series name into words for flexible matching
    series_words = norm_sn.split()
    
    # If series name is a single word, check if it appears as a word boundary
    if len(series_words) == 1:
        # Use word boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(series_words[0]) + r'\b'
        return bool(re.search(pattern, norm_fn))
    
    # For multi-word series names, check if all words appear in order
    # This allows for some flexibility in separators
    for word in series_words:
        if word not in norm_fn:
            return False
    
    return True

def _detect_episode_info(filename, series_name):
    """Try to detect season and episode numbers from filename"""
    # Regular expressions for detecting episode patterns
    EPISODE_PATTERNS = [
        r'[Ss](\d+)[Ee](\d+)',  # S01E01 format
        r'(\d+)x(\d+)',         # 1x01 format
        r'[Ee]pisode\s*(\d+)',  # Episode 1 format
        r'[Ee]p\s*(\d+)',       # Ep 1 format
        r'[Ee](\d+)',           # E1 format
        r'(\d+)\.\s*(\d+)'      # 1.01 format
    ]
    
    # Normalize filename and series name for easier matching
    norm_fn = _normalize(filename)
    norm_sn = _normalize(series_name)

    # Remove the series name from the filename more intelligently
    cleaned = norm_fn
    series_words = norm_sn.split()
    for word in series_words:
        # Remove each word of the series name with word boundaries
        pattern = r'\b' + re.escape(word) + r'\b'
        cleaned = re.sub(pattern, '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Try each of our patterns
    for pattern in EPISODE_PATTERNS:
        match = re.search(pattern, cleaned)
        if match:
            groups = match.groups()
            if len(groups) == 2:  # Patterns like S01E02
                return int(groups[0]), int(groups[1])
            elif len(groups) == 1:  # Patterns like Episode 5
                # Assume season 1 if only episode number is found
                return 1, int(groups[0])
    
    # If no match found, try to infer from the filename
    if 'season' in cleaned or 'serie' in cleaned:
        # Try to find season number
        season_match = re.search(r'season\s*(\d+)', cleaned)
        if season_match:
            season_num = int(season_match.group(1))
            # Try to find episode number
            ep_match = re.search(r'(\d+)', cleaned.replace(season_match.group(0), ''))
            if ep_match:
                return season_num, int(ep_match.group(1))
    
    # Default fallback
    return None, None

def api(fnct, data):
    """Production API function (copied from yawsp.py)"""
    response = _session.post(API + fnct + "/", data=data)
    return response

def is_ok(xml):
    """Check if API response is OK (copied from yawsp.py)"""
    status = xml.find('status').text
    return status == 'OK'

def login_to_webshare():
    """Login to Webshare using production method (copied from yawsp.py)"""
    username = os.getenv('WEBSHARE_USERNAME')
    password = os.getenv('WEBSHARE_PASSWORD')
    
    if not username or not password:
        print("ERROR: Please set WEBSHARE_USERNAME and WEBSHARE_PASSWORD in .env file")
        return None
    
    print(f"Logging in as: {username}")
    
    # First get salt (production method)
    response = api('salt', {'username_or_email': username})
    xml = ET.fromstring(response.content)
    if not is_ok(xml):
        print("Failed to get salt")
        return None
        
    salt = xml.find('salt').text
    
    # Encrypt password (production method)
    try:
        encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
        pass_digest = hashlib.md5(username.encode('utf-8') + REALM.encode('utf-8') + encrypted_pass.encode('utf-8')).hexdigest()
    except TypeError:
        encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8')).encode('utf-8')).hexdigest()
        pass_digest = hashlib.md5(username.encode('utf-8') + REALM.encode('utf-8') + encrypted_pass.encode('utf-8')).hexdigest()
    
    # Login with encrypted password
    response = api('login', {
        'username_or_email': username, 
        'password': encrypted_pass, 
        'digest': pass_digest, 
        'keep_logged_in': 1
    })
    
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        token = xml.find('token').text
        print(f"Login successful! Token: {token[:20]}...")
        return token
    else:
        error_elem = xml.find('message')
        error_msg = error_elem.text if error_elem is not None else 'Unknown error'
        print(f"Login failed: {error_msg}")
        return None

def test_local_matching():
    """Test the matching logic locally first"""
    print("=== Testing Local Matching Logic ===")
    
    # Test files from your examples - focusing on silo
    silo_test_files = [
        "silo-s01e01-freedom-day-2160p-atvp-web-dl-ddp5-1-dovi-h-265-cz-tit-mkv",
        "silo-s01e01-1080p-10bit-webrip-6ch-x265-hevc-psa-mkv",
        "silo-s02e01-2024-1080p-cz-titulky-mkv",
        # Add more silo test cases here as you find them
    ]
    
    series_name = "silo"
    
    print(f"Testing series matching for: '{series_name}'")
    print("-" * 50)
    
    matches = []
    for filename in silo_test_files:
        is_match = _is_series_match(filename, series_name)
        season, episode = _detect_episode_info(filename, series_name)
        
        print(f"{'✓' if is_match else '✗'} {filename}")
        if is_match:
            print(f"    Season: {season}, Episode: {episode}")
            matches.append({
                'filename': filename,
                'season': season,
                'episode': episode
            })
        else:
            print(f"    ❌ Failed to match - this should be investigated!")
    
    print(f"\nFound {len(matches)} matches for '{series_name}'")
    
    # Test normalization to see what's happening
    print(f"\nNormalization examples:")
    for filename in silo_test_files[:2]:  # Show first 2
        normalized = _normalize(filename)
        print(f"  '{filename}'")
        print(f"  -> '{normalized}'")
    
    return matches

def search_webshare(token, query, limit=50):
    """Search Webshare for a specific query using production API"""
    print(f"\nSearching Webshare for: '{query}'")
    
    response = api('search', {
        'what': query,
        'category': 'video',
        'sort': 'recent',
        'limit': limit,
        'offset': 0,
        'wst': token,
        'maybe_removed': 'true'
    })
    
    try:
        xml = ET.fromstring(response.content)
        
        if is_ok(xml):
            files = []
            for file in xml.iter('file'):
                item = {}
                for elem in file:
                    item[elem.tag] = elem.text
                files.append(item)
            
            print(f"  Found {len(files)} total results")
            return files
        else:
            error_elem = xml.find('message')
            error_msg = error_elem.text if error_elem is not None else 'Unknown error'
            print(f"  Search failed: {error_msg}")
            return []
            
    except Exception as e:
        print(f"  Error parsing search response: {e}")
        return []

def test_webshare_search(token):
    """Test different search queries against Webshare"""
    print("\n=== Testing Webshare Search ===")
    
    queries = [
        "silo",
        "silo s01",
        "silo s02", 
        "silo-s01",
        "silo-s02",
        "silo 2024"
    ]
    
    all_results = {}
    
    for query in queries:
        results = search_webshare(token, query)
        
        # Filter for silo matches
        silo_matches = []
        for result in results:
            filename = result.get('name', '')
            if _is_series_match(filename, 'silo'):
                season, episode = _detect_episode_info(filename, 'silo')
                silo_matches.append({
                    'filename': filename,
                    'season': season,
                    'episode': episode,
                    'ident': result.get('ident', ''),
                    'size': result.get('size', '')
                })
        
        all_results[query] = silo_matches
        print(f"  '{query}': {len(silo_matches)} silo matches")
        
        # Show first few matches
        for i, match in enumerate(silo_matches[:3]):
            print(f"    {i+1}. S{match['season']:02d}E{match['episode']:02d} - {match['filename']}")
    
    return all_results

def organize_by_season(all_matches):
    """Organize all matches by season"""
    seasons = {}
    
    for query, matches in all_matches.items():
        for match in matches:
            season = match['season']
            episode = match['episode']
            
            if season is None or episode is None:
                continue
                
            season_str = str(season)
            episode_str = str(episode)
            
            if season_str not in seasons:
                seasons[season_str] = {}
            
            # Keep the best quality version (prefer higher resolution)
            if episode_str not in seasons[season_str]:
                seasons[season_str][episode_str] = match
            else:
                # Simple quality preference: 2160p > 1080p > 720p
                current = seasons[season_str][episode_str]['filename']
                new = match['filename']
                
                if '2160p' in new and '2160p' not in current:
                    seasons[season_str][episode_str] = match
                elif '1080p' in new and '720p' in current:
                    seasons[season_str][episode_str] = match
    
    return seasons

def main():
    print("=== Webshare Search Logic Test ===")
    
    # Test local matching first
    local_matches = test_local_matching()
    
    # Test with Webshare API
    token = login_to_webshare()
    if not token:
        print("Failed to login. Only local tests completed.")
        return
    
    # Test actual API searches
    webshare_results = test_webshare_search(token)
    
    # Organize results by season
    print("\n=== Organizing Results by Season ===")
    seasons = organize_by_season(webshare_results)
    
    print(f"Found {len(seasons)} seasons:")
    for season_num in sorted(seasons.keys(), key=int):
        episodes = seasons[season_num]
        print(f"  Season {season_num}: {len(episodes)} episodes")
        for ep_num in sorted(episodes.keys(), key=int):
            episode = episodes[ep_num]
            print(f"    Episode {ep_num}: {episode['filename']}")
    
    # Save results
    results = {
        'local_test_matches': local_matches,
        'webshare_query_results': webshare_results,
        'organized_seasons': seasons
    }
    
    with open('search_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to search_test_results.json")
    
    # Summary
    print("\n=== SUMMARY ===")
    print(f"Local test matches: {len(local_matches)}")
    for query, matches in webshare_results.items():
        print(f"'{query}' API results: {len(matches)} matches")
    print(f"Final organized seasons: {len(seasons)}")

if __name__ == "__main__":
    main()