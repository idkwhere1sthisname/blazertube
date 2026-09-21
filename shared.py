# constants
import os
import dotenv
import xml.etree.ElementTree as ET
import re

dotenv.load_dotenv()

GDATA_API_KEY           = os.getenv("YOUTUBE_API_KEY")

# enables the use of custom credentials instead of the default InnerTube ones
# by default this is disabled, if you want to use this, you'll need to create an oauth2 application on Google Cloud Console
# and add values to OVERRIDE_CLIENT_SECRET, OVERRIDE_CLIENT_ID and OVERRIDE_LOGIN_SCOPE
ENABLE_CREDS_OVERRIDE   = False
if ENABLE_CREDS_OVERRIDE:
    OAUTH_ID            = os.getenv("OVERRIDE_CLIENT_ID")
    OAUTH_SECRET        = os.getenv("OVERRIDE_CLIENT_SECRET")
    LOGIN_SCOPE         = os.getenv("OVERRIDE_LOGIN_SCOPE")
else:
    OAUTH_ID            = os.getenv("OAUTH_CLIENT_ID")
    OAUTH_SECRET        = os.getenv("OAUTH_CLIENT_SECRET")
    LOGIN_SCOPE         = os.getenv("LOGIN_SCOPE")
DEFAULT_DEVICE_ID       = os.getenv("DEFAULT_DEVICE_ID")
DEFAULT_DEVICE_MODEL    = os.getenv("DEFAULT_DEVICE_MODEL")
FLASK_SECRET_KEY        = os.getenv("FLASK_SECRET_KEY")
INNERTUBE_KEY           = os.getenv("INNERTUBE_KEY")

API_USERAGENT           = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
TV_USERAGENT            = "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.5) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/5.0 Chrome/108.0.5359.1 TV Safari/537.36"
PS4_TV_USER_AGENT       = "Mozilla/5.0 (PS4; Leanback Shell) Gecko/20100101 Firefox/65.0 LeanbackShell/01.00.01.75 Sony PS4/ (PS4, , no, CH)"
TV_CLIENT_VERSION       = "7.20260715.15.00"
CONSENT_COOKIES         = {"CONSENT":"YES+1","SOCS":"CAISAiAD"}
GRANT_TYPE              = "urn:ietf:params:oauth:grant-type:device_code"
GRANT_TYPE_REFRESH      = "refresh_token"

GENERATED_CHANNELS      = {
    "UC-9-kyTW8ZkZNDHQJ6FgpwQ": "Music",
    "UCEgdi0XIXXZ-qJOFPf4JSKw": "Sports",
    "UCOpNcN46UbXVtpKMrmU4Abg": "Gaming",
    "UCYfdidRxbB8Qhf0Nx7ioOYw": "News",
    "UClgRkhTL3_hImCAmdLfDE4g": "Movies",
    "HCJYRSLjSb4y8": "Nonprofits & Activism",
    "SBAaOjE-GIlRI": "Live",
    "UC4R8DWoMoI7CAwX8_LjQHig": "Live",
    "HCtB5yQiZTr7Y": "Animals",
    "HCLfhQGBROujg": "Autos & Vehicles",
    "HCRgNMjm7t2M0": "Comedy",
    "HCxAJ-ON2kZuw": "Entertainment",
    "HCVezXaU34vJk": "People & Blogs",
    "HCOJfFxLS-8g4": "Technology",
    "HCMCTE41mELnQ": "Travel & Events",
    "UC3yA8nDwraeOfnYfBWun83g": "Education",
    "UC1vGae2Q3oT5MkhhfW8lwjg": "Lifestyle",
    "UCrpQ4p1Ql_hG8rKXIKM1MOQ": "Fashion & Beauty",
    "UCl8dMTqDrJQ0c8y23UBu4kQ": "TV Shows",
}

