#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import tempfile
import shutil

# Add the current directory to Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock XBMC modules before importing series_manager
class MockXBMC:
    LOGINFO = 1
    LOGERROR = 4
    
    @staticmethod
    def log(message, level=None):
        print(f"[XBMC LOG] {message}")
    
    @staticmethod
    def getInfoLabel(label):
        if label == 'System.Date':
            return '2024-01-01'
        return ''

class MockAddon:
    def __init__(self):
        pass

# Mock the XBMC modules
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = type('MockModule', (), {'Addon': MockAddon})()
sys.modules['xbmcgui'] = type('MockModule', (), {})()
sys.modules['xbmcvfs'] = type('MockModule', (), {'translatePath': lambda x: x})()

# Now import the actual production code
import series_manager

def mock_api_function(action, params):
    """Mock API function that returns real data from our test results"""
    # Load the real API results
    try:
        with open('search_test_results.json', 'r', encoding='utf-8') as f:
            real_api_data = json.load(f)
    except FileNotFoundError:
        print("❌ search_test_results.json not found!")
        print("   Run 'python test_search_logic.py' first to generate real API data")
        return MockResponse([])
    
    if action != 'search':
        return MockResponse([])
    
    query = params.get('what', '')
    webshare_results = real_api_data.get('webshare_query_results', {})
    
    if query in webshare_results:
        mock_files = webshare_results[query]
        print(f"  Mock API returning {len(mock_files)} results for '{query}'")
        return MockResponse(mock_files)
    else:
        print(f"  Mock API: No data for query '{query}'")
        return MockResponse([])

class MockResponse:
    """Mock response object that mimics the XML response format"""
    def __init__(self, files_data):
        self.files_data = files_data
        self._create_xml()
    
    def _create_xml(self):
        """Create XML content that matches the expected format"""
        xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<response>\n<status>OK</status>\n'
        
        for file_data in self.files_data:
            xml_content += '<file>\n'
            xml_content += f'<name>{file_data["filename"]}</name>\n'
            xml_content += f'<ident>{file_data["ident"]}</ident>\n'
            xml_content += f'<size>{file_data["size"]}</size>\n'
            xml_content += '</file>\n'
        
        xml_content += '</response>'
        self.content = xml_content.encode('utf-8')

