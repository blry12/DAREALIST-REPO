import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import sys
import urllib.parse
import requests
import base64
import re
import certifi
import xbmcvfs
import os
from datetime import datetime, timedelta

try:
    from resources.lib.api_client import APIClient
    from resources.lib.cache_helper import CacheHelper
except ImportError:
    from api_client import APIClient
    from cache_helper import CacheHelper

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

API_SERVERS = [
    "http://streamedez.hidenmc.com:24670",
    "http://june.hidencloud.com:24670",
    "http://fi7.bot-hosting.net:22382"
]

cache_helper = CacheHelper()

def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"StreamedEZ: {msg}", level)

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def fetch_from_api(method_name):
    last_error = None
    
    for url in API_SERVERS:
        try:
            client = APIClient(url)
            
            if method_name == 'get_sports':
                return client.get_sports()
            elif method_name == 'get_kodi_data':
                return client.get_kodi_data()
            else:
                raise ValueError(f"Unknown API method: {method_name}")
                
        except Exception as e:
            log(f"Connection failed for {url}: {str(e)}", level=xbmc.LOGWARNING)
            last_error = e
            continue
            
    log(f"All API servers failed. Last error: {str(last_error)}", level=xbmc.LOGERROR)
    raise last_error if last_error else Exception("No API servers available")

def get_clean_timestamp(match):
    try:
        ts = float(match.get('start_time', 0) or 0)
        if ts > 100000000000: 
            ts = ts / 1000
        return ts
    except:
        return 0

def get_sports_list():
    cached = cache_helper.get('sports_list')
    if cached: return cached
    
    try:
        response = fetch_from_api('get_sports')
        
        if response and 'sports' in response:
            data = response['sports']
            cache_helper.set('sports_list', data, ttl_hours=24)
            return data
            
    except Exception as e:
        xbmcgui.Dialog().ok(ADDON_NAME, f"Failed to load sports list:\nCould not connect to any server.")
        return []
    
    return []

def get_kodi_data():
    cached = cache_helper.get('kodi_data')
    if cached: return cached
    
    try:
        data = fetch_from_api('get_kodi_data')
        
        if data:
            cache_helper.set('kodi_data', data, ttl_hours=0.08) 
            return data
            
    except Exception as e:
        xbmcgui.Dialog().ok(ADDON_NAME, f"Failed to load match data:\nCould not connect to any server.")
        return None
        
    return None

def get_duration_hours(sport_name):
    if not sport_name: return int(ADDON.getSetting('duration_default') or 4)
    s = sport_name.lower()
    
    setting_map = {
        'soccer': 'duration_soccer',
        'football': 'duration_football', 'nfl': 'duration_football', 'ncaa': 'duration_football',
        'basketball': 'duration_basketball', 'nba': 'duration_basketball',
        'baseball': 'duration_baseball', 'mlb': 'duration_baseball',
        'hockey': 'duration_hockey', 'nhl': 'duration_hockey',
        'boxing': 'duration_fighting', 'mma': 'duration_fighting', 'fight': 'duration_fighting', 'ufc': 'duration_fighting',
        'racing': 'duration_racing', 'f1': 'duration_racing', 'nascar': 'duration_racing', 'motor': 'duration_racing',
        'cricket': 'duration_cricket'
    }
    
    for key, setting_id in setting_map.items():
        if key in s:
            try:
                val = ADDON.getSetting(setting_id)
                return int(val) if val else 4
            except:
                return 4
                
    try:
        val = ADDON.getSetting('duration_default')
        return int(val) if val else 4
    except:
        return 4

def get_pre_game_seconds():
    try:
        minutes = int(ADDON.getSetting('pre_game_window') or 30)
        return minutes * 60
    except:
        return 1800 

def format_match_time(ts, sport_name=None):
    if not ts: return ""
    try:
        ts = float(ts)
        if ts > 100000000000: ts = ts / 1000
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        
        diff = (now - dt).total_seconds()
        
        duration_hours = get_duration_hours(sport_name)
        
        if 0 <= diff <= (duration_hours * 3600):
            return f"[COLOR red]LIVE[/COLOR] [{dt.strftime('%H:%M')}] "
        
        if dt.date() == now.date():
            return f"[{dt.strftime('%H:%M')}] "
        if dt.date() == (now + timedelta(days=1)).date():
            return f"Tomorrow [{dt.strftime('%H:%M')}] "
        return f"{dt.strftime('%a')} [{dt.strftime('%H:%M')}] "
    except: return ""

