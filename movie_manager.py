# -*- coding: utf-8 -*-
"""Simple movie search and selection utilities."""

import os
import io
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

from series_manager import _normalize, BaseManager


class MovieManager(BaseManager):
    """Manage movie searches and local storage."""

    def __init__(self, addon, profile):
        self.addon = addon
        super().__init__(profile, 'movies_db')

    def search_movie(self, movie_name, api_function, token):
        """Search for a movie and return the best available file."""
        search_queries = [
            movie_name,
            f"{movie_name} cz",
            f"{movie_name} 1080p",
            f"{movie_name} 720p"
        ]

        if ' ' in movie_name:
            search_queries.append(movie_name.replace(' ', '.'))
            search_queries.append(movie_name.replace(' ', '-'))

        all_results = []
        for query in search_queries:
            results = self._perform_search(query, api_function, token)
            for result in results:
                if result not in all_results and self._is_movie_match(result.get('name', ''), movie_name):
                    all_results.append(result)

        best_file = None
        best_score = -1
        for item in all_results:
            score = self._calculate_file_score(item['name'], item.get('size', '0'))
            if score > best_score:
                best_file = item
                best_score = score

        movie_data = {
            'name': movie_name,
            'last_updated': xbmc.getInfoLabel('System.Date'),
            'file': best_file
        }
        self._save_movie_data(movie_name, movie_data)
        return movie_data

    def _is_movie_match(self, filename, movie_name):
        norm_fn = _normalize(filename)
        norm_mn = _normalize(movie_name)
        return norm_mn in norm_fn


    def _save_movie_data(self, movie_name, movie_data):
        self._save_data(movie_name, movie_data)

    def load_movie_data(self, movie_name):
        return self.load_data(movie_name)

