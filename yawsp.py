# -*- coding: utf-8 -*-
# Module: default
# Author: cache-sk
# Created on: 10.5.2020
# License: AGPL v.3 https://www.gnu.org/licenses/agpl-3.0.html

import io
import os
import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
import requests.cookies
from xml.etree import ElementTree as ET
import hashlib
from md5crypt import md5crypt
import traceback
import json
import unidecode
import re
import zipfile
import uuid
import requests
import series_manager
import movie_manager

# Precompiled regex patterns for performance
_DIGITS_ONLY_RE = re.compile(r'[^\d]+')

try:
    from urllib import urlencode
    from urlparse import parse_qsl, urlparse
except ImportError:
    from urllib.parse import urlencode
    from urllib.parse import parse_qsl, urlparse

try:
    from xbmc import translatePath
except ImportError:
    from xbmcvfs import translatePath

BASE = 'https://webshare.cz'
API = BASE + '/api/'
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"
HEADERS = {'User-Agent': UA, 'Referer': BASE}
REALM = ':Webshare:'
CATEGORIES = ['', 'video', 'images', 'audio', 'archives', 'docs', 'adult']
SORTS = ['', 'recent', 'rating', 'largest', 'smallest']
SEARCH_HISTORY = 'search_history'
NONE_WHAT = '%#NONE#%'
BACKUP_DB = 'D1iIcURxlR'

_url = sys.argv[0]
_handle = int(sys.argv[1])
_addon = xbmcaddon.Addon()
_session = requests.Session()
_session.headers.update(HEADERS)
_profile = translatePath(_addon.getAddonInfo('profile'))
try:
    _profile = _profile.decode("utf-8")
except:
    pass


def get_url(**kwargs):
    return '{0}?{1}'.format(_url, urlencode(kwargs, 'utf-8'))


def api(fnct, data):
    response = _session.post(API + fnct + "/", data=data)
    return response


def is_ok(xml):
    status = xml.find('status').text
    return status == 'OK'


def popinfo(message, heading=_addon.getAddonInfo('name'), icon=xbmcgui.NOTIFICATION_INFO, time=3000, sound=False):  # NOTIFICATION_WARNING NOTIFICATION_ERROR
    xbmcgui.Dialog().notification(heading, message, icon, time, sound=sound)


def login():
    username = _addon.getSetting('wsuser')
    password = _addon.getSetting('wspass')
    if username == '' or password == '':
        popinfo(_addon.getLocalizedString(30101), sound=True)
        _addon.openSettings()
        return
    response = api('salt', {'username_or_email': username})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        salt = xml.find('salt').text
        try:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM + encrypted_pass.encode('utf-8')).hexdigest()
        except TypeError:
            encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8')).encode('utf-8')).hexdigest()
            pass_digest = hashlib.md5(username.encode('utf-8') + REALM.encode('utf-8') + encrypted_pass.encode('utf-8')).hexdigest()
        response = api('login', {'username_or_email': username, 'password': encrypted_pass, 'digest': pass_digest, 'keep_logged_in': 1})
        xml = ET.fromstring(response.content)
        if is_ok(xml):
            token = xml.find('token').text
            _addon.setSetting('token', token)
            return token
        else:
            popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
            _addon.openSettings()
    else:
        popinfo(_addon.getLocalizedString(30102), icon=xbmcgui.NOTIFICATION_ERROR, sound=True)
        _addon.openSettings()


def revalidate():
    token = _addon.getSetting('token')
    if len(token) == 0:
        if login():
            return revalidate()
    else:
        response = api('user_data', {'wst': token})
        xml = ET.fromstring(response.content)
        status = xml.find('status').text
        if is_ok(xml):
            vip = xml.find('vip').text
            if vip != '1':
                popinfo(_addon.getLocalizedString(30103), icon=xbmcgui.NOTIFICATION_WARNING)
            return token
        else:
            if login():
                return revalidate()


def todict(xml, skip=[]):
    result = {}
    for e in xml:
        if e.tag not in skip:
            value = e.text if len(list(e)) == 0 else todict(e, skip)
            if e.tag in result:
                if isinstance(result[e.tag], list):
                    result[e.tag].append(value)
                else:
                    result[e.tag] = [result[e.tag], value]
            else:
                result[e.tag] = value
    # result = {e.tag:(e.text if len(list(e)) == 0 else todict(e,skip)) for e in xml if e.tag not in skip}
    return result


def sizelize(txtsize, units=['B', 'KB', 'MB', 'GB']):
    if txtsize:
        size = float(txtsize)
        if size < 1024:
            size = str(size) + units[0]
        else:
            size = size / 1024
            if size < 1024:
                size = str(int(round(size))) + units[1]
            else:
                size = size / 1024
                if size < 1024:
                    size = str(round(size, 2)) + units[2]
                else:
                    size = size / 1024
                    size = str(round(size, 2)) + units[3]
        return size
    return str(txtsize)


def labelize(file):
    if 'size' in file:
        size = sizelize(file['size'])
    elif 'sizelized' in file:
        size = file['sizelized']
    else:
        size = '?'
    label = file['name'] + ' (' + size + ')'
    return label


def tolistitem(file, addcommands=[]):
    label = labelize(file)
    listitem = xbmcgui.ListItem(label=label)
    if 'img' in file:
        listitem.setArt({'thumb': file['img']})
    listitem.setInfo('video', {'title': label})
    listitem.setProperty('IsPlayable', 'true')
    commands = []
    commands.append((_addon.getLocalizedString(30211), 'RunPlugin(' + get_url(action='info', ident=file['ident']) + ')'))
    commands.append((_addon.getLocalizedString(30212), 'RunPlugin(' + get_url(action='download', ident=file['ident']) + ')'))
    if addcommands:
        commands = commands + addcommands
    listitem.addContextMenuItems(commands)
    return listitem