def is_match_live(start_ts, sport_name=None):
    if start_ts == 0: return True 
    try:
        ts = float(start_ts)
        if ts > 100000000000: ts = ts / 1000
        dt = datetime.fromtimestamp(ts)
        now = datetime.now()
        diff = (now - dt).total_seconds()
        
        duration_hours = get_duration_hours(sport_name)
        pre_game_seconds = get_pre_game_seconds()
        
        return -pre_game_seconds <= diff <= (duration_hours * 3600)
    except:
        return False

def is_future_or_grace_period(start_ts, grace_minutes=5):
    if not start_ts: return False
    try:
        ts = float(start_ts)
        if ts > 100000000000: ts = ts / 1000
        now_ts = datetime.now().timestamp()
        seconds_since_start = now_ts - ts
        return seconds_since_start < (grace_minutes * 60)
    except:
        return False

def get_processed_sports():
    sports = get_sports_list()
    if not sports: return []
    
    filtered_sports = []
    for sport in sports:
        raw_val = sport.get('group_to_other', False)
        should_group = False
        
        if isinstance(raw_val, bool):
            should_group = raw_val
        elif isinstance(raw_val, str):
            should_group = raw_val.lower() == 'true'
        elif isinstance(raw_val, int):
            should_group = raw_val == 1
            
        if should_group:
            continue
            
        if sport.get('id') == 'fight':
            sport['name'] = 'Boxing-MMA-Wrassling'
        
        filtered_sports.append(sport)
    return filtered_sports

def normalize_name(name):
    if not name: return ""
    return name.lower().strip().replace('-', ' ').replace('_', ' ')

def find_match_in_data(data, match_id, sport_name):
    if not data or 'sports' not in data:
        return None

    target_match = None
    search_order = []
    
    if sport_name:
        others = []
        target_name_norm = normalize_name(sport_name)
        
        for s in data.get('sports', []):
            s_name_norm = normalize_name(s['name'])
            is_match = False
            
            if s['name'].lower() == sport_name.lower(): is_match = True
            elif s_name_norm == target_name_norm: is_match = True
            elif s.get('id') == 'fight' and 'boxing mma' in target_name_norm: is_match = True
            
            if is_match:
                search_order.append(s)
            else:
                others.append(s)
        search_order.extend(others)
    else:
        search_order = data.get('sports', [])

    for s in search_order:
        for m in s.get('matches', []):
            if str(m.get('id')) == str(match_id):
                target_match = m
                break
        if target_match: break
        
    return target_match

def verify_stream(url, referer):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': referer if referer else url
    }
    
    response = requests.get(url, headers=headers, timeout=10, verify=False)
    response.raise_for_status()
    
    playlist_content = response.text
    
    if '.png' in playlist_content:
        log("Detected disguised segments (.png), patching to .ts")
        modified_playlist = playlist_content.replace('.png', '.ts')
        encoded_playlist = base64.b64encode(modified_playlist.encode('utf-8')).decode('utf-8')
        play_url = f"data:application/vnd.apple.mpegurl;base64,{encoded_playlist}"
    else:
        play_url = url

    li = xbmcgui.ListItem(path=play_url)
    li.setProperty('inputstream', 'inputstream.adaptive')
    li.setProperty('inputstream.adaptive.manifest_type', 'hls')
    
    ua = headers['User-Agent']
    ref = headers['Referer']
    stream_headers = f'User-Agent={ua}&Referer={ref}'
    
    li.setProperty('inputstream.adaptive.manifest_headers', stream_headers)
    li.setProperty('inputstream.adaptive.stream_headers', stream_headers)
    
    return li

def clear_full_cache():
    cache_helper.clear()
    xbmcgui.Dialog().notification(ADDON_NAME, 'Cache Cleared Successfully', xbmcgui.NOTIFICATION_INFO)
    xbmc.executebuiltin('Container.Refresh')

def refresh_cache():
    cache_helper.clear()
    xbmcgui.Dialog().notification(ADDON_NAME, 'Cache Cleared', xbmcgui.NOTIFICATION_INFO)
    xbmc.executebuiltin('Container.Refresh')

def add_refresh_context_menu(list_item):
    refresh_url = build_url({'mode': 'refresh_cache'})
    list_item.addContextMenuItems([('Refresh Data', f'RunPlugin({refresh_url})')])

