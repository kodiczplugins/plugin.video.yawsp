"""Mock Kodi modules for testing"""

# Mock xbmc module
class MockXBMC:
    LOGERROR = 4
    LOGWARNING = 3
    LOGINFO = 2
    LOGDEBUG = 1
    
    @staticmethod
    def log(msg, level=LOGDEBUG):
        print(f"[XBMC LOG {level}] {msg}")
    
    @staticmethod
    def getInfoLabel(label):
        if label == 'System.Date':
            return "Wednesday, July 2, 2025"
        return ""
    
    @staticmethod
    def translatePath(path):
        return path

# Mock xbmcaddon module
class MockAddon:
    def __init__(self, id=None):
        self.id = id
        self.settings = {}
    
    def getSetting(self, key):
        return self.settings.get(key, "")
    
    def setSetting(self, key, value):
        self.settings[key] = value
    
    def getAddonInfo(self, key):
        if key == 'name':
            return "YAWSP Test"
        elif key == 'path':
            return "/test/path"
        return ""
    
    def openSettings(self):
        pass

class MockXBMCAddon:
    @staticmethod
    def Addon(id=None):
        return MockAddon(id)

# Mock xbmcgui module
class MockListItem:
    def __init__(self, label="", label2="", iconImage="", thumbnailImage="", path=""):
        self.label = label
        self.label2 = label2
        self.iconImage = iconImage
        self.thumbnailImage = thumbnailImage
        self.path = path
        self.info = {}
        self.art = {}
    
    def setInfo(self, type, infoLabels):
        self.info[type] = infoLabels
    
    def setArt(self, art):
        self.art.update(art)

class MockXBMCGui:
    NOTIFICATION_INFO = 0
    NOTIFICATION_WARNING = 1
    NOTIFICATION_ERROR = 2
    
    @staticmethod
    def ListItem(label="", label2="", iconImage="", thumbnailImage="", path=""):
        return MockListItem(label, label2, iconImage, thumbnailImage, path)
    
    @staticmethod
    def Dialog():
        return MockDialog()

class MockDialog:
    def notification(self, heading, message, icon=0, time=5000, sound=True):
        print(f"[NOTIFICATION] {heading}: {message}")

# Mock xbmcplugin module
class MockXBMCPlugin:
    SORT_METHOD_LABEL = 1
    
    @staticmethod
    def addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
        return True
    
    @staticmethod
    def addSortMethod(handle, sortMethod):
        pass
    
    @staticmethod
    def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
        pass
    
    @staticmethod
    def setPluginCategory(handle, category):
        pass

# Mock xbmcvfs module
class MockXBMCVfs:
    @staticmethod
    def exists(path):
        import os
        return os.path.exists(path)
    
    @staticmethod
    def mkdirs(path):
        import os
        return os.makedirs(path, exist_ok=True)
    
    @staticmethod
    def translatePath(path):
        return path

# Setup mocks
import sys
sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcaddon'] = MockXBMCAddon()
sys.modules['xbmcgui'] = MockXBMCGui()
sys.modules['xbmcplugin'] = MockXBMCPlugin()
sys.modules['xbmcvfs'] = MockXBMCVfs()