def ask(what):
    if what is None:
        what = ''
    kb = xbmc.Keyboard(what, _addon.getLocalizedString(30007))
    kb.doModal()  # Onscreen keyboard appears
    if kb.isConfirmed():
        return kb.getText()  # User input
    return None


def loadsearch():
    history = []
    try:
        if not os.path.exists(_profile):
            os.makedirs(_profile)
    except Exception as e:
        traceback.print_exc()

    try:
        with io.open(os.path.join(_profile, SEARCH_HISTORY), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            try:
                history = json.loads(fdata, "utf-8")
            except TypeError:
                history = json.loads(fdata)
    except Exception as e:
        traceback.print_exc()

    return history


def storesearch(what):
    if what:
        size = int(_addon.getSetting('shistory'))

        history = loadsearch()

        if what in history:
            history.remove(what)

        history = [what] + history

        if len(history) > size:
            history = history[:size]

        try:
            with io.open(os.path.join(_profile, SEARCH_HISTORY), 'w', encoding='utf8') as file:
                try:
                    data = json.dumps(history).decode('utf8')
                except AttributeError:
                    data = json.dumps(history)
                file.write(data)
                file.close()
        except Exception as e:
            traceback.print_exc()


def removesearch(what):
    if what:
        history = loadsearch()
        if what in history:
            history.remove(what)
            try:
                with io.open(os.path.join(_profile, SEARCH_HISTORY), 'w', encoding='utf8') as file:
                    try:
                        data = json.dumps(history).decode('utf8')
                    except AttributeError:
                        data = json.dumps(history)
                    file.write(data)
                    file.close()
            except Exception as e:
                traceback.print_exc()


def dosearch(token, what, category, sort, limit, offset, action):
    response = api('search',
                   {'what': '' if what == NONE_WHAT else what, 'category': category, 'sort': sort, 'limit': limit, 'offset': offset, 'wst': token, 'maybe_removed': 'true'})
    xml = ET.fromstring(response.content)
    if is_ok(xml):

        if offset > 0:  # prev page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset - limit if offset > limit else 0),
                                        listitem, True)

        for file in xml.iter('file'):
            item = todict(file)
            commands = []
            commands.append((_addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='search', toqueue=item['ident'], what=what, offset=offset) + ')'))
            listitem = tolistitem(item, commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=item['ident'], name=item['name']), listitem, False)

        try:
            total = int(xml.find('total').text)
        except:
            total = 0

        if offset + limit < total:  # next page
            listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            xbmcplugin.addDirectoryItem(_handle, get_url(action=action, what=what, category=category, sort=sort, limit=limit, offset=offset + limit), listitem, True)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)


def search(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30201))
    token = revalidate()

    updateListing = False

    if 'remove' in params:
        removesearch(params['remove'])
        updateListing = True

    if 'toqueue' in params:
        toqueue(params['toqueue'], token)
        updateListing = True

    what = None

    if 'what' in params:
        what = params['what']

    if 'ask' in params:
        slast = _addon.getSetting('slast')
        if slast != what:
            what = ask(what)
            if what is not None:
                storesearch(what)
                # Ensure the container refreshes with the new search results
                updateListing = True
            else:
                updateListing = True

    if what is not None:
        if 'offset' not in params:
            _addon.setSetting('slast', what)
        else:
            _addon.setSetting('slast', NONE_WHAT)
            updateListing = True

        category = params['category'] if 'category' in params else CATEGORIES[int(_addon.getSetting('scategory'))]
        sort = params['sort'] if 'sort' in params else SORTS[int(_addon.getSetting('ssort'))]
        limit = int(params['limit']) if 'limit' in params else int(_addon.getSetting('slimit'))
        offset = int(params['offset']) if 'offset' in params else 0
        dosearch(token, what, category, sort, limit, offset, 'search')
    else:
        _addon.setSetting('slast', NONE_WHAT)
        history = loadsearch()
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30205))
        listitem.setArt({'icon': 'DefaultAddSource.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search', ask=1), listitem, True)

        # newest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30208))
        listitem.setArt({'icon': 'DefaultAddonsRecentlyUpdated.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search', what=NONE_WHAT, sort=SORTS[1]), listitem, True)

        # biggest
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30209))
        listitem.setArt({'icon': 'DefaultHardDisk.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='search', what=NONE_WHAT, sort=SORTS[3]), listitem, True)

        for search in history:
            listitem = xbmcgui.ListItem(label=search)
            listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
            commands = []
            commands.append((_addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='search', remove=search) + ')'))
            listitem.addContextMenuItems(commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='search', what=search, ask=1), listitem, True)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def queue(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30202))
    token = revalidate()
    updateListing = False

    if 'dequeue' in params:
        response = api('dequeue_file', {'ident': params['dequeue'], 'wst': token})
        xml = ET.fromstring(response.content)
        if is_ok(xml):
            popinfo(_addon.getLocalizedString(30106))
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        updateListing = True

    response = api('queue', {'wst': token})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        for file in xml.iter('file'):
            item = todict(file)
            commands = []
            commands.append((_addon.getLocalizedString(30215), 'Container.Update(' + get_url(action='queue', dequeue=item['ident']) + ')'))
            listitem = tolistitem(item, commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=item['ident'], name=item['name']), listitem, False)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def toqueue(ident, token):
    response = api('queue_file', {'ident': ident, 'wst': token})
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        popinfo(_addon.getLocalizedString(30105))
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)