def menu_main():
    li = xbmcgui.ListItem(label="[COLOR red]Live Now[/COLOR]")
    li.setInfo('video', {'title': "Live Now", 'plot': "Show all currently live matches"})
    url = build_url({'mode': 'live_now'})
    add_refresh_context_menu(li)
    xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=True)

    sports = get_processed_sports()
    if not sports:
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    for sport in sports:
        url = build_url({'mode': 'matches', 'sport_id': sport['id'], 'sport_name': sport['name']})
        li = xbmcgui.ListItem(label=sport['name'])
        li.setInfo('video', {'title': sport['name'], 'plot': f"Browse {sport['name']} matches"})
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def menu_live_now():
    data = get_kodi_data()
    if not data or 'sports' not in data:
        if not data: 
             xbmcplugin.endOfDirectory(ADDON_HANDLE)
             return
        xbmcgui.Dialog().notification(ADDON_NAME, 'No data available', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    show_all = ADDON.getSetting('show_all_matches') == 'true'

    live_matches_to_sort = []
    
    for sport in data['sports']:
        sport_name = sport['name']
        if sport.get('id') == 'fight': 
            sport_name = 'Boxing-MMA-Wrassling'

        for match in sport.get('matches', []):
            start = match.get('start_time', 0)
            
            if is_match_live(start, sport_name):
                has_playable = match.get('has_playable_source', False)
                
                if show_all or has_playable:
                    match_copy = match.copy()
                    match_copy['_sport_name'] = sport_name
                    live_matches_to_sort.append(match_copy)

    now_ts = datetime.now().timestamp()
    started_matches = []
    upcoming_matches = []
    
    for m in live_matches_to_sort:
        ts = get_clean_timestamp(m)
        if ts <= now_ts:
            started_matches.append(m)
        else:
            upcoming_matches.append(m)
            
    started_matches.sort(key=lambda x: get_clean_timestamp(x), reverse=True)
    
    upcoming_matches.sort(key=lambda x: get_clean_timestamp(x))
    
    final_display_list = started_matches + upcoming_matches

    if not final_display_list:
        li = xbmcgui.ListItem(label="No live matches right now")
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url="", listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return
    
    for match in final_display_list:
        title = match.get('title', 'Unknown Match')
        sport_name = match.get('_sport_name')
        match_id = match.get('id')
        poster = match.get('poster')
        start_time = match.get('start_time')
        
        if start_time == 0:
            time_str = "[COLOR red]LIVE 24/7[/COLOR] "
        else:
            time_str = format_match_time(start_time, sport_name)
        
        display_title = f"{time_str}[{sport_name}] {title}"
        
        raw_streams = match.get('streams', [])
        playable_streams = [s for s in raw_streams if s.get('media_url') or s.get('direct_url')]
        
        if not playable_streams:
            display_title = f"[COLOR gray]{display_title}[/COLOR]"
        
        url_params = {
            'match_id': match_id,
            'sport_name': sport_name 
        }

        is_folder = True
        is_playable = 'false'
        
        if playable_streams:
            stream = playable_streams[0]
            media_url = stream.get('media_url') or stream.get('direct_url')
            embed_url = stream.get('url')
            
            url_params['mode'] = 'play'
            url_params['url'] = media_url
            url_params['playable'] = 'true'
            url_params['referer'] = embed_url
            
            is_folder = False
            is_playable = 'true'
        else:
            url_params['mode'] = 'streams'
        
        url = build_url(url_params)
        
        li = xbmcgui.ListItem(label=display_title)
        if poster and poster.startswith('http'):
            li.setArt({'thumb': poster, 'icon': poster, 'fanart': poster})
        
        li.setInfo('video', {'title': title, 'plot': title})
        if is_playable == 'true':
            li.setProperty('IsPlayable', 'true')
            
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=is_folder)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def menu_matches(sport_id, sport_name):
    data = get_kodi_data()
    
    if not data or 'sports' not in data:
        if data is None: 
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return
        xbmcgui.Dialog().notification(ADDON_NAME, 'No match data available', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    is_other_category = False
    if sport_id and str(sport_id).lower() == 'other':
        is_other_category = True
    elif sport_name and sport_name.lower() == 'other':
        is_other_category = True

    target_matches = []
    
    if is_other_category:
        for s in data['sports']:
            raw_val = s.get('group_to_other', False)
            should_group = False
            if isinstance(raw_val, bool): should_group = raw_val
            elif isinstance(raw_val, str): should_group = raw_val.lower() == 'true'
            elif isinstance(raw_val, int): should_group = raw_val == 1
            
            is_literal_other = (str(s.get('id', '')).lower() == 'other' or s.get('name', '').lower() == 'other')
            
            if should_group or is_literal_other:
                for m in s.get('matches', []):
                    m_copy = m.copy()
                    if should_group and not is_literal_other:
                        real_sport_name = s.get('name', 'Unknown')
                        original_title = m_copy.get('title', 'Unknown')
                        if not original_title.startswith(f"[{real_sport_name}]"):
                            m_copy['title'] = f"[{real_sport_name}] {original_title}"
                            
                    m_copy['_real_sport_name'] = s.get('name')
                    target_matches.append(m_copy)
    else:
        target_sport = None
        clean_sport_id = str(sport_id) if sport_id and str(sport_id).lower() != 'none' else None
        
        if clean_sport_id:
            for s in data['sports']:
                if str(s.get('id')) == clean_sport_id:
                    target_sport = s; break

        if not target_sport:
            target_name_norm = normalize_name(sport_name)
            for s in data['sports']:
                s_name_norm = normalize_name(s['name'])
                if s['name'].lower() == sport_name.lower(): 
                    target_sport = s; break
                if s_name_norm == target_name_norm: 
                    target_sport = s; break
                if s.get('id') == 'fight' and 'boxing mma' in target_name_norm: 
                    target_sport = s; break
        
        if target_sport:
            target_matches = target_sport.get('matches', [])

    if not target_matches:
        li = xbmcgui.ListItem(label="No matches found")
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url="", listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    show_all = ADDON.getSetting('show_all_matches') == 'true'
    
    now_ts = datetime.now().timestamp()
    
    matches_to_sort = []
    
    for match in target_matches:
        current_match_sport = match.get('_real_sport_name') or sport_name
        
        duration_hours = get_duration_hours(current_match_sport)
        cutoff_ts = now_ts - (duration_hours * 3600)

        start = match.get('start_time', 0)
        
        if start != 0:
            try:
                ts_val = get_clean_timestamp(match)
                if ts_val < cutoff_ts:
                    continue 
            except: pass

        has_playable = match.get('has_playable_source', False)
        in_grace_period = is_future_or_grace_period(start, grace_minutes=5)
        
        if not show_all and not has_playable and not in_grace_period:
            continue

        matches_to_sort.append(match)

    started_matches = []
    upcoming_matches = []
    
    for m in matches_to_sort:
        ts = get_clean_timestamp(m)
        if ts <= now_ts:
            started_matches.append(m)
        else:
            upcoming_matches.append(m)
            
    started_matches.sort(key=lambda x: get_clean_timestamp(x), reverse=True)
    
    upcoming_matches.sort(key=lambda x: get_clean_timestamp(x))
    
    all_display_matches = started_matches + upcoming_matches

    if not all_display_matches:
        li = xbmcgui.ListItem(label="No upcoming matches")
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url="", listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    for match in all_display_matches:
        title = match.get('title', 'Unknown Match')
        match_id = match.get('id')
        poster = match.get('poster')
        start_time = match.get('start_time')
        current_sport_name = match.get('_real_sport_name', sport_name)

        if start_time == 0:
            time_str = "[COLOR red]LIVE 24/7[/COLOR] "
        else:
            time_str = format_match_time(start_time, current_sport_name)
        
        display_title = f"{time_str}{title}"
        
        raw_streams = match.get('streams', [])
        playable_streams = [s for s in raw_streams if s.get('media_url') or s.get('direct_url')]
        
        if not playable_streams:
            display_title = f"[COLOR gray]{display_title}[/COLOR]"
        
        url_params = {
            'match_id': match_id,
            'sport_name': current_sport_name
        }

        is_folder = True
        is_playable = 'false'
        
        if playable_streams:
            stream = playable_streams[0]
            media_url = stream.get('media_url') or stream.get('direct_url')
            embed_url = stream.get('url')
            
            url_params['mode'] = 'play'
            url_params['url'] = media_url
            url_params['playable'] = 'true'
            url_params['referer'] = embed_url
            
            is_folder = False
            is_playable = 'true'
        else:
            url_params['mode'] = 'streams'
            
        url = build_url(url_params)
        
        li = xbmcgui.ListItem(label=display_title)
        if poster and poster.startswith('http'):
            li.setArt({'thumb': poster, 'icon': poster, 'fanart': poster})
        
        li.setInfo('video', {'title': title, 'plot': title})
        if is_playable == 'true':
            li.setProperty('IsPlayable', 'true')
        
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=is_folder)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def auto_play(match_id, sport_name):
    data = get_kodi_data()
    match = find_match_in_data(data, match_id, sport_name)
    
    if not match:
        xbmcgui.Dialog().notification(ADDON_NAME, 'Match not found', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
        return

    streams = match.get('streams', [])
    
    if streams:
        first_stream = streams[0]
        media_url = first_stream.get('media_url') or first_stream.get('direct_url')
        embed_url = first_stream.get('url')
        
        if media_url:
            try:
                log(f"AutoPlay: Testing 1st stream {media_url}")
                li = verify_stream(media_url, embed_url)
                log("AutoPlay: Stream 1 is valid. Playing.")
                xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, li)
                return
            except Exception as e:
                log(f"AutoPlay: Stream 1 failed ({str(e)}). Falling back to list.", xbmc.LOGWARNING)
        else:
            log("AutoPlay: Stream 1 is Web Only. Falling back to list.", xbmc.LOGINFO)
    
    list_url = build_url({
        'mode': 'streams',
        'match_id': match_id,
        'sport_name': sport_name
    })
    xbmc.executebuiltin(f"Container.Update({list_url})")

