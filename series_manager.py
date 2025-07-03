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

# Precompiled regular expressions for detecting episode patterns
EPISODE_PATTERNS = [
    re.compile(r'[Ss](\d+)[Ee](\d+)'),  # S01E01 format
    re.compile(r'(\d+)x(\d+)'),        # 1x01 format
    re.compile(r'[Ee]pisode\s*(\d+)'), # Episode 1 format
    re.compile(r'[Ee]p\s*(\d+)'),      # Ep 1 format
    re.compile(r'[Ee](\d+)'),           # E1 format
    re.compile(r'(\d+)\.\s*(\d+)')   # 1.01 format
]

# Precompiled regex for normalization
_NORMALIZE_RE = re.compile(r'[\W_]+')
_RESOLUTION_RE = re.compile(r'(\d+)p')

# Additional precompiled regex patterns for performance
_SAFE_FILENAME_RE = re.compile(r'[^\w\-_\. ]')
_SEASON_MATCH_RE = re.compile(r'season\s*(\d+)')
_EPISODE_EXTRACT_RE = re.compile(r'(\d+)')
_WHITESPACE_RE = re.compile(r'\s+')

# Cache for compiled word boundary patterns to avoid recompiling same patterns
_WORD_BOUNDARY_CACHE = {}


def _normalize(text):
    """Normalize text for comparisons."""
    # Replace non-word characters (including underscore) with spaces and
    # convert to lower case for easier matching.
    return _NORMALIZE_RE.sub(' ', text).strip().lower()



def _is_series_match(filename, series_name):
    """Check if filename contains the series name with flexible matching."""
    norm_fn = _normalize(filename)
    norm_sn = _normalize(series_name)

    # Split series name into words for flexible matching
    series_words = norm_sn.split()

    # If series name is a single word, check if it appears as a word boundary
    if len(series_words) == 1:
        # Use cached word boundary pattern for performance
        word = series_words[0]
        if word not in _WORD_BOUNDARY_CACHE:
            escaped_word = re.escape(word)
            _WORD_BOUNDARY_CACHE[word] = re.compile(r'\b' + escaped_word + r'\b')
        pattern = _WORD_BOUNDARY_CACHE[word]
        return bool(pattern.search(norm_fn))

    # For multi-word series names, check if all words appear in order
    # This allows for some flexibility in separators
    for word in series_words:
        if word not in norm_fn:
            return False

    return True


def _calculate_series_match_score(filename, series_name):
    """Calculate a match score for prioritizing exact title matches."""
    norm_fn = _normalize(filename)
    norm_sn = _normalize(series_name)
    
    # Check if filename starts with the series name (highest priority)
    if norm_fn.startswith(norm_sn):
        return 100
    
    # Check if series name appears at word boundary near beginning
    # Pattern: "Series Name S01E01" or "Series.Name.S01E01"
    series_at_start_pattern = r'^\W*' + re.escape(norm_sn) + r'[\s\.\-_]'
    if re.search(series_at_start_pattern, norm_fn):
        return 90
    
    # Check if it's the exact series name with common separators
    exact_patterns = [
        r'\b' + re.escape(norm_sn) + r'\b[\s\.\-_]*s\d+',  # "silo s01"
        r'\b' + re.escape(norm_sn) + r'\b[\s\.\-_]*season',  # "silo season"
        r'\b' + re.escape(norm_sn) + r'\b[\s\.\-_]*\d{4}',  # "silo 2023"
    ]
    
    for pattern in exact_patterns:
        if re.search(pattern, norm_fn, re.IGNORECASE):
            return 80
    
    # Basic word boundary match (current behavior)
    if _is_series_match(filename, series_name):
        return 50
    
    return 0


