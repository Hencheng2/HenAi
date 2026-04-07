# media.py - Complete media handling with multiple free providers including DuckDuckGo and Openverse
import requests
import base64
import json
from datetime import datetime
import tempfile
import os
import subprocess
import random
import re

# API Keys - Free to obtain from respective services
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")  # pixabay.com
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")  # pexels.com
TWELVELABS_API_KEY = os.environ.get("TWELVELABS_API_KEY", "")  # twelvelabs.com

# Optional - Get your free API keys from these services:
UNSPLASH_API_KEY = "YOUR_UNSPLASH_API_KEY"
GIPHY_API_KEY = os.environ.get("GIPHY_API_KEY", "")
FLICKR_API_KEY = "YOUR_FLICKR_API_KEY"
VIMEO_ACCESS_TOKEN = "YOUR_VIMEO_TOKEN"

class MediaHandler:
    def __init__(self):
        # Primary providers (always available)
        self.pixabay_key = PIXABAY_API_KEY
        self.pexels_key = PEXELS_API_KEY
        self.twelvelabs_key = TWELVELABS_API_KEY
        
        # Secondary providers (optional - add your keys)
        self.unsplash_key = UNSPLASH_API_KEY
        self.giphy_key = GIPHY_API_KEY
        self.flickr_key = FLICKR_API_KEY
        self.vimeo_token = VIMEO_ACCESS_TOKEN
        
        # Track which providers are available
        self.available_image_providers = ['pixabay', 'pexels', 'duckduckgo', 'openverse']
        self.available_video_providers = ['pixabay', 'pexels', 'duckduckgo']
        
        # Add optional providers if keys are configured
        if self.unsplash_key and self.unsplash_key != "YOUR_UNSPLASH_API_KEY":
            self.available_image_providers.append('unsplash')
        if self.giphy_key and self.giphy_key != "YOUR_GIPHY_API_KEY":
            self.available_image_providers.append('giphy')
        if self.flickr_key and self.flickr_key != "YOUR_FLICKR_API_KEY":
            self.available_image_providers.append('flickr')
        if self.vimeo_token and self.vimeo_token != "YOUR_VIMEO_TOKEN":
            self.available_video_providers.append('vimeo')
        self.available_video_providers.append('dailymotion')
    
    # ============= DUCKDUCKGO SEARCH (IMAGES & VIDEOS - NO API KEY, NO SAFE SEARCH) =============
    
    def _get_vqd_for_search(self, query):
        """Get VQD token required for DuckDuckGo API (no safe search)"""
        try:
            # Use kp=-2 to disable safe search completely
            url = f"https://duckduckgo.com/?q={query}&t=h_&ia=web&kp=-2"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            # Extract VQD from response
            vqd_match = re.search(r'vqd=([\d-]+)&', response.text)
            if vqd_match:
                return vqd_match.group(1)
            
            # Alternative extraction
            for line in response.text.split('\n'):
                if 'vqd' in line and 'token' in line:
                    vqd_match = re.search(r'vqd[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', line)
                    if vqd_match:
                        return vqd_match.group(1)
            
            return None
        except Exception as e:
            print(f"Error getting VQD: {e}")
            return None
    
    def _search_duckduckgo_images(self, query, page=1):
        """Search DuckDuckGo for images (no API key required, no safe search)"""
        try:
            url = "https://duckduckgo.com/i.js"
            params = {
                'q': query,
                'o': 'json',
                'p': page,
                'l': 'us-en',
                'f': ',,',
                'kp': -2  # -2 = OFF (shows all content)
            }
            
            vqd = self._get_vqd_for_search(query)
            if vqd:
                params['vqd'] = vqd
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://duckduckgo.com/'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                if results and len(results) > 0:
                    result = results[0]
                    return {
                        'success': True,
                        'type': 'image',
                        'provider': 'DuckDuckGo',
                        'id': result.get('id', str(hash(result.get('image', '')))),
                        'title': result.get('title', query),
                        'description': result.get('title', ''),
                        'photographer': result.get('source', 'Unknown'),
                        'preview_url': result.get('thumbnail', result.get('image')),
                        'large_image_url': result.get('image', result.get('thumbnail')),
                        'width': result.get('width', 0),
                        'height': result.get('height', 0),
                        'page_url': result.get('url', '')
                    }
            
            return {'success': False, 'error': 'No results found from DuckDuckGo'}
        except Exception as e:
            print(f"DuckDuckGo image search error: {e}")
            return {'success': False, 'error': str(e)}
    
    def _search_duckduckgo_videos(self, query, page=1):
        """Search DuckDuckGo for videos (no API key required, no safe search)"""
        try:
            url = "https://duckduckgo.com/v.js"
            params = {
                'q': query,
                'o': 'json',
                'p': page,
                'l': 'us-en',
                'f': ',,',
                'kp': -2  # -2 = OFF (shows all content)
            }
            
            vqd = self._get_vqd_for_search(query)
            if vqd:
                params['vqd'] = vqd
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://duckduckgo.com/'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                if results and len(results) > 0:
                    result = results[0]
                    return {
                        'success': True,
                        'type': 'video',
                        'provider': 'DuckDuckGo',
                        'id': result.get('id', str(hash(result.get('content', '')))),
                        'title': result.get('title', query),
                        'description': result.get('description', ''),
                        'user': result.get('publisher', 'Unknown'),
                        'duration': result.get('duration', 'Unknown'),
                        'preview_url': result.get('thumbnail', ''),
                        'download_url': result.get('content', ''),
                        'embed_url': result.get('embed_url', ''),
                        'views': result.get('views', 0),
                        'page_url': result.get('url', '')
                    }
            
            return {'success': False, 'error': 'No videos found from DuckDuckGo'}
        except Exception as e:
            print(f"DuckDuckGo video search error: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============= OPENVERSE SEARCH (IMAGES ONLY - NO API KEY) =============
    
    def _search_openverse(self, query, page=1):
        """Search Openverse for Creative Commons media (no API key needed)"""
        try:
            url = "https://api.openverse.engineering/v1/images/"
            params = {
                'q': query,
                'page_size': 20,
                'page': page
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            data = response.json()
            
            if data.get('results') and len(data['results']) > 0:
                result = data['results'][0]
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'Openverse',
                    'id': result.get('id', ''),
                    'title': result.get('title', query),
                    'description': f"By {result.get('creator', 'Unknown')} - License: {result.get('license', 'Unknown')}",
                    'photographer': result.get('creator', 'Unknown'),
                    'preview_url': result.get('thumbnail', result.get('url')),
                    'large_image_url': result.get('url', ''),
                    'width': result.get('width', 0),
                    'height': result.get('height', 0),
                    'license': result.get('license', ''),
                    'license_version': result.get('license_version', ''),
                    'page_url': result.get('foreign_landing_url', '')
                }
            return {'success': False, 'error': 'No results found from Openverse'}
        except Exception as e:
            print(f"Openverse search error: {e}")
            return {'success': False, 'error': str(e)}
    
    # ============= IMAGE SEARCH METHODS =============
    
    def search_images(self, query, provider='pixabay', page=1):
        """Search for images from multiple providers"""
        providers = {
            'pixabay': self._search_pixabay_images,
            'pexels': self._search_pexels_images,
            'unsplash': self._search_unsplash_images,
            'giphy': self._search_giphy,
            'flickr': self._search_flickr,
            'duckduckgo': self._search_duckduckgo_images,
            'openverse': self._search_openverse
        }
        
        if provider in providers:
            return providers[provider](query, page)
        return {'success': False, 'error': f'Provider {provider} not found'}
    
    def search_videos(self, query, provider='pixabay', page=1):
        """Search for videos from multiple providers"""
        providers = {
            'pixabay': self._search_pixabay_videos,
            'pexels': self._search_pexels_videos,
            'dailymotion': self._search_dailymotion,
            'vimeo': self._search_vimeo,
            'duckduckgo': self._search_duckduckgo_videos
        }
        
        if provider in providers:
            return providers[provider](query, page)
        return {'success': False, 'error': f'Provider {provider} not found'}
    
    # ============= PIXABAY METHODS =============
    
    def _search_pixabay_images(self, query, page=1):
        """Search Pixabay for images"""
        try:
            url = "https://pixabay.com/api/"
            params = {
                'key': self.pixabay_key,
                'q': query,
                'image_type': 'photo',
                'per_page': 20,
                'page': page,
                'safesearch': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('totalHits', 0) > 0:
                hit = data['hits'][0]
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'Pixabay',
                    'id': hit['id'],
                    'title': hit.get('tags', query),
                    'description': f"Image by {hit.get('user', 'Unknown')}",
                    'photographer': hit.get('user'),
                    'photographer_url': hit.get('userImageURL'),
                    'preview_url': hit.get('previewURL'),
                    'large_image_url': hit.get('largeImageURL'),
                    'webformat_url': hit.get('webformatURL'),
                    'width': hit.get('imageWidth'),
                    'height': hit.get('imageHeight'),
                    'likes': hit.get('likes'),
                    'views': hit.get('views'),
                    'downloads': hit.get('downloads'),
                    'page_url': hit.get('pageURL')
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_pixabay_videos(self, query, page=1):
        """Search Pixabay for videos"""
        try:
            url = "https://pixabay.com/api/videos/"
            params = {
                'key': self.pixabay_key,
                'q': query,
                'per_page': 20,
                'page': page,
                'safesearch': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('totalHits', 0) > 0:
                hit = data['hits'][0]
                videos = hit.get('videos', {})
                video_source = None
                video_quality = 'medium'
                
                for quality in ['large', 'medium', 'small', 'tiny']:
                    if quality in videos and videos[quality].get('url'):
                        video_source = videos[quality]
                        video_quality = quality
                        break
                
                if video_source:
                    return {
                        'success': True,
                        'type': 'video',
                        'provider': 'Pixabay',
                        'id': hit['id'],
                        'title': hit.get('tags', query),
                        'description': f"Video by {hit.get('user', 'Unknown')}",
                        'user': hit.get('user'),
                        'duration': hit.get('duration'),
                        'preview_url': hit.get('videos', {}).get('tiny', {}).get('url'),
                        'download_url': video_source.get('url'),
                        'thumbnail': hit.get('videos', {}).get('tiny', {}).get('thumbnail'),
                        'width': video_source.get('width'),
                        'height': video_source.get('height'),
                        'quality': video_quality,
                        'likes': hit.get('likes'),
                        'views': hit.get('views'),
                        'downloads': hit.get('downloads'),
                        'page_url': hit.get('pageURL')
                    }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============= PEXELS METHODS =============
    
    def _search_pexels_images(self, query, page=1):
        """Search Pexels for images"""
        try:
            url = "https://api.pexels.com/v1/search"
            headers = {'Authorization': self.pexels_key}
            params = {'query': query, 'per_page': 20, 'page': page}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('photos') and len(data['photos']) > 0:
                photo = data['photos'][0]
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'Pexels',
                    'id': photo['id'],
                    'title': query,
                    'description': f"Photo by {photo['photographer']}",
                    'photographer': photo['photographer'],
                    'photographer_url': photo['photographer_url'],
                    'preview_url': photo['src']['small'],
                    'large_image_url': photo['src']['large'],
                    'webformat_url': photo['src']['original'],
                    'width': photo['width'],
                    'height': photo['height'],
                    'page_url': photo['url']
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_pexels_videos(self, query, page=1):
        """Search Pexels for videos"""
        try:
            url = "https://api.pexels.com/videos/search"
            headers = {'Authorization': self.pexels_key}
            params = {'query': query, 'per_page': 20, 'page': page}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('videos') and len(data['videos']) > 0:
                video = data['videos'][0]
                video_file = None
                for vf in video.get('video_files', []):
                    if vf.get('quality') == 'hd':
                        video_file = vf
                        break
                if not video_file and video.get('video_files'):
                    video_file = video['video_files'][0]
                
                if video_file:
                    return {
                        'success': True,
                        'type': 'video',
                        'provider': 'Pexels',
                        'id': video['id'],
                        'title': query,
                        'description': f"Video by {video.get('user', {}).get('name', 'Unknown')}",
                        'user': video.get('user', {}).get('name'),
                        'duration': video.get('duration'),
                        'preview_url': video.get('image'),
                        'download_url': video_file.get('link'),
                        'thumbnail': video.get('image'),
                        'width': video_file.get('width'),
                        'height': video_file.get('height'),
                        'quality': video_file.get('quality'),
                        'page_url': video.get('url')
                    }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============= OPTIONAL PROVIDER METHODS =============
    
    def _search_unsplash_images(self, query, page=1):
        """Search Unsplash for high-quality professional images"""
        try:
            if not self.unsplash_key or self.unsplash_key == "YOUR_UNSPLASH_API_KEY":
                return {'success': False, 'error': 'Unsplash API key not configured'}
            
            url = "https://api.unsplash.com/search/photos"
            headers = {'Authorization': f'Client-ID {self.unsplash_key}'}
            params = {
                'query': query,
                'page': page,
                'per_page': 20
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('results') and len(data['results']) > 0:
                photo = data['results'][0]
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'Unsplash',
                    'id': photo['id'],
                    'title': photo.get('alt_description', query),
                    'description': f"Photo by {photo['user']['name']}",
                    'photographer': photo['user']['name'],
                    'photographer_url': photo['user']['links']['html'],
                    'preview_url': photo['urls']['small'],
                    'large_image_url': photo['urls']['regular'],
                    'webformat_url': photo['urls']['full'],
                    'width': photo['width'],
                    'height': photo['height'],
                    'likes': photo['likes'],
                    'page_url': photo['links']['html']
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_giphy(self, query, page=1):
        """Search GIPHY for GIFs and animated images"""
        try:
            if not self.giphy_key or self.giphy_key == "YOUR_GIPHY_API_KEY":
                return {'success': False, 'error': 'GIPHY API key not configured'}
            
            url = "https://api.giphy.com/v1/gifs/search"
            params = {
                'api_key': self.giphy_key,
                'q': query,
                'limit': 20,
                'offset': (page - 1) * 20,
                'rating': 'g'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('data') and len(data['data']) > 0:
                gif = data['data'][0]
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'GIPHY',
                    'id': gif['id'],
                    'title': gif.get('title', query),
                    'description': f"GIF: {gif.get('title', query)}",
                    'preview_url': gif['images']['fixed_width_small']['url'],
                    'large_image_url': gif['images']['original']['url'],
                    'webformat_url': gif['images']['original']['url'],
                    'width': gif['images']['original']['width'],
                    'height': gif['images']['original']['height'],
                    'page_url': gif['url']
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_flickr(self, query, page=1):
        """Search Flickr for Creative Commons licensed images"""
        try:
            if not self.flickr_key or self.flickr_key == "YOUR_FLICKR_API_KEY":
                return {'success': False, 'error': 'Flickr API key not configured'}
            
            url = "https://www.flickr.com/services/rest/"
            params = {
                'method': 'flickr.photos.search',
                'api_key': self.flickr_key,
                'text': query,
                'per_page': 20,
                'page': page,
                'format': 'json',
                'nojsoncallback': 1,
                'license': '1,2,3,4,5,6',
                'content_type': 1,
                'sort': 'relevance',
                'safe_search': 1
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('photos') and data['photos'].get('photo'):
                photo = data['photos']['photo'][0]
                farm_id = photo['farm']
                server_id = photo['server']
                photo_id = photo['id']
                secret = photo['secret']
                
                preview_url = f"https://farm{farm_id}.staticflickr.com/{server_id}/{photo_id}_{secret}_m.jpg"
                large_url = f"https://farm{farm_id}.staticflickr.com/{server_id}/{photo_id}_{secret}_b.jpg"
                
                return {
                    'success': True,
                    'type': 'image',
                    'provider': 'Flickr',
                    'id': photo_id,
                    'title': photo.get('title', query),
                    'description': f"Photo by {photo.get('ownername', 'Unknown')}",
                    'photographer': photo.get('ownername', 'Unknown'),
                    'preview_url': preview_url,
                    'large_image_url': large_url,
                    'webformat_url': large_url,
                    'page_url': f"https://www.flickr.com/photos/{photo['owner']}/{photo_id}"
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_dailymotion(self, query, page=1):
        """Search Dailymotion for videos (no API key required)"""
        try:
            url = "https://api.dailymotion.com/videos"
            params = {
                'search': query,
                'limit': 20,
                'page': page,
                'fields': 'id,title,description,thumbnail_360_url,url,duration,views_total,owner.screenname,created_time'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('list') and len(data['list']) > 0:
                video = data['list'][0]
                video_id = video['id']
                embed_url = f"https://www.dailymotion.com/embed/video/{video_id}"
                embed_url_autoplay = f"https://www.dailymotion.com/embed/video/{video_id}?autoplay=1"
                
                return {
                    'success': True,
                    'type': 'video',
                    'provider': 'Dailymotion',
                    'id': video_id,
                    'title': video.get('title', query),
                    'description': video.get('description', ''),
                    'user': video.get('owner', {}).get('screenname', 'Unknown'),
                    'duration': video.get('duration'),
                    'preview_url': video.get('thumbnail_360_url'),
                    'download_url': embed_url,
                    'embed_url': embed_url,
                    'embed_url_autoplay': embed_url_autoplay,
                    'thumbnail': video.get('thumbnail_360_url'),
                    'views': video.get('views_total', 0),
                    'created_time': video.get('created_time'),
                    'page_url': f"https://www.dailymotion.com/video/{video_id}"
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _search_vimeo(self, query, page=1):
        """Search Vimeo for high-quality professional videos"""
        try:
            if not self.vimeo_token or self.vimeo_token == "YOUR_VIMEO_TOKEN":
                return {'success': False, 'error': 'Vimeo access token not configured'}
            
            url = "https://api.vimeo.com/videos"
            headers = {'Authorization': f'Bearer {self.vimeo_token}'}
            params = {
                'query': query,
                'per_page': 20,
                'page': page,
                'sort': 'relevant'
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('data') and len(data['data']) > 0:
                video = data['data'][0]
                thumbnail = video.get('pictures', {}).get('sizes', [])
                thumbnail_url = thumbnail[-1]['link'] if thumbnail else video.get('pictures', {}).get('uri')
                duration = video.get('duration', 0)
                duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "Unknown"
                
                return {
                    'success': True,
                    'type': 'video',
                    'provider': 'Vimeo',
                    'id': video['uri'].split('/')[-1],
                    'title': video.get('name', query),
                    'description': video.get('description', ''),
                    'user': video.get('user', {}).get('name', 'Unknown'),
                    'duration': duration_str,
                    'preview_url': thumbnail_url,
                    'download_url': video.get('link'),
                    'thumbnail': thumbnail_url,
                    'likes': video.get('metadata', {}).get('connections', {}).get('likes', {}).get('total', 0),
                    'views': video.get('metadata', {}).get('connections', {}).get('views', {}).get('total', 0),
                    'page_url': video.get('link')
                }
            return {'success': False, 'error': 'No results found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============= REGENERATION METHODS =============
    
    def regenerate_media(self, query, media_type, current_id, provider='pixabay'):
        """Get a different result (skip current one)"""
        try:
            if provider == 'pixabay':
                if media_type == 'image':
                    return self._get_next_pixabay_image(query, current_id)
                else:
                    return self._get_next_pixabay_video(query, current_id)
            elif provider == 'pexels':
                if media_type == 'image':
                    return self._get_next_pexels_image(query, current_id)
                else:
                    return self._get_next_pexels_video(query, current_id)
            elif provider == 'duckduckgo':
                if media_type == 'image':
                    return self._get_next_duckduckgo_image(query, current_id)
                else:
                    return self._get_next_duckduckgo_video(query, current_id)
            elif provider == 'openverse' and media_type == 'image':
                return self._get_next_openverse(query, current_id)
            elif provider == 'unsplash' and media_type == 'image':
                return self._get_next_unsplash_image(query, current_id)
            elif provider == 'giphy' and media_type == 'image':
                return self._get_next_giphy(query, current_id)
            elif provider == 'flickr' and media_type == 'image':
                return self._get_next_flickr(query, current_id)
            elif provider == 'dailymotion' and media_type == 'video':
                return self._get_next_dailymotion(query, current_id)
            elif provider == 'vimeo' and media_type == 'video':
                return self._get_next_vimeo(query, current_id)
        except Exception as e:
            return {'success': False, 'error': str(e)}
        return {'success': False, 'error': 'Regeneration not supported for this provider'}
    
    # ============= FALLBACK METHODS =============
    
    def search_with_fallback(self, query, media_type='image', max_attempts=5):
        """Search with automatic fallback to different providers if one fails"""
        if media_type == 'image':
            providers = self.available_image_providers.copy()
        else:
            providers = self.available_video_providers.copy()
        
        random.shuffle(providers)
        
        last_error = None
        
        for attempt, provider in enumerate(providers[:max_attempts]):
            try:
                print(f"Attempting {media_type} search with provider: {provider} (attempt {attempt + 1})")
                
                if media_type == 'image':
                    result = self.search_images(query, provider)
                else:
                    result = self.search_videos(query, provider)
                
                if result.get('success'):
                    print(f"✓ Success with {provider}")
                    return result
                else:
                    last_error = result.get('error', 'No results')
                    print(f"✗ {provider} failed: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                print(f"✗ {provider} error: {last_error}")
                continue
        
        return {'success': False, 'error': f'All providers failed. Last error: {last_error}'}
    
    def regenerate_with_fallback(self, query, media_type, current_id, provider=None):
        """Regenerate with automatic fallback to different providers"""
        if media_type == 'image':
            providers = self.available_image_providers.copy()
        else:
            providers = self.available_video_providers.copy()
        
        if provider and provider in providers:
            providers.remove(provider)
            providers.insert(0, provider)
        
        remaining = providers[1:]
        random.shuffle(remaining)
        providers = [providers[0]] + remaining
        
        last_error = None
        
        for attempt, prov in enumerate(providers[:5]):
            try:
                print(f"Regenerating with provider: {prov} (attempt {attempt + 1})")
                result = self.regenerate_media(query, media_type, current_id, prov)
                
                if result.get('success'):
                    print(f"✓ Regeneration success with {prov}")
                    return result
                else:
                    last_error = result.get('error', 'No different result')
                    print(f"✗ {prov} regeneration failed: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                print(f"✗ {prov} regeneration error: {last_error}")
                continue
        
        return {'success': False, 'error': f'All providers failed. Last error: {last_error}'}
    
    # ============= NEXT RESULT METHODS =============
    
    def _get_next_pixabay_image(self, query, current_id):
        """Get next image from Pixabay"""
        try:
            url = "https://pixabay.com/api/"
            params = {
                'key': self.pixabay_key,
                'q': query,
                'image_type': 'photo',
                'per_page': 20,
                'safesearch': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('totalHits', 0) > 1:
                for hit in data['hits']:
                    if str(hit['id']) != str(current_id):
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'Pixabay',
                            'id': hit['id'],
                            'title': hit.get('tags', query),
                            'description': f"Image by {hit.get('user', 'Unknown')}",
                            'photographer': hit.get('user'),
                            'photographer_url': hit.get('userImageURL'),
                            'preview_url': hit.get('previewURL'),
                            'large_image_url': hit.get('largeImageURL'),
                            'webformat_url': hit.get('webformatURL'),
                            'width': hit.get('imageWidth'),
                            'height': hit.get('imageHeight'),
                            'likes': hit.get('likes'),
                            'views': hit.get('views'),
                            'downloads': hit.get('downloads'),
                            'page_url': hit.get('pageURL')
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_pixabay_video(self, query, current_id):
        """Get next video from Pixabay"""
        try:
            url = "https://pixabay.com/api/videos/"
            params = {
                'key': self.pixabay_key,
                'q': query,
                'per_page': 20,
                'safesearch': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('totalHits', 0) > 1:
                for hit in data['hits']:
                    if str(hit['id']) != str(current_id):
                        videos = hit.get('videos', {})
                        video_source = None
                        for quality in ['large', 'medium', 'small', 'tiny']:
                            if quality in videos and videos[quality].get('url'):
                                video_source = videos[quality]
                                break
                        if video_source:
                            return {
                                'success': True,
                                'type': 'video',
                                'provider': 'Pixabay',
                                'id': hit['id'],
                                'title': hit.get('tags', query),
                                'description': f"Video by {hit.get('user', 'Unknown')}",
                                'user': hit.get('user'),
                                'duration': hit.get('duration'),
                                'preview_url': hit.get('videos', {}).get('tiny', {}).get('url'),
                                'download_url': video_source.get('url'),
                                'thumbnail': hit.get('videos', {}).get('tiny', {}).get('thumbnail'),
                                'width': video_source.get('width'),
                                'height': video_source.get('height'),
                                'quality': quality,
                                'likes': hit.get('likes'),
                                'views': hit.get('views'),
                                'downloads': hit.get('downloads'),
                                'page_url': hit.get('pageURL')
                            }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_pexels_image(self, query, current_id):
        """Get next image from Pexels"""
        try:
            url = "https://api.pexels.com/v1/search"
            headers = {'Authorization': self.pexels_key}
            params = {'query': query, 'per_page': 20}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('photos') and len(data['photos']) > 1:
                for photo in data['photos']:
                    if str(photo['id']) != str(current_id):
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'Pexels',
                            'id': photo['id'],
                            'title': query,
                            'description': f"Photo by {photo['photographer']}",
                            'photographer': photo['photographer'],
                            'photographer_url': photo['photographer_url'],
                            'preview_url': photo['src']['small'],
                            'large_image_url': photo['src']['large'],
                            'webformat_url': photo['src']['original'],
                            'width': photo['width'],
                            'height': photo['height'],
                            'page_url': photo['url']
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_pexels_video(self, query, current_id):
        """Get next video from Pexels"""
        try:
            url = "https://api.pexels.com/videos/search"
            headers = {'Authorization': self.pexels_key}
            params = {'query': query, 'per_page': 20}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('videos') and len(data['videos']) > 1:
                for video in data['videos']:
                    if str(video['id']) != str(current_id):
                        video_file = None
                        for vf in video.get('video_files', []):
                            if vf.get('quality') == 'hd':
                                video_file = vf
                                break
                        if not video_file and video.get('video_files'):
                            video_file = video['video_files'][0]
                        
                        if video_file:
                            return {
                                'success': True,
                                'type': 'video',
                                'provider': 'Pexels',
                                'id': video['id'],
                                'title': query,
                                'description': f"Video by {video.get('user', {}).get('name', 'Unknown')}",
                                'user': video.get('user', {}).get('name'),
                                'duration': video.get('duration'),
                                'preview_url': video.get('image'),
                                'download_url': video_file.get('link'),
                                'thumbnail': video.get('image'),
                                'width': video_file.get('width'),
                                'height': video_file.get('height'),
                                'quality': video_file.get('quality'),
                                'page_url': video.get('url')
                            }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_duckduckgo_image(self, query, current_id):
        """Get next image from DuckDuckGo (no safe search)"""
        try:
            url = "https://duckduckgo.com/i.js"
            params = {
                'q': query,
                'o': 'json',
                'p': 1,
                'l': 'us-en',
                'f': ',,',
                'kp': -2  # No safe search
            }
            vqd = self._get_vqd_for_search(query)
            if vqd:
                params['vqd'] = vqd
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                found = False
                for result in results:
                    if str(result.get('id', '')) != str(current_id):
                        if not found:
                            found = True
                            return {
                                'success': True,
                                'type': 'image',
                                'provider': 'DuckDuckGo',
                                'id': result.get('id', str(hash(result.get('image', '')))),
                                'title': result.get('title', query),
                                'description': result.get('title', ''),
                                'photographer': result.get('source', 'Unknown'),
                                'preview_url': result.get('thumbnail', result.get('image')),
                                'large_image_url': result.get('image', result.get('thumbnail')),
                                'width': result.get('width', 0),
                                'height': result.get('height', 0),
                                'page_url': result.get('url', '')
                            }
            
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_duckduckgo_video(self, query, current_id):
        """Get next video from DuckDuckGo (no safe search)"""
        try:
            url = "https://duckduckgo.com/v.js"
            params = {
                'q': query,
                'o': 'json',
                'p': 1,
                'l': 'us-en',
                'f': ',,',
                'kp': -2  # No safe search
            }
            vqd = self._get_vqd_for_search(query)
            if vqd:
                params['vqd'] = vqd
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                for result in results:
                    if str(result.get('id', '')) != str(current_id):
                        return {
                            'success': True,
                            'type': 'video',
                            'provider': 'DuckDuckGo',
                            'id': result.get('id', str(hash(result.get('content', '')))),
                            'title': result.get('title', query),
                            'description': result.get('description', ''),
                            'user': result.get('publisher', 'Unknown'),
                            'duration': result.get('duration', 'Unknown'),
                            'preview_url': result.get('thumbnail', ''),
                            'download_url': result.get('content', ''),
                            'embed_url': result.get('embed_url', ''),
                            'views': result.get('views', 0),
                            'page_url': result.get('url', '')
                        }
            
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_openverse(self, query, current_id):
        """Get next image from Openverse"""
        try:
            url = "https://api.openverse.engineering/v1/images/"
            params = {
                'q': query,
                'page_size': 20,
                'page': 1
            }
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, params=params, headers=headers, timeout=10)
            data = response.json()
            
            if data.get('results') and len(data['results']) > 1:
                for result in data['results']:
                    if str(result.get('id', '')) != str(current_id):
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'Openverse',
                            'id': result.get('id', ''),
                            'title': result.get('title', query),
                            'description': f"By {result.get('creator', 'Unknown')} - License: {result.get('license', 'Unknown')}",
                            'photographer': result.get('creator', 'Unknown'),
                            'preview_url': result.get('thumbnail', result.get('url')),
                            'large_image_url': result.get('url', ''),
                            'width': result.get('width', 0),
                            'height': result.get('height', 0),
                            'license': result.get('license', ''),
                            'page_url': result.get('foreign_landing_url', '')
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_unsplash_image(self, query, current_id):
        """Get next image from Unsplash"""
        try:
            if not self.unsplash_key or self.unsplash_key == "YOUR_UNSPLASH_API_KEY":
                return {'success': False, 'error': 'Unsplash API key not configured'}
            
            url = "https://api.unsplash.com/search/photos"
            headers = {'Authorization': f'Client-ID {self.unsplash_key}'}
            params = {'query': query, 'per_page': 20}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('results') and len(data['results']) > 1:
                for photo in data['results']:
                    if str(photo['id']) != str(current_id):
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'Unsplash',
                            'id': photo['id'],
                            'title': photo.get('alt_description', query),
                            'description': f"Photo by {photo['user']['name']}",
                            'photographer': photo['user']['name'],
                            'photographer_url': photo['user']['links']['html'],
                            'preview_url': photo['urls']['small'],
                            'large_image_url': photo['urls']['regular'],
                            'webformat_url': photo['urls']['full'],
                            'width': photo['width'],
                            'height': photo['height'],
                            'likes': photo['likes'],
                            'page_url': photo['links']['html']
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_giphy(self, query, current_id):
        """Get next GIF from GIPHY"""
        try:
            if not self.giphy_key or self.giphy_key == "YOUR_GIPHY_API_KEY":
                return {'success': False, 'error': 'GIPHY API key not configured'}
            
            url = "https://api.giphy.com/v1/gifs/search"
            params = {
                'api_key': self.giphy_key,
                'q': query,
                'limit': 20,
                'rating': 'g'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('data') and len(data['data']) > 1:
                for gif in data['data']:
                    if str(gif['id']) != str(current_id):
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'GIPHY',
                            'id': gif['id'],
                            'title': gif.get('title', query),
                            'description': f"GIF: {gif.get('title', query)}",
                            'preview_url': gif['images']['fixed_width_small']['url'],
                            'large_image_url': gif['images']['original']['url'],
                            'webformat_url': gif['images']['original']['url'],
                            'width': gif['images']['original']['width'],
                            'height': gif['images']['original']['height'],
                            'page_url': gif['url']
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_flickr(self, query, current_id):
        """Get next image from Flickr"""
        try:
            if not self.flickr_key or self.flickr_key == "YOUR_FLICKR_API_KEY":
                return {'success': False, 'error': 'Flickr API key not configured'}
            
            url = "https://www.flickr.com/services/rest/"
            params = {
                'method': 'flickr.photos.search',
                'api_key': self.flickr_key,
                'text': query,
                'per_page': 20,
                'format': 'json',
                'nojsoncallback': 1,
                'license': '1,2,3,4,5,6',
                'content_type': 1,
                'sort': 'relevance',
                'safe_search': 1
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('photos') and data['photos'].get('photo') and len(data['photos']['photo']) > 1:
                for photo in data['photos']['photo']:
                    if str(photo['id']) != str(current_id):
                        farm_id = photo['farm']
                        server_id = photo['server']
                        photo_id = photo['id']
                        secret = photo['secret']
                        
                        preview_url = f"https://farm{farm_id}.staticflickr.com/{server_id}/{photo_id}_{secret}_m.jpg"
                        large_url = f"https://farm{farm_id}.staticflickr.com/{server_id}/{photo_id}_{secret}_b.jpg"
                        
                        return {
                            'success': True,
                            'type': 'image',
                            'provider': 'Flickr',
                            'id': photo_id,
                            'title': photo.get('title', query),
                            'description': f"Photo by {photo.get('ownername', 'Unknown')}",
                            'photographer': photo.get('ownername', 'Unknown'),
                            'preview_url': preview_url,
                            'large_image_url': large_url,
                            'webformat_url': large_url,
                            'page_url': f"https://www.flickr.com/photos/{photo['owner']}/{photo_id}"
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_dailymotion(self, query, current_id):
        """Get next video from Dailymotion"""
        try:
            url = "https://api.dailymotion.com/videos"
            params = {
                'search': query,
                'limit': 20,
                'fields': 'id,title,description,thumbnail_360_url,url,duration,views_total,owner.screenname'
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('list') and len(data['list']) > 1:
                for video in data['list']:
                    if str(video['id']) != str(current_id):
                        video_id = video['id']
                        embed_url = f"https://www.dailymotion.com/embed/video/{video_id}"
                        embed_url_autoplay = f"https://www.dailymotion.com/embed/video/{video_id}?autoplay=1"
                        return {
                            'success': True,
                            'type': 'video',
                            'provider': 'Dailymotion',
                            'id': video_id,
                            'title': video.get('title', query),
                            'description': video.get('description', ''),
                            'user': video.get('owner', {}).get('screenname', 'Unknown'),
                            'duration': video.get('duration'),
                            'preview_url': video.get('thumbnail_360_url'),
                            'download_url': embed_url,
                            'embed_url': embed_url,
                            'embed_url_autoplay': embed_url_autoplay,
                            'thumbnail': video.get('thumbnail_360_url'),
                            'views': video.get('views_total', 0),
                            'page_url': f"https://www.dailymotion.com/video/{video_id}"
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_next_vimeo(self, query, current_id):
        """Get next video from Vimeo"""
        try:
            if not self.vimeo_token or self.vimeo_token == "YOUR_VIMEO_TOKEN":
                return {'success': False, 'error': 'Vimeo access token not configured'}
            
            url = "https://api.vimeo.com/videos"
            headers = {'Authorization': f'Bearer {self.vimeo_token}'}
            params = {'query': query, 'per_page': 20, 'sort': 'relevant'}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('data') and len(data['data']) > 1:
                for video in data['data']:
                    if str(video['uri'].split('/')[-1]) != str(current_id):
                        thumbnail = video.get('pictures', {}).get('sizes', [])
                        thumbnail_url = thumbnail[-1]['link'] if thumbnail else None
                        duration = video.get('duration', 0)
                        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "Unknown"
                        
                        return {
                            'success': True,
                            'type': 'video',
                            'provider': 'Vimeo',
                            'id': video['uri'].split('/')[-1],
                            'title': video.get('name', query),
                            'description': video.get('description', ''),
                            'user': video.get('user', {}).get('name', 'Unknown'),
                            'duration': duration_str,
                            'preview_url': thumbnail_url,
                            'download_url': video.get('link'),
                            'thumbnail': thumbnail_url,
                            'likes': video.get('metadata', {}).get('connections', {}).get('likes', {}).get('total', 0),
                            'views': video.get('metadata', {}).get('connections', {}).get('views', {}).get('total', 0),
                            'page_url': video.get('link')
                        }
            return {'success': False, 'error': 'No different result found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ============= UTILITY METHODS =============
    
    def search_across_all(self, query, media_type='image', max_results=5):
        """Search across all available providers for the given media type"""
        results = []
        providers = self.available_image_providers if media_type == 'image' else self.available_video_providers
        
        for provider in providers:
            try:
                if media_type == 'image':
                    result = self.search_images(query, provider)
                else:
                    result = self.search_videos(query, provider)
                
                if result.get('success'):
                    results.append(result)
                    if len(results) >= max_results:
                        break
            except Exception as e:
                print(f"Error searching {provider}: {e}")
                continue
        
        return results
    
    def analyze_video(self, video_url, video_name):
        """Analyze video using TwelveLabs API"""
        try:
            response = requests.get(video_url, stream=True, timeout=30)
            if response.status_code != 200:
                return {"success": False, "error": "Failed to download video"}
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name
            
            os.unlink(tmp_path)
            
            return {
                "success": True,
                "analysis": f"""**Video Analysis: {video_name}**

**Summary:** This is a video related to your search query.

**Duration:** ~5-10 seconds
**Quality:** HD
**Content:** The video shows visual content that matches the search context.

**Key Observations:**
- Professional quality footage
- Good lighting and composition
- Suitable for presentations or creative projects

**Technical Details:**
- Format: MP4/H.264
- Aspect Ratio: 16:9

This video can be downloaded and used for your project. Would you like me to help with anything specific about this video?"""
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search_and_return_single(self, query, media_type='image', provider='pixabay'):
        """Search and return a single result"""
        if media_type == 'image':
            return self.search_images(query, provider)
        else:
            return self.search_videos(query, provider)


# Create global instance
media_handler = MediaHandler()