def menu_streams(match_id, sport_name):
    data = get_kodi_data()
    if not data or 'sports' not in data:
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    target_match = find_match_in_data(data, match_id, sport_name)
    
    if not target_match:
        xbmcgui.Dialog().notification(ADDON_NAME, 'Match data not found', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    poster = target_match.get('poster')
    raw_streams = target_match.get('streams', [])
    
    playable_streams = [s for s in raw_streams if s.get('media_url') or s.get('direct_url')]

    if not playable_streams:
        li = xbmcgui.ListItem(label="No streams available, check back at game time or refresh data")
        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url="", listitem=li, isFolder=False)
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    for i, stream in enumerate(playable_streams, 1):
        quality = stream.get('quality', 'SD')
        language = stream.get('language', 'En')
        viewers = stream.get('viewers', 0)
        
        media_url = stream.get('media_url') or stream.get('direct_url')
        embed_url = stream.get('url')
        
        label = f"[{quality}] Stream {i} ({language}) - {viewers} Viewers"
        is_playable = 'true'
        play_url = media_url

        url_params = {
            'mode': 'play',
            'url': play_url,
            'playable': is_playable,
            'referer': embed_url
        }
        url = build_url(url_params)
        
        li = xbmcgui.ListItem(label=label)
        li.setInfo('video', {'title': label})
        li.setProperty('IsPlayable', 'true')
        
        if poster and poster.startswith('http'):
            li.setArt({'thumb': poster, 'icon': poster, 'fanart': poster})

        add_refresh_context_menu(li)
        xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(ADDON_HANDLE)