class BaseManager:
    """Base manager providing common utilities for Series and Movies."""

    def __init__(self, profile, db_subdir):
        """Initialize with profile path and database subdirectory."""
        self.profile = profile
        self.db_path = os.path.join(profile, db_subdir)
        self.ensure_db_exists()

    def ensure_db_exists(self):
        """Ensure that the database directory exists."""
        try:
            if not os.path.exists(self.profile):
                os.makedirs(self.profile)
            if not os.path.exists(self.db_path):
                os.makedirs(self.db_path)
        except Exception as e:
            xbmc.log(f'YaWSP BaseManager: Error creating directories: {str(e)}',
                     level=xbmc.LOGERROR)

    def _calculate_file_score(self, filename, file_size):
        """Calculate preference score for a file based on language and quality indicators."""
        score = 0
        filename_lower = filename.lower()

        # Czech language indicators (highest priority)
        czech_indicators = ['cz', 'czech', 'čeština', 'dabing', 'titulky', 'tit', 'cztit', 'cestina']
        for indicator in czech_indicators:
            if indicator in filename_lower:
                score += 100
                break  # Only count once

        # Quality indicators - extract resolution number
        resolution_match = _RESOLUTION_RE.search(filename_lower)
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
        """Perform the actual search using the provided API function with pagination."""
        results = []
        limit = 100
        max_results = 300  # Limit total results to avoid excessive API calls

        for offset in range(0, max_results, limit):
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
                xbmc.log(f'YaWSP BaseManager: XML Parse Error for query "{search_query}": {str(e)}', level=xbmc.LOGERROR)
                continue

            status = xml.find('status')
            if status is not None and status.text == 'OK':
                page_results = []
                for file in xml.iter('file'):
                    item = {}
                    for elem in file:
                        item[elem.tag] = elem.text
                    page_results.append(item)

                results.extend(page_results)
                if len(page_results) < limit:
                    break
            else:
                break

        return results

    def _base_variations(self, name):
        """Return common variations of a name for search queries."""
        variations = {name}
        if ' ' in name:
            variations.update({
                name.replace(' ', '.'),
                name.replace(' ', '-'),
                name.replace(' ', '_')
            })
        return variations

    def _build_search_queries(self, name, seasons=None, extras=None):
        """Construct a list of search queries for the given media name.

        Extras allow additional queries like language or quality variants.
        Passing no extras keeps searches minimal and relies on filtering.
        """
        seasons = seasons or []
        extras = extras or []
        queries = []

        for base in self._base_variations(name):
            queries.append(base)
            for season in seasons:
                queries.append(f"{base} s{int(season):02d}")

        for extra in extras:
            queries.append(f"{name} {extra}")

        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                unique.append(q)
                seen.add(q)
        return unique

    def _safe_filename(self, name):
        """Convert a media title to a safe filename"""
        safe = _SAFE_FILENAME_RE.sub('_', name)
        return safe.lower().replace(' ', '_')

    def _save_data(self, name, data):
        """Save generic media data to the database."""
        safe_name = self._safe_filename(name)
        file_path = os.path.join(self.db_path, f"{safe_name}.json")
        try:
            with io.open(file_path, 'w', encoding='utf8') as file:
                try:
                    json_data = json.dumps(data, indent=2).decode('utf8')
                except AttributeError:
                    json_data = json.dumps(data, indent=2)
                file.write(json_data)
                file.close()
        except Exception as e:
            xbmc.log(f'YaWSP BaseManager: Error saving data: {str(e)}',
                     level=xbmc.LOGERROR)

    def load_data(self, name):
        """Load generic media data from the database."""
        safe_name = self._safe_filename(name)
        file_path = os.path.join(self.db_path, f"{safe_name}.json")
        if not os.path.exists(file_path):
            return None
        try:
            with io.open(file_path, 'r', encoding='utf8') as file:
                data = file.read()
                file.close()
                try:
                    return json.loads(data, "utf-8")
                except TypeError:
                    return json.loads(data)
        except Exception as e:
            xbmc.log(f'YaWSP BaseManager: Error loading data: {str(e)}',
                     level=xbmc.LOGERROR)
            return None

    def remove_item(self, name):
        """Remove a media item from the database."""
        safe_name = self._safe_filename(name)
        file_path = os.path.join(self.db_path, f"{safe_name}.json")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            xbmc.log(f'YaWSP BaseManager: Error removing data: {str(e)}',
                     level=xbmc.LOGERROR)
        return False