def history(params):
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + _addon.getLocalizedString(30203))
    token = revalidate()
    updateListing = False

    if 'remove' in params:
        remove = params['remove']
        updateListing = True
        response = api('history', {'wst': token})
        xml = ET.fromstring(response.content)
        ids = []
        if is_ok(xml):
            for file in xml.iter('file'):
                if remove == file.find('ident').text:
                    ids.append(file.find('download_id').text)
        else:
            popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        if ids:
            rr = api('clear_history', {'ids[]': ids, 'wst': token})
            xml = ET.fromstring(rr.content)
            if is_ok(xml):
                popinfo(_addon.getLocalizedString(30104))
            else:
                popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)

    if 'toqueue' in params:
        toqueue(params['toqueue'], token)
        updateListing = True

    response = api('history', {'wst': token})
    xml = ET.fromstring(response.content)
    files = []
    if is_ok(xml):
        for file in xml.iter('file'):
            item = todict(file, ['ended_at', 'download_id', 'started_at'])
            if item not in files:
                files.append(item)
        for file in files:
            commands = []
            commands.append((_addon.getLocalizedString(30213), 'Container.Update(' + get_url(action='history', remove=file['ident']) + ')'))
            commands.append((_addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='history', toqueue=file['ident']) + ')'))
            listitem = tolistitem(file, commands)
            xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=file['ident'], name=file['name']), listitem, False)
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def settings(params):
    _addon.openSettings()
    xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def infonize(data, key, process=str, showkey=True, prefix='', suffix='\n'):
    if key in data:
        return prefix + (key.capitalize() + ': ' if showkey else '') + process(data[key]) + suffix
    return ''


def fpsize(fps):
    x = round(float(fps), 3)
    if int(x) == x:
        return str(int(x))
    return str(x)


def getinfo(ident, wst):
    response = api('file_info', {'ident': ident, 'wst': wst})
    xml = ET.fromstring(response.content)
    ok = is_ok(xml)
    if not ok:
        response = api('file_info', {'ident': ident, 'wst': wst, 'maybe_removed': 'true'})
        xml = ET.fromstring(response.content)
        ok = is_ok(xml)
    if ok:
        return xml
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None


def info(params):
    token = revalidate()
    xml = getinfo(params['ident'], token)

    if xml is not None:
        info = todict(xml)
        text = ''
        text += infonize(info, 'name')
        text += infonize(info, 'size', sizelize)
        text += infonize(info, 'type')
        text += infonize(info, 'width')
        text += infonize(info, 'height')
        text += infonize(info, 'format')
        text += infonize(info, 'fps', fpsize)
        text += infonize(info, 'bitrate', lambda x: sizelize(x, ['bps', 'Kbps', 'Mbps', 'Gbps']))
        if 'video' in info and 'stream' in info['video']:
            streams = info['video']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Video stream: '
                text += infonize(stream, 'width', showkey=False, suffix='')
                text += infonize(stream, 'height', showkey=False, prefix='x', suffix='')
                text += infonize(stream, 'format', showkey=False, prefix=', ', suffix='')
                text += infonize(stream, 'fps', fpsize, showkey=False, prefix=', ', suffix='')
                text += '\n'
        if 'audio' in info and 'stream' in info['audio']:
            streams = info['audio']['stream']
            if isinstance(streams, dict):
                streams = [streams]
            for stream in streams:
                text += 'Audio stream: '
                text += infonize(stream, 'format', showkey=False, suffix='')
                text += infonize(stream, 'channels', prefix=', ', showkey=False, suffix='')
                text += infonize(stream, 'bitrate', lambda x: sizelize(x, ['bps', 'Kbps', 'Mbps', 'Gbps']), prefix=', ', showkey=False, suffix='')
                text += '\n'
        text += infonize(info, 'removed', lambda x: 'Yes' if x == '1' else 'No')
        xbmcgui.Dialog().textviewer(_addon.getAddonInfo('name'), text)


def getlink(ident, wst, dtype='video_stream'):
    # uuid experiment
    duuid = _addon.getSetting('duuid')
    if not duuid:
        duuid = str(uuid.uuid4())
        _addon.setSetting('duuid', duuid)
    data = {'ident': ident, 'wst': wst, 'download_type': dtype, 'device_uuid': duuid}
    # TODO password protect
    # response = api('file_protected',data) #protected
    # xml = ET.fromstring(response.content)
    # if is_ok(xml) and xml.find('protected').text != 0:
    #    pass #ask for password
    response = api('file_link', data)
    xml = ET.fromstring(response.content)
    if is_ok(xml):
        return xml.find('link').text
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        return None


def play(params):
    token = revalidate()
    link = getlink(params['ident'], token)
    if link is not None:
        headers = _session.headers
        if headers:
            headers.update({'Cookie': 'wst=' + token})
            link = link + '|' + urlencode(headers)
        listitem = xbmcgui.ListItem(label=params['name'], path=link)
        listitem.setProperty('mimetype', 'application/octet-stream')

        xbmcplugin.setResolvedUrl(_handle, True, listitem)

        if 'series' in params and 'season' in params and 'episode' in params:
            try:
                playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
                start = int(params['episode'])
                sm = series_manager.SeriesManager(_addon, _profile)
                data = sm.load_series_data(params['series']) or {}
                season_data = data.get('seasons', {}).get(str(params['season']), {})
                for ep_num in sorted(season_data.keys(), key=int):
                    if int(ep_num) <= start:
                        continue
                    ep = season_data[ep_num]
                    ep_link = getlink(ep['ident'], token)
                    if headers:
                        ep_link = ep_link + '|' + urlencode(headers)
                    li = xbmcgui.ListItem(label=f"Epizoda {ep_num} - {ep['name']}", path=ep_link)
                    li.setProperty('mimetype', 'application/octet-stream')
                    playlist.add(url=ep_link, listitem=li)
            except Exception:
                traceback.print_exc()
    else:
        popinfo(_addon.getLocalizedString(30107), icon=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())


