import xbmc
import xbmcaddon
import xbmcvfs
import os
import json
import time
from datetime import datetime, timedelta

class CacheHelper:
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        # translatePath is crucial for compatibility across different OS file systems
        profile_path = xbmcvfs.translatePath(self.addon.getAddonInfo('profile'))
        self.cache_dir = os.path.join(profile_path, 'cache')
        
        if not xbmcvfs.exists(self.cache_dir):
            xbmc.log(f"StreamedEZ: Creating cache dir at {self.cache_dir}", xbmc.LOGINFO)
            success = xbmcvfs.mkdirs(self.cache_dir)
            if not success:
                xbmc.log(f"StreamedEZ: FAILED to create cache dir at {self.cache_dir}", xbmc.LOGERROR)
    
    def get(self, cache_key):
        """Standard get: returns None if expired (and deletes)."""
        data, is_expired = self.get_extended(cache_key)
        if is_expired:
            return None
        return data

    def get_extended(self, cache_key):
        """
        Retrieves data and expiration status.
        Returns tuple: (data, is_expired)
        Does NOT delete the file if expired, allowing for stale fallback.
        """
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if not xbmcvfs.exists(cache_file):
            return None, True
        
        try:
            with xbmcvfs.File(cache_file, 'r') as f:
                content = f.read()
                cache_data = json.loads(content)
            
            is_expired = time.time() > cache_data.get('expires_at', 0)
            return cache_data.get('data'), is_expired
            
        except Exception as e:
            xbmc.log(f"CacheHelper: Error reading cache {cache_key}: {str(e)}", xbmc.LOGERROR)
            return None, True
    
    def set(self, cache_key, data, ttl_hours=24):
        """Saves data to cache with a specified time-to-live."""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        cache_data = {
            'data': data,
            'created_at': time.time(),
            'expires_at': time.time() + (ttl_hours * 3600),
            'created_human': datetime.now().isoformat()
        }
        
        try:
            with xbmcvfs.File(cache_file, 'w') as f:
                f.write(json.dumps(cache_data))
            return True
        except Exception as e:
            xbmc.log(f"CacheHelper: Error writing cache {cache_key}: {str(e)}", xbmc.LOGERROR)
            return False
    
    def clear(self, cache_key=None):
        """Clears a specific cache key or the entire cache directory."""
        if cache_key:
            cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
            if xbmcvfs.exists(cache_file):
                xbmcvfs.delete(cache_file)
        else:
            dirs, files = xbmcvfs.listdir(self.cache_dir)
            for file in files:
                if file.endswith('.json'):
                    xbmcvfs.delete(os.path.join(self.cache_dir, file))

    def cleanup_cache(self, max_age_hours=48):
        """Scans cache directory and removes files older than max_age_hours."""
        try:
            if not xbmcvfs.exists(self.cache_dir):
                return

            dirs, files = xbmcvfs.listdir(self.cache_dir)
            now = time.time()
            cutoff = now - (max_age_hours * 3600)
            
            for file in files:
                file_path = os.path.join(self.cache_dir, file)
                try:
                    # Use xbmcvfs.Stat to get modification time
                    stat = xbmcvfs.Stat(file_path)
                    # st_mtime() returns a float timestamp
                    if stat.st_mtime() < cutoff:
                        xbmcvfs.delete(file_path)
                        xbmc.log(f"StreamedEZ: Deleted expired cache file {file}", xbmc.LOGDEBUG)
                except Exception as inner_e:
                    # Individual file errors shouldn't break the loop
                    pass
        except Exception as e:
            xbmc.log(f"StreamedEZ: Cache cleanup error: {str(e)}", xbmc.LOGERROR)