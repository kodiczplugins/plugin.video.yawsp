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

# Import mock modules before importing series_manager
import mock_xbmc

# Production API settings (copied from yawsp.py)
BASE = 'https://webshare.cz'
API = BASE + '/api/'
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
HEADERS = {'User-Agent': UA, 'Referer': BASE}
REALM = ':Webshare:'

# Create session like production code
_session = requests.Session()
_session.headers.update(HEADERS)

# Import business logic functions from production code
from series_manager import (
    _normalize, 
    _is_series_match, 
    _calculate_series_match_score,
    SeriesManager
)

# Import _detect_episode_info - need to access it from SeriesManager instance
def _detect_episode_info(filename, series_name):
    """Wrapper to access _detect_episode_info from SeriesManager"""
    # Create a temporary instance to access the method
    temp_manager = SeriesManager(None, '.')
    return temp_manager._detect_episode_info(filename, series_name)

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

def test_improved_scoring():
    """Test the new improved scoring system"""
    print("=== Testing Improved Scoring Logic ===")
    
    # Test Silo series matching
    series_name = "Silo"
    
    test_cases = [
        # High priority matches (should get highest scores)
        ("Silo.S01E01.720p.WEB-DL.x264", 100),  # Starts with series name
        ("Silo S01E01 1080p BluRay x264", 90),    # Series at start with separator
        ("Silo.2023.S01E01.WEB-DL", 80),         # Exact match with year
        ("Silo Season 1 Episode 1", 80),          # Exact match with season
        ("Silo.s01.Complete.720p", 80),           # Exact match with season
        
        # Medium priority matches
        ("The.Silo.S01E01.720p", 50),            # Contains as word boundary
        ("Movie.About.Silo.Building.S01E01", 50), # Contains as word boundary
        
        # Should NOT match (score 0)
        ("Missile.Silo.Documentary", 0),          # No season/episode info
        ("Grain.Silos.of.America", 0),           # Different word (silos vs silo)
        ("Prison.Isolation.Ward", 0),             # No match at all
    ]
    
    print(f"Testing improved scoring for: '{series_name}'")
    print("-" * 60)
    
    for filename, expected_min_score in test_cases:
        score = _calculate_series_match_score(filename, series_name)
        season, episode = _detect_episode_info(filename, series_name)
        
        status = "✓" if score >= expected_min_score else "✗"
        has_episode = "E" if season is not None else "-"
        
        print(f"{status} {has_episode} Score:{score:3d} | {filename}")
        if score >= expected_min_score and season is not None:
            print(f"         -> S{season:02d}E{episode:02d}")
        elif score < expected_min_score:
            print(f"         -> Expected >={expected_min_score}, got {score}")
    
    print(f"\nHigh-scoring matches (>=80) will appear first in search results")
    
    # Test multi-word series
    print(f"\nTesting multi-word series: 'Breaking Bad'")
    print("-" * 60)
    
    multi_word_cases = [
        ("Breaking.Bad.S01E01.720p", 100),
        ("Breaking Bad S01E01", 90),
        ("Breaking.Bad.2008.S01E01", 80),
        ("The.Breaking.Bad.S01E01", 50),
    ]
    
    for filename, expected_min_score in multi_word_cases:
        score = _calculate_series_match_score(filename, "Breaking Bad")
        season, episode = _detect_episode_info(filename, "Breaking Bad")
        
        status = "✓" if score >= expected_min_score else "✗"
        has_episode = "E" if season is not None else "-"
        
        print(f"{status} {has_episode} Score:{score:3d} | {filename}")
        if season is not None:
            print(f"         -> S{season:02d}E{episode:02d}")

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

    # Additional test files for Simpsonovi
    simpsonovi_test_files = [
        "Simpsonovi s01e01 - Vánoce u Simpsonových.mkv",
        "Simpsonovi.S05E12.Bart.Gets.Famous.DVDRip.XviD.mkv",
        "The.Simpsons.S34E01.1080p.WEB.H264-CAKES.mkv",
        "Simpsonovi.S12E08.Skinner's.Sense.of.Snow.mkv"
    ]
    
    all_matches = {}
    for series_name, files in [("silo", silo_test_files), ("Simpsonovi", simpsonovi_test_files)]:
        print(f"Testing series matching for: '{series_name}'")
        print("-" * 50)
        matches = []
        for filename in files:
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
        all_matches[series_name] = matches
    
    # Test normalization to see what's happening
    print(f"\nNormalization examples:")
    for filename in silo_test_files[:2] + simpsonovi_test_files[:2]:  # Show examples
        normalized = _normalize(filename)
        print(f"  '{filename}'")
        print(f"  -> '{normalized}'")
    
    return all_matches

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
    
    # Test queries for both series
    series_queries = {
        'silo': [
            "silo",
            "silo s01",
            "silo s02", 
            "silo-s01",
            "silo-s02",
            "silo 2024"
        ],
        'Simpsonovi': [
            "simpsonovi",
            "simpsonovi s01",
            "simpsons",
            "the simpsons"
        ]
    }
    
    all_results = {}
    
    for series_name, queries in series_queries.items():
        print(f"\n--- Testing {series_name} ---")
        series_results = {}
        
        for query in queries:
            results = search_webshare(token, query)
            
            # Filter for series matches
            series_matches = []
            for result in results:
                filename = result.get('name', '')
                if _is_series_match(filename, series_name):
                    season, episode = _detect_episode_info(filename, series_name)
                    series_matches.append({
                        'filename': filename,
                        'season': season,
                        'episode': episode,
                        'ident': result.get('ident', ''),
                        'size': result.get('size', '')
                    })
            
            series_results[query] = series_matches
            print(f"  '{query}': {len(series_matches)} {series_name} matches")
            
            # Show first few matches
            for i, match in enumerate(series_matches[:3]):
                if match['season'] is not None and match['episode'] is not None:
                    print(f"    {i+1}. S{match['season']:02d}E{match['episode']:02d} - {match['filename']}")
        
        all_results[series_name] = series_results
    
    return all_results

def organize_by_season(all_matches):
    """Organize all matches by season for each series"""
    organized = {}
    
    for series_name, series_data in all_matches.items():
        seasons = {}
        
        for query, matches in series_data.items():
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
        
        organized[series_name] = seasons
    
    return organized

def main():
    print("=== Webshare Search Logic Test ===")
    
    # Test the improved scoring system first
    test_improved_scoring()
    
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
    organized_seasons = organize_by_season(webshare_results)
    
    for series_name, seasons in organized_seasons.items():
        print(f"\n{series_name}: {len(seasons)} seasons found")
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
        'organized_seasons': organized_seasons
    }
    
    with open('search_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to search_test_results.json")
    
    # Summary
    print("\n=== SUMMARY ===")
    for series_name, matches in local_matches.items():
        print(f"Local {series_name} matches: {len(matches)}")
    
    for series_name, series_data in webshare_results.items():
        total_matches = sum(len(matches) for matches in series_data.values())
        print(f"API {series_name} matches: {total_matches}")
        for query, matches in series_data.items():
            print(f"  '{query}': {len(matches)} matches")
    
    for series_name, seasons in organized_seasons.items():
        total_episodes = sum(len(episodes) for episodes in seasons.values())
        print(f"Final {series_name} organized: {len(seasons)} seasons, {total_episodes} episodes")

if __name__ == "__main__":
    main()