import xbmc
import requests
import json
import xbmcaddon
import uuid

class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.addon = xbmcaddon.Addon()
        
        try:
            setting_val = self.addon.getSetting('api_timeout')
            self.timeout = int(setting_val) if setting_val else 2
        except:
            self.timeout = 2

        self.user_id = self._get_or_create_user_id()

    def _get_or_create_user_id(self):
        stored_id = self.addon.getSetting('user_uuid')
        
        if not stored_id:
            new_id = str(uuid.uuid4())
            self.addon.setSetting('user_uuid', new_id)
            return new_id
        
        return stored_id
    
    def _get_headers(self):
        return {
            'User-Agent': 'Kodi/StreamedEZ',
            'X-User-ID': self.user_id
        }
    
    def _make_request(self, endpoint, method='GET', data=None, params=None):
        try:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            
            headers = self._get_headers()
            
            if method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=self.timeout)
            else:
                response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            xbmc.log("StreamedEZ: API Timeout", xbmc.LOGERROR)
            raise Exception(f"Connection timed out ({self.timeout}s). Check API settings.\nCurrent URL: {self.base_url}")
            
        except requests.exceptions.ConnectionError:
            xbmc.log("StreamedEZ: API Connection Error", xbmc.LOGERROR)
            raise Exception(f"Could not connect. Check API settings.\nCurrent URL: {self.base_url}")
            
        except requests.exceptions.HTTPError as e:
            xbmc.log(f"StreamedEZ: API HTTP Error {e.response.status_code}", xbmc.LOGERROR)
            raise Exception(f"Server Error ({e.response.status_code})")
            
        except Exception as e:
            xbmc.log(f"StreamedEZ: API Request failed: {str(e)}", xbmc.LOGERROR)
            raise Exception(f"API Error: {str(e)}")
    
    def get_sports(self):
        return self._make_request('full/sports')

    def get_kodi_data(self):
        return self._make_request('kodi/data.json')