def join(path, file):
    if path.endswith('/') or path.endswith('\\'):
        return path + file
    else:
        return path + '/' + file


def download(params):
    token = revalidate()
    where = _addon.getSetting('dfolder')
    if not where or not xbmcvfs.exists(where):
        popinfo('set folder!', sound=True)  # _addon.getLocalizedString(30101)
        _addon.openSettings()
        return

    local = os.path.exists(where)

    normalize = 'true' == _addon.getSetting('dnormalize')
    notify = 'true' == _addon.getSetting('dnotify')
    every = _addon.getSetting('dnevery')
    try:
        every = int(_DIGITS_ONLY_RE.sub('', every))
    except:
        every = 10

    try:
        link = getlink(params['ident'], token, 'file_download')
        info = getinfo(params['ident'], token)
        name = info.find('name').text
        if normalize:
            name = unidecode.unidecode(name)
        bf = io.open(os.path.join(where, name), 'wb') if local else xbmcvfs.File(join(where, name), 'w')
        response = _session.get(link, stream=True)
        total = response.headers.get('content-length')
        if total is None:
            popinfo(_addon.getLocalizedString(30301) + name, icon=xbmcgui.NOTIFICATION_WARNING, sound=True)
            bf.write(response.content)
        elif not notify:
            popinfo(_addon.getLocalizedString(30302) + name)
            bf.write(response.content)
        else:
            popinfo(_addon.getLocalizedString(30302) + name)
            dl = 0
            total = int(total)
            pct = total / 100
            lastpop = 0
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                bf.write(data)
                done = int(dl / pct)
                if done % every == 0 and lastpop != done:
                    popinfo(str(done) + '% - ' + name)
                    lastpop = done
        bf.close()
        popinfo(_addon.getLocalizedString(30303) + name, sound=True)
    except Exception as e:
        # TODO - remove unfinished file?
        traceback.print_exc()
        popinfo(_addon.getLocalizedString(30304) + name, icon=xbmcgui.NOTIFICATION_ERROR, sound=True)


def loaddb(dbdir, file):
    try:
        data = {}
        with io.open(os.path.join(dbdir, file), 'r', encoding='utf8') as file:
            fdata = file.read()
            file.close()
            try:
                data = json.loads(fdata, "utf-8")['data']
            except TypeError:
                data = json.loads(fdata)['data']
        return data
    except Exception as e:
        traceback.print_exc()
        return {}