def play_video(url, playable, referer):
    if playable == 'true':
        try:
            log(f"Attempting playback for: {url}")
            li = verify_stream(url, referer)
            xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, li)

        except requests.exceptions.ConnectionError:
            log("Playback Connection Error", xbmc.LOGERROR)
            xbmcgui.Dialog().ok(ADDON_NAME, "Playback Error:\nCould not connect to the stream source.\nThe server might be offline.")
            xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())

        except requests.exceptions.Timeout:
            log("Playback Timeout", xbmc.LOGERROR)
            xbmcgui.Dialog().ok(ADDON_NAME, "Playback Error:\nConnection to stream timed out.\nYour connection or the server is too slow.")
            xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())

        except requests.exceptions.HTTPError as e:
            log(f"Playback HTTP Error: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().ok(ADDON_NAME, f"Playback Error:\nServer returned error code {e.response.status_code}.")
            xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
            
        except Exception as e:
            log(f"Playback failed: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().ok(ADDON_NAME, f"Playback Failed:\n{str(e)}")
            xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
    else:
        log(f"User clicked embed URL: {url}", xbmc.LOGWARNING)
        msg = "No direct stream URL available.\nThis match is only available via embedded web player."
        xbmcgui.Dialog().ok(ADDON_NAME, msg)
        xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())

def router(param_string):
    params = dict(urllib.parse.parse_qsl(param_string))
    mode = params.get('mode')

    if mode is None:
        menu_main()
    elif mode == 'matches':
        menu_matches(params.get('sport_id'), params.get('sport_name'))
    elif mode == 'streams':
        menu_streams(params.get('match_id'), params.get('sport_name'))
    elif mode == 'play':
        play_video(params.get('url'), params.get('playable'), params.get('referer'))
    elif mode == 'live_now':
        menu_live_now()
    elif mode == 'auto_play':
        auto_play(params.get('match_id'), params.get('sport_name'))
    elif mode == 'refresh_cache':
        refresh_cache()
    elif mode == 'clear_full_cache':
        clear_full_cache()

if __name__ == '__main__':
    router(sys.argv[2][1:])