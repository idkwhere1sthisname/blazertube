from __future__ import print_function
from flask import Flask, Response, send_file, request, abort, render_template, redirect, send_from_directory, g, make_response, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_ipban import IpBan
from flask_cors import cross_origin
import json
import time
import re
import requests
from werkzeug.serving import WSGIRequestHandler
from werkzeug.middleware.proxy_fix import ProxyFix
from xml.etree import ElementTree as ET
from urllib3 import disable_warnings
from urllib.parse import urlencode, unquote, quote
import ssl
from functools import wraps
import sys
from bs4 import BeautifulSoup
import threading
from xml.sax.saxutils import escape
import colorama
from pathlib import Path
import traceback
import secrets
import hmac
from typing import Literal

from video import GetVideo
import functions as funcmod
from youtubei import GDataAPI, InnerTubeAPI, OAuth2API, CombinedAPIs, LoungeAPI, Utils
from youtubei import fmt_view, fmt_duration, CHANNEL_ID_RE, TOPIC_ID_RE
from shared import *
import debug as debugmodule
from captions import Captions

BASE           = Path(__file__).resolve().parent
TEMPLATES_DIR  = BASE/"templates"
DEFAULT_FMT    = "©2013 YouTube LLC"
root           = ""
METADIR        = BASE/"meta"

EXT_API_PROT   = "http"
EXT_API_HOST   = "127.0.0.1"
EXT_API_PATH   = "status"
EXT_API_PORT   = ""
VERSION_URL    = ""
XLB_URL        = ""

# app config + extensions
app            = Flask("BlazerTube",static_folder="static",template_folder="templates")
app.wsgi_app   = ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)
limiter        = Limiter(app=app,key_func=get_remote_address,default_limits=["100 per minute"],storage_uri="memory://")
ipban          = IpBan(app,ban_seconds=86400)

gdata          = GDataAPI(
                    GDataKey=GDATA_API_KEY,
               )
innertube      = InnerTubeAPI(
                    innerTubeKey=INNERTUBE_KEY,
               )
oauth2         = OAuth2API(
                    oauth_id=OAUTH_ID,
                    oauth_secret=OAUTH_SECRET,
                    login_scopes=LOGIN_SCOPE,
                    device_id=DEFAULT_DEVICE_ID,
                    device_model=DEFAULT_DEVICE_MODEL,
               )
apicombo       = CombinedAPIs(
                    gdataKey=GDATA_API_KEY,
                    innerTubeKey=INNERTUBE_KEY
               )
lounge         = LoungeAPI()
youtubeiUtils  = Utils(innertubeKey=INNERTUBE_KEY)

nuisancesfile  = METADIR/"nuisances.yml"
allowedfile    = METADIR/"allowed.yml"
if nuisancesfile.is_file():
    ipban.load_nuisances(nuisancesfile)
if allowedfile.is_file():
    ipban.load_allowed(allowedfile)
else:
    ipban.load_allowed()

ENTERTAINMENT_KW = {"entertainment", "comedy", "funny", "vlog", "prank", "talk", "show",
                    "late night", "sketch", "skit", "reaction", "talkshow", "interview"}
MUSIC_KW         = {"music", "song", "official", "lyrics", "mv", "album", "audio", "remix", "cover",
                    "ft.", "feat", "beat", "rap", "pop", "rock", "jazz", "k-pop", "kpop", "vevo"}

config      = BASE/"config.xml"
colorama.init(autoreset=True)
Fore  = colorama.Fore
Back  = colorama.Back

paths            = "account_notifications account_privacy account_revert account_sharing account_switcher inbox my_favorites my_history my_playlists my_videos offer_details paid_unsubscribe_confirmation post_purchase_confirmation subscription_manager".split(" ")
HTMLpaths        = "account_recovery auth_sub_request create_account create_channel eval identity_merge_done merge_identity merge_identity_done oauth_authorize_token oops remote_error signin terms verify_age verify_controversy".split(" ")
# ln. 77, col 281 in swatch module, these are parsed by HTML so they can be recreated theoretically
# NOTE: flag is in another path but it uses the same system
allpaths         = "account_notifications account_privacy account_revert account_switcher inbox my_playlists my_videos offer_details paid_unsubscribe_confirmation post_purchase_confirmation subscription_manager account_recovery auth_sub_request create_account create_channel eval identity_merge_done merge_identity merge_identity_done oauth_authorize_token oops remote_error signin terms verify_age verify_controversy channel_switcher credits".split(" ")
NOT_IMPLEMENTED  = "account_revert account_notifications account_privacy account_switcher inbox my_playlists offer_details paid_unsubscribe_confirmation post_purchase_confirmation account_recovery auth_sub_request create_account create_channel identity_merge_done merge_identity merge_identity_done oauth_authorize_token oops remote_error signin terms verify_age verify_controversy channel_switcher".split(" ")
# https://web.archive.org/web/20130330172122/http://m.youtube.com/remote_error
# https://web.archive.org/web/20130317103105/http://m.youtube.com/oops
# https://web.archive.org/web/20140302004802/http://www.youtube.com/account_recovery
OTHER_HTML_ROUTE = "new_visual_design usearch_optin asignin_optin autoplay_optin nirvana_optin newsearch_optin not_implemented".split(" ")

# topic channels
# as defined in swatch module
kw_topics        = "activism artist autos blogs comedy education entertainment film gaming howto live movies music news people pets programme recommended science show shows sports travel videos".split(" ")
actual_topics    = "activism artist autos comedy education entertainment film gaming howto live movies music news people pets science show shows sports travel".split(" ")
TOPIC_LINKS      = {
    "movies": "UClgRkhTL3_hImCAmdLfDE4g",
    "show": "UClgRkhTL3_hImCAmdLfDE4g",
    "shows": "UClgRkhTL3_hImCAmdLfDE4g",
    "film": "UClgRkhTL3_hImCAmdLfDE4g",
    "news": "UCYfdidRxbB8Qhf0Nx7ioOYw",
    "gaming": "UCOpNcN46UbXVtpKMrmU4Abg",
    "sports": "UCEgdi0XIXXZ-qJOFPf4JSKw",
    "music": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
    "artist": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
    "live": "UC4R8DWoMoI7CAwX8_LjQHig",
    "activism": "HCJYRSLjSb4y8",
    "pets": "HCtB5yQiZTr7Y",
    "autos": "HCLfhQGBROujg",
    "comedy": "HCRgNMjm7t2M0",
    "entertainment": "HCxAJ-ON2kZuw",
    "people": "HCVezXaU34vJk",
    "science": "HCOJfFxLS-8g4",
    "travel": "HCMCTE41mELnQ",
    "education": "UC3yA8nDwraeOfnYfBWun83g",
    "howto": "UC1vGae2Q3oT5MkhhfW8lwjg",
}

# defaults
port         = 80
debugmode    = False
host         = "0.0.0.0"
pempath      = BASE/"ssl"/"rootCA.crt"
keypath      = BASE/"ssl"/"rootCA.key"
secureserver = False
maint        = False

cfgexist          = False

def set_external_API_url(extapiprot,extapihost,extapiport="443"):
    global EXT_API_PROT,EXT_API_HOST,EXT_API_PORT
    if extapihost == "0.0.0.0":
        EXT_API_HOST = funcmod.showlanip() or "127.0.0.1"
    else:
        EXT_API_HOST = extapihost
    EXT_API_PROT = extapiprot
    EXT_API_PORT = extapiport
def set_version_subpath(subpath):
    global VERSION_URL
    VERSION_URL = "%s://%s:%s/%s"%(EXT_API_PROT,EXT_API_HOST,EXT_API_PORT,subpath)
def set_versioned_xlb_subpath(subpath):
    global XLB_URL
    XLB_URL = "%s://%s:%s/%s"%(EXT_API_PROT,EXT_API_HOST,EXT_API_PORT,subpath)

def loadcfg():
    global host,port,debugmode,secureserver,keypath,pempath,config,cfgexist,maint,huluhost,huluport
    if not config.is_file():
        cfgexist = False
        return
    else:
        cfgexist = True
    parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
    root = ET.parse(config,parser=parser).getroot()
    def safeget(name,default=None):
        elem = root.find(f"cfg:{name}",CFG_NAMESPACE)
        return elem.text if elem is not None else default
    host = safeget("yt_host","0.0.0.0")
    if host == "localip":
        host = "0.0.0.0"
    try:
        port = int(safeget("yt_port","80"))
    except (Exception,ValueError,TypeError):
        port = 80
    debugmode = bool(safeget("debugging","false").lower().strip() == "true")
    secureserver = bool(safeget("secure","false").lower().strip() == "true")
    if secureserver:
        pempath = Path(safeget("pempath","ssl/rootCA.crt"))
        keypath = Path(safeget("keypath","ssl/rootCA.key"))
        if not pempath.is_absolute():
            pempath = BASE/pempath
        if not keypath.is_absolute():
            keypath = BASE/keypath
    maint = bool(safeget("maint","false").lower().strip() == "true")
def cleanup_schedule():
    doflush = False if debugmode else True
    print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Cleaning up in 6 seconds...",flush=doflush)
    time.sleep(6.00)
    schedulevideo = GetVideo()
    while True:
        print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Cleaning up videos older than 1 day...",flush=doflush)
        schedulevideo.cleanup()
        sleepfor = 86400
        sleepfor_min = sleepfor//86400
        print("%s[cleanup]%s Done! Next cleanup in %s day%s (%s second%s)..."%(Fore.MAGENTA,Fore.RESET,sleepfor_min,'' if abs(sleepfor_min) == 1 else 's',sleepfor,'' if abs(sleepfor) == 1 else 's'),flush=doflush)
        time.sleep(sleepfor)
def getVersion():
    if not debugmode:
        ext_host_secure = EXT_API_PROT == "https"
        try:
            r = requests.get(VERSION_URL,verify=ext_host_secure,timeout=10,headers={
                "Accept": "application/json;q=1.0,text/json;q=0.9,application/x-www-form-urlencoded;q=0.8;text/plain;q=0.7,*/*;q=0.0",
                "User-Agent": "-",
                "Accept-Language": "en-US;q=1.0,en;q=1.0,*;q=0.0",
                "Accept-Charset": "UTF-8",
                "X-Real-IP": request.remote_addr,
                "X-Secure": str(ext_host_secure).lower(),
            },params={
                "action_get_version": "1",
                "fmt": "json",
            })
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            return {
                "prefix": "??",
                "strversion": "??"
            }
    else:
        return {
            "prefix":" ",
            "strversion":" "
        }
def getXLB(lang,country):
    ext_host_secure = EXT_API_PROT == "https"
    l = str(lang).lower()
    c = str(country).upper()
    try:
        r = requests.get(XLB_URL,verify=ext_host_secure,timeout=25,headers={
            "Accept": "application/xml;q=1.0,text/xml;q=0.9,text/json;q=0.4,application/json;q=0.5,application/x-www-form-urlencoded;q=0.2,text/plain;q=0.2,*/*;q=0.0",
            "User-Agent": "-",
            "Accept-Language": f"{l}_{c};q=1.0,{lang}-{c};q=1.0,{lang};q=0.5",
            "Accept-Charset": "UTF-8",
            "X-Real-IP": request.remote_addr,
            "X-Secure": str(ext_host_secure).lower(),
            "X-HL": l,
            "X-GL": c,
        },params={
            "action_get_versioned_xlb": "1",
            "fmt": "xml"
        })
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None
# this does NOT enforce these strings as arguments for xsrf_fmt or xsrf_stor_name, it's just for type checking
XSRF_TYPES = Literal[
    # standard xsrf_token field names
    'xsrf_token',
    'subscribe_xsrf_token',
    'sentiment_xsrf_token',
    'add_favorite_xsrf_token',
    'autoshare_xsrf_token',
    'manage_playlist_xsrf_token',
    'set_safety_mode_xsrf_token',
    # these are unused but still present in the files
    'comment_xsrf_token',
    'post_xsrf_token',
    'session_token',
]
def get_xsrf(
    xsrf_fmt:XSRF_TYPES="xsrf_token",
    xsrf_stor_name:XSRF_TYPES|None="xsrf_token"
) -> str:
    stor_xsrf = session.get(xsrf_fmt)
    if stor_xsrf is None:
        stor_xsrf = secrets.token_urlsafe(32)
        session[xsrf_stor_name] = stor_xsrf
    return stor_xsrf

def vfy_xsrf(
    xsrf_fmt:XSRF_TYPES,
    recv_xsrf_name:XSRF_TYPES|None=None
) -> None:
    recv_xsrf = request.form.get(xsrf_fmt)
    stor_xsrf = session.get(recv_xsrf_name)
    if not recv_xsrf or not stor_xsrf:
        if debugmode:
            print(f"{Fore.RED}[error]{Fore.RESET} either the received XSRF or stored XSRF token(s) aren't present")
        return abort(403)
    digestmatches = hmac.compare_digest(stor_xsrf,recv_xsrf)
    if not digestmatches:
        if debugmode:
            print(f"{Fore.RED}[error]{Fore.RESET} XSRF digest doesn't match")
        return abort(403)
    if debugmode:
        print(f"{Fore.BLUE}[info]{Fore.RESET} XSRF token check passed for {unquote(recv_xsrf_name)}")

def json_response(data):
    return Response(
        json.dumps(data),
        headers={"Content-Type": "application/json","Access-Control-Allow-Origin":"*"},
        status=200
    )

