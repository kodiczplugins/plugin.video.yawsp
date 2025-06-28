# -*- coding: utf-8 -*-
# Module: series_manager
# Author: user extension
# Created on: 5.6.2023
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import os
import io
import re
import json
import xbmc
import xbmcaddon
import xbmcgui
import xml.etree.ElementTree as ET

try:
    from urllib import urlencode
    from urlparse import parse_qsl
except ImportError:
    from urllib.parse import urlencode
    from urllib.parse import parse_qsl

try:
    from xbmc import translatePath
except ImportError:
    from xbmcvfs import translatePath

# Regular expressions for detecting episode patterns
EPISODE_PATTERNS = [
    r'[Ss](\d+)[Ee](\d+)',  # S01E01 format
    r'(\d+)x(\d+)',  # 1x01 format
    r'[Ee]pisode\s*(\d+)',  # Episode 1 format
    r'[Ee]p\s*(\d+)',  # Ep 1 format
    r'[Ee](\d+)',  # E1 format
    r'(\d+)\.\s*(\d+)'  # 1.01 format
]


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


class SeriesManager:
    def __init__(self, addon, profile):
        self.addon = addon
        self.profile = profile
        self.series_db_path = os.path.join(profile, 'series_db')
        self.ensure_db_exists()

    def ensure_db_exists(self):
        """Ensure that the series database directory exists"""
        try:
            if not os.path.exists(self.profile):
                os.makedirs(self.profile)
            if not os.path.exists(self.series_db_path):
                os.makedirs(self.series_db_path)
        except Exception as e:
            xbmc.log(f'YaWSP Series Manager: Error creating directories: {str(e)}', level=xbmc.LOGERROR)

    def search_series(self, series_name, api_function, token):
        """Search for episodes of a series"""
        # Structure to hold results
        series_data = {
            'name': series_name,
            'last_updated': xbmc.getInfoLabel('System.Date'),
            'seasons': {}
        }

        # Define search queries to try - prioritize season-specific searches
        search_queries = [
            f"{series_name} s01",  # name + s01 (most reliable)
            f"{series_name} s02",  # name + s02
            f"{series_name} s03",  # name + s03
            f"{series_name} s04",  # name + s04
            f"{series_name} s05",  # name + s05
            series_name,  # exact name (fallback)
            f"{series_name} season",  # name + season
            f"{series_name} episode",  # name + episode
            f"{series_name} 1080p",  # name + quality
            f"{series_name} 720p",  # name + quality
            f"{series_name} 2160p",  # name + 4K quality
            f"{series_name} webrip",  # name + release type
            f"{series_name} bluray",  # name + release type
            f"{series_name} web-dl",  # name + release type
        ]

        # Add variations where spaces are replaced with common separators
        base_variations = [series_name]
        if ' ' in series_name:
            base_variations.extend([
                series_name.replace(' ', '.'),
                series_name.replace(' ', '-'),
                series_name.replace(' ', '')
            ])

        # For each base variation, add season-specific searches
        for base in base_variations:
            if base != series_name:  # Don't duplicate the exact name
                search_queries.append(base)
            search_queries.extend([
                f"{base} s01",
                f"{base} s02",
                f"{base} s03",
                f"{base}.s01",
                f"{base}.s02",
                f"{base}.s03",
                f"{base}-s01",
                f"{base}-s02",
                f"{base}-s03"
            ])

        all_results = []

        # Try each search query
        for query in search_queries:
            results = self._perform_search(query, api_function, token)
            # Add results to our collection, avoiding duplicates
            for result in results:
                if result not in all_results and self._is_likely_episode(result['name'], series_name):
                    all_results.append(result)

        # Process results and organize into seasons with quality/language preference
        for item in all_results:
            season_num, episode_num = self._detect_episode_info(item['name'], series_name)
            if season_num is not None:
                # Convert to strings for JSON compatibility
                season_num_str = str(season_num)
                episode_num_str = str(episode_num)

                if season_num_str not in series_data['seasons']:
                    series_data['seasons'][season_num_str] = {}

                # Check if we already have this episode
                current_episode = series_data['seasons'][season_num_str].get(episode_num_str)
                
                if current_episode is None:
                    # First file for this episode
                    series_data['seasons'][season_num_str][episode_num_str] = {
                        'name': item['name'],
                        'ident': item['ident'],
                        'size': item.get('size', '0')
                    }
                else:
                    # Compare with existing file and keep the better one
                    new_score = self._calculate_file_score(item['name'], item.get('size', '0'))
                    current_score = self._calculate_file_score(current_episode['name'], current_episode['size'])
                    
                    if new_score > current_score:
                        series_data['seasons'][season_num_str][episode_num_str] = {
                            'name': item['name'],
                            'ident': item['ident'],
                            'size': item.get('size', '0')
                        }

        # Save the series data
        self._save_series_data(series_name, series_data)

        return series_data

    def _is_likely_episode(self, filename, series_name):
        """Check if a filename is likely to be an episode of the series"""
        # Use the new flexible series matching
        if not _is_series_match(filename, series_name):
            return False

        norm_fn = _normalize(filename)

        # Positive indicators
        for pattern in EPISODE_PATTERNS:
            if re.search(pattern, norm_fn, re.IGNORECASE):
                return True

        # Keywords that suggest it's a episode
        episode_keywords = ['episode', 'season', 'series', 'ep', 'complete', 'serie', 'season', 'disk']

        for keyword in episode_keywords:
            if keyword in norm_fn:
                return True

        return False

    def _calculate_file_score(self, filename, file_size):
        """Calculate preference score for a file based on language and quality indicators"""
        score = 0
        filename_lower = filename.lower()
        
        # Czech language indicators (highest priority)
        czech_indicators = ['cz', 'czech', 'čeština', 'dabing', 'titulky', 'cztit', 'cestina']
        for indicator in czech_indicators:
            if indicator in filename_lower:
                score += 100
                break  # Only count once
        
        # Quality indicators - extract resolution number
        import re
        resolution_match = re.search(r'(\d+)p', filename_lower)
        if resolution_match:
            resolution = int(resolution_match.group(1))
            # Score based on resolution height
            if resolution >= 2160:  # 4K and above
                score += 40
            elif resolution >= 1440:  # 1440p, 1600p, etc.
                score += 35
            elif resolution >= 1080:  # 1080p, 1200p, etc.
                score += 30
            elif resolution >= 720:   # 720p, 900p, etc.
                score += 20
            elif resolution >= 480:   # 480p, 576p, etc.
                score += 10
            else:  # Lower resolutions
                score += 5
        
        # Special case for 4K without 'p'
        if '4k' in filename_lower:
            score += 40
        
        # File size bonus (larger files usually better quality)
        try:
            size_bytes = int(file_size)
            # Add small bonus for larger files (1 point per GB)
            size_gb = size_bytes / (1024 * 1024 * 1024)
            score += min(size_gb, 10)  # Cap at 10 points
        except (ValueError, TypeError):
            pass
        
        # Prefer certain release types
        if 'bluray' in filename_lower or 'blu-ray' in filename_lower:
            score += 15
        elif 'web-dl' in filename_lower:
            score += 10
        elif 'webrip' in filename_lower:
            score += 5
        
        return score

    def _perform_search(self, search_query, api_function, token):
        """Perform the actual search using the provided API function with pagination"""
        results = []
        limit = 100
        max_results = 300  # Limit total results to avoid excessive API calls

        for offset in range(0, max_results, limit):
            # Call the Webshare API to search for the series
            response = api_function('search', {
                'what': search_query,
                'category': 'video',
                'sort': 'recent',
                'limit': limit,
                'offset': offset,
                'wst': token,
                'maybe_removed': 'true'
            })

            try:
                xml = ET.fromstring(response.content)
            except ET.ParseError as e:
                xbmc.log(f'YaWSP Series Manager: XML Parse Error for query "{search_query}": {str(e)}', level=xbmc.LOGERROR)
                xbmc.log(f'YaWSP Series Manager: Response content: {response.content[:200]}', level=xbmc.LOGERROR)
                continue

            # Check if the search was successful
            status = xml.find('status')
            if status is not None and status.text == 'OK':
                page_results = []
                # Convert XML to a list of dictionaries
                for file in xml.iter('file'):
                    item = {}
                    for elem in file:
                        item[elem.tag] = elem.text
                    page_results.append(item)

                # If we got fewer results than the limit, we've reached the end
                if len(page_results) < limit:
                    results.extend(page_results)
                    break

                results.extend(page_results)
            else:
                # API error or no more results
                break

        return results

    def _detect_episode_info(self, filename, series_name):
        """Try to detect season and episode numbers from filename"""
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

    def _save_series_data(self, series_name, series_data):
        """Save series data to the database"""
        safe_name = self._safe_filename(series_name)
        file_path = os.path.join(self.series_db_path, f"{safe_name}.json")

        try:
            with io.open(file_path, 'w', encoding='utf8') as file:
                try:
                    data = json.dumps(series_data, indent=2).decode('utf8')
                except AttributeError:
                    data = json.dumps(series_data, indent=2)
                file.write(data)
                file.close()
        except Exception as e:
            xbmc.log(f'YaWSP Series Manager: Error saving series data: {str(e)}', level=xbmc.LOGERROR)

    def load_series_data(self, series_name):
        """Load series data from the database"""
        safe_name = self._safe_filename(series_name)
        file_path = os.path.join(self.series_db_path, f"{safe_name}.json")

        if not os.path.exists(file_path):
            return None

        try:
            with io.open(file_path, 'r', encoding='utf8') as file:
                data = file.read()
                file.close()
                try:
                    series_data = json.loads(data, "utf-8")
                except TypeError:
                    series_data = json.loads(data)
                return series_data
        except Exception as e:
            xbmc.log(f'YaWSP Series Manager: Error loading series data: {str(e)}', level=xbmc.LOGERROR)
            return None

    def get_all_series(self):
        """Get a list of all saved series"""
        series_list = []

        try:
            for filename in os.listdir(self.series_db_path):
                if filename.endswith('.json'):
                    series_name = os.path.splitext(filename)[0]
                    # Convert safe filename back to proper name (rough conversion)
                    proper_name = series_name.replace('_', ' ')
                    series_list.append({
                        'name': proper_name,
                        'filename': filename,
                        'safe_name': series_name
                    })
        except Exception as e:
            xbmc.log(f'YaWSP Series Manager: Error listing series: {str(e)}', level=xbmc.LOGERROR)

        return series_list

    def _safe_filename(self, name):
        """Convert a series name to a safe filename"""
        # Replace problematic characters
        safe = re.sub(r'[^\w\-_\. ]', '_', name)
        return safe.lower().replace(' ', '_')


# Utility functions for the UI layer
def get_url(**kwargs):
    """Create a URL for calling the plugin recursively"""
    from yawsp import _url
    return '{0}?{1}'.format(_url, urlencode(kwargs, 'utf-8'))


def create_series_menu(series_manager, handle):
    """Create the series selection menu"""
    import xbmcplugin

    # Add "Search for new series" option
    listitem = xbmcgui.ListItem(label="Hledat novy serial")
    listitem.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='series_search'), listitem, True)

    # List existing series
    series_list = series_manager.get_all_series()
    for series in series_list:
        listitem = xbmcgui.ListItem(label=series['name'])
        listitem.setArt({'icon': 'DefaultFolder.png'})
        xbmcplugin.addDirectoryItem(handle, get_url(action='series_detail', series_name=series['name']), listitem, True)

    xbmcplugin.endOfDirectory(handle)


def create_seasons_menu(series_manager, handle, series_name):
    """Create menu of seasons for a series"""
    import xbmcplugin

    series_data = series_manager.load_series_data(series_name)
    if not series_data:
        xbmcgui.Dialog().notification('YaWSP', 'Data serialu nenalezena', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    # Add "Refresh series" option
    listitem = xbmcgui.ListItem(label="Aktualizovat serial")
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='series_refresh', series_name=series_name), listitem, True)

    # List seasons
    for season_num in sorted(series_data['seasons'].keys(), key=int):
        season_name = f"Rada {season_num}"
        listitem = xbmcgui.ListItem(label=season_name)
        listitem.setArt({'icon': 'DefaultFolder.png'})
        xbmcplugin.addDirectoryItem(handle, get_url(action='series_season', series_name=series_name, season=season_num), listitem, True)

    xbmcplugin.endOfDirectory(handle)


def create_episodes_menu(series_manager, handle, series_name, season_num):
    """Create menu of episodes for a season"""
    import xbmcplugin

    series_data = series_manager.load_series_data(series_name)
    if not series_data or str(season_num) not in series_data['seasons']:
        xbmcgui.Dialog().notification('YaWSP', 'Data sezony nenalezena', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    # Convert season_num to a string for dict lookup if it's not already
    season_num = str(season_num)

    # List episodes
    season = series_data['seasons'][season_num]
    for episode_num in sorted(season.keys(), key=int):
        episode = season[episode_num]
        episode_name = f"Epizoda {episode_num} - {episode['name']}"

        listitem = xbmcgui.ListItem(label=episode_name)
        listitem.setArt({'icon': 'DefaultVideo.png'})
        listitem.setProperty('IsPlayable', 'true')

        # Generate URL for playing this episode
        url = get_url(action='play', ident=episode['ident'], name=episode['name'])

        xbmcplugin.addDirectoryItem(handle, url, listitem, False)

    xbmcplugin.endOfDirectory(handle) 