def db(params):
    token = revalidate()
    updateListing = False

    dbdir = os.path.join(_profile, 'db')
    if not os.path.exists(dbdir):
        link = getlink(BACKUP_DB, token)
        dbfile = os.path.join(_profile, 'db.zip')
        with io.open(dbfile, 'wb') as bf:
            response = _session.get(link, stream=True)
            bf.write(response.content)
            bf.flush()
            bf.close()
        with zipfile.ZipFile(dbfile, 'r') as zf:
            zf.extractall(_profile)
        os.unlink(dbfile)

    if 'toqueue' in params:
        toqueue(params['toqueue'], token)
        updateListing = True

    if 'file' in params and 'key' in params:
        data = loaddb(dbdir, params['file'])
        item = next((x for x in data if x['id'] == params['key']), None)
        if item is not None:
            for stream in item['streams']:
                commands = []
                commands.append(
                    (_addon.getLocalizedString(30214), 'Container.Update(' + get_url(action='db', file=params['file'], key=params['key'], toqueue=stream['ident']) + ')'))
                listitem = tolistitem({'ident': stream['ident'], 'name': stream['quality'] + ' - ' + stream['lang'] + stream['ainfo'], 'sizelized': stream['size']}, commands)
                xbmcplugin.addDirectoryItem(_handle, get_url(action='play', ident=stream['ident'], name=item['title']), listitem, False)
    elif 'file' in params:
        data = loaddb(dbdir, params['file'])
        for item in data:
            listitem = xbmcgui.ListItem(label=item['title'])
            if 'plot' in item:
                listitem.setInfo('video', {'title': item['title'], 'plot': item['plot']})
            xbmcplugin.addDirectoryItem(_handle, get_url(action='db', file=params['file'], key=item['id']), listitem, True)
    else:
        if os.path.exists(dbdir):
            dbfiles = [f for f in os.listdir(dbdir) if os.path.isfile(os.path.join(dbdir, f))]
            for dbfile in dbfiles:
                listitem = xbmcgui.ListItem(label=os.path.splitext(dbfile)[0])
                xbmcplugin.addDirectoryItem(_handle, get_url(action='db', file=dbfile), listitem, True)
    xbmcplugin.addSortMethod(_handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def menu():
    revalidate()
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name'))

    # Add Movies Manager menu item
    listitem = xbmcgui.ListItem(label='Filmy')
    listitem.setArt({'icon': 'DefaultMovies.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movie'), listitem, True)

    # Add Series Manager menu item
    listitem = xbmcgui.ListItem(label='Serialy')
    listitem.setArt({'icon': 'DefaultTVShows.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='series'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30201))
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='search'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30202))
    listitem.setArt({'icon': 'DefaultPlaylist.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='queue'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30203))
    listitem.setArt({'icon': 'DefaultAddonsUpdates.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='history'), listitem, True)

    if 'true' == _addon.getSetting('experimental'):
        listitem = xbmcgui.ListItem(label='Backup DB')
        listitem.setArt({'icon': 'DefaultAddonsZip.png'})
        xbmcplugin.addDirectoryItem(_handle, get_url(action='db'), listitem, True)

    listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30204))
    listitem.setArt({'icon': 'DefaultAddonService.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='settings'), listitem, False)

    xbmcplugin.endOfDirectory(_handle)


def series_menu(params):
    """Handle Series functionality"""
    updateListing = False
    # Initialize SeriesManager
    sm = series_manager.SeriesManager(_addon, _profile)

    if 'remove' in params:
        sm.remove_series(params['remove'])
        updateListing = True

    series_manager.create_series_menu(sm, _handle, end=False)
    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def series_search(params):
    """Search for a TV series and organize it into seasons and episodes"""
    token = revalidate()

    # Determine series name
    series_name = params.get('series_name')
    if not series_name:
        series_name = ask(None)
    if not series_name:
        xbmcplugin.endOfDirectory(_handle, succeeded=False)
        return

    # Initialize SeriesManager
    sm = series_manager.SeriesManager(_addon, _profile)

    # If series already exists locally, open it without refreshing
    if sm.load_series_data(series_name):
        xbmc.executebuiltin(f'Container.Update({get_url(action="series_detail", series_name=series_name)})')
        return

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('YaWSP', f'Vyhledavam serial {series_name}...')

    try:
        # Search for the series
        series_data = sm.search_series(series_name, api, token)

        if not series_data or not series_data['seasons']:
            progress.close()
            popinfo('Nenalezeny zadne epizody tohoto serialu', icon=xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return

        # Success
        progress.close()
        popinfo(f'Nalezeno {sum(len(season) for season in series_data["seasons"].values())} epizod v {len(series_data["seasons"])} sezonach')

        # Redirect to series detail
        xbmc.executebuiltin(f'Container.Update({get_url(action="series_detail", series_name=series_name)})')

    except Exception as e:
        progress.close()
        traceback.print_exc()
        popinfo(f'Chyba: {str(e)}', icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)


def series_detail(params):
    """Show seasons for a series"""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + params['series_name'])

    series_name = params['series_name']
    sm = series_manager.SeriesManager(_addon, _profile)
    series_data = sm.load_series_data(series_name)
    if not series_data:
        xbmcgui.Dialog().notification('YaWSP', 'Data serialu nenalezena', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)
        return

    # Add refresh option
    listitem = xbmcgui.ListItem(label='Aktualizovat serial')
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='series_refresh', series_name=series_name), listitem, True)

    show_info = _trakt_show_info(series_name)
    poster = None
    plot = ''
    rating = None
    if show_info:
        img = show_info.get('images', {}).get('poster')
        poster = img[0] if isinstance(img, list) and img else None
        if poster and not poster.startswith('http'):
            poster = 'https://' + poster
        plot = show_info.get('overview') or ''
        rating = show_info.get('rating')

    for season_num in sorted(series_data['seasons'].keys(), key=int):
        season_name = f'Rada {season_num}'
        listitem = xbmcgui.ListItem(label=season_name)
        art = {'icon': 'DefaultFolder.png'}
        if poster:
            art['thumb'] = poster
        listitem.setArt(art)
        info = {'title': f'{series_name} - {season_name}'}
        if plot:
            info['plot'] = plot
        if rating is not None:
            info['rating'] = rating
        listitem.setInfo('video', info)
        xbmcplugin.addDirectoryItem(_handle, get_url(action='series_season', series_name=series_name, season=season_num), listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def series_season(params):
    """Show episodes for a season"""
    series_name = params['series_name']
    season = params['season']

    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + series_name + " \\ " + f"Rada {season}")

    sm = series_manager.SeriesManager(_addon, _profile)
    season_str = str(season)
    series_data = sm.load_series_data(series_name)
    if not series_data or season_str not in series_data['seasons']:
        xbmcgui.Dialog().notification('YaWSP', 'Data sezony nenalezena', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)
        return

    show_slug = _trakt_search('show', series_name)
    episode_details = {}
    if show_slug:
        eps, _ = _trakt_request(f'shows/{show_slug}/seasons/{season_str}',
                                {'extended': 'episodes,full,images'})
        if isinstance(eps, list):
            for ep in eps:
                episode_details[str(ep.get('number'))] = ep

    season_data = series_data['seasons'][season_str]
    for episode_num in sorted(season_data.keys(), key=int):
        episode = season_data[episode_num]
        info_data = episode_details.get(str(episode_num), {})
        label = f"Epizoda {episode_num} - {episode['name']}"

        listitem = xbmcgui.ListItem(label=label)
        art = {'icon': 'DefaultVideo.png'}
        shot = info_data.get('images', {}).get('screenshot')
        thumb = shot[0] if isinstance(shot, list) and shot else None
        if thumb and not thumb.startswith('http'):
            thumb = 'https://' + thumb
        if thumb:
            art['thumb'] = thumb
        listitem.setArt(art)
        listitem.setProperty('IsPlayable', 'true')

        meta = {'title': label}
        overview = info_data.get('overview')
        if overview:
            meta['plot'] = overview
        rating = info_data.get('rating')
        if rating is not None:
            meta['rating'] = rating
        listitem.setInfo('video', meta)

        url = get_url(
            action='play',
            ident=episode['ident'],
            name=episode['name'],
            series=series_name,
            season=season,
            episode=episode_num
        )
        xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    xbmcplugin.endOfDirectory(_handle)


def series_refresh(params):
    """Refresh series data"""
    token = revalidate()
    series_name = params['series_name']

    # Initialize SeriesManager and perform search
    sm = series_manager.SeriesManager(_addon, _profile)

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('YaWSP', f'Aktualizuji data pro serial {series_name}...')

    try:
        # Search for the series
        series_data = sm.search_series(series_name, api, token)

        if not series_data or not series_data['seasons']:
            progress.close()
            popinfo('Nenalezeny zadne epizody tohoto serialu', icon=xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return

        # Success
        progress.close()
        popinfo(f'Aktualizovano: {sum(len(season) for season in series_data["seasons"].values())} epizod v {len(series_data["seasons"])} sezonach')

        # Redirect to series detail to refresh the view
        xbmc.executebuiltin(f'Container.Update({get_url(action="series_detail", series_name=series_name)})')

    except Exception as e:
        progress.close()
        traceback.print_exc()
        popinfo(f'Chyba: {str(e)}', icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)


def _trakt_request(endpoint, params=None):
    """Helper to call Trakt API. Returns JSON data and response headers."""
    client_id = _addon.getSetting('trakt_client_id')
    if not client_id:
        popinfo('Missing Trakt client id', icon=xbmcgui.NOTIFICATION_WARNING)
        return [], {}

    headers = {
        'Content-Type': 'application/json',
        'trakt-api-version': '2',
        'trakt-api-key': client_id,
    }

    try:
        response = _session.get('https://api.trakt.tv/' + endpoint,
                                headers=headers,
                                params=params or {}, timeout=10)
        if response.status_code == 200:
            return response.json(), response.headers
        else:
            popinfo('Trakt API error', icon=xbmcgui.NOTIFICATION_WARNING)
    except Exception:
        traceback.print_exc()
        popinfo('Trakt API request failed', icon=xbmcgui.NOTIFICATION_WARNING)
    return [], {}


def _trakt_search(media_type, query):
    """Search Trakt for a show or movie and return its slug."""
    data, _ = _trakt_request(f'search/{media_type}', {'query': query, 'limit': 1})
    if data:
        item = data[0].get(media_type) or data[0].get('show') or data[0].get('movie')
        if isinstance(item, dict):
            ids = item.get('ids', {})
            return ids.get('slug') or ids.get('trakt')
    return None


def _trakt_show_info(name_or_slug):
    """Return detailed show info including images."""
    slug = name_or_slug
    if not slug or ' ' in slug:
        slug = _trakt_search('show', name_or_slug)
    if slug:
        info, _ = _trakt_request(f'shows/{slug}', {'extended': 'full,images'})
        if isinstance(info, dict):
            return info
    return {}


def _trakt_movie_info(name_or_slug):
    """Return detailed movie info including images."""
    slug = name_or_slug
    if not slug or ' ' in slug:
        slug = _trakt_search('movie', name_or_slug)
    if slug:
        info, _ = _trakt_request(f'movies/{slug}', {'extended': 'full,images'})
        if isinstance(info, dict):
            return info
    return {}


def _trakt_episode_info(show_slug, season, episode):
    """Return detailed episode info including screenshot."""
    if not show_slug:
        return {}
    data, _ = _trakt_request(f'shows/{show_slug}/seasons/{season}',
                             {'extended': 'episodes,full,images'})
    if isinstance(data, list):
        for ep in data:
            if str(ep.get('number')) == str(episode):
                return ep
    return {}


def series_trending(params):
    """List trending series from Trakt with paging."""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + ' \\ ' +
                                 _addon.getLocalizedString(30401))

    page = int(params.get('page', '1'))
    limit = 20

    data, headers = _trakt_request('shows/trending',
                                   {'limit': limit, 'page': page,
                                    'extended': 'full,images'})

    if page > 1:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_trending', page=page - 1),
                                    listitem, True)

    for item in data:
        show = item.get('show', {})
        title = show.get('title')
        if not title:
            continue
        watchers = item.get('watchers', 0)
        label = f"{title} ({watchers} users)"
        listitem = xbmcgui.ListItem(label=label)
        poster = show.get('images', {}).get('poster')
        thumb = poster[0] if isinstance(poster, list) and poster else None
        if thumb and not thumb.startswith('http'):
            thumb = 'https://' + thumb
        art = {'icon': 'DefaultTVShows.png'}
        if thumb:
            art['thumb'] = thumb
        listitem.setArt(art)
        info = {'title': title}
        overview = show.get('overview')
        if overview:
            info['plot'] = overview
        rating = show.get('rating')
        if rating is not None:
            info['rating'] = rating
        listitem.setInfo('video', info)
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_search', series_name=title),
                                    listitem, True)

    page_count = int(headers.get('X-Pagination-Page-Count', page))
    if page < page_count:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_trending', page=page + 1),
                                    listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def series_popular(params):
    """List popular series from Trakt with paging."""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + ' \\ ' +
                                 _addon.getLocalizedString(30402))

    page = int(params.get('page', '1'))
    limit = 20

    data, headers = _trakt_request('shows/popular',
                                   {'limit': limit, 'page': page,
                                    'extended': 'full,images'})

    if page > 1:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_popular', page=page - 1),
                                    listitem, True)

    for show in data:
        title = show.get('title')
        if not title:
            continue
        watchers = 0
        ids = show.get('ids', {})
        slug = ids.get('slug') or ids.get('trakt')
        if slug:
            stats, _ = _trakt_request(f'shows/{slug}/stats')
            if isinstance(stats, dict):
                watchers = stats.get('watchers', 0)
        label = f"{title} ({watchers} users)"
        listitem = xbmcgui.ListItem(label=label)
        poster = show.get('images', {}).get('poster')
        thumb = poster[0] if isinstance(poster, list) and poster else None
        if thumb and not thumb.startswith('http'):
            thumb = 'https://' + thumb
        art = {'icon': 'DefaultTVShows.png'}
        if thumb:
            art['thumb'] = thumb
        listitem.setArt(art)
        info = {'title': title}
        overview = show.get('overview')
        if overview:
            info['plot'] = overview
        rating = show.get('rating')
        if rating is not None:
            info['rating'] = rating
        listitem.setInfo('video', info)
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_search', series_name=title),
                                    listitem, True)

    page_count = int(headers.get('X-Pagination-Page-Count', page))
    if page < page_count:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
        listitem.setArt({'icon': 'DefaultTVShows.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='series_popular', page=page + 1),
                                    listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def movie_menu(params):
    """Handle Movies functionality"""
    updateListing = False
    # Initialize MovieManager
    mm = movie_manager.MovieManager(_addon, _profile)

    if 'remove' in params:
        mm.remove_item(params['remove'])
        updateListing = True

    # Create movie menu similar to series menu
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ Movies")

    # Add "Search for new movie" option
    listitem = xbmcgui.ListItem(label="Hledat novy film")
    listitem.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movie_search'), listitem, True)

    # Trending from Trakt
    listitem = xbmcgui.ListItem(label="Trending movies")
    listitem.setArt({'icon': 'DefaultRecentlyAddedMovies.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movie_trending'), listitem, True)

    # Popular from Trakt
    listitem = xbmcgui.ListItem(label="Popular movies")
    listitem.setArt({'icon': 'DefaultMovies.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movie_popular'), listitem, True)

    # List existing movies
    try:
        movie_list = []
        for filename in os.listdir(mm.db_path):
            if filename.endswith('.json'):
                movie_name = os.path.splitext(filename)[0]
                proper_name = movie_name.replace('_', ' ')
                file_path = os.path.join(mm.db_path, filename)
                mtime = 0
                try:
                    mtime = os.path.getmtime(file_path)
                except Exception as e:
                    xbmc.log(f'YaWSP Movie: Error accessing {filename}: {str(e)}', level=xbmc.LOGERROR)
                movie_list.append({
                    'name': proper_name,
                    'filename': filename,
                    'safe_name': movie_name,
                    'mtime': mtime
                })

        movie_list.sort(key=lambda m: m.get('mtime', 0), reverse=True)
    except Exception as e:
        xbmc.log(f'YaWSP Movie: Error listing movies: {str(e)}', level=xbmc.LOGERROR)
        movie_list = []

    for movie in movie_list:
        listitem = xbmcgui.ListItem(label=movie['name'])
        listitem.setArt({'icon': 'DefaultVideo.png'})
        commands = []
        commands.append((_addon.getLocalizedString(30213),
                         'Container.Update(' + get_url(action='movie', remove=movie['name']) + ')'))
        listitem.addContextMenuItems(commands)
        xbmcplugin.addDirectoryItem(_handle, get_url(action='movie_detail', movie_name=movie['name']), listitem, True)

    xbmcplugin.endOfDirectory(_handle, updateListing=updateListing)


def movie_search(params):
    """Search for a movie"""
    token = revalidate()

    # Determine movie name
    movie_name = params.get('movie_name')
    if not movie_name:
        movie_name = ask(None)
    if not movie_name:
        xbmcplugin.endOfDirectory(_handle, succeeded=False)
        return

    # Initialize MovieManager
    mm = movie_manager.MovieManager(_addon, _profile)

    # If movie already exists locally, play it without refreshing
    if mm.load_movie_data(movie_name):
        xbmc.executebuiltin(f'Container.Update({get_url(action="movie_detail", movie_name=movie_name)})')
        return

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('YaWSP', f'Vyhledavam film {movie_name}...')

    try:
        # Search for the movie
        movie_data = mm.search_movie(movie_name, api, token)

        if not movie_data or not movie_data['file']:
            progress.close()
            popinfo('Nenalezen zadny film', icon=xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return

        # Success
        progress.close()
        popinfo(f'Nalezen film: {movie_data["file"]["name"]}')

        # Redirect to movie detail
        xbmc.executebuiltin(f'Container.Update({get_url(action="movie_detail", movie_name=movie_name)})')

    except Exception as e:
        progress.close()
        traceback.print_exc()
        popinfo(f'Chyba: {str(e)}', icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)


def movie_detail(params):
    """Show movie detail and play option"""
    movie_name = params['movie_name']
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + " \\ " + movie_name)

    # Initialize MovieManager
    mm = movie_manager.MovieManager(_addon, _profile)

    movie_data = mm.load_movie_data(movie_name)
    if not movie_data:
        xbmcgui.Dialog().notification('YaWSP', 'Data filmu nenalezena', xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)
        return

    # Add "Refresh movie" option
    listitem = xbmcgui.ListItem(label="Aktualizovat film")
    listitem.setArt({'icon': 'DefaultAddonsSearch.png'})
    xbmcplugin.addDirectoryItem(_handle, get_url(action='movie_refresh', movie_name=movie_name), listitem, True)

    # Show movie file if available
    if movie_data['file']:
        movie_file = movie_data['file']
        movie_title = f"{movie_name} - {movie_file['name']}"
        info = _trakt_movie_info(movie_name)
        poster = None
        plot = ''
        rating = None
        if info:
            img = info.get('images', {}).get('poster')
            poster = img[0] if isinstance(img, list) and img else None
            if poster and not poster.startswith('http'):
                poster = 'https://' + poster
            plot = info.get('overview') or ''
            rating = info.get('rating')

        listitem = xbmcgui.ListItem(label=movie_title)
        art = {'icon': 'DefaultVideo.png'}
        if poster:
            art['thumb'] = poster
        listitem.setArt(art)
        listitem.setProperty('IsPlayable', 'true')
        meta = {'title': movie_title}
        if plot:
            meta['plot'] = plot
        if rating is not None:
            meta['rating'] = rating
        listitem.setInfo('video', meta)

        url = get_url(action='play', ident=movie_file['ident'], name=movie_file['name'])
        xbmcplugin.addDirectoryItem(_handle, url, listitem, False)

    xbmcplugin.endOfDirectory(_handle)


def movie_refresh(params):
    """Refresh movie data"""
    token = revalidate()
    movie_name = params['movie_name']

    # Initialize MovieManager and perform search
    mm = movie_manager.MovieManager(_addon, _profile)

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('YaWSP', f'Aktualizuji data pro film {movie_name}...')

    try:
        # Search for the movie
        movie_data = mm.search_movie(movie_name, api, token)

        if not movie_data or not movie_data['file']:
            progress.close()
            popinfo('Nenalezen zadny film', icon=xbmcgui.NOTIFICATION_WARNING)
            xbmcplugin.endOfDirectory(_handle, succeeded=False)
            return

        # Success
        progress.close()
        popinfo(f'Aktualizovano: {movie_data["file"]["name"]}')

        # Redirect to movie detail to refresh the view
        xbmc.executebuiltin(f'Container.Update({get_url(action="movie_detail", movie_name=movie_name)})')

    except Exception as e:
        progress.close()
        traceback.print_exc()
        popinfo(f'Chyba: {str(e)}', icon=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(_handle, succeeded=False)


def movie_trending(params):
    """List trending movies from Trakt with paging."""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + ' \\ Trending movies')

    page = int(params.get('page', '1'))
    limit = 20

    data, headers = _trakt_request('movies/trending',
                                   {'limit': limit, 'page': page,
                                    'extended': 'full,images'})

    if page > 1:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_trending', page=page - 1),
                                    listitem, True)

    for item in data:
        movie = item.get('movie', {})
        title = movie.get('title')
        if not title:
            continue
        watchers = item.get('watchers', 0)
        label = f"{title} ({watchers} users)"
        listitem = xbmcgui.ListItem(label=label)
        poster = movie.get('images', {}).get('poster')
        thumb = poster[0] if isinstance(poster, list) and poster else None
        if thumb and not thumb.startswith('http'):
            thumb = 'https://' + thumb
        art = {'icon': 'DefaultMovies.png'}
        if thumb:
            art['thumb'] = thumb
        listitem.setArt(art)
        info = {'title': title}
        overview = movie.get('overview')
        if overview:
            info['plot'] = overview
        rating = movie.get('rating')
        if rating is not None:
            info['rating'] = rating
        listitem.setInfo('video', info)
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_search', movie_name=title),
                                    listitem, True)

    page_count = int(headers.get('X-Pagination-Page-Count', page))
    if page < page_count:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_trending', page=page + 1),
                                    listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def movie_popular(params):
    """List popular movies from Trakt with paging."""
    xbmcplugin.setPluginCategory(_handle, _addon.getAddonInfo('name') + ' \\ Popular movies')

    page = int(params.get('page', '1'))
    limit = 20

    data, headers = _trakt_request('movies/popular',
                                   {'limit': limit, 'page': page,
                                    'extended': 'full,images'})

    if page > 1:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30206))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_popular', page=page - 1),
                                    listitem, True)

    for movie in data:
        title = movie.get('title')
        if not title:
            continue
        watchers = 0
        ids = movie.get('ids', {})
        slug = ids.get('slug') or ids.get('trakt')
        if slug:
            stats, _ = _trakt_request(f'movies/{slug}/stats')
            if isinstance(stats, dict):
                watchers = stats.get('watchers', 0)
        label = f"{title} ({watchers} users)"
        listitem = xbmcgui.ListItem(label=label)
        poster = movie.get('images', {}).get('poster')
        thumb = poster[0] if isinstance(poster, list) and poster else None
        if thumb and not thumb.startswith('http'):
            thumb = 'https://' + thumb
        art = {'icon': 'DefaultMovies.png'}
        if thumb:
            art['thumb'] = thumb
        listitem.setArt(art)
        info = {'title': title}
        overview = movie.get('overview')
        if overview:
            info['plot'] = overview
        rating = movie.get('rating')
        if rating is not None:
            info['rating'] = rating
        listitem.setInfo('video', info)
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_search', movie_name=title),
                                    listitem, True)

    page_count = int(headers.get('X-Pagination-Page-Count', page))
    if page < page_count:
        listitem = xbmcgui.ListItem(label=_addon.getLocalizedString(30207))
        listitem.setArt({'icon': 'DefaultMovies.png'})
        xbmcplugin.addDirectoryItem(_handle,
                                    get_url(action='movie_popular', page=page + 1),
                                    listitem, True)

    xbmcplugin.endOfDirectory(_handle)