def serve_index():
    host = request.host
    headers = request.headers
    cookies = request.cookies
    index = str(TEMPLATES_DIR/"index.html")
    with open(index,"r",encoding="utf-8") as f:
        html = f.read()
    for key, val in {
        "{{ lang_cfg.html_lang }}": "en",
        "{{ lang_cfg.lang }}": "en",
        "{{ lang_cfg.language }}": "en",
        "{{ lang_cfg.languageName }}": "English",
        "{{ lang_cfg.locale }}": "en_US",
    }.items():
        html = html.replace(key, val)
    # 1
    sl_og1 = "https://accounts.google.com/ServiceLogin?passive=true&amp;uilel=3&amp;hl=en&amp;continue=http%3A%2F%2Fm.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Dm%26feature%3Dmobile_passive%26hl%3Den%26next%3Dhttp%253A%252F%252Fm.youtube.com%252Fsignin_passive%253Foriginal_url%253DORIGINAL_URL_PLACE_HOLDER&amp;service=youtube&amp;ltmpl=mobile"
    # 2
    sl_og2 = "https://accounts.google.com/ServiceLogin?passive=true\u0026uilel=3\u0026hl=en\u0026continue=http%3A%2F%2Fm.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Dm%26feature%3Dblazerbootstrap%26hl%3Dja%26next%3D_NEXT_URL_PLACEHOLDER_\u0026service=youtube\u0026ltmpl=mobile"
    html = html.replace('<script src="//pagead2.googlesyndication.com/pagead/show_ads.js"', "<script ")
    ver = getVersion()
    PRE = ver["prefix"]
    VER = ver["strversion"]
    ua = headers.get("User-Agent","-")
    FMT = f"{PRE} {VER}"
    hl = g.HL or cookies.get("hl") or "en"
    gl = g.GL or cookies.get("gl") or "US"
    shownversion = f"'+new Date().getFullYear()+' BlazerTube ({FMT.upper()})" if not debugmode else DEFAULT_FMT
    html = html.replace("{{FMTVER}}",shownversion)
    ServiceLogin1 = f"{'https' if request.is_secure else 'http'}://{host}/vendor_signin"
    ServiceLogin2 = f"{'https' if request.is_secure else 'http'}://{host}/vendor_signin"
    html = html.replace("{{SVCLOGIN1}}",ServiceLogin1)
    html = html.replace("{{SVCLOGIN2}}",ServiceLogin2)
    if g.SIGNED_IN:
        pfp_final = "/static/images/1.png"
        email_final = ""
        if g.INFO["photo"]:
            pfp_final = g.INFO["photo"].replace("https://","http://")
        if g.INFO["email"]:
            email_final = g.INFO["email"]
        channelId = innertube.GetChannelIDFromHandle(g.INFO["handle"])
        channelUrl = "%s://%s/channel/%s"%("https" if request.is_secure else "http",request.host,channelId)
        html = html.replace('{{STYLE}}','display:block')
        html = html.replace('{{STYLE_SIGN_OUT_BTN}}','display:block')
        html = html.replace('{{CLEARMEM_STYLE}}','display:none')
        html = html.replace("{{USERNAME}}",g.INFO["name"])
        html = html.replace("{{SIGNED_IN_PROFILE_PICTURE}}",'"%s"'%(pfp_final))
        html = html.replace("{{SIGNED_IN_EMAIL}}",email_final)
        html = html.replace("{{CHANNEL_URL}}",f'"{channelUrl}"')
    else:
        html = html.replace('{{STYLE}}','display:block')
        html = html.replace('{{STYLE_SIGN_OUT_BTN}}','display:none')
        html = html.replace('{{CLEARMEM_STYLE}}','display:block' if ENABLE_CLEAR_MEMORY_BTN else 'display:none')
        html = html.replace("{{USERNAME}}",'')
        html = html.replace("{{SIGNED_IN_EMAIL}}",'')
        html = html.replace("{{CHANNEL_URL}}","null")
        html = html.replace("{{SIGNED_IN_PROFILE_PICTURE}}",'null')
    html = html.replace("{{SIGNED_IN_BOOL}}",str(g.SIGNED_IN).lower())
    html = html.replace("{{SECURE_BOOL}}",str("true" if request.is_secure else "false").lower().strip())
    html = html.replace("{{BUILD_ID}}",str(BUILD_ID))
    html = html.replace("{{BUILD_SIGNATURE}}",BUILD_SIG)
    html = html.replace("{{hl}}",hl)
    html = html.replace("{{gl}}",gl)
    html = html.replace("{{host}}","%s://%s"%("https" if secureserver else "http",request.host),-1)
    html = html.replace("{{host_noprot}}",request.host,-1)
    languagespath = METADIR/"language.json"
    countriespath = METADIR/"country.json"
    languageName = "English"
    localeName = "America"
    langlist = [["en","English"]]
    countrylist = [["US","America"]]
    if languagespath.is_file():
        with open(languagespath,"r",encoding="utf-8") as f:
            langlist = json.load(f)
    if countriespath.is_file():
        with open(countriespath,"r",encoding="utf-8") as f:
            countrylist = json.load(f)
    languageName = next((n for c,n in langlist if c == hl),hl)
    localeName = next((n for c,n in countrylist if c == gl),gl)
    html = html.replace("{{LOCALENAME}}",localeName)
    html = html.replace("{{LANGUAGENAME}}",languageName)
    html = html.replace("{{GAPI_LOCALE}}",f"{languageName}_{localeName}")
    html = html.replace('{{REQUEST_LANGUAGE}}',hl)
    IS3DS = IS_3DS(ua)
    vendor = "UNKNOWN"
    model = "unk"
    param_app = "youtube_mobile"
    if IS3DS:
        vendor = "NINTENDO"
        model = "3ds"
        param_app = "youtube_embedded"
        ISNEW3DS = IS_NEW_3DS(ua)
        if ISNEW3DS:
            model = "new3ds"
    html = html.replace("{{VENDOR}}",vendor)
    html = html.replace("{{MODEL}}",model,-1)
    loginframeparams = {
        # we don't even store this stuff
        "vendor": vendor,
        "model": model,
        "cbrver": "7.0.11B554a",
        "c": "MWEB",
        "noflv": "1",
        "cos": model,
        "cbr": vendor,
        "cver": "html5",
        "hl": hl,
        "gl": gl,
        "ns": "yt",
        "app": param_app,
        "ps": "blazer",
        "preq": "http://embedded.ctr/launcher.html",
        "gdata_url": f"{'http' if secureserver else 'https'}://{host}",
    }
    if IS3DS:
        loginframeparams["screenw"] = "320"
        loginframeparams["screenh"] = "240"
    ServiceLoginFrame = f"{'https' if request.is_secure else 'http'}://{host}/vendor_signin/frame?" + urlencode(loginframeparams)
    html = html.replace("{{SVCLOGIN_FRAME}}",ServiceLoginFrame)
    return Response(html,status=200,headers={"Content-Type":"text/html; charset=utf-8"})

def checkifajax(func):
    """Checks if a route is accessed through AJAX"""
    @wraps(func)
    def wrap(*args,**kwargs):
        if request.args.get("ajax") == "1":
            return func(*args,**kwargs)
        return serve_index()
    return wrap
def checkifajax_POST(func):
    """Checks if a route is accessed through AJAX (POST)"""
    @wraps(func)
    def wrap(*args,**kwargs):
        if request.form.get("ajax") == "1":
            return func(*args,**kwargs)
        return serve_index()
    return wrap
def checkifajax_ANY(func):
    """Checks if a route is accessed through AJAX (POST+GET)"""
    @wraps(func)
    def wrap(*args,**kwargs):
        if request.form.get("ajax") == "1" or request.args.get("ajax") == "1":
            return func(*args,**kwargs)
        return serve_index()
    return wrap

def require_xsrf(xsrf_fmt:XSRF_TYPES):
    """Makes a route require one or more XSRF tokens via POST (lounge API optionally using DELETE, PUT and PATCH)"""
    def wrap(func):
        @wraps(func)
        def wrapper(*args,**kwargs):
            vfy_xsrf('session_token',xsrf_fmt)
            return func(*args, **kwargs)
        return wrapper
    return wrap

def fetch_popular(maxResults=10):
    ret = gdata.GetPopularVideos(limit=maxResults)
    final = ret["items"]
    return final

def shelf_item(k):
    vid_id = k["encrypted_id"]
    thumb = funcmod.getThumbnail(vid_id)
    return {
        "content_type": 500,
        "content_item": {
            "ua": vid_id,
            "encrypted_id": vid_id,
            "title": k["title"],
            "short_byline": k.get("short_byline", ""),
            "public_name": k.get("public_name", ""),
            "nb": k.get("public_name") or k.get("short_byline", ""),
            "view_count": fmt_view(k["view_count"]),
            "duration": fmt_duration(k["duration"]),
            "Sc": f"/watch?v={vid_id}",
            "Jb": {
                "url": thumb,
            },
            "thumbnail_info": {
                "url": thumb,
            },
        }
    }

def flat_item(k):
    vid_id = k["encrypted_id"]
    thumb = funcmod.getThumbnail(vid_id)
    return {
        "item_type": "compact_video",
        "action_type": "WL",
        "video": {
            "encrypted_id": vid_id,
            "title": k["title"],
            "short_byline": k["short_byline"],
            "public_name": k["public_name"],
            "view_count": fmt_view(k["view_count"]),
            "duration": fmt_duration(k["duration"]),
            "watch_link": f"/watch?v={vid_id}",
            "thumbnail_info": {
                "url": thumb,
            },
        }
    }

def flat_channel(k):
    channelId = k["channel_id"]
    thumb = f"/channel/{channelId}/icon"
    return {
        "public_name": k["title"],
        "title": k["title"],
        "url": f"/channel/{channelId}",
        "subscriber_count": k["subscriber_count"],
        "video_count": k["video_count"],
        "thumbnail": thumb,
    }

def make_shelf(title, items, view_url=""):
    return {"title": title, "items": items, "view_url": view_url}

def guess_category(title, byline):
    combined = (title + " " + byline).lower()
    if any(k in combined for k in MUSIC_KW):
        return "music"
    if any(k in combined for k in ENTERTAINMENT_KW):
        return "entertainment"
    return "general"

def build_shelves(popularJSON):
    all_items = [shelf_item(v["video"]) for v in popularJSON]
    buckets = {"music": [], "entertainment": [], "general": []}
    for v in popularJSON:
        k = v["video"]
        buckets[guess_category(k.get("title", ""), k.get("short_byline", ""))].append(shelf_item(k))

    shelves = [
        make_shelf("", all_items[:3], "/feed/trending"),
        make_shelf("Most Popular", all_items[3:6]),
    ]
    ent = buckets["entertainment"][:3] or all_items[6:7]
    if ent:
        shelves.append(make_shelf("Entertainment", ent[:3]))
    music = buckets["music"][:3] or all_items[7:10]
    if music:
        shelves.append(make_shelf("Music", music[:3], '/topic/UC-9-kyTW8ZkZNDHQJ6FgpwQ'))
    return {"shelf_groups": [shelves]}

def make_guide_item(title, url, thumbnail="",count=0):
    return {"title": title, "url": url, "count": count, "thumbnail": thumbnail}

@app.errorhandler(403)
def forbidden(err):
    return render_template("errors/403.html"),403
@app.errorhandler(404)
def not_found(err):
    return render_template("errors/404.html"),404
@app.errorhandler(405)
def methodnotallowed(err):
    return render_template("errors/405.html"),405
@app.errorhandler(409)
def conflict(err):
    return render_template("errors/409.html"),409
@app.errorhandler(429)
def toomanyrequests(err):
    return render_template("errors/429.html"),429
@app.errorhandler(500)
def internalerror(err):
    return render_template("errors/500.html"),500
@app.errorhandler(502)
def badgateway(err):
    return render_template("errors/502.html"),502

@app.route("/")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def redir():
    data = request.args
    ajax = data.get("ajax","0") == "1"
    clear_memory = data.get("clear_local_data","0") == "1"
    get_flashvars = data.get("action_get_flashvars","0") == "1"
    versioned_xlb = data.get("action_get_versioned_xlb","0") == "1"
    if clear_memory and ENABLE_CLEAR_MEMORY_BTN:
        if not IS_3DS(request.headers.get("User-Agent","-")):
            return redirect("/")
        resp = make_response(render_template("clear_memory.html"))
        return resp
    elif ajax:
        return redirect("/home",code=301)
    return redirect("/home",code=301)

@app.route("/home")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
@checkifajax
def home():
    return serve_index()

@app.route("/debug.html")
@app.route("/debug")
def debug():
    if debugmode:
        return render_template("debug.html",UserAgent=request.headers.get("User-Agent",""),mimetype="text/html")
    else:
        return abort(404)