def test_series_manager_with_real_code():
    """Test the actual production SeriesManager with mock API data"""
    print("=== Testing Production SeriesManager ===")
    print("Using real series_manager.py code with mock API data from previous test")
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp()
    print(f"Using temp directory: {temp_dir}")
    
    try:
        # Create SeriesManager instance with temp directory
        mock_addon = MockAddon()
        sm = series_manager.SeriesManager(mock_addon, temp_dir)
        
        # Test the exact issue: search for "silo"
        print("\n" + "="*80)
        print("TESTING: Production SeriesManager.search_series('silo')")
        print("EXPECTED: Should find both Season 1 and Season 2 based on our API test")
        print("ACTUAL: Let's see what the production code does...")
        print("="*80)
        
        # Use mock token
        mock_token = "mock_token_12345"
        
        # Call the actual production method
        series_data = sm.search_series('silo', mock_api_function, mock_token)
        
        print("\n" + "="*80)
        print("PRODUCTION CODE RESULTS:")
        print("="*80)
        
        print(f"Found {len(series_data['seasons'])} seasons:")
        for season_num in sorted(series_data['seasons'].keys(), key=int):
            episodes = series_data['seasons'][season_num]
            print(f"  Season {season_num}: {len(episodes)} episodes")
            
            # Show first few episodes
            for ep_num in sorted(list(episodes.keys())[:3], key=int):
                episode = episodes[ep_num]
                print(f"    Episode {ep_num}: {episode['name']}")
        
        print("\n" + "="*80)
        print("DIAGNOSIS:")
        print("="*80)
        
        if len(series_data['seasons']) == 1 and '1' in series_data['seasons']:
            print("❌ BUG CONFIRMED: Production code only found Season 1!")
            print("   This means there's a bug in the production series_manager.py")
            print("   Even though our API test showed both seasons are available.")
            
            # Let's analyze why
            print("\n🔍 ROOT CAUSE ANALYSIS:")
            print("   From our API test, we know:")
            print("   - 'silo s01' query returns 50 Season 1 episodes ✅")
            print("   - 'silo s02' query returns 50 Season 2 episodes ✅") 
            print("   - But production code is missing Season 2...")
            print("   - Possible causes:")
            print("     1. Duplicate detection removing Season 2 episodes")
            print("     2. Episode detection failing for Season 2 files")
            print("     3. Search query order issue")
            print("     4. API pagination cutting off Season 2 results")
            
        elif len(series_data['seasons']) >= 2:
            print("✅ WORKING: Production code found multiple seasons!")
            print("   The recent fixes are working correctly.")
            seasons = sorted(series_data['seasons'].keys(), key=int)
            print(f"   Seasons found: {seasons}")
            
        else:
            print("⚠️  UNEXPECTED: No seasons found at all!")
            print("   Check if mock API data is working correctly.")
        
        # Save the actual production results for analysis
        with open('production_test_results.json', 'w', encoding='utf-8') as f:
            json.dump(series_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Production results saved to 'production_test_results.json'")
        
        return series_data
        
    finally:
        # Clean up
        shutil.rmtree(temp_dir)

def test_quality_selection():
    """Test the quality and language selection logic"""
    print("\n=== Testing Quality Selection Logic ===")
    
    # Create SeriesManager instance for testing
    mock_addon = MockAddon()
    sm = series_manager.SeriesManager(mock_addon, '/tmp/test')
    
    print("\n1. Testing Czech language priority:")
    czech_720p = sm._calculate_file_score("Stargate.S01E01.720p.CZ.mkv", "1000000000")
    english_1080p = sm._calculate_file_score("Stargate.S01E01.1080p.EN.mkv", "2000000000")
    print(f"   Czech 720p score: {czech_720p}")
    print(f"   English 1080p score: {english_1080p}")
    assert czech_720p > english_1080p, "Czech 720p should beat English 1080p"
    print("   ✅ Czech language gets priority over higher resolution")
    
    print("\n2. Testing resolution scoring:")
    test_cases = [
        ("Series.S01E01.2160p.mkv", "4K"),
        ("Series.S01E01.1440p.mkv", "1440p"),
        ("Series.S01E01.1080p.mkv", "1080p"),
        ("Series.S01E01.720p.mkv", "720p"),
        ("Series.S01E01.480p.mkv", "480p"),
    ]
    
    scores = []
    for filename, label in test_cases:
        score = sm._calculate_file_score(filename, "2000000000")
        scores.append(score)
        print(f"   {label}: {score} points")
    
    # Check that higher resolutions get higher scores
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i+1], f"Higher resolution should score higher or equal"
    print("   ✅ Resolution scoring works correctly")
    
    print("\n3. Testing Czech indicators:")
    czech_indicators = ['cz', 'czech', 'dabing', 'titulky', 'cztit']
    for indicator in czech_indicators:
        filename = f"Series.S01E01.1080p.{indicator}.mkv"
        score = sm._calculate_file_score(filename, "1000000000")
        assert score >= 100, f"File with '{indicator}' should get Czech bonus"
        print(f"   ✅ '{indicator}' detected: {score} points")
    
    print("\n4. Testing release type preferences:")
    bluray_score = sm._calculate_file_score("Series.S01E01.1080p.BluRay.mkv", "2000000000")
    webdl_score = sm._calculate_file_score("Series.S01E01.1080p.WEB-DL.mkv", "2000000000")
    webrip_score = sm._calculate_file_score("Series.S01E01.1080p.WEBRip.mkv", "2000000000")
    
    print(f"   BluRay: {bluray_score} points")
    print(f"   WEB-DL: {webdl_score} points") 
    print(f"   WEBRip: {webrip_score} points")
    
    assert bluray_score > webdl_score > webrip_score, "BluRay > WEB-DL > WEBRip"
    print("   ✅ Release type preferences work correctly")
    
    print("\n5. Testing combined scoring:")
    # Czech 720p vs English 4K
    czech_720p = sm._calculate_file_score("Series.S01E01.720p.CZ.BluRay.mkv", "1500000000")
    english_4k = sm._calculate_file_score("Series.S01E01.2160p.EN.WEB-DL.mkv", "5000000000")
    
    print(f"   Czech 720p BluRay: {czech_720p} points")
    print(f"   English 4K WEB-DL: {english_4k} points")
    assert czech_720p > english_4k, "Czech content should beat higher quality English"
    print("   ✅ Combined scoring prioritizes Czech content correctly")
    
    print("\n✅ ALL QUALITY SELECTION TESTS PASSED!")
    return True

def main():
    print("=== Production SeriesManager Test ===")
    print("This test calls the actual production series_manager.py code")
    print("Using real API data from our previous test")
    
    # Run quality selection tests first
    test_quality_selection()
    
    # Check if we have the API test data
    if not os.path.exists('search_test_results.json'):
        print("❌ search_test_results.json not found!")
        print("   Please run: python test_search_logic.py")
        print("   This will generate the real API data needed for this test.")
        return
    
    # Run the production code test
    series_data = test_series_manager_with_real_code()
    
    # Final summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("This test proves whether the issue is:")
    print("1. ❌ In our production code logic (if only Season 1 found)")
    print("2. ✅ In the API/external factors (if both seasons found)")
    print("")
    print("Next steps depend on the result above!")
    
if __name__ == "__main__":
    main()