def router(paramstring):
    params = dict(parse_qsl(paramstring))
    if params:
        if params['action'] == 'search':
            search(params)
        elif params['action'] == 'queue':
            queue(params)
        elif params['action'] == 'history':
            history(params)
        elif params['action'] == 'settings':
            settings(params)
        elif params['action'] == 'info':
            info(params)
        elif params['action'] == 'play':
            play(params)
        elif params['action'] == 'download':
            download(params)
        elif params['action'] == 'db':
            db(params)
        # Series Manager actions
        elif params['action'] == 'series':
            series_menu(params)
        elif params['action'] == 'series_search':
            series_search(params)
        elif params['action'] == 'series_trending':
            series_trending(params)
        elif params['action'] == 'series_popular':
            series_popular(params)
        elif params['action'] == 'series_detail':
            series_detail(params)
        elif params['action'] == 'series_season':
            series_season(params)
        elif params['action'] == 'series_refresh':
            series_refresh(params)
        # Movie Manager actions
        elif params['action'] == 'movie':
            movie_menu(params)
        elif params['action'] == 'movie_search':
            movie_search(params)
        elif params['action'] == 'movie_trending':
            movie_trending(params)
        elif params['action'] == 'movie_popular':
            movie_popular(params)
        elif params['action'] == 'movie_detail':
            movie_detail(params)
        elif params['action'] == 'movie_refresh':
            movie_refresh(params)
        else:
            menu()
    else:
        menu()