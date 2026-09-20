import requests
import re
import json
from urllib.parse import quote
import socket
from pathlib import Path
import warnings

from shared import *

BASE = Path(__file__).resolve().parent

def getThumbnail(videoId):
    url = f"http://i.ytimg.com/vi/{videoId}/mqdefault.jpg"
    FALLBACK = f"/static/images/thumbnail/meh_mini.png"
    try:
        r = requests.get(url,timeout=10,headers={"User-Agent":API_USERAGENT,"Accept-Language":"en-US;q=1.0,en;q=1.0,*;q=0.5"},cookies=CONSENT_COOKIES)
        r.raise_for_status()
    except requests.RequestException:
        return FALLBACK
    if not r.ok:
        return FALLBACK
    return url

def fetchUserBanner(userId,hd=False):
    starturl = f"https://www.youtube.com/channel/{userId}"
    FALLBACK = f"/static/images/topics/banners/default_img.png"
    if userId in GENERATED_CHANNELS:
        bnrpath = BASE/"static"/"images"/"topics"/"banners"
        path = bnrpath/f"{str(GENERATED_CHANNELS.get(userId)).lower() or 'default_img'}.png"
        altpath = bnrpath/f"{str(GENERATED_CHANNELS.get(userId)).lower() or 'default_img'}.jpg"
        usealt = False
        if not path.is_file():
            usealt = True
            if not altpath.is_file():
                usealt = False
                return ""
        if usealt:
            finalpath = altpath
        else:
            finalpath = path
        httpPath = str(finalpath.relative_to(BASE)).replace("\\","/")
        return str(f"/{httpPath}")
    try:
        html = requests.get(starturl,headers={"User-Agent":API_USERAGENT,"Accept-Language":"en-US;q=1.0,en;q=1.0,*;q=0.5"},timeout=10,cookies=CONSENT_COOKIES)
        html.raise_for_status()
    except requests.RequestException:
        return None
    match = re.search(r'https\:\/\/yt3\.googleusercontent\.com/[^\"]+?=w\d+-[^\"]+',html.text)
    if not match:
        return None
    bnr = match.group(0)
    if hd:
        bnr = re.sub(r'=w\d+-','=w2120-',bnr)
    bnr = re.sub(r"https\:\/\/","http://",bnr)
    return bnr

def getDislikes(videoId):
    videoId = quote(videoId)
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={videoId}"
    try:
        r = requests.get(url,verify=True,headers={"Accept-Language":"en;q=1.0,en-US;q=1.0,*;0.5","Accept":"application/json;q=1.0,text/json;q=0.9,*/*;q=0.0","User-Agent":API_USERAGENT},timeout=10)
        r.raise_for_status()
        cnt = r.json()
    except (requests.RequestException,ValueError):
        return 0
    if cnt.get("dislikes") is None: return 0
    return json.dumps(cnt.get("dislikes","0"))

def getRating(videoId):
    videoId = quote(videoId)
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={videoId}"
    try:
        r = requests.get(url,verify=True,headers={"Accept-Language":"en;q=1.0,en-US;q=1.0,*;0.5","Accept":"application/json;q=1.0,text/json;q=0.9,*/*;q=0.0","User-Agent":API_USERAGENT},timeout=10)
        r.raise_for_status()
        cnt = r.json()
    except (requests.RequestException,ValueError):
        return 0
    if cnt.get("rating") is None: return 0
    return json.dumps(cnt.get("rating","0"))

def showlanip():
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    ip = s.getsockname()[0]
    s.close()
    return ip

def clearscreen():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

def make_destination_moments(vidinf,chinf):
    """
creates a 2013 YouTube rewind card (feeds only)\n
this is more of a thing to mess around with, it shouldn't be in production\n
example:
```
            {
                "video": {
                    "time_created_text": "3223",
                    "title": "hi",
                    "user_image_url": "/channel/UC3IL0b1yqcimDNNGxSRxDkA/icon",
                    "watch_link": "/watch?v=as",
                    "watched": False,
                    "duration": "12:12",
                    "view_count": 12,
                    "thumbnail_info": {
                        "url": "/static/images/meh_mini-vfl0Ugnu3.png"
                    }
                },
                "channel": {
                    "url": "/channel/abc",
                    "public_name": "title",
                    "title": "title",
                    "thumbnail": "<img src='/channel/UC3IL0b1yqcimDNNGxSRxDkA/icon'>",
                    "subscription_state": {},
                    "subscription_button_data": {},
                    "category_link": "Hi",
                    "category_rec_count": 2,
                    "category_title": "Null",
                },
            },
```
"""
    return {
        "video": {
            "time_created_text": vidinf.get("upload_date"),
            "title": vidinf.get("title"),
            "user_image_url": f"/channel/{chinf.get('channel_id')}/icon",
            "watch_link": f"/watch?v={vidinf.get('video_id')}",
            "watched": False,
            "view_count": vidinf.get("view_count"),
            "duration": vidinf.get("duration"),
            "thumbnail_info": {
                "url": getThumbnail(vidinf.get("video_id")),
            },
        },
        "channel": {
            "url": f"/channel/{chinf.get('channel_id')}",
            "public_name": chinf.get("display_name"),
            "thumbnail": f"<img src='/channel/{chinf.get('channel_id')}/icon'>",
            "subscription_state": {},
            "subscription_button_data": {},
            "category_link": "Hi",
            "category_rec_count": 2,
            "category_title": "Null",
        },
    }

def create_html5only_advert(clickUrl,adImage,duration,encId,message,streamUrl):
    """
requires allow_html5_ads to be set to true\n
DO NOT USE IN PRODUCTION. PLEASE."""
    return {
        "ad_instream": {
            "click": clickUrl,
            "clickthrough": clickUrl,
            "companion_image": adImage,
            "duration": duration,
            "encrypted_id": encId,
            "message": message,
            "source": streamUrl,
            "stream_url": streamUrl,
            "tracking": "",
        },
    }

def make_HTMLOnly_AJAX_response(htmlInner,timestamp,signed_in_username=None,signed_in_email=None):
    json_r = {
        "content": {
            "data": htmlInner
        },
        "result": "ok",
        "timestamp": timestamp,
        "conn": "wifi",
        "signed_in_username": "",
        "signed_in_email": "",
        "build_id": BUILD_ID,
        "build_signature": BUILD_SIG,
    }
    if signed_in_username:
        json_r["signed_in_username"] = signed_in_username
    if signed_in_email:
        json_r["signed_in_email"] = signed_in_email
    return json_r

def disable_warnings(warn):
    warnings.simplefilter("ignore",warn)