@app.route("/feed_ajax")
@app.route("/feed",strict_slashes=False)
@app.route("/feed/<path:subpath>",strict_slashes=False)
@app.route("/browse")
@app.route("/menugrid")
@app.route("/index")
@app.route("/my_account")
@app.route("/my_history")
@app.route("/my_subscriptions")
@app.route("/feed/<path:subpath>/<path:subsubpath>",strict_slashes=False)
@app.route("/recommended")
@app.route("/my_videos")
@checkifajax
# todo: playlists
def feed(subpath=None,subsubpath=None):
    cookies = request.cookies
    hl = cookies.get("hl") or getattr(g,"HL","en")
    gl = cookies.get("gl") or getattr(g,"GL","US")
    json_r = {
        "content": {
            "feed_items": None,
            "feed_title": f"Feed not implemented ({request.path.removeprefix('/feed/')})",
            "featured_shelves": None,
            "image_url": None,
            "channel_url": None,
            "show_filter": False,
            "show_social_upsell": False,
            "destination_moments": None,
        },
    }
    if subpath is None or subpath == "popular":
        raw = fetch_popular(maxResults=10)
        json_r = {
            "content": {
                "feed_items": [flat_item(v["video"]) for v in raw],
                "feed_title": "Popular on YouTube",
                "featured_shelves": build_shelves(raw),
                "channel_url": None,
                "image_url": None,
                "show_filter": False,
                "show_social_upsell": False,
                "destination_moments": None,
            }
        }
    elif subpath == "subscriptions" or request.path == "/my_subscriptions":
        if not g.SIGNED_IN:
            return redirect("/vendor_signin/required?from=subscriptions")
        feed_items_activity = None
        oauth_token = g.OAUTH_TOKEN
        if subsubpath == "activity":
            json_r = {
                "content": {
                    "feed_items": feed_items_activity,
                    "feed_title": "My subscriptions",
                    "featured_shelves": None,
                    "channel_url": None,
                    "image_url": None,
                    "next_url": None,
                    "show_social_upsell": False,
                    # first check should be enough to show the filter or not
                    "show_filter": True,
                    "destination_moments": None,
                }
            }
        else:
            feed_items = innertube.ActivityFeed(hl=hl,gl=gl,oauth_token=oauth_token,remove_shorts=True)
            json_r = {
                "content": {
                    "feed_items": feed_items,
                    "feed_title": "My subscriptions",
                    "featured_shelves": None,
                    "channel_url": None,
                    "image_url": None,
                    "next_url": None,
                    "show_social_upsell": False,
                    "show_filter": True,
                    "destination_moments": None,
                }
            }
    elif subpath == "river":
        if not g.SIGNED_IN:
            return redirect("/vendor_signin/required?from=river")
        oauth_token = g.OAUTH_TOKEN
        raw,shelves = innertube.WhatToWatch(oauth_token=oauth_token,hl=hl,gl=gl)
        json_r = {
            "content": {
                "feed_items": [flat_item(w) for w in raw[:20]],
                "feed_title": "What to Watch",
                "featured_shelves": shelves, # ln. 69 col 131: b.N&&c -> b&&b.N&&c in swatch module to make this work, without this, it'll error out
                "channel_url": None,
                "image_url": None,
                "show_filter": False,
                "next_url": None,
                "show_social_upsell": False,
                "destination_moments": None,
            }
        }
    elif subpath == "history" or request.path == "/my_history":
        if not g.SIGNED_IN:
            return redirect("/vendor_signin/required?from=history")
        oauth_token = g.OAUTH_TOKEN
        continuation_token = request.args.get("continuation") or None
        page = request.args.get("p") or 1
        try:
            page = int(page)
        except ValueError:
            page = 1
        nextPage = page+1
        raw,continuation = innertube.WatchHistory(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
        next_url = None
        if continuation:
            next_url = "/feed/history?" + urlencode({
                "continuation": continuation,
                "p": nextPage
            })
        json_r = {
            "content": {
                "feed_items": [flat_item(w) for w in raw],
                "feed_title": "Watch History",
                "featured_shelves": None,
                "channel_url": None,
                "image_url": None,
                "next_url": next_url,
                "show_filter": False,
                "show_social_upsell": False,
                "destination_moments": None,
            }
        }
    elif subpath == "uploads" or request.path == "/my_videos":
        if not g.SIGNED_IN:
            return redirect("/vendor_signin/required?from=ownvideos")
        oauth_token = g.OAUTH_TOKEN
        continuation_token = request.args.get("continuation") or None
        page = request.args.get("p") or 1
        try:
            page = int(page)
        except ValueError:
            page = 1
        nextPage = page+1
        next_url = None
        ownvideos,continuation = innertube.MyVideos(oauth_token=oauth_token)
        if continuation_token:
            next_url = "/feed/uploads?" + urlencode({
                "p": nextPage,
                "continuation": continuation,
            })
        json_r = {
            "content": {
                "feed_items": ownvideos,
                "feed_title": "My videos",
                "channel_url": None,
                "image_url": None,
                "featured_shelves": None,
                "show_social_upsell": False,
                "show_filter": False,
                "destination_moments": False,
                "next_url": next_url,
            }
        }
    json_r_footer = {
        "result": "ok",
        "signed_in_username": "",
        "signed_in_email": "",
        "conn": "wifi",
        "build_signature": BUILD_SIG,
        "timestamp": int(time.time()),
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_username"] = g.INFO["name"]
        json_r_footer["signed_in_email"] = g.INFO["email"]
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/leanback_ajax")
@app.route("/guide_ajax")
def guide_ajax():
    json_r = {
        "content": {
            "innertube_guide": [
                {"title": "", "items": [
                    make_guide_item("Popular on YouTube", "/home", "/static/images/topics/icons/thumb_popular.jpg"),
                    make_guide_item("Music", "/topic/UC-9-kyTW8ZkZNDHQJ6FgpwQ", "/static/images/topics/icons/thumb_music.jpg"),
                    make_guide_item("Sports", "/topic/UCEgdi0XIXXZ-qJOFPf4JSKw", "/static/images/topics/icons/thumb_sports.jpg"),
                    make_guide_item("Gaming", "/topic/UCOpNcN46UbXVtpKMrmU4Abg", "/static/images/topics/icons/thumb_gaming.jpg"),
                    make_guide_item("News", "/topic/UCYfdidRxbB8Qhf0Nx7ioOYw", "/static/images/topics/icons/thumb_news.jpg"),
                    make_guide_item("Movies", "/topic/UClgRkhTL3_hImCAmdLfDE4g", "/static/images/topics/icons/thumb_movies_new.jpg"),
                    make_guide_item("Spotlight","/user/UCBR8-60-B28hp2BmDPdntcQ","/static/images/topics/icons/thumb_spotlight.png"), # what channel would this even be?
                ]},
                {"title": "CHANNELS FOR YOU", "items": []},
                {"title": "","items": []},
            ],
            "innertube_guide_error": None,
        },
        "signed_in_username": "",
        "signed_in_email": "",
        "result": "ok",
        "build_id": BUILD_ID,
        "conn": "wifi",
        "timestamp": int(time.time()),
        "build_signature": BUILD_SIG
    }
    if g.SIGNED_IN:
        name = g.INFO["name"]
        handle = g.INFO["handle"]
        hasch = g.INFO["haschannel"]
        oauth_token = g.OAUTH_TOKEN
        hl = request.cookies.get("hl") or getattr(g,"HL","en")
        gl = request.cookies.get("gl") or getattr(g,"GL","US")
        if hasch:
            channelId = innertube.GetChannelIDFromHandle(handle)
        else:
            channelId = None
        if channelId is None:
            channelId = "/"
        else:
            channelId = "/user/%s"%(channelId)
        IT_GUIDE = json_r["content"]["innertube_guide"]
        IT_GUIDE.insert(0,{"title":"","items":[
            make_guide_item("What to Watch","/recommended"),
            make_guide_item("My Subscriptions","/my_subscriptions"),
            make_guide_item("Favorites","/my_favorites"),
            make_guide_item("My playlists","/my_playlists"),
            make_guide_item("Social","/not_implemented"),
            make_guide_item("History","/my_history"),
            make_guide_item("Watch Later","/my_watch_later_videos"),
            make_guide_item("Inbox","/inbox"),
        ]})
        items = IT_GUIDE[0]["items"] # CHANNEL SWITCHER
        if hasch:
            items.insert(-1,make_guide_item("Your videos","/my_videos"))
        default_subscription = IT_GUIDE[1] # SUBSCRIPTIONS
        default_subscription["title"] = "SUBSCRIPTIONS"
        recom_channels = IT_GUIDE[2]
        ret = gdata.RecommendedChannels(oauth_token=oauth_token,maxResults=4,hl=hl,gl=gl)
        channels = ret or []
        if channels:
            recom_channels["title"] = "CHANNELS FOR YOU"
            for c in ret:
                recom_channels["items"].append(
                    make_guide_item(c["title"],f"/channel/{c['channel_id']}/",f"/channel/{c['channel_id']}/icon")
                )
            recom_channels["items"].append(
                make_guide_item("YouTube Spotlight","/user/UCBR8-60-B28hp2BmDPdntcQ","/static/images/topics/icons/thumb_spotlight.png"),
            )
            recomm_channels_btns = IT_GUIDE[3]
        else:
            recomm_channels_btns = IT_GUIDE[2] # CHANNELS FOR YOU
        recomm_channels_btns["title"] = ""
        recomm_channels_btns["items"] = [
            make_guide_item("Browse channels","/channels/browser","/static/images/topics/thumb_channels_lq.png"),
            make_guide_item("Manage subscriptions","/subscription_manager","/static/images/topics/thumb_submanager_lq.png"),
        ]
        json_r["signed_in_username"] = name
        json_r["signed_in_email"] = g.INFO["email"]
    else:
        json_r["content"]["innertube_guide"][1]["items"] = [
            make_guide_item("Sign in to see channels", "/signin","/static/images/topics/thumb_channels_lq.png"),
        ]
    return json_response(json_r)

@app.route("/static/js/common.js")
def commonJS():
    jspath = BASE/"static"/"js"/"common.js"
    if jspath.is_file():
        return send_file(jspath),200,{"Content-Type": "application/javascript"}
    return abort(404)
@app.route("/static/js/signin.prod.js")
@app.route("/static/js/signin.js")
def signinJS():
    jspath = BASE/"static"/"js"/"signin.prod.js"
    if jspath.is_file():
        return send_file(jspath),200,{"Content-Type": "application/javascript"}
    return abort(404)
@app.route("/mobile-blazer-swatch_mobile_blazer_profile_swatch_mod__ja-vflvm1gnu.js")
def profile_js():
    jspath = "js/mobile-blazer-swatch_mobile_blazer_profile_swatch_mod__ja-vflvm1gnu.js"
    return Response(render_template(jspath), headers={"Content-Type":"application/javascript"})
@app.route("/mobile-blazer-swatch_mobile_blazer_noncore_swatch_mod__ja-vflDGyE3t.js")
def blazer_js():
    finalhost = request.host
    signinbool = g.SIGNED_IN
    userId = "null"
    if signinbool:
        if g.INFO:
            if g.INFO["handle"] and g.INFO["haschannel"]:
                if innertube.GetChannelIDFromHandle(g.INFO["handle"]):
                    userId = innertube.GetChannelIDFromHandle(g.INFO["handle"])
    jspath = "js/mobile-blazer-swatch_mobile_blazer_noncore_swatch_mod__ja-vflDGyE3t.js"
    jstopics = []
    for t in actual_topics:
        link = TOPIC_LINKS.get(t,"")
        jstopics.append(f'Jn.{t}=new oB("/topic/{link}")')
    topics_template = ";".join(jstopics)
    return Response(render_template(jspath,debug=debugmode,host=finalhost,signinbool=signinbool,USER_ID=userId,channeltopicsJN=topics_template), headers={"Content-Type":"application/javascript"})
@app.route("/mobile-blazer-swatch_mobile_blazer_noncore_swatch_mod__en_gb-vfljD38pu.js")
def blazer_js_en():
    return Response(render_template("js/mobile-blazer-swatch_mobile_blazer_noncore_swatch_mod__en_gb-vfljD38pu.js"), headers={"Content-Type":"application/javascript"})
@app.route("/mobile-blazer-swatch_mobile_blazer_searchbox_swatch_mod__ja-vflDLuTbH.js")
def searcher_js():
    host = "%s://%s"%("https" if request.is_secure else "http",request.host)
    host_noprotocol = request.host.removeprefix("https://").removeprefix("http://")
    jspath = "js/mobile-blazer-swatch_mobile_blazer_searchbox_swatch_mod__ja-vflDLuTbH.js"
    return Response(render_template(jspath,host=host,host_noprot=host_noprotocol),headers={"Content-Type":"application/javascript"})
@app.route("/mobile-blazer-swatch_mobile_blazer_pubsub_swatch_mod__ja-vflWARhYd.js")
def pubsub_js():
    protocol = "https" if secureserver else "http"
    HOST_NOHTTP = request.host.removeprefix("https://") if secureserver else request.host.removeprefix("http://")
    jspath = "js/mobile-blazer-swatch_mobile_blazer_pubsub_swatch_mod__ja-vflWARhYd.js"
    return Response(render_template(jspath,PROTOCOL=protocol,host_noprotocol=HOST_NOHTTP), headers={"Content-Type":"application/javascript"})
@app.route("/mobile-blazer-swatch_mobile_blazer_remote_swatch_mod__ja-vflwU69Ye.js")
def pair_js():
    jspath = "js/mobile-blazer-swatch_mobile_blazer_remote_swatch_mod__ja-vflwU69Ye.js"
    return Response(render_template(jspath),headers={"Content-Type":"application/javascript"})

@app.route("/watch")
@checkifajax
def watch():
    data = request.args
    video_id = data.get("v")
    CPN = data.get("cpn")
    cookies = request.cookies
    hl = cookies.get("hl",g.HL)
    gl = cookies.get("gl",g.GL)
    oauth_token = g.OAUTH_TOKEN
    GET_continuation = data.get("continuation") or None
    if CPN and not video_id:
        return Response(status=204)
    if not video_id:
        return abort(400)
    info = gdata.GetVideoInfo(video_id)
    if info:
        title        = info["title"]
        description  = info["description"]
        channel_name = info["channel_name"]
        duration     = info["duration"]
        upload_date  = info["upload_date"]
        view_count   = info["view_count"]
        likes        = info["likes"]
        channel_icon = info["channel_icon_url"]
        profile_url  = info["profile_url"]
    else:
        title = description = channel_name  = duration = upload_date = channel_icon = profile_url = ""
        view_count = likes = 0
    dislikes_num = funcmod.getDislikes(video_id)
    if not dislikes_num: dislikes_num = int("0")
    else: dislikes_num = int(dislikes_num)
    thumb = funcmod.getThumbnail(video_id)
    rating = float(funcmod.getRating(video_id))
    related,_ = innertube.RecommendedVideos(video_id,hl=hl,gl=gl,continuation_token=None,maxResults=15)
    ua = request.headers.get("User-Agent") or "-"
    next_url = None
    if debugmode:
        region = GET_REGION_UA(ua)
        regions = {"US":"America","EU":"Europe","JP":"Japan"}
        if debugmode:
            if IS_3DS(ua):
                print(f"{Fore.LIGHTGREEN_EX}[region]{Fore.RESET} reported User-Agent region: {regions.get(region,'unknown region')} ({region})")
    def _to_second(duration):
        if isinstance(duration,(int,float)):
            return int(duration)
        if not duration:
            return 0
        try:
            p = [int(x) for x in str(duration).split(":")]
            if len(p) == 3:
                h,m,s = p
                return h*3600 + m*60 + s
            if len(p) == 2:
                m,s = p
                return m*60+s
            return int(p[0])
        except (ValueError,TypeError):
            return 0
    duration_seconds = _to_second(duration)
    vpl_params_t = {
        "q": "tiny",
        "v": video_id,
    }
    vpl_params_s = {
        "q": "small",
        "v": video_id
    }
    SENT_MODEL = "unk"
    SENT_VENDOR = "UNKNOWN"
    if IS_3DS(ua):
        SENT_MODEL = "new3ds" if IS_NEW_3DS(ua) else "3ds"
        SENT_VENDOR = "NINTENDO"
    for p in (vpl_params_s,vpl_params_t):
        p["vendor"] = SENT_VENDOR
        p["model"] = SENT_MODEL
    videoplayback_small = "/videoplayback?" + urlencode(vpl_params_s)
    videoplayback_tiny = "/videoplayback?" + urlencode(vpl_params_t)
    ua = request.headers.get("User-Agent","-")
    json_r = {
        "content": {
            "allow_ratings": True,
            "rating": 5,
            "action_rate": 1,
            "sentiment_xsrf_token": "",
            "next_url": next_url,
            "video": {
                "title": title,
                "thumbnail_for_watch":thumb,
                "thumbnail_info": {
                    "url": thumb,
                    "width": 120,
                    "height": 190
                },
                "duration": duration,
                # fixes duration when paired with youtube tv
                "duration_seconds": duration_seconds,
                "ih": duration_seconds,
                "channel_icon_url": channel_icon,
                "url": f"/watch?v={video_id}",
                "public_name": channel_name,
                "profile_url": profile_url,
                "time_created_text": upload_date,
                "likes_num": likes,
                "dislikes_num": dislikes_num,
                "view_count": fmt_view(view_count),
                "description": description,
                "encrypted_id": video_id,
                "subscriber_count": "",
                "is_public": True,
                "rating": rating,
                "type": "video",
                "is_watch_later": False,
                "ad_content": {},
            },
            "player_data": {
                "playability": "PLAY_OK",
                "player_vars": {
                    "ttsurl": f"/timedtext",
                },
                "player_type": PLAYER_TYPE_3DS_HTML5FS if IS_3DS(ua) else PLAYER_TYPE_HTML5,
                "tracks": [
                    {
                        "format": "vtt",
                        "languageCode":"en",
                        "languageName":"English",
                        "kind": "track",
                        "label": "en",
                        "name":"English",
                        "id": "2",
                        "src": f"/timedtext?hl=en&gl=US&type=track",
                        "translationLanguage":"en",
                        "is_servable":True,
                        "is_default": True,
                        "is_translateable":False,
                        "fmt":"vtt",
                    },
                ],
                "fmt": "133/320x240/9/0/115",
                "itag": "133",
                "length_seconds": str(duration),
                "ih": duration,
                "allow_html5_ads": False,
                "delay": 0,
                "adaptive_fmts": f"type=video/mp4&itag=133&size=320x240&bitrate=450000&init=0-999&index=1000-1999",
                "allow_embed": False,
                "autoplay": True,
                "cc_load_policy": 1,
                "iv_load_policy": 1,
                "fmt_stream_map": f"133|videoplayback?v={video_id}",
                "url_encoded_fmt_stream_map": f"133|videoplayback?v={video_id}",
                "stream_url": videoplayback_tiny,
                "stream_sig": "None",
                "hq_stream_url": videoplayback_small,
                "hq_stream_sig": "None",
                "desktop_get_video_info": "",
                "playability_message": "hi",
                "ttsurl": f"/timedtext",
            },
            "ad_instream": None,
            "subscription_state": {
                "is_subscribed": False,
                "subscribe_url": f"/subscribe?action_subscribe=1",
                "unsubscribe_url": f"/subscribe?action_unsubscribe=0",
            },
            "should_prompt_merge_identity": False,
            "related_videos": related,
            "pyv_content": {
                "show_pyv_in_related": False,
            },
            "pyv_ping_url": "/pyv_ping?action_USELESS_parameter=1",
            "signed_in_username": "",
            "signed_in_email": "",
            "build_id": BUILD_ID,
            "conn": "wifi",
            "result": "ok",
            "timestamp": int(time.time()),
            "clientWidth": 320,
            "build_signature": BUILD_SIG
        }
    }
    if g.SIGNED_IN:
        json_r["signed_in_username"] = g.INFO["name"]
        json_r["signed_in_email"] = g.INFO["email"]
        json_r["content"]["sentiment_xsrf_token"] = get_xsrf("sentiment_xsrf_token","sentiment_xsrf_token")
    return json_response(json_r)

@app.get("/videoplayback")
def videoplayback():
    video = GetVideo()
    video.createviddir()
    data = request.args
    videoId = data.get("v","")
    cookies = request.cookies
    quality = data.get("q","tiny") # tiny->144p, small->240p, new3DS->360p
    hl = cookies.get("hl",getattr(g,"HL","en"))
    gl = cookies.get("gl",getattr(g,"GL","US"))
    models = ["3ds","new3ds"]
    vendors = ["NINTENDO"]
    model = data.get("model","unk")
    vendor = data.get("vendor","UNKNOWN")
    IS3DS = (vendor == "NINTENDO" and model in models)
    NEW3DS = model == "new3ds"
    OLD3DS = model == "3ds"
    if model not in models:
        model = "unk"
    if vendor not in vendors:
        vendor = "UNKNOWN"
    if debugmode:
        print(f"{Fore.GREEN}[playback]{Fore.RESET}: videoplayback::3DSCheck returned {str(IS3DS).lower()}")
        if IS3DS:
            print(f"{Fore.GREEN}[playback]{Fore.RESET}: videoplayback::OLD3DSCheck returned {str(OLD3DS).lower()}")
            print(f"{Fore.GREEN}[playback]{Fore.RESET}: videoplayback::NEW3DSCheck returned {str(NEW3DS).lower()}")
    try:
        if debugmode:
            print(f"{Fore.LIGHTYELLOW_EX}[vendor]{Fore.RESET} vendor: {vendor.lower().capitalize()}")
        if IS3DS:
            if OLD3DS:
                if debugmode:
                    print(f"{Fore.YELLOW}[model]{Fore.RESET} Model: Old3DS")
                    print(f"{Fore.GREEN}[playback]{Fore.RESET} Downloading and serving video...")
                # this loads videos slowly, but plays well on old 3DS systems
                # we only use fetchAndLoadStreamOnly_DLEncode and fetchAndLoadStreamOnly_New3DSOnly
                response = video.fetchAndLoadStreamOnly_DLEncode(hl,gl,videoId,quality)
                # HEADERS FIX
                # (i have no idea how this enables playback)
                response.headers["Cache-Control"] = "no-cache, no-store, no-transform"
                # i have no idea how to get the video, encode it so that it doesn't lag on an Old 3DS, and then return it without downloading
                # for now this is gonna take a lot for longer videos
            elif NEW3DS:
                if debugmode:
                    print(f"{Fore.YELLOW}[model]{Fore.RESET} Model: New3DS")
                    print(f"{Fore.GREEN}[playback]{Fore.RESET} Serving video from googlevideo CDN...")
                # this loads videos significantly faster, but plays very badly on old 3DS systems
                # only plays on New 3DS systems with overclocking enabled
                # im gonna assume overclocking is enabled by default on new 3DS systems when using YouTube
                response = video.fetchAndLoadStreamOnly_New3DSOnly(hl,gl,videoId,quality)
                # HEADERS FIX
                # (i have no idea how this enables playback)
                response.headers["Cache-Control"] = "no-cache, no-store, no-transform"
            else:
                if debugmode:
                    print(f"{Fore.YELLOW}[model]{Fore.RESET} Unknown device")
                    print(f"{Fore.GREEN}[playback]{Fore.RESET} Serving video from googlevideo CDN...")
                response = video.fetchAndLoadStreamOnly_New3DSOnly(hl,gl,videoId,quality)
            return response
        else:
            # non 3DS consoles can use this too and they should
            if debugmode:
                print(f"{Fore.YELLOW}[model]{Fore.RESET} Not a 3DS")
                print(f"{Fore.GREEN}[playback]{Fore.RESET} Serving video from googlevideo CDN...")
            response = video.fetchAndLoadStreamOnly_New3DSOnly(hl,gl,videoId,quality)
            return response
    except Exception as e:
        if debugmode:
            traceback.print_exc()
            print(f"{Fore.RED}[playback]{Fore.RESET} exception @ videoplayback:",e)
        return Response("failed to get video. Please try again.",status=500)

@app.route("/channel/<string:userId>/icon")
@app.route("/user/<string:userId>/icon")
@app.route("/topic/<string:userId>/icon")
def pfpproxy(userId):
    SIDEBAR_THUMB = {
        "UClgRkhTL3_hImCAmdLfDE4g":"thumb_movies_new.jpg",
        "UCYfdidRxbB8Qhf0Nx7ioOYw":"thumb_news.jpg",
        "UCOpNcN46UbXVtpKMrmU4Abg":"thumb_gaming.jpg",
        "UCEgdi0XIXXZ-qJOFPf4JSKw":"thumb_sports.jpg",
        "UC-9-kyTW8ZkZNDHQJ6FgpwQ":"thumb_music.jpg",
        "UC4R8DWoMoI7CAwX8_LjQHig":"thumb_live.png",
        "UCBR8-60-B28hp2BmDPdntcQ":"thumb_spotlight.png",
        "HCJYRSLjSb4y8": "thumb_topic.jpg",
        "UC3yA8nDwraeOfnYfBWun83g": "thumb_education.png",
        "SBAaOjE-GIlRI": "thumb_live.png",
        "HCtB5yQiZTr7Y": "thumb_topic.jpg",
        "HCLfhQGBROujg": "thumb_topic.jpg",
        "HCRgNMjm7t2M0": "thumb_topic.jpg",
        "HCxAJ-ON2kZuw": "thumb_topic.jpg",
        "HCVezXaU34vJk": "thumb_topic.jpg",
        "HCOJfFxLS-8g4": "thumb_topic.jpg",
        "HCMCTE41mELnQ": "thumb_topic.jpg",
        "UC1vGae2Q3oT5MkhhfW8lwjg": "thumb_topic.jpg",
    }
    FALLBACK = BASE/"static"/"images"/"1.png"
    if not userId:
        return send_file(FALLBACK)
    if userId in SIDEBAR_THUMB:
        filename = SIDEBAR_THUMB[userId]
        path = BASE/"static"/"images"/"topics"/"icons"/filename
        return send_file(path)
    valid = (re.search(CHANNEL_ID_RE,userId) or re.search(TOPIC_ID_RE,userId) or userId == "SBAaOjE-GIlRI")
    if not valid:
        return send_file(FALLBACK)
    try:
        initial = requests.get(f"https://www.youtube.com/channel/{userId}",timeout=20,cookies=CONSENT_COOKIES,headers={"User-Agent":API_USERAGENT})
        initial.raise_for_status()
    except requests.RequestException:
        return send_file(FALLBACK)
    url = None
    # try opengraph first
    html = BeautifulSoup(initial.text,"html.parser")
    og = html.find("meta",property="og:image")
    if og:
        url = og.get("content") or None
        if url:
            try:
                imgr = requests.get(url,timeout=20,headers={"User-Agent":API_USERAGENT},cookies=CONSENT_COOKIES)
            except requests.RequestException:
                return send_file(FALLBACK)
            if not imgr.ok:
                return send_file(FALLBACK)
            return Response(imgr.content,content_type="image/jpeg",status=200)
    if not url:
        match = re.search(r"https://yt3\.(?:ggpht|googleusercontent)\.com/[^\"]+",initial.text)
        if not match:
            return send_file(FALLBACK)
        url = match.group(0)
        url = re.sub(r"=s\d+-","=s48-",url)
        url = re.sub(r"https\:\/\/","http://",url)
        try:
            imgr = requests.get(url,timeout=20,cookies=CONSENT_COOKIES,headers={"User-Agent":API_USERAGENT})
            imgr.raise_for_status()
        except requests.RequestException:
            return send_file(FALLBACK)
        mime = imgr.headers.get("Content-Type","image/jpeg")
        return Response(imgr.content,status=200,content_type=mime)
    return send_file(FALLBACK)

# Sign in routes
@app.route("/vendor_signin/refresh",methods=["POST"])
def refreshOauth2():
    # already does this in before_request
    return abort(404)

@app.route("/vendor_signin/poll", methods=["POST"])
@limiter.limit("10 per 10 seconds;120 per minute")
def checkSignIn():
    if request.cookies.get("oauth_token") != None or request.cookies.get("refresh_token") != None:
        return abort(409)
    success = request.form.get("action_success","0") == "1"
    device_code = request.form.get("device_code") or None
    if not device_code:
        return json_response({"status":"error","message":"missing device code"})
    if ENABLE_DUMMY_SIGNIN and device_code == "DeviceCode":
        return json_response({"status":"pending","message":"dummy response, never authorizing"})
    result,token,refresh,status = oauth2.CheckAuthorization(device_code=device_code)
    policy = "Strict" if secureserver else "Lax"
    if result.get("status") == "success":
        response = json_response(result)
        response.set_cookie("oauth_token",token,httponly=True,secure=secureserver,samesite=policy,max_age=3600,path="/")
        response.set_cookie("refresh_token",refresh,httponly=True,secure=secureserver,samesite=policy,max_age=31536000,path="/")
        return response
    else:
        return json_response(result),status

@app.route("/vendor_signout")
@limiter.limit("5 per minute")
def signout():
    cookies = request.cookies
    oauth_token = cookies.get("oauth_token")
    refresh_token = cookies.get("refresh_token")
    vendor = request.args.get("vendor","NINTENDO")
    model = request.args.get("model","3ds")
    policy = "Strict" if secureserver else "Lax"
    if refresh_token:
        try:
            oauth2.RevokeToken(refresh_token)
        except:
            pass
    elif oauth_token:
        try:
            oauth2.RevokeToken(oauth_token)
        except:
            pass
    resp = redirect("/")
    resp.delete_cookie("oauth_token",path="/",httponly=True,samesite=policy,secure=secureserver)
    resp.delete_cookie("refresh_token",path="/",httponly=True,samesite=policy,secure=secureserver)
    resp.delete_cookie("session",path="/",httponly=True,samesite=policy,secure=secureserver)
    g.DELETE_AUTH = True
    g.SIGNED_IN = False
    return resp

@app.route("/vendor_signin",methods=["GET","POST"])
def signin_vendor():
    success = request.args.get("action_success","0") == "1"
    device_code = request.form.get("device_code")
    vendor = request.args.get("vendor","NINTENDO")
    model = request.args.get("model","3ds")
    pg = "signin.html"
    sl_og2 = "https://accounts.google.com/ServiceLogin?passive=true\u0026uilel=3\u0026hl=en\u0026continue=http%3A%2F%2Fm.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Dm%26feature%3Dblazerbootstrap%26hl%3Dja%26next%3D_NEXT_URL_PLACEHOLDER_\u0026service=youtube\u0026ltmpl=mobile"
    #if (not request.is_secure) and (not debugmode):
    #    ret = Response(render_template("signin_stub.html",reason="Request isn't secure (HTTPS)."),status=406,headers={"Content-Type":"text/html;charset=UTF-8"})
    if success and device_code is not None:
        pg = "signin_success.html"
        name = g.INFO["name"]
        pfp = g.INFO["photo"]
        pfp_path = pfp
        if not pfp:
            pfp_path = "/static/images/1.png"
        else:
            pfp_path = pfp_path.replace("https://","http://")
        if not name:
            name = "undefined"
        ret = Response(render_template(pg,username=name,profileImg=pfp_path),status=200,headers={"Content-Type":"text/html;charset=UTF-8"})
    else:
        if request.cookies.get("oauth_token") != None or request.cookies.get("refresh_token") != None:
            return abort(409)
        if not SIGNINDISABLED:
            DUMMY_FWD_HDR = [('Pragma', 'no-cache'), ('Expires', 'Mon, 01 Jan 1990 00:00:00 GMT'), ('Cache-Control', 'no-cache, no-store, max-age=0, must-revalidate'), ('Content-Type', 'application/json; charset=utf-8')]
            DUMMY_STATUSCD = 200
            DUMMY_RESPONSECONTENT = b'{\n  "device_code": "DeviceCode",\n  "user_code": "123-456-7890",\n  "expires_in": 1800,\n  "interval": 5,\n  "verification_url": "https://www.youtube.com/pair"\n}'
            if ENABLE_DUMMY_SIGNIN:
                fwd_headers = DUMMY_FWD_HDR
                statuscd = DUMMY_STATUSCD
                responseContent = DUMMY_RESPONSECONTENT
            else:
                _headers = request.headers
                responseContent,statuscd,fwd_headers = oauth2.GetLoginCode(headers=_headers)
                if statuscd != 200:
                    print(f"status code != 200, expect issues! ({statuscd})")
            fwd_hdr = dict(fwd_headers)
            fwd_hdr["Content-Type"] = "text/html;charset=UTF-8"
            fwd_headers = list(fwd_hdr.items())
            responseContent = json.loads(responseContent)
            actcode = responseContent["user_code"] or None
            acturl = responseContent["verification_url"] or "https://www.youtube.com/activate"
            if acturl == "https://www.google.com/device":
                # okay, not gonna lie, youtube.com/activate is better than google.com/device, and they both do the same thing for YouTube on TV activation.
                acturl = "https://www.youtube.com/activate"
            act_ttl = int(responseContent["expires_in"])
            actttl_mins = (int(responseContent["expires_in"]) / 60 or int("0"))
            actdevicecd = responseContent["device_code"]
            if not ENABLE_DUMMY_SIGNIN:
                if debugmode:
                    print("Visit %s and enter %s, code expires in %d minutes (%s seconds)"%(acturl,actcode,actttl_mins,act_ttl))
            else:
                print("Dummy response was sent. You can't activate the device")
            ret = Response(render_template(pg,ACT_cd=actcode,ACT_url=acturl,ACT_devcd=actdevicecd,ACT_TTL=act_ttl),status=statuscd,headers=fwd_headers)
        else:
            pg = "signin_stub.html"
            reason = ""
            if not SIGNINDISABLED_REASON:
                reason = "Sign-Ins are disabled by an administrator."
            else:
                reason = SIGNINDISABLED_REASON
            ret = Response(render_template(pg,reason=reason),status=501,headers={"Content-Type": "text/html;charset=UTF-8"})
    return ret

@app.route("/vendor_signin/required")
def requires_signin():
    #if g.SIGNED_IN:
    #    return redirect("/")
    data = request.args
    argfrom = data.get("from","type_unk")
    hl = getattr(g,"HL","en") or "en"
    mesg = {
        "river": {
            "en": "To view personalized videos for you, you must sign in.",
        },
        "history": {
            "en": "To view your watch history, you must sign in.",
        },
        "type_WL": {
            "en": "To add videos to your watch later playlist, you must sign in."
        },
        "type_LL": {
            "en": "To like videos, you must sign in."
        },
        "type_unk": {
            "en": "To perform this action, you must<BR>be signed in.",
        },
    }
    reason = mesg.get(argfrom,mesg["type_unk"])
    fromreason = reason.get(hl,reason.get("en"))
    return Response(render_template("requires_signin.html",redirectBody=fromreason),status=200,headers={"Content-Type":"text/html; charset=utf-8"})
# End authentication routes

@app.route("/<string:channeltype>/<string:user_id>",strict_slashes=False)
@app.route("/<string:channeltype>/<string:user_id>/<string:subpath>",strict_slashes=False)
@app.route("/my_channel")
@checkifajax
def userchannel(channeltype="channel",user_id=None,subpath=None):
    if channeltype not in ["topic","user","channel"]:
        return abort(404)
    if not user_id:
        return abort(404)
    valid = (re.search(CHANNEL_ID_RE,user_id) or re.search(TOPIC_ID_RE,user_id) or user_id == "SBAaOjE-GIlRI")
    if not valid:
        return abort(404)
    chinf = apicombo.GetChannelInfoCombo(user_id)
    banner = funcmod.fetchUserBanner(user_id)
    if not banner:
        banner = None
    uploadcount = str(chinf.get("upload_count",0)).upper().strip()
    displayuploads = 0
    if "K" in uploadcount:
        displayuploads = int(float(uploadcount.replace("K","").replace(",",""))*1000)
    elif "M" in uploadcount:
        displayuploads = int(float(uploadcount.replace("M","").replace(",",""))*1000000)
    else:
        try:
            displayuploads = int(float(uploadcount.replace(",","")) or 0)
        except ValueError:
            displayuploads = 0
    totalviews = str(chinf.get("total_views",0)).upper().strip()
    displayviews = 0
    kwmap = {
        "UC-9-kyTW8ZkZNDHQJ6FgpwQ": "music",
        "UCEgdi0XIXXZ-qJOFPf4JSKw": "sports",
        "UCOpNcN46UbXVtpKMrmU4Abg": "gaming",
        "UCYfdidRxbB8Qhf0Nx7ioOYw": "news",
        "UClgRkhTL3_hImCAmdLfDE4g": "movies",
        "SBAaOjE-GIlRI": "live",
        "HCJYRSLjSb4y8": "activism",
        "HCtB5yQiZTr7Y": "pets",
        "HCLfhQGBROujg": "autos",
        "HCRgNMjm7t2M0": "comedy",
        "HCxAJ-ON2kZuw": "entertainment",
        "HCVezXaU34vJk": "people",
        "HCOJfFxLS-8g4": "technology",
        "HCMCTE41mELnQ": "travel",
        "UC3yA8nDwraeOfnYfBWun83g": "education"
    }
    if "K" in totalviews:
        displayviews = int(float(totalviews.replace("K","").replace(",",""))*1000)
    elif "M" in totalviews:
        displayviews = int(float(totalviews.replace("M","").replace(",",""))*1000000)
    elif "B" in totalviews:
        displayviews = int(float(totalviews.replace("B","").replace(",",""))*1000000000)
    elif "T" in totalviews:
        displayviews = int(float(totalviews.replace("T","").replace(",",""))*1000000000000)
    else:
        displayviews =int(float(totalviews.replace(",","")) or 0)
    json_r = {}
    countrylist = METADIR/"country.json"
    showncountry = chinf.get("country","")
    if countrylist.is_file():
        with open(countrylist,"r",encoding="utf-8") as f:
            countryJSON = json.load(f)
        showncountry = next((n for c,n in countryJSON if c == showncountry),showncountry)
    cookies = request.cookies
    hl = cookies.get("hl") or g.HL
    gl = cookies.get("gl") or g.GL
    if channeltype == "topic":
        kw = kwmap.get(user_id) or "music"
        home,_,_ = innertube.GetTopicVideos(kw,continuation_token=None,hl=hl,gl=gl)
        home_title = kw.capitalize()
    else:
        home,_ = innertube.GetChannelVideos(user_id,hl,gl)
        home_title = "Recent uploads"
    featured_shelves = {}
    home_videos = []
    seen = set()
    for v in home:
        vid = v.get("encrypted_id") or v.get("video_id")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        if channeltype == "topic":
            appendvideos = youtubeiUtils.flat_topic_video(v)
        else:
            appendvideos = youtubeiUtils.flat_item_tab(v)
        home_videos.append(appendvideos)
    featured_shelves = {
        "shelf_groups": [
            [
                make_shelf(home_title,home_videos[:10])
            ]
        ],
        "next_url": None
    }
    show_subscribe_button = True
    is_subscribed = False
    subscribe_xsrf_token = xsrf_token = ""
    if g.SIGNED_IN:
        oauth_token = g.OAUTH_TOKEN
        xsrf_token = get_xsrf("xsrf_token","xsrf_token")
        subscribe_xsrf_token = get_xsrf("subscribe_xsrf_token","subscribe_xsrf_token")
        is_subscribed = innertube.IsSubscribed(oauth_token,user_id)
        if g.INFO:
            if g.INFO["haschannel"]:
              if g.INFO["handle"]:
                if innertube.GetChannelIDFromHandle(g.INFO["handle"]) == user_id:
                    show_subscribe_button = False
    auto_generated = False
    if chinf.get("auto_generated"):
        auto_generated = True
    elif user_id in GENERATED_CHANNELS:
        auto_generated = True
    json_r = {
        "content": {
            "owner_profile": {
                "about_me": chinf.get("description", ""),
                "description": chinf.get("description", ""),
                "auto_generated": auto_generated,
                "country": showncountry,
                "custom_url_items": [],
                "linked_sites": [],
                "hometown": None,
                "age": None,
                "image_url": f"/{channeltype}/{user_id}/icon",
                "joined_date": chinf.get("joined_date", ""),
                "profile_url": f"/{channeltype}/{user_id}",
                "public_name": chinf.get("real_name", user_id),
                "channel_subscriber_count": int(chinf.get("subscribers","0")),
                "subscriber_count": chinf.get("subscribers", "0"),
                "title": chinf.get("channel_name", user_id),
                "upload_count": displayuploads,
                "video_view_count": displayviews,
                "url": f"/channel/{user_id}"
            },
            "subscribe_xsrf_token": subscribe_xsrf_token,
            "subscription_button_data": {
                "has_available_offer": False,
                "offer_unavailable": False,
                "render_as_paid": False,
                "channel_external_id": user_id,
            },
            "subscription_state": {
                "is_subscribed": is_subscribed,
                "subscribe_url": {
                    "url": f"/subscribe?action_subscribe=1",
                    "channel_id": user_id
                },
                # does this one even get read???
                "unsubscribe_url": {
                   "url": f"/subscribe?action_subscribe=0",
                   "channel_id": user_id
                },
                "show_button": show_subscribe_button,
            },
            "category_link": "Hi",
            "category_rec_count": 2,
            "category_title": "Null",
            "items": [],
            "banner_images": {
                "banner_image": banner,
                "banner_image_hd": banner,
            },
            "tab_settings": {
                "available_tabs": [
                    {
                        "id": "100",
                        "title": "",
                        "path": "featured"
                    },
                    {
                        "id": "102",
                        "title": "Feed",
                        "path": "feed"
                    },
                    {
                        "id": "101",
                        "title": "Videos",
                        "path": "videos",
                    },
                    {
                        "id": "301",
                        "title": "",
                        "path": ""
                    },
                ],
                "current_tab_id": 100,
            },
            "xsrf_token": xsrf_token,
            "channel_comments": {
                "comment_enabled": False,
                "comment_url": "",
                "xsrf_token": xsrf_token,
                "channel_distiller_comments": "",
            },
            "featured_video": chinf.get("featured"),
            "featured_shelves": featured_shelves,
            "signed_in_username": "",
            "signed_in_email": "",
            "build_id": BUILD_ID,
            "conn": "wifi",
            "result": "ok",
            "timestamp": int(time.time()),
            "build_signature": BUILD_SIG
        }
    }
    if subpath is not None:
        allow = ["movies","videos","about","feed","featured"]
        if subpath == "videos":
            continuation_token = request.args.get("continuation") or None
            if channeltype == "topic":
                # topics don't support continuation tokens
                kw = kwmap.get(user_id) or "music"
                continuation = None
                videos,_,_ = innertube.GetTopicVideos(kw,hl=hl,gl=gl,continuation_token=None)
            else:
                videos,continuation = innertube.GetChannelVideos(channelId=user_id,hl=hl,gl=gl,continuation_token=continuation_token)
            next_url = None
            curpage = request.args.get("p","1")
            try:
                curpage = int(curpage)
            except ValueError:
                curpage = 1
            nextpage = curpage+1
            if continuation is not None:
                next_url = f"/next_channel_continuation?" + urlencode({
                    "id": user_id,
                    "p": nextpage,
                    "continuation": continuation,
                    "ajax": "1"
                })
            seen = set()
            video_items = []
            for v in videos:
                vid = v.get("encrypted_id") or v.get("video_id")
                if vid in seen:
                    continue
                seen.add(vid)
                if channeltype == "topic":
                    appendvideos = youtubeiUtils.flat_topic_video(v)
                else:
                    appendvideos = youtubeiUtils.flat_item_tab(v)
                video_items.append(appendvideos)
            json_r = {
                "content": {
                    "videos": {
                        "view_type": "grid",
                        "items": video_items,
                        "next_url": next_url,
                    },
                    "playlists": None,
                    "events": None,
                    "liked_videos": None,
                    "liked_playlists": None,
                    "episodes": None,
                    "seasons": None,
                },
                "signed_in_username": "",
                "signed_in_email": "",
                "result": "ok",
                "conn": "wifi",
                "timestamp": int(time.time()),
                "build_id": BUILD_ID,
                "build_signature": BUILD_SIG
            }
        elif subpath == "feed":
            json_r = {
                "content": {
                    "recent_activities": {
                        "posts": None,
                        "next_url": None,
                    },
                    "channel_comments": {
                        "posts": None,
                        "next_url": None,
                    },
                    "recent_posts": {
                        "posts": None,
                        "next_url": None,
                    },
                    "xsrf_token": "aa",
                },
                "signed_in_username": "",
                "signed_in_email": "",
                "result": "ok",
                "conn": "wifi",
                "timestamp": int(time.time()),
                "build_id": BUILD_ID,
                "build_signature": BUILD_SIG
            }
        elif subpath == "posts":
            json_r = {
                "content": {
                    "channel_comments": {
                        "posts": None,
                        "next_url": None,
                        "comment_enabled": True,
                    },
                    "xsrf_token": "aa",
                },
                "signed_in_username": "",
                "signed_in_email": "",
                "build_id": BUILD_ID,
                "conn": "wifi",
                "result": "ok",
                "timestamp": int(time.time()),
                "build_signature": BUILD_SIG
            }
        elif subpath == "icon":
            ret = pfpproxy(user_id)
            return ret
    if g.SIGNED_IN:
        json_r["signed_in_username"] = g.INFO["name"]
        json_r["signed_in_email"] = g.INFO["email"]
    return json_response(json_r)

@app.route("/channels",strict_slashes=False)
@app.route("/channels/<string:subpath>",strict_slashes=False)
@app.route("/subscription_manager")
@checkifajax
def channelfeed(subpath=None):
    data = request.args
    cookies = request.cookies
    hl = cookies.get("hl") or g.HL
    gl = cookies.get("gl") or g.GL
    json_r_footer = {
        "result": "ok",
        "signed_in_username": "",
        "signed_in_email": "",
        "conn": "wifi",
        "timestamp": int(time.time()),
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
    }
    json_r = {}
    if subpath == "manager" or request.path == "/subscription_manager":
        if not g.SIGNED_IN:
            return redirect("/vendor_signin/required?from=subscriptions")
        oauth_token = g.OAUTH_TOKEN
        raw = innertube.MySubscriptions(oauth_token,hl=hl,gl=gl)
        json_r = {
            "content": {
                "title": "Manage subscriptions",
                "show_all_categories_link": False,
                "channels": [flat_channel(c) for c in raw],
                "xsrf_token": "aaa",
                "next_url": None,
            }
        }
    elif subpath == "browser":
        oauth_token = g.OAUTH_TOKEN
        if not oauth_token:
            return redirect("/vendor_signin/required?from=subscriptions")
        raw = gdata.RecommendedChannels(hl=hl,gl=gl,oauth_token=oauth_token,maxResults=25)
        json_r = {
            "content": {
                "title": "Browse channels",
                "show_all_categories_link": False,
                "channels": [flat_channel(c) for c in raw],
                "xsrf_token": "aaa",
                "next_url": None,
            }
        }
    if g.SIGNED_IN:
        json_r_footer["signed_in_email"] = g.INFO["email"]
        json_r_footer["signed_in_username"] = g.INFO["name"]
    if not json_r.get("content"):
        json_r_footer["errors"] = ["Couldn't fetch feed. Please try again later."]
        json_r_footer["result"] = "error"
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/subscribe",methods=["POST"])
@require_xsrf("xsrf_token") # doesn't even consume subscribe_xsrf_token
@checkifajax_POST
def subscribe():
    data = request.form
    GET_data = request.args
    if not g.SIGNED_IN: return redirect("/vendor_signin/required?from=action_subscribe")
    oauth_token = g.OAUTH_TOKEN
    json_r = {
        "content": {}
    }
    json_r_footer = {
        "errors": [],
        "signed_in_username": "",
        "signed_in_email": "",
        "conn": "wifi",
        "timestamp": int(time.time()),
        "result": "ok",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
    }
    action_subscribe = GET_data.get("action_subscribe","0") == "1"
    action_unsubscribe = GET_data.get("action_unsubscribe","0") == "1"
    channelId = data.get("channel_id","")
    valid = (re.search(CHANNEL_ID_RE,channelId) or re.search(TOPIC_ID_RE,channelId) or channelId == "SBAaOjE-GIlRI")
    if not valid:
        json_r_footer["errors"] = ["Couldn't subscribe to channel. Please try again."]
        json_r_footer["result"] = "error"
        return json_response(json_r_footer)
    if g.INFO:
        if g.INFO["haschannel"]:
            if g.INFO["handle"]:
              if innertube.GetChannelIDFromHandle(g.INFO["handle"]) == channelId:
                  json_r_footer["content"] = {
                        "subscription_state": {
                            "is_subscribed": False,
                            "show_button": False,
                            "subscribe_url": {
                                "url": "/subscribe?action_subscribe=1",
                                "channel_id": channelId
                            },
                            "unsubscribe_url": {
                                "url": "/subscribe?action_unsubscribe=1",
                                "channel_id": channelId,
                            },
                        }
                  }
                  json_r_footer["errors"] = ["You can't subscribe to yourself."]
                  json_r_footer["result"] = "error"
                  return json_response(json_r_footer)
    state = innertube.IsSubscribed(oauth_token,channelId)
    if state is None:
        json_r_footer["result"] = "error"
        json_r_footer["errors"] = ["Couldn't subscribe to channel. Please try again."]
        return json_response(json_r_footer)
    subscribing = not state
    ret = innertube.UnsubscribeOrSubscribe(oauth_token,channelId,subscribing)
    if not ret:
        json_r["content"] = {}
        json_r_footer["result"] = "error"
        json_r_footer["errors"] = ["Couldn't subscribe to channel. Please try again."]
    else:
        json_r["content"] = {
            "subscription_state": {
                "is_subscribed": subscribing,
                "show_button": True,
                "subscribe_url": {
                    "url": "/subscribe?action_subscribe=1",
                    "channel_id": channelId
                },
                # does this one even get read??
                "unsubscribe_url": {
                    "url": "/subscribe?action_unsubscribe=1",
                    "channel_id": channelId,
                },
            }
        }
    if g.INFO["name"]:
        json_r_footer["signed_in_username"] = g.INFO["name"]
    if g.INFO["email"]:
        json_r_footer["signed_in_email"] = g.INFO["email"]
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/next_channel_continuation",methods=["GET"])
@checkifajax
def nextChannelContinuation():
    data = request.args
    cookies = request.cookies
    continuation_token = data.get("continuation") or None
    user_id = unquote(data.get("id",""))
    if not continuation_token or not user_id:
        return "",412
    try:
        continuation_token = unquote(continuation_token)
    except:
        pass
    hl = cookies.get("hl") or g.HL
    gl = cookies.get("gl") or g.GL
    videos,continuation = innertube.GetChannelVideos(channelId=user_id,hl=hl,gl=gl,continuation_token=continuation_token)
    next_url = None
    curpage = data.get("p","1")
    try:
        curpage = int(curpage)
    except ValueError:
        curpage = 1
    try:
        continuation = unquote(continuation)
    except:
        pass
    nextpage = curpage+1
    json_r = {
        "content": {
            "videos": {
                "view_type": "grid",
                "items": [],
                "next_url": None,
            }
        },
        "signed_in_username": "",
        "signed_in_email": "",
        "result": "ok",
        "conn": "wifi",
        "timestamp": int(time.time()),
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG
    }
    if continuation is not None:
        next_url = f"/next_channel_continuation?" + urlencode({
            "id": user_id,
            "p": nextpage,
            "continuation": continuation,
            "ajax": "1"
        })
        json_r = {
            "content": {
                "videos": {
                    "view_type": "grid",
                    "items": [youtubeiUtils.flat_item_tab(v) for v in videos],
                    "next_url": next_url,
                },
                "playlists": None,
                "events": None,
                "liked_videos": None,
                "liked_playlists": None,
                "episodes": None,
                "seasons": None,
            },
            "signed_in_username": "",
            "signed_in_email": "",
            "result": "ok",
            "conn": "wifi",
            "timestamp": int(time.time()),
            "build_id": BUILD_ID,
            "build_signature": BUILD_SIG
        }
    if g.SIGNED_IN:
        json_r["signed_in_email"] = g.INFO["email"]
        json_r["signed_in_username"] = g.INFO["name"]
    return json_r

@app.route("/results")
@checkifajax
def search_results():
    query = request.args.get("q") or request.args.get("search_query", "")
    page = request.args.get("p","1")
    action_corrected = request.args.get("action_corrected","0") == "1"
    try:
        page = int(page)
    except ValueError:
        page = 1
    continuation = None
    continuation_token = request.args.get("continuation","")
    next_url = None
    if not query:
        json_r = {
            "result": "error",
            "signed_in_username": "",
            "signed_in_email": "",
            "build_id": BUILD_ID,
            "build_signature": BUILD_SIG,
            "timestamp": int(time.time()),
            "conn": "wifi",
        }
        if g.SIGNED_IN:
            json_r["signed_in_email"] = g.INFO["email"]
            json_r["signed_in_username"] = g.INFO["name"]
        return json_response(json_r)
    search_type = request.args.get("search_type", "search_all")
    search_sort = request.args.get("search_sort", "relevance")
    correction = None
    results = []
    def did_you_mean_item(originalQuery,newquery):
        display_query = escape(newquery)
        urlquery = quote(newquery,safe="")
        searchcorrectionhtml = render_template("components/search_correction.html",urlquery=urlquery,display_query=display_query)
        return {
            "corrected_query": newquery,
            "original_query": originalQuery,
            "corrected_html": searchcorrectionhtml,
            "from_escape_hatch": False,
        }
    def video_item(v):
        author = v["author"]
        ch_id = v["channel_id"]
        video_id = v["video_id"]
        thumb_final = funcmod.getThumbnail(video_id)
        return {
            "content_type": 500,
            "content_item": {
                "video_id": v["video_id"],
                "title": v["title"],
                "short_byline": author,
                "byline": author,
                "public_name": author,
                "channel_name": author,
                "owner": {"display_name": author, "href": f"/channel/{ch_id}"},
                "channel": {"title": author, "public_name": author, "url": f"/channel/{ch_id}"},
                "duration": v["duration"],
                "view_count": fmt_view(v["view_count"]),
                "thumbnail_info": {
                    "url": thumb_final,
                },
                "watch_link": f"/watch?v={v['video_id']}",
            }
        }
    def channel_item(c):
        thumb = c["thumbnail"]
        return {
            "content_type": 505,
            "content_item": {
                "url": f"/channel/{c['channel_id']}",
                "title": c["title"],
                "public_name": c["title"],
                "thumbnail": f'<img src="{thumb}" width="60" height="60" style="border:0;margin:0px;">',
                "image_url": thumb,
                "video_count": c["video_count"],
                "subscriber_count": c["subscriber_count"],
            }
        }
    def playlist_item(p):
        return {
            "content_type": 501,
            "content_item": {
                "playlist_id": p["playlist_id"],
                "title": p["title"],
                "name": p["title"],
                "url": f"/playlist?list={p['playlist_id']}",
                "is_public": True,
                "is_watch_later": False,
                "thumbs_info": [
                    {
                        "url": p["thumbnail"],
                        "width": 120,
                        "height": 90,
                    }
                ],
                "video_count": p["video_count"],
                "display_name": p["owner"],
                "owner": {
                    "display_name": p["owner"],
                }
            }
        }
    try:
        if search_type == "search_users":
            channels,continuation,correction = innertube.ChannelSearch(query,limit=15,continuation_token=continuation_token)
            video_count = gdata.GetVideoCountBatch([c["channel_id"] for c in channels])
            for c in channels:
                c["video_count"] = video_count.get(c["channel_id"],0)
                results.append(channel_item(c))
        elif search_type == "search_playlists":
            playlists,continuation,correction = innertube.PlaylistSearch(query,limit=15,continuation_token=continuation_token)
            for p in playlists:
                results.append(playlist_item(p))
        else: # search_all
            seen = set()
            videos,continuation,correction = innertube.VideoSearch(query,order=search_sort,limit=15,continuation_token=continuation_token)
            if not continuation_token:
                channels,_,_ = innertube.ChannelSearch(query,limit=3)
                video_count = gdata.GetVideoCountBatch([c["channel_id"] for c in channels])
                for c in channels:
                    c["video_count"] = video_count.get(c["channel_id"],0)
                    results.append(channel_item(c))
                    ch_videos = [v for v in videos if v["channel_id"] == c["channel_id"]][:3]
                    for v in ch_videos:
                        seen.add(v["video_id"])
                        results.append(video_item(v))
                playlists,_,_ = innertube.PlaylistSearch(query,limit=2)
                for p in playlists:
                    results.append(playlist_item(p))
            for v in videos:
                if v["video_id"] in seen:
                    continue
                results.append(video_item(v))
    except Exception as ex:
        print(f"[search] {ex}")
    if continuation:
        next_url = f"/results?" + urlencode({
            "q": query,
            "p": page+1,
            "search_type": search_type,
            "search_sort": search_sort,
            "continuation": continuation
        })
    json_r = {
        "content": {
            "search_results": results,
            "search_type": search_type,
            "query": query,
            "next_url": next_url,
            "spell_correction": None,
        },
        "result": "ok",
        "build_signature": BUILD_SIG,
        "timestamp": int(time.time()),
        "signed_in_username":"",
        "signed_in_email":"",
        "conn": "wifi",
        "build_id":BUILD_ID
    }
    if correction:
        json_r["content"]["spell_correction"] = did_you_mean_item(originalQuery=query,newquery=correction)
    if g.SIGNED_IN:
        json_r["signed_in_email"] = g.INFO["email"]
        json_r["signed_in_username"] = g.INFO["name"]
    return json_response(json_r)

@app.route("/select_site")
@checkifajax
def select_site():
    data = request.args
    cookies = request.cookies
    action_language = data.get("action_language","0") == "1"
    action_country  = data.get("action_country","0") == "1"
    safe_mode = cookies.get("safety_mode","0") == "1"
    json_r = {}
    if action_language:
        languagespath = METADIR/"language.json"
        SUPPORTED_LANGUAGES = [
            ["en","English"]
        ]
        if languagespath.is_file():
            with open(languagespath,"r",encoding="utf-8") as f:
                SUPPORTED_LANGUAGES = json.load(f)
        token = get_xsrf("xsrf_token","xsrf_token")
        json_r = {
            "content": {
                "supported_languages": SUPPORTED_LANGUAGES,
                "xsrf_token": token,
            }
        }
    elif action_country:
        countryspath = METADIR/"country.json"
        SUPPORTED_COUNTRIES = [
            ["US","America"]
        ]
        if countryspath.is_file():
            with open(countryspath,"r",encoding="utf-8") as f:
                SUPPORTED_COUNTRIES = json.load(f)
        token = get_xsrf('xsrf_token','xsrf_token')
        json_r = {
            "content": {
                "supported_countries": SUPPORTED_COUNTRIES,
                "xsrf_token": token,
            }
        }
    else:
        ua = request.headers.get("User-Agent","-")
        show_identity_merge = show_identity_revert = not IS_3DS(ua)
        json_r = {
            "content": {
                "identity_revert_label": "Unlink Account",
                "show_identity_merge": show_identity_merge, # shows a link account to Google+, too bad its not a thing anymore
                "show_identity_revert": show_identity_revert, # same as above but unlinks instead
                "version": BUILD_ID,
                "safety_mode_enabled": safe_mode,
                "set_safety_mode_xsrf_token": get_xsrf('set_safety_mode_xsrf_token','set_safety_mode_xsrf_token')
            },
        }
    json_r_footer = {
        "result": "ok",
        "signed_in_username": "",
        "signed_in_email": "",
        "conn": "wifi",
        "build_signature": BUILD_SIG,
        "build_id": BUILD_ID,
        "timestamp": int(time.time())
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_username"] = g.INFO["name"]
        json_r_footer["signed_in_email"] = g.INFO["email"]
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/picker",methods=["POST"])
def picker():
    data = request.args
    postdata = request.form
    cookiepolicy = "Strict" if secureserver else "Lax"
    update_language = data.get("action_update_language","0")
    update_country  = data.get("persist_gl","0")
    recv = postdata.get("session_token")
    stor = session.get('xsrf_token')
    if not recv or not stor:
        if debugmode:
            print(f"{Fore.RED}[error]{Fore.RESET} either the received token or stored tokens are missing")
        return abort(403)
    if not hmac.compare_digest(recv,stor):
        if debugmode:
            print(f"{Fore.RED}[error]{Fore.RESET} XSRF token digest doesn't match")
        return abort(403)
    if debugmode:
        print(f"{Fore.BLUE}[info]{Fore.RESET} XSRF token check passed for picker")
    try:
        update_language = bool(int(update_language))
    except (TypeError,ValueError):
        update_language = False
    try:
        update_country = bool(int(update_country))
    except (TypeError,ValueError):
        update_country = False
    if update_language:
        hl = postdata.get("hl","en")
        resp = redirect("/")
        g.HL = hl
        resp.set_cookie("hl",hl,samesite=cookiepolicy,httponly=False,path="/",secure=secureserver)
        return resp
    elif update_country:
        gl = postdata.get("gl","US")
        resp = redirect("/")
        g.GL = gl
        resp.set_cookie("gl",gl,samesite=cookiepolicy,httponly=False,path="/",secure=secureserver)
        return resp
    return redirect("/")

@app.route("/playlist")
@app.route("/my_favorites")
@app.route("/my_watch_later_videos")
@checkifajax
def playlists():
    data = request.args
    listId = data.get("list")
    others = ["WL","LL","FL","SS","YS"] #watch later, liked videos, liked videos again, "sounds from shorts", "saved shorts"
    json_r = {}
    cookies = request.cookies
    hl = g.HL or cookies.get("hl","en")
    gl = g.GL or cookies.get("gl","US")
    page = data.get("p","1")
    try:
        count = int(data.get("count","0"))
    except (TypeError,ValueError):
        count = 0
    try:
        page = int(page)
    except (TypeError,ValueError):
        page = 1
    nextPage = page+1
    continuation_token = data.get("continuation") or None
    def getNextUrl(listId,continuation=None,page=1,totalVideos=0):
        if not continuation:
            return None
        param = {
            "list": listId,
            "p": page,
            "continuation": unquote(continuation),
            "count": totalVideos
        }
        return f"/playlist?" + urlencode(param)
    def get_playlist_length(plID=None):
        if not plID:
            return 0
        ret = innertube.GetPlaylists(oauth_token,hl=hl,gl=gl).get(plID,{}).get("video_count",0)
        return ret
    if listId in others or request.path in ["/my_watch_later_videos","/my_favorites"]:
        oauth_token = g.OAUTH_TOKEN or cookies.get("oauth_token")
        if listId == "LL" or listId == "FL" or request.path == "/my_favorites":
            if not g.SIGNED_IN:
                return redirect("/vendor_signin/required?from=list_LL")
            LL,continuation = innertube.Favorites(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
            count += len(LL)
            next_url = getNextUrl(listId="LL",continuation=continuation,page=nextPage,totalVideos=count)
            json_r = {
                "content": {
                    "public_name": "Favorites",
                    "channel_url": None,
                    "manage_playlist_xsrf_token": get_xsrf('manage_playlist_xsrf_token','manage_playlist_xsrf_token'),
                    "is_owner_viewing": False,
                    "reversed": False,
                    "next_url": next_url,
                    "playlist": {
                        "encrypted_id": "LL",
                        "full_encrypted_id": "LL",
                        "title": "Favorites",
                        "name": "Favorites",
                        "type": "LL",
                        "video_count": count,
                        "description": "Liked videos"
                    },
                    "videos": [youtubeiUtils.flat_playlist_item(v) for v in LL]
                }
            }
        elif listId == "WL" or request.path == "/my_watch_later_videos":
            if not g.SIGNED_IN:
                return redirect("/vendor_signin/required?from=list_WL")
            WL,continuation = innertube.WatchLater(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
            wl_count = get_playlist_length("WL")
            next_url = getNextUrl(listId="WL",continuation=continuation,page=nextPage,totalVideos=wl_count)
            json_r = {
                "content": {
                    "public_name": "Watch Later",
                    "channel_url": None,
                    "manage_playlist_xsrf_token": get_xsrf('manage_playlist_xsrf_token','manage_playlist_xsrf_token'),
                    "is_owner_viewing": True,
                    "reversed": False,
                    "next_url": next_url,
                    "playlist": {
                        "encrypted_id": "WL",
                        "full_encrypted_id": "WL",
                        "title": "Watch Later",
                        "name": "Watch Later",
                        "type": "WL",
                        "video_count": wl_count,
                        "description": None
                    },
                    "videos": WL
                }
            }
    else:
        def getNextUrl_forPL(listId,playlistname,ownerViewing,nextcontinuation,videoCount,description=None):
            if not nextcontinuation:
                return None
            return "/playlist?" + urlencode({
                "list": listId,
                "is_owner_viewing": "true" if ownerViewing else "false",
                "title": playlistname or "",
                "video_count": videoCount,
                "continuation": nextcontinuation,
                "description": description or "",
            })
        safe_oauth = cookies.get("oauth_token") or g.OAUTH_TOKEN or None
        header,videos,continuation = innertube.GetPlaylistFromSearch(listId,oauth_token=safe_oauth,hl=hl,gl=gl,continuation_token=continuation_token)
        if not header:
            public_name = data.get("title") or ""
            ownerViewing = data.get("is_owner_viewing","false").lower() == "true"
            try:
                videoCount = int(data.get("video_count","0"))
            except (TypeError, ValueError):
                videoCount = 0
            description = data.get("description") or None
            header = {
                "public_name": public_name,
                "manage_playlist_xsrf_token": get_xsrf('manage_playlist_xsrf_token','manage_playlist_xsrf_token'),
                "is_owner_viewing": ownerViewing,
                "reversed": False,
                "next_url": None,
                "channel_url": None,
                "playlist": {
                    "encrypted_id": listId,
                    "full_encrypted_id": listId,
                    "name": public_name,
                    "title": public_name,
                    "type": "PL",
                    "video_count": videoCount,
                    "description": description,
                }
            }
        videoCount = header["playlist"]["video_count"]
        if continuation:
            header["next_url"] = getNextUrl_forPL(
                listId=listId,
                playlistname=header["public_name"],
                ownerViewing=header["is_owner_viewing"],
                nextcontinuation=continuation,
                videoCount=videoCount,
                description=header["playlist"]["description"],
            )
        else:
            header["next_url"] = None
        json_r = {
            "content": {
                **header,
                "videos": videos,
            },
        }
    json_r_footer = {
        "result": "ok",
        "signed_in_username": "",
        "signed_in_email": "",
        "build_signature": BUILD_SIG,
        "build_id": BUILD_ID,
        "conn": "wifi",
        "timestamp": int(time.time())
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_email"] = g.INFO["email"]
        json_r_footer["signed_in_username"] = g.INFO["name"]
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/set_safety_mode",methods=["POST"])
@require_xsrf('set_safety_mode_xsrf_token')
@checkifajax
def setsafetymode():
    postdata = request.form
    enabled = postdata.get("safety_mode_enabled","0")
    try:
        enabled = int(enabled)
    except (TypeError,ValueError):
        enabled = 0
    cookiepolicy = "Strict" if secureserver else "Lax"
    json_r = {
        "content": {},
        "messages": [],
        "errors": [],
        "result": "ok",
        "build_signature":BUILD_SIG,
        "build_id": BUILD_ID,
        "timestamp": int(time.time()),
        "signed_in_username": "",
        "conn": "wifi",
        "signed_in_email": ""
    }
    if g.SIGNED_IN:
        json_r["signed_in_email"] = g.INFO["email"]
        json_r["signed_in_username"] = g.INFO["name"]
    resp = json_response(json_r)
    g.SAFETY_MODE = enabled
    resp.set_cookie("safety_mode",str(enabled),httponly=False,samesite=cookiepolicy,path="/",secure=secureserver)
    return resp

def handleHTMLpaths_fornow():
    data = request.args
    AJAX = data.get("ajax","0") == "1"
    if not AJAX:
        return redirect("/",code=301)
    htmlInner = render_template("components/not_implemented.html")
    timestamp = int(time.time())
    signed_in_username = ""
    signed_in_email = ""
    if g.SIGNED_IN:
        signed_in_username = g.INFO["name"]
        signed_in_email = g.INFO["email"]
    json_r = funcmod.make_HTMLOnly_AJAX_response(htmlInner,timestamp,signed_in_username,signed_in_email)
    return json_response(json_r)

@app.route("/credits")
@checkifajax
def credits():
    htmlcredits = render_template("components/credits.html")
    timestamp = int(time.time())
    signed_in_username = ""
    signed_in_email = ""
    if g.SIGNED_IN:
        signed_in_username = g.INFO["name"]
        signed_in_email = g.INFO["email"]
    json_r = funcmod.make_HTMLOnly_AJAX_response(htmlcredits,timestamp,signed_in_username=signed_in_username,signed_in_email=signed_in_email)
    return json_response(json_r)

for p in NOT_IMPLEMENTED+OTHER_HTML_ROUTE:
    try:
        app.add_url_rule(f"/{p}",endpoint=p,view_func=handleHTMLpaths_fornow,methods=["GET"])
    except:
        pass

# this isn't even for the 3DS but its neat
# though stubbed
@app.route("/email_unsubscribe",methods=["GET","POST"])
@checkifajax
def emailNotifications():
    action_types = Literal["live_event","subs_confirmation","monthly","newsletter","popular","subscriber","profile","comment","contact","upload_complete","other","digest"]
    json_r = {
        "content": {
            "digest_frequency": "w",
        },
    }
    json_r_footer = {
        "conn": "wifi",
        "signed_in_username": "",
        "signed_in_email": "",
        "result": "ok",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_email"] = g.INFO["email"]
        json_r_footer["signed_in_username"] = g.INFO["name"]
    json_r.update(json_r_footer)
    return json_response(json_r)
# https://youtu.be/zijg6T0Xduk?t=82
@app.route("/account_notifications_probably")
def account_notifications_probably():
    action_types = ["live_event","subs_confirmation","monthly","newsletter","popular","subscriber","profile","comment","contact","upload_complete","other","digest"]
    action = request.args.get("action") or None
    protocol = "https" if request.is_secure else "http"
    url = f"{protocol}://{request.host}/share"
    json_r = {
        "content": {
            "google_plus_setting_link": url,
            "supported_email_locales": [[
                "en_US", "English",
            ]],
            "email_profile": True,
            "video_distiller_enabled": True,
            "email_subscription_confirm": True,
            "email_popular_newsletter": True,
            "email_locale": "en_US",
            "email_live_events": True,
            "email_comments": True,
            "email_contact": True,
            "dasher_disabled": False,
            "email_monthly_product_updates": True,
            "email_subscriber": True,
            "uid": "a",
            "xsrf_token": "ac",
            "email_address": "",
            "logged_in_account": "",
            "action": "other",
            "token": "abc"
        }
    }
    json_r_footer = {
        "conn": "wifi",
        "signed_in_username": "",
        "signed_in_email": "",
        "result": "ok",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_email"] = json_r["content"]["email_address"] = json_r["content"]["logged_in_account"] = g.INFO["email"]
        json_r_footer["signed_in_username"] = g.INFO["name"]
    json_r.update(json_r_footer)
    return json_response(json_r)
@app.route("/account_sharing",methods=["GET","POST"])
@checkifajax
def accountsharing():
    if not g.SIGNED_IN:
        return redirect("/vendor_signin/required?from=sharing")
    data = request.args
    cookies = request.cookies
    formdata = request.form
    action_save = data.get("action_save","0") == "1"
    perm_upload = formdata.get("autoshare_upload","0") == "1"
    perm_add_to_playlist = formdata.get("autoshare_add_to_playlist","0") == "1"
    perm_like = formdata.get("autoshare_likes","0") == "1"
    json_r = {
        "content": {
            "autoshare_xsrf_token": get_xsrf('autoshare_xsrf_token','autoshare_xsrf_token'),
            "autoshare_service_info": {
                "facebook": {
                    "is_connected": False,
                    "is_autosharing": True,
                },
                "twitter": {
                    "is_connected": False,
                    "is_autosharing": True,
                },
            },
            "xsrf_token": get_xsrf('xsrf_token','xsrf_token'),
            "autoshare_upload": False,
            "autoshare_add_to_playlist": False,
            "autoshare_likes": False,
            "discoverable_likes": False,
        },
        "errors": [],
        "result": "success",
        "conn": "wifi",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
        "signed_in_username": "",
        "signed_in_email": "",
        "timestamp": int(time.time()),
    }
    if g.INFO:
        if g.INFO["name"]:
            json_r["signed_in_username"] = g.INFO["name"]
        if g.INFO["email"]:
            json_r["signed_in_email"] = g.INFO["email"]
    return json_response(json_r)

@app.route("/autoshare",methods=["GET","POST"])
@app.route("/share")
def autoshare_POSTONLY():
    data = request.args
    cookies = request.cookies
    if not g.SIGNED_IN:
        return redirect("/vendor_signin/required?from=sharing")
    if request.method == "GET":
        stat = data.get("stat")
        action_ping = data.get("action_ajax_stats_ping","0") == "1"
        action_popup = data.get("action_popup_auth","0") == "1"
        connectOnly = data.get("connect_only","True").lower() == "false"
        servicename = data.get("service")
        if servicename == "facebook":
            permissions = data.get("permissions")
            return Response("Hey so you're not supposed to be here. (facebook ver.)",status=200,mimetype="text/plain")
        rootUrl = data.get("root_url") or f"{request.scheme}://{request.host}"
        return Response("Hey so you're not supposed to be here.",status=200,mimetype="text/plain")
    json_r = {
        "content": {}
    }
    json_r_footer = {
        "result": "ok",
        "errors": [],
        "conn": "wifi",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
        "timestamp": int(time.time()),
        "signed_in_username": "",
        "signed_in_email": ""
    }
    formdata = request.form
    ajax_disconnect_service = data.get("ajax_disconnect_service")
    action_disconnect = formdata.get("action_ajax_disconnect_service","0") == "1"
    servicename = formdata.get("service") or None
    if not action_disconnect or (ajax_disconnect_service != ""):
        return redirect("/")
    if not servicename:
        json_r_footer["result"] = "error"
        json_r_footer["errors"] = [f"Couldn't disconnect this service from your account. Please try again later."]
    if g.INFO:
        if g.INFO["name"]:
            json_r_footer["signed_in_username"] = g.INFO["name"]
        if g.INFO["email"]:
            json_r_footer["signed_in_email"] = g.INFO["email"]
    return json_response(json_r_footer)

@app.route("/manage_playlist",methods=["POST","GET"])
@checkifajax_ANY
def manage_playlist():
    data = request.args
    formdata = request.form
    if not g.SIGNED_IN: return redirect("/vendor_signin/required?from=manage_playlist")
    cookies = request.cookies
    playlist_to_add = data.get("action_view_playlists_to_add","0") == "1"
    action_delete_video = data.get("action_delete","0") == "1"
    action_favorite = data.get("action_favorite","0") == "1"
    action_create_playlist = formdata.get("action_create_playlist","0") == "1"
    action_add_to_playlist = formdata.get("action_add_to_playlist","0") == "1"
    action_reorder = formdata.get("action_reorder","0") == "1"
    oauth_token = cookies.get("oauth_token") or g.OAUTH_TOKEN
    hl = cookies.get("hl") or g.HL
    gl = cookies.get("gl") or g.GL
    pid = formdata.get("pid") or ""
    json_r = {}
    json_r_footer = {
        "result": "ok",
        "build_signature": BUILD_SIG,
        "build_id": BUILD_ID,
        "timestamp": int(time.time()),
        "conn": "wifi",
        "signed_in_username": "",
        "signed_in_email": "",
        "clientWidth": 320
    }
    if playlist_to_add:
        playlists = innertube.GetPlaylists(oauth_token=oauth_token,hl=hl,gl=gl)
        wl_count = playlists.get("WL",{}).get("video_count") # WL is a special case and requires its own field
        json_r = {
            "content": {
                "xsrf_token": get_xsrf('xsrf_token','xsrf_token'),
                "add_favorite_xsrf_token": get_xsrf('add_favorite_xsrf_token','add_favorite_xsrf_token'),
                "playlists": [youtubeiUtils.flat_playlist(plid,title) for plid,title in playlists.items() if plid not in ["WL","LL","SS","YS"]],
                "watch_later_video_count": wl_count
            },
        }
    elif action_create_playlist:
        # i dont think the TV client can create playlists
        # also not WEB without cookies
        playlist_name = formdata.get("playlist_name") or None
        v = formdata.get("v") or None
        json_r = {
            "content": {},
            "errors": [],
            "location": None,
        }
        json_r["errors"] = ["Couldn't create playlist. Please try again."]
        json_r_footer["result"] = "error"
    elif action_delete_video:
        v = formdata.get("v") or None
        plid = formdata.get("p") or None
        recv = formdata.get("session_token")
        stor = session.get('manage_playlist_xsrf_token')
        if not recv or not stor:
            if debugmode:
                print(f"{Fore.RED}[error]{Fore.RESET} either the received token or stored tokens are missing")
            json_r_footer["result"] = "error"
            json_r["errors"] = ["Couldn't delete video from playlist. Please try again."]
            json_r.update(json_r_footer)
            return json_response(json_r)
        if not hmac.compare_digest(recv,stor):
            if debugmode:
                print(f"{Fore.RED}[error]{Fore.RESET} XSRF token digest doesn't match")
            json_r_footer["result"] = "error"
            json_r["errors"] = ["Couldn't delete video from playlist. Please try again."]
            json_r.update(json_r_footer)
            return json_response(json_r)
        if debugmode:
            print(f"{Fore.BLUE}[info]{Fore.RESET} XSRF token check passed")
        ret = innertube.RemoveFromPlaylist(oauth_token,plid,v,hl=hl,gl=gl)
        if ret != "STATUS_SUCCEEDED":
            json_r_footer["result"] = "error"
            json_r["errors"] = ["Couldn't delete video from playlist. Please try again."]
    elif action_add_to_playlist:
        videoId = formdata.get("v") or None
        json_r = {
            "content": {},
            "errors": [],
            "location": None
        }
        if pid.upper() == "W":
            ret = innertube.AddToPlaylist(oauth_token,"WL",videoId,hl=hl,gl=gl)
            if ret != "STATUS_SUCCEEDED":
                json_r_footer["result"] = "error"
                json_r["errors"] = ["Couldn't add video to playlist. Please try again."]
        elif pid.upper() == "SS":
            ret = innertube.AddToPlaylist(oauth_token,"VLSS",videoId,hl=hl,gl=gl)
            if ret != "STATUS_SUCCEEDED":
                json_r_footer["result"] = "error"
                json_r["errors"] = ["Couldn't add video to playlist. Please try again."]
        elif pid.upper() == "YS":
            ret = innertube.AddToPlaylist(oauth_token,"VLYS",videoId,hl=hl,gl=gl)
            if ret != "STATUS_SUCCEEDED":
                json_r_footer["result"] = "error"
                json_r["errors"] = ["Couldn't add video to playlist. Please try again."]
        else:
            ret = innertube.AddToPlaylist(oauth_token,videoId=videoId,playlistId=pid,hl=hl,gl=gl)
            if ret != "STATUS_SUCCEEDED":
                json_r_footer["result"] = "error",
                json_r["errors"] = ["Couldn't add video to playlist. Please try again."]
    else:
        json_r_footer.update({"result":"error"})
    if g.INFO["email"]:
        json_r_footer["signed_in_email"] = g.INFO["email"]
    if g.INFO["name"]:
        json_r_footer["signed_in_username"] = g.INFO["name"]
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/add_favorite",methods=["POST"])
@require_xsrf('add_favorite_xsrf_token')
@checkifajax_POST
def ratevideo_2():
    if not g.SIGNED_IN:
        return redirect("/vendor_signin/required?from=add_favorite")
    data = request.form
    cookies = request.cookies
    json_r = {}
    json_r_footer = {
        "result": "ok",
        "errors": [],
        "build_signature": BUILD_SIG,
        "build_id": BUILD_ID,
        "timestamp": int(time.time()),
        "conn": "wifi",
        "signed_in_username": "",
        "signed_in_email": "",
        "clientWidth": 320
    }
    oauth_token = cookies.get("oauth_token") or g.OAUTH_TOKEN
    hl = cookies.get("hl") or g.HL
    gl = cookies.get("gl") or g.GL
    if g.INFO["email"]:
        json_r_footer["signed_in_email"] = g.INFO["email"]
    if g.INFO["name"]:
        json_r_footer["signed_in_username"] = g.INFO["name"]
    # required to be in the form
    action_favorite = data.get("action_favorite","0") == "1"
    plid = data.get("pid") or None
    videoId = data.get("v") or None
    if not action_favorite or plid != "F" or not videoId:
        json_r_footer["result"] = "error"
        json_r_footer["errors"] = ["Couldn't favorite video. Please try again."]
        return json_response(json_r_footer)
    ret = innertube.RateVideo(oauth_token,videoId,"like",hl=hl,gl=gl)
    if not ret:
        json_r_footer["result"] = "error"
        json_r_footer["errors"] = ["Couldn't favorite video. Please try again."]
        return json_response(json_r_footer)
    json_r_footer["content"] = json_r
    return json_response(json_r_footer)

# nothing is associated with these, JavaScript just navigates there client sided without requesting anything
@app.route("/remote_pairing")
@app.route("/edit_screen")
@app.route("/capture")
@app.route("/tv_queue")
def clientnavigation_stubs():
    return redirect("/",code=302)

@app.route("/_video_info")
def TV_videoinfo():
    data = request.args
    cookies = request.cookies
    hl = getattr(g,"HL",cookies.get("hl","en") or "en") or "en"
    gl = getattr(g,"GL",cookies.get("gl","US") or "US") or "US"
    videoIds_arg = data.get("video_ids")
    json_r_footer = {
        "result": "ok",
        "messages": [],
        "errors": [],
        "conn": "wifi",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
        "signed_in_username": "",
        "signed_in_email": "",
        "timestamp": int(time.time())
    }
    if g.SIGNED_IN:
        json_r_footer["signed_in_email"] = g.INFO["email"]
        json_r_footer["signed_in_username"] = g.INFO["name"]
    if videoIds_arg:
        videoIds = videoIds_arg.split(",")
    else:
        return json_response({
            "content": {},
            **json_r_footer
        })
    videos = []
    for v in videoIds:
        IT_info = innertube.GetVideoInfo(v,hl=hl,gl=gl)
        if not IT_info:
            continue
        vidid = IT_info["encrypted_id"]
        thumb = funcmod.getThumbnail(vidid)
        seconds = int(IT_info["duration"])
        hours,remainder = divmod(seconds,3600)
        minutes,seconds = divmod(remainder,60)
        if hours:
            duration = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            duration = f"{minutes}:{seconds:02d}"
        videos.append({
            "encrypted_id": vidid,
            "title": IT_info["title"],
            "duration": fmt_duration(duration),
            "nb": IT_info["author"],
            "public_name": IT_info["author"],
            "short_byline": IT_info["author"],
            "wh": thumb,
            "view_count": fmt_view(IT_info["view_count"]),
            "Sc": f"/watch?v={vidid}"
        })
    json_r = {
        "content": {
            "videoIds": videoIds_arg,
            "videos": videos,
        }
    }
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/api/lounge/bc/<string:BcSubpath>",methods=["GET","POST"])
def browserchannel(BcSubpath):
    headers = request.headers
    userAgent = headers.get("User-Agent","-")
    is3ds = IS_3DS(userAgent)
    cnt,status,mime = lounge.BrowserChannel(
        endpoint=BcSubpath,
        method=request.method,
        headers={
            "User-Agent": userAgent,
        },
        form=request.form.to_dict(flat=False),
        is3DS=is3ds,
        params=request.args.to_dict(flat=False),
    )
    return Response(response=cnt,status=status,content_type=mime)

@app.route("/api/lounge/<string:APIType>",strict_slashes=False,methods=["POST","PUT","DELETE","GET"])
@app.route("/api/lounge/<string:APIType>/<string:subpath>",strict_slashes=False,methods=["POST","PUT","DELETE","GET"])
@limiter.limit("350 per minute")
def loungeAPI(APIType=None,subpath=None):
    headers = request.headers
    userAgent = headers.get("User-Agent","-")
    cnt,status,mime = lounge.Lounge(
        apitype=APIType,
        endpoint=subpath,
        subpath=subpath,
        method=request.method,
        form=request.form.to_dict(flat=False),
        headers={
            "User-Agent": userAgent,
        },
        scrids=request.form.get("screen_ids"),
        loungetoken=request.form.get("lounge_token"),
        paircd=request.form.get("pairing_code"),
    )
    return Response(response=cnt,status=status,content_type=mime)

@app.post("/rating")
@require_xsrf('sentiment_xsrf_token')
@checkifajax_POST
def ratevideo():
    if not g.SIGNED_IN: return "",412
    oauth_token = g.OAUTH_TOKEN
    data = request.form
    action_rate = data.get("action_rate","0") == "1"
    if not action_rate:
        return "",400
    videoid = data.get("v","")
    if not videoid:
        return "",400
    endpoint = "indifferent"
    rating = data.get("rating","0")
    hl = g.HL
    gl = g.GL
    if rating == "5":
        endpoint = "like"
    elif rating == "1":
        endpoint = "dislike"
    json_r_footer = {
        "result": "ok",
        "signed_in_username": g.INFO["name"],
        "signed_in_email": g.INFO["email"],
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
        "conn": "wifi",
        "timestamp": int(time.time())
    }
    likes = 0
    info = gdata.GetVideoInfo(videoid)
    if info:
        likes = info["likes"]
    boolOk = innertube.RateVideo(oauth_token,videoid,endpoint,hl=hl,gl=gl)
    dislikes = funcmod.getDislikes(videoid)
    final_likes = int(likes)
    final_dislikes = int(dislikes)
    json_r = {
        "content": {
            "likes_num": final_likes,
            "dislikes_num": final_dislikes
        }
    }
    if not boolOk:
        json_r_footer["result"] = "error"
        return json_response(json_r_footer)
    json_r.update(json_r_footer)
    return json_response(json_r)

@app.route("/flag",methods=["GET"])
@checkifajax
def flagvideo():
    data = request.args
    video = data.get("v","")
    html = render_template("components/flag.html",video=video)
    timestamp = int(time.time())
    name = email = ""
    if g.SIGNED_IN:
        name = g.INFO["name"]
        email = g.INFO["email"]
    json_r = funcmod.make_HTMLOnly_AJAX_response(html,timestamp,name,email)
    return json_response(json_r)

@app.route("/complete/search")
def completesearch():
    data = request.args
    query = data.get("q","")
    lang = data.get("hl","en")
    gl = request.cookies.get("gl") or getattr(g,"GL","US")
    ret = innertube.CompleteSearch(query=query,hl=lang,gl=gl)
    return Response(ret,headers={"Content-Type":"text/javascript"},status=200)

@app.route("/timedtext")
def captionsold():
    return ""
    data = request.args
    subtkind = data.get("type", "list")
    v = data.get("v", "")
    lang = data.get("hl", "en")

    if subtkind == "list":
        ret = (
            "<transcript_list>"
            "<track "
            "id='0' "
            "lang_code='en' "
            "lang_original='englishog' "
            "lang_translated='englishtrnaslated' "
            "name='engname' "
            "kind='subtitles' "
            "lang_default='false' "
            "cantran='false' "
            "/>"
            "</transcript_list>"
        )
    elif subtkind == "track":
            ret = """WEBVTT

00:00:00.000 --> 00:00:02.000
hello
"""
            return Response(ret,mimetype="text/vtt",status=200)
    return Response(ret,mimetype="application/xml",status=200)

@app.route("/timedtext_")
def captions_new():
    return ""
    data = request.args
    subtkind = data.get("type", "list")
    videoId = data.get("v", "")
    lang = data.get("hl") or data.get("lang") or "en"
    tlangs = data.get("tlangs","")
    if not videoId:
        return abort(400)
    if subtkind == "list":
        #languages = lbl351_captions.getLanguages_pytube(videoId)
        #xml_content = lbl351_captions.buildXMLList(languages,videoId,lang)
        testing_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<transcript_list>
    <track id="0" lang_code="en" lang_original="English" lang_translated="English (Auto-Translated)" name="English" kind="subtitles" lang_default="true" cantran="false" />
</transcript_list>"""
        return Response(testing_xml,status=200,mimetype="application/xml")
    elif subtkind == "track":
        #xml_content = lbl351_captions.getCaption_pytube(videoId,lang)
        #print(xml_content)
        return Response(lbl351_captions.buildEmptyTranscript(),status=200,mimetype="application/xml")
    #xml_content = lbl351_captions.getCaption_pytube(videoId,lang)
    return Response(lbl351_captions.buildEmptyTranscript(),status=200,headers={"Content-Type": "application/xml"})

# other/miscellanous routes
@app.route("/version")
def versioncheck():
    if not debugmode:
        return getVersion()
    else:
        return {"prefix":" ","strversion":" "}

@app.route("/status",methods=["GET","HEAD"]) # used on website
def status():
    s = 204
    if maint:
        s = 502
    return Response(status=s)

@app.route("/_get_ads")
@app.route("/view_comment") # 204 because youtube 3DS never had commenting
@app.route("/post_comment",methods=["GET","POST"])
@app.route("/stream_204")
@app.route("/gen_204",methods=["POST","GET"])
@app.route("/generate_204",methods=["POST","GET"])
@app.route("/set_awesome",methods=["GET","POST"])
@app.route("/live_204",methods=["GET","POST"])
@app.route("/csi",methods=["GET","POST"]) # shouldn't be enabled anyway
@app.route("/user_watch",methods=["GET"],strict_slashes=False)
@app.route("/s",methods=["GET"])
@app.route("/dartproxy/mobile.handler",strict_slashes=False,methods=["GET"])
@app.route("/pyv_ping",methods=["GET"])
@app.route("/vendor_signin/frame",methods=["GET"])
@app.route("/ga.js",methods=["GET"])
def nocontentroutes():
    data_post = request.form
    data_get  = request.args
    return Response(status=204)

@app.route("/static/images/netflix/<string:subpath>",strict_slashes=False)
@app.route("/static/favicon_hulu.ico")
@app.route("/static/favicon_netflix.ico")
@app.route("/static/images/netflix/<string:subpath>",strict_slashes=False)
def routes404(subpath=None):
    return abort(404)

@app.route("/robots.txt")
def robotstxt():
    robotstxtfile = METADIR/"robots.txt"
    if robotstxtfile.is_file():
        return send_from_directory(METADIR,"robots.txt")
    else:
        return abort(404)

@app.route("/static/configuration.xsd")
def configxsd():
    if debugmode:
        return send_from_directory("static","configuration.xsd"),200,{"Content-Type":"application/xhtml+xml; charset=utf-8"}
    else:
        return abort(404)

@app.route("/favicon.ico",methods=["GET"])
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def favicon():
    return send_from_directory("static","favicon.ico"),200,{"Content-Type":"image/x-icon"}

@app.route("/maintenance",methods=["GET"])
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def maintenance():
    if maint:
        return Response(render_template("maintenance.html",debug=debugmode),status=200,headers={"Content-Type":"text/html; charset=utf-8"})
    else:
        abort(404)

# before/after request
@app.before_request
def before_request():
    cookies = request.cookies
    g.DELETE_AUTH   = False # whether to delete oauth_token & refresh_token and sign the user out basically
    g.SIGNED_IN     = False # sign in bool
    g.OAUTH_TOKEN   = None # oauth_token cookie (oauth_token in backend)
    g.REFRESH_TOKEN = None # refresh_token cookie
    g.NEW_OAUTH     = None # new oauth token gotten from /vendor_signin/refresh
    g.INFO          = {} # user info; email (which for some reason the 2014 layout used), name, user icon, whether the user has a channel or not, user handle
    # (dict) name, photo, handle, haschannel, email
    g.HL            = "en" # html display language
    g.GL            = "US" # overridden region in html, no idea how its gonna be used
    g.SAFETY_MODE   = 0 # safety mode, again, no idea how this is gonna be used
    ua = request.headers.get("User-Agent","")
    allow = [
        "Mozilla/5.0 (Nintendo 3DS; U; Factory Media Production; en) Version/1.7498.US",
        "Mozilla/5.0 (Nintendo 3DS; U; Factory Media Production; en) Version/1.7498.EU",
        "Mozilla/5.0 (Nintendo 3DS; U; Factory Media Production; en) Version/1.7498.JP",
        "Mozilla/5.0 (Nintendo 3DS New3DS; U; Factory Media Production; en) Version/1.7499.US",
        "Mozilla/5.0 (Nintendo 3DS New3DS; U; Factory Media Production; en) Version/1.7499.EU",
        "Mozilla/5.0 (Nintendo 3DS New3DS; U; Factory Media Production; en) Version/1.7499.JP",
    ]
    #if ua not in allow:
    #    abort(403)
    if request.path == "/api/lounge/pairing/get_screen_availability":
        # you'd be surpised at how many people are unemployed
        if request.method == "GET" and len(request.query_string) > 1000:
            ipban.block(request.remote_addr)
            return abort(403)
        forbid_params = {
            "exec",
            "execute",
            "command",
            "cmd",
            "include",
            "file",
            "filename",
            "download",
            "redirect_uri",
            "payload",
            "process",
            "module",
        }
        if forbid_params.intersection(request.args.keys()):
            ipban.block(request.remote_addr)
            abort(403)
    if secureserver:
        if not request.is_secure:
            return redirect(request.url.replace("http://","https://",1))
    if debugmode:
        debugmodule.request_dump(request,request.get_data(as_text=True,cache=True))
    if maint and request.path != "/maintenance" and request.path != "/favicon.ico" and "/static/" not in request.path:
        if debugmode and request.path not in ["/debug","/debug.html"]:
            return redirect("/maintenance",code=302)
        else: pass
    if cookies.get("hl"):
        g.HL = cookies.get("hl")
    if cookies.get("gl"):
        g.GL = cookies.get("gl")
    if cookies.get("safety_mode"):
        g.SAFETY_MODE = cookies.get("safety_mode")
    oauth_token = cookies.get("oauth_token")
    refresh_token = cookies.get("refresh_token")
    if oauth_token:
        if oauth2.CheckIsTokenValid(oauth_token):
            g.SIGNED_IN = True
            g.OAUTH_TOKEN = oauth_token
            g.INFO = oauth2.GetUserInfo(g.OAUTH_TOKEN)
        elif refresh_token:
            newtoken = oauth2.RefreshToken(refresh_token)
            if newtoken:
                g.SIGNED_IN = True
                g.OAUTH_TOKEN = newtoken
                g.NEW_OAUTH = newtoken
                g.INFO = oauth2.GetUserInfo(newtoken)
            else:
                g.DELETE_AUTH = True
        else:
            g.DELETE_AUTH = True
    elif refresh_token:
        newtoken = oauth2.RefreshToken(refresh_token)
        if newtoken:
            g.SIGNED_IN = True
            g.OAUTH_TOKEN = newtoken
            g.NEW_OAUTH = newtoken
            g.INFO = oauth2.GetUserInfo(newtoken)
        else:
            g.DELETE_AUTH = True
    else:
        g.SIGNED_IN = False

@app.after_request
def after_request(response:Response):
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if response.status_code == 403:
        return response
    if response.status_code == 204:
        response.headers.pop("Content-Type",None)
    policy = "Strict" if secureserver else "Lax"
    if getattr(g,"DELETE_AUTH",False):
        response.delete_cookie("oauth_token",path="/",httponly=True,samesite=policy,secure=secureserver)
        response.delete_cookie("refresh_token",path="/",httponly=True,samesite=policy,secure=secureserver)
    elif getattr(g,"NEW_OAUTH",None):
        response.set_cookie("oauth_token",g.NEW_OAUTH,httponly=True,samesite=policy,max_age=3600,path="/",secure=secureserver)
    response.set_cookie("hl",getattr(g,"HL","en"),samesite=policy,secure=secureserver,httponly=False,path="/")
    response.set_cookie("gl",getattr(g,"GL","US"),samesite=policy,secure=secureserver,httponly=False,path="/")
    response.set_cookie("safety_mode",str(getattr(g,"SAFETY_MODE","0")),samesite=policy,secure=secureserver,httponly=False,path="/")
    return response

# main
if __name__ == "__main__":
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    loadcfg()
    if not cfgexist:
        funcmod.clearscreen()
        print("Let's set up BlazerTube")
        time.sleep(1.5000)
        host = input("On what host should the main YouTube server run? (leave empty for 0.0.0.0): ").lower().strip()
        if host == "":
            host = "0.0.0.0"
        port = None
        while port is None:
            try:
                port_in = input("On what port should BlazerTube run? (leave empty for 80): ").lower().strip()
                if port_in == "": port_in = "80"
                port_in = int(port_in)
                if not 1 <= port_in <= 65535:
                    raise TypeError
                port = port_in
                break
            except ValueError:
                print("Please enter a valid integer.")
                time.sleep(2.00)
            except TypeError:
                port = None
                print("The port must be greater than 1 and lower than 65535.")
                time.sleep(2.00)
        debugmode = None
        while debugmode is None:
            debugmode_input = input("Should the server run in debug mode? (leave empty for true): ").lower().strip()
            if debugmode_input == "":
                debugmode = True
                break
            elif debugmode_input == "true":
                debugmode = True
                break
            elif debugmode_input == "false":
                debugmode = False
                break
            else:
                print("Please enter a valid boolean")
                time.sleep(2.00)
        secureserver = None
        while secureserver is None:
            secureserver_in = input("Should the server run on HTTPS? (leave empty for false): ").lower().strip()
            if secureserver_in == "":
                secureserver = False
            elif secureserver_in == "true":
                secureserver = True
            elif secureserver_in == "false":
                secureserver = False
            else:
                print("Please enter a valid boolean")
                time.sleep(2.00)
            break
        if secureserver:
            pempath = None
            keypath = None
            while pempath is None:
                pempath_in = input("Please enter your private PEM certificate path: ").strip()
                if not pempath_in:
                    print("A certificate is required.")
                    continue
                tmp_pempath = Path(pempath_in)
                if not tmp_pempath.is_file():
                    print(f"Certificate not found: {tmp_pempath}")
                    continue
                pempath = tmp_pempath
            while keypath is None:
                keypath_in = input("Please enter your private key path: ").strip()
                if not keypath_in:
                    print("A private key is required")
                    continue
                tmp_keypath = Path(keypath_in)
                if not tmp_keypath.is_file():
                    print(f"Private key not found: {tmp_keypath}")
                    continue
                keypath = tmp_keypath
        ET.register_namespace("xsi",XMLSCHEMA_INSTANCE_NS)
        ET.register_namespace("",CFG_NAMESPACE_STR)
        root = ET.Element(f"{{{CFG_NAMESPACE_STR}}}configuration",{
            "version":"1",
            f"{{{XMLSCHEMA_INSTANCE_NS}}}schemaLocation":f"{CFG_NAMESPACE_STR} static/configuration.xsd",
        })
        def createelem(tagname,text=None,nil=False):
            subelem = ET.SubElement(root,f"{{{CFG_NAMESPACE_STR}}}{tagname}")
            if nil:
                subelem.set(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil","true")
            else:
                subelem.text = text
        createelem("yt_host",host)
        createelem("yt_port",str(port))
        createelem("nasc_host",nil=True)
        createelem("nasc_port",nil=True)
        createelem("debugging",str(debugmode).lower())
        createelem("secure",str(secureserver).lower())
        if secureserver:
            createelem("pempath",str(pempath))
            createelem("keypath",str(keypath))
        else:
            createelem("pempath",nil=True)
            createelem("keypath",nil=True)
        # default stuff
        createelem("maint","false")
        createelem("hulu_host",nil=True)
        createelem("hulu_port",nil=True)
        createelem("proxy_port",nil=True)
        createelem("netflix_host",nil=True)
        createelem("netflix_port",nil=True)
        tree = ET.ElementTree(root)
        ET.indent(tree,space="    ")
        print("Saving your configuration...")
        tree.write(config,encoding="utf-8",xml_declaration=True)
        print("Done! To create a patch, please go to /patcher/ and run patcher.py")
        print("Remember to install the patcher dependencies")
        print("For more information, please read the README.")
        time.sleep(5.00)
        funcmod.clearscreen()
    context = None
    if secureserver:
        disable_warnings(DeprecationWarning)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_ciphers("ALL:@SECLEVEL=0")
        context.minimum_version = ssl.TLSVersion.TLSv1
        context.maximum_version = ssl.TLSVersion.TLSv1
        context.load_cert_chain(certfile=pempath,keyfile=keypath)
    envexample = BASE/".env.example"
    envfile = BASE/".env"
    if envexample.is_file() and not envfile.is_file():
        print("Please rename .env.example to .env, and then re-run the server to continue.")
        sys.exit(-1)
    if (not GDATA_API_KEY) or (not GDATA_API_KEY.strip()):
        print("Cannot continue without a GDATA API key. Please place one in .env")
        sys.exit(-1)
    if (not LOGIN_SCOPE) or (not OAUTH_ID) or (not OAUTH_SECRET):
        print("One or more required environment variables are missing.")
        print("Please check your environment (.env) file and try again.")
        sys.exit(-1)
    if not ENABLE_CREDS_OVERRIDE:
        if (not DEFAULT_DEVICE_ID) or (not DEFAULT_DEVICE_MODEL):
            print("DEFAULT_DEVICE_ID and DEFAULT_DEVICE_MODEL are required when using InnerTube's login system.")
            print("Please check your environment (.env) file and try again.")
            sys.exit(-1)
    app.secret_key = FLASK_SECRET_KEY
    if not app.secret_key:
        thistmpkey = secrets.token_hex(32)
        print(f"{Fore.RED}[err]{Fore.RESET} No Flask secret key has been configured")
        print(f"{Fore.BLUE}[info]{Fore.RESET} Open your environment (.env) file and add:")
        print(f"FLASK_SECRET_KEY={thistmpkey}",flush=True)
        sys.exit(-1)
    else:
        policy = "Strict" if secureserver else "Lax"
        app.secret_key = FLASK_SECRET_KEY
        app.config.update({
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SECURE": secureserver,
            "SESSION_COOKIE_SAMESITE": policy,
        })
    if not debugmode:
        funcmod.clearscreen()
    print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Starting video cleanup thread")
    thread = threading.Thread(target=cleanup_schedule,daemon=True,name="btvidcleanupd")
    thread.start()
    lbl351_captions = Captions()
    tmpvideo = GetVideo()
    tmpvideo.createviddir()
    if not debugmode:
        set_external_API_url("https","lbl-api.idkwh.ct8.pl","443")
        set_versioned_xlb_subpath("api/ctr/GetVersionedXLB.php")
        set_version_subpath("api/ctr/GetVersion.php")
    app.run(host=host,port=port,debug=debugmode,threaded=True,ssl_context=context,extra_files=["config.xml",".env"])
