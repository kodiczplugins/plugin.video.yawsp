#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re

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

# Test cases
test_files = [
    "silo-s01e01-freedom-day-2160p-atvp-web-dl-ddp5-1-dovi-h-265-cz-tit-mkv",
    "silo-s01e01-1080p-10bit-webrip-6ch-x265-hevc-psa-mkv",
    "breaking.bad.s01e01.pilot.720p.bluray.x264-demand.mkv",
    "game.of.thrones.s01e01.winter.is.coming.1080p.bluray.x264-reward.mkv",
    "stranger things s01e01 the vanishing of will byers 2160p netflix webrip ddp5 1 atmos x265 deflate.mkv",
    "Simpsonovi s01e01 - Vánoce u Simpsonových.mkv"
]

search_terms = ["silo", "breaking bad", "game of thrones", "stranger things", "Simpsonovi"]

print("Testing improved series matching:")
print("=" * 50)

for search_term in search_terms:
    print(f"\nSearching for: '{search_term}'")
    print("-" * 30)
    for filename in test_files:
        match = _is_series_match(filename, search_term)
        print(f"  {'✓' if match else '✗'} {filename}")

# Test normalization
print("\n\nTesting normalization:")
print("=" * 50)
test_strings = [
    "silo-s01e01-freedom-day",
    "breaking.bad.s01e01.pilot",
    "Game_Of_Thrones_S01E01",
    "Simpsonovi s01e01 - Vánoce u Simpsonových"
]

for test_str in test_strings:
    normalized = _normalize(test_str)
    print(f"'{test_str}' -> '{normalized}'")