class SeriesManager(BaseManager):
    def __init__(self, addon, profile):
        self.addon = addon
        super().__init__(profile, 'series_db')

    def search_series(self, series_name, api_function, token):
        """Search for episodes of a series"""
        # Structure to hold results
        series_data = {
            'name': series_name,
            'last_updated': xbmc.getInfoLabel('System.Date'),
            'seasons': {}
        }

        search_queries = self._build_search_queries(
            series_name,
            seasons=range(1, 6)
        )

        all_results = []

        # Try each search query
        for query in search_queries:
            results = self._perform_search(query, api_function, token)
            # Add results to our collection, avoiding duplicates and prioritizing exact matches
            for result in results:
                if result not in all_results:
                    # Calculate match score to prioritize exact title matches
                    match_score = _calculate_series_match_score(result['name'], series_name)
                    if match_score > 0:  # Only include if there's a match
                        season_num, episode_num = self._detect_episode_info(result['name'], series_name)
                        if season_num is not None:
                            # Add match score to result for sorting
                            result['_match_score'] = match_score
                            all_results.append(result)

        # Sort results by match score (highest first) to prioritize exact matches
        all_results.sort(key=lambda x: x.get('_match_score', 0), reverse=True)
        
        # Limit results to reduce noise - keep top 200 highest scoring matches
        if len(all_results) > 200:
            all_results = all_results[:200]

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
        if not _is_series_match(filename, series_name):
            return False

        season_num, episode_num = self._detect_episode_info(filename, series_name)
        if season_num is not None:
            return True

        norm_fn = _normalize(filename)
        episode_keywords = ['episode', 'season', 'series', 'ep', 'complete', 'serie', 'disk']
        return any(keyword in norm_fn for keyword in episode_keywords)


    def _detect_episode_info(self, filename, series_name):
        """Try to detect season and episode numbers from filename"""
        # Normalize filename and series name for easier matching
        norm_fn = _normalize(filename)
        norm_sn = _normalize(series_name)

        # Remove the series name from the filename more intelligently
        cleaned = norm_fn
        series_words = norm_sn.split()
        for word in series_words:
            # Use cached word boundary pattern for better performance
            if word not in _WORD_BOUNDARY_CACHE:
                escaped_word = re.escape(word)
                _WORD_BOUNDARY_CACHE[word] = re.compile(r'\b' + escaped_word + r'\b')
            pattern = _WORD_BOUNDARY_CACHE[word]
            cleaned = pattern.sub('', cleaned)
        cleaned = _WHITESPACE_RE.sub(' ', cleaned).strip()

        # Try each of our patterns
        for pattern in EPISODE_PATTERNS:
            match = pattern.search(cleaned)
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
            season_match = _SEASON_MATCH_RE.search(cleaned)
            if season_match:
                season_num = int(season_match.group(1))
                # Try to find episode number
                ep_match = _EPISODE_EXTRACT_RE.search(cleaned.replace(season_match.group(0), ''))
                if ep_match:
                    return season_num, int(ep_match.group(1))

        # Default fallback
        return None, None

    def _save_series_data(self, series_name, series_data):
        """Save series data to the database"""
        self._save_data(series_name, series_data)

    def load_series_data(self, series_name):
        """Load series data from the database"""
        return self.load_data(series_name)

    def get_all_series(self):
        """Get a list of all saved series"""
        series_list = []

        try:
            for filename in os.listdir(self.db_path):
                if filename.endswith('.json'):
                    series_name = os.path.splitext(filename)[0]
                    # Convert safe filename back to proper name (rough conversion)
                    proper_name = series_name.replace('_', ' ')
                    file_path = os.path.join(self.db_path, filename)
                    mtime = 0
                    try:
                        mtime = os.path.getmtime(file_path)
                    except Exception as e:
                        xbmc.log(f'YaWSP Series Manager: Error accessing {filename}: {str(e)}', level=xbmc.LOGERROR)
                    series_list.append({
                        'name': proper_name,
                        'filename': filename,
                        'safe_name': series_name,
                        'mtime': mtime
                    })

            series_list.sort(key=lambda s: s.get('mtime', 0), reverse=True)
        except Exception as e:
            xbmc.log(f'YaWSP Series Manager: Error listing series: {str(e)}', level=xbmc.LOGERROR)

        return series_list

    def remove_series(self, series_name):
        """Remove a series from the database"""
        return self.remove_item(series_name)

# Utility functions for the UI layer
def get_url(**kwargs):
    """Create a URL for calling the plugin recursively"""
    from yawsp import _url
    return '{0}?{1}'.format(_url, urlencode(kwargs, 'utf-8'))


def create_series_menu(series_manager, handle, end=True):
    """Create the series selection menu"""
    import xbmcplugin

    # Add "Search for new series" option
    listitem = xbmcgui.ListItem(label="Hledat novy serial")
    listitem.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='series_search'), listitem, True)

    # Trending from Trakt
    listitem = xbmcgui.ListItem(label=series_manager.addon.getLocalizedString(30401))
    listitem.setArt({'icon': 'DefaultRecentlyAddedEpisodes.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='series_trending'), listitem, True)

    # Popular from Trakt
    listitem = xbmcgui.ListItem(label=series_manager.addon.getLocalizedString(30402))
    listitem.setArt({'icon': 'DefaultTVShows.png'})
    xbmcplugin.addDirectoryItem(handle, get_url(action='series_popular'), listitem, True)

    # List existing series
    series_list = series_manager.get_all_series()
    for series in series_list:
        listitem = xbmcgui.ListItem(label=series['name'])
        listitem.setArt({'icon': 'DefaultFolder.png'})
        commands = []
        commands.append((series_manager.addon.getLocalizedString(30213),
                         'Container.Update(' + get_url(action='series', remove=series['name']) + ')'))
        listitem.addContextMenuItems(commands)
        xbmcplugin.addDirectoryItem(handle, get_url(action='series_detail', series_name=series['name']), listitem, True)

    if end:
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

        # Generate URL for playing this episode with playlist info
        url = get_url(
            action='play',
            ident=episode['ident'],
            name=episode['name'],
            series=series_name,
            season=season_num,
            episode=episode_num
        )

        xbmcplugin.addDirectoryItem(handle, url, listitem, False)

    xbmcplugin.endOfDirectory(handle) 