# html constants
BUILD_SIG               = "ja:901479,901812,903309,906001,906945,906948,907231,907240,909717,911427,912715,912909,914922,919389,919811,920607,921090,921410,922804,923305,923311,925728,927303,927704,929150,929505,931207,931943,932276,932295,934003,934004,934507,935704,936327,936702,936910,936912,936913,936914,938614,938617,938626,939201,939918,941241,941325,943102"
BUILD_ID                = 58452362

PLAYER_TYPE_UNPLAYABLE  = "unplayable"
PLAYER_TYPE_CRAWLER     = "crawler"
PLAYER_TYPE_FLASH       = "embedflash"
PLAYER_TYPE_HTML5       = "html5"
PLAYER_TYPE_3DS_HTML5FS = "html5fs"
PLAYER_TYPE_HTTP        = "http"
PLAYER_TYPE_LINK        = "link"
PLAYER_TYPE_RTSP        = "rtsp"
PLAYER_TYPE_RTSPCONN    = "rtspconn"
PLAYER_TYPE_VNDRIM      = "vnd.rim"
PLAYER_TYPE_VNDYT       = "vnd.youtube"
PLAYER_TYPE_VNDYTHTTP   = "vnd.youtube.http"

IS_3DS                  = lambda ua : "Factory Media Production" in ua # common check to see if device is a 3DS system
IS_NEW_3DS              = lambda ua : "Nintendo 3DS New3DS" in ua
IS_OLD_3DS              = lambda ua : "Nintendo 3DS" in ua and not IS_NEW_3DS(ua)
GET_REGION_UA           = lambda ua : m.group(1) if (m := re.search(r"Version/[\d.]+\.([A-Z]{2})\b",ua)) else None

# InnerTube constants
SEARCH_VIDEO            = "EgIQAQ%3D%3D"
SEARCH_CHANNEL          = "EgIQAg%3D%3D"
SEARCH_PLAYLIST         = "EgIQAw%3D%3D"
ABOUT_PARAMS            = "EgVhYm91dPIGBAoCEgA%3D"
WATCH_LATER_PLAYLIST    = "cAc%3D"
PARAM_UNSUBSCRIBE       = "CgIIAhgA"
PARAM_SUBSCRIBE         = "EgIIAhgA"
PARAM_PLAYLIST_CREATE   = "CAAoAA%3D%3D"

# advanced options
SIGNINDISABLED          = False
"""disables sign ins."""
SIGNINDISABLED_REASON   = ""
"""reason why sign ins are disabled. it'll show up in the sign ins disabled page."""
ENABLE_CLEAR_MEMORY_BTN = False
"""this option enables a button that deletes every cookie that has been set. It only shows up when the user is signed out. Similar to going to http://embedded.wii/launcher.html?clear_local_data=1 on previous VOD apps. (3DS only, doesn't show up on normal browsers)"""
ENABLE_DUMMY_SIGNIN     = False
"""uses fake credentials instead of requesting Google for them. useful for designing the sign in page."""

# other
CFG_NAMESPACE_STR       = "urn:bt.config"
CFG_NAMESPACE           = {"cfg":"urn:bt.config"}
PARSER_KEEP_COMMENTS    = lambda: ET.TreeBuilder(insert_comments=True)
XMLSCHEMA_INSTANCE_NS   = "http://www.w3.org/2001/XMLSchema-instance"
XSI_NIL                 = f"{{{XMLSCHEMA_INSTANCE_NS}}}nil"

#  TABS
#  case 100: m += '<div class="_mui"></div>'; break;        home page (with vids on ch)
#  case 101: m += EM(); break;                              movies?? (lens) (needs translation)
#  case 102: m += FM(); break;                              フィード (feed? needs translation)
#  case 110: m += GM(); break;                              フリートーク (discussion tab, translation needed) 
#  case 201: m += L(c.title); break;                        weird arrow up, idk, probably because of no title
#  case 114: m += L(c.title); break;                        weird arrow up, idk, probably because of no title
#  case 303: m += '<div class="_mvi"></div>'; break;        weird arrow up, idk, probably because of no title
#  case 301: m += DM(); break;                              about pg, doesnt need a title, needs translation
