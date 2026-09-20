from __future__ import print_function, annotations
import requests
import re
import json
import time
import threading
from datetime import datetime
from datetime import timedelta
from isodate import parse_duration
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import typing as t
import werkzeug.datastructures as wd
import traceback

from shared import *
import functions as funcmod

CHANNEL_ID_RE = re.compile(r"UC[A-Za-z0-9_-]{22}")
TOPIC_ID_RE   = re.compile(r"HC[A-Za-z0-9_-]{11}")
LIVE_ID_TOPIC = "SBAaOjE-GIlRI"
TOPIC_TYPES   = t.Literal["edu","education","music","live","sports","autos","gaming","news","tv"]

def simpletext(obj):
    if not obj: return None
    if "simpleText" in obj: return obj["simpleText"]
    runs = obj.get("runs")
    if runs: return runs[0].get("text")
    return None

def _digit(text):
    if not text:
        return "0"
    m = re.sub(r"[^\d]","",text)
    return m or "0"

def parsecount(text):
    if not text:
        return "0"
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*([KMB]?)",text,re.IGNORECASE)
    if not m:
        return _digit(text)
    num_str = m.group(1).replace(",","")
    suffix = m.group(2).upper()
    try:
        num = float(num_str)
    except ValueError:
        return "0"
    multiplier = {"":1,"K":1000,"M":1000000,"B":1000000000}.get(suffix,1)
    return str(int(num * multiplier))

def fmt_date(iso):
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%b %d, %Y").replace(" 0", " ")
    except Exception:
        return iso
def fmt_view(v):
    try:
        return f"{int(v):,}".replace(",",".")
    except (ValueError,TypeError):
        return v
def fmt_duration(d):
    p = d.split(":")
    if len(p) == 2:
        m, s = int(p[0]), int(p[1])
        if m < 60:
            return d
        return f"{m // 60}:{m % 60:02d}:{s:02d}"
    return d
def parsedura(dur):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return ""
    h, mn, s = int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0)
    return f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"

def parseViews(text):
    if not text: return 0
    t = text.strip()
    m = re.match(r"^([\d.]+)\s*(views|view)",t)
    if m:
        num = m.group(1).replace(".", "")
        try: return int(num)
        except ValueError: return 0
    m = re.match(r"^([\d,\.]+)\s*Mio\.?\s*views",t)
    if m:
        num = m.group(1).replace(".","").replace(",",".")
        try: return int(float(num)*1000000)
        except ValueError: return 0
    m = re.match(r"^([\d,\.]+)\s*([KMB]?)\s*views?",t,re.IGNORECASE)
    if m:
        num_str = m.group(1).replace(",","")
        suffix = m.group(2).upper()
        try: num = float(num_str)
        except ValueError: return 0
        multiplier = {"":1,"K":1000,"M":1000000,"B":1000000000}.get(suffix,1)
        return int(num*multiplier)
    digits = re.sub(r"[^\d]","",t)
    return int(digits) if digits else 0

class GDataAPI:
    def __init__(self, GDataKey:str) -> None:
        self.GDATA_API_URL = "https://www.googleapis.com/youtube/v3"
        self.GDATA_API_KEY = GDataKey
    def _gdata_get_mostpopular(self,hl="en",gl="US",maxResults=25):
        if not self.GDATA_API_KEY:
            return []
        try:
            url = f"{self.GDATA_API_URL}/videos"
            r = requests.get(url,params={
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": gl,
            "maxResults": maxResults,
            "key": self.GDATA_API_KEY
        },timeout=20)
            r.raise_for_status()
            data = r.json()
            return data.get("items",[])
        except (requests.RequestException,ValueError):
            return []
    def _gdata_getchannelstats(self,channelIds):
        if not self.GDATA_API_KEY:
            return {}
        if not channelIds:
            return {}
        try:
            url = f"{self.GDATA_API_URL}/channels"
            r = requests.get(url,params={
                "part": "statistics",
                "id": ",".join(channelIds),
                "key": self.GDATA_API_KEY},
                timeout=20
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return {}
        return {
            item["id"]: item.get("statistics",{})
            for item in data.get("items",[])
        }
    @staticmethod
    def yt(url,params=None,timeout=10):
        r = requests.get(url,params=params,timeout=timeout)
        r.raise_for_status()
        return r.json()
    @staticmethod
    def _convert_duration(iso):
        duration = parse_duration(iso)
        total = int(duration.total_seconds())
        minutes,seconds = divmod(total,60)
        return f"{minutes}:{seconds:02d}"
    def _build_video_item(self,snippet,stats):
        video_id = snippet["id"]
        author = snippet["snippet"]["channelTitle"]
        return {
            "item_type": "compact_video",
            "action_type": "WL",
            "video": {
                "encrypted_id": video_id,
                "title": snippet["snippet"]["title"],
                "short_byline": author,
                "public_name": author,
                "view_count": stats.get("statistics",{}).get("viewCount","0"),
                "duration": (
                    self._convert_duration(stats["contentDetails"]["duration"]).strip()
                    if "contentDetails" in stats
                    else "0:00"
                ),
                "watch_link": f"/watch?v={video_id}",
                "thumbnail_info": {
                    "url": funcmod.getThumbnail(video_id)
                }
            }
        }
    def _gdata_getvideocountforsearch(self,channelIds):
        if not self.GDATA_API_KEY:
            return {}
        url = f"{self.GDATA_API_URL}/channels"
        try:
            r = requests.get(url,params={
                "part": "statistics",
                "id": ",".join(channelIds),
                "key": self.GDATA_API_KEY
            },timeout=20)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return {}
        return {item["id"]: item.get("statistics",{}).get("videoCount") for item in data.get("items",[])}
    def _gdata_getvideocount(self,channelId):
        if not self.GDATA_API_KEY:
            return 0
        if not channelId:
            return 0
        url = f"{self.GDATA_API_URL}/channels"
        try:
            r = requests.get(url,params={
                "part": "statistics",
                "id": channelId,
                "key": self.GDATA_API_KEY
            },timeout=20)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return 0
        item = data.get("items")
        if not item:
            return 0
        return item[0].get("statistics",{}).get("videoCount")
    def _get_video_info(self,video_id):
        try:
            url = f"{self.GDATA_API_URL}/videos"
            r = requests.get(url, params={
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "key": self.GDATA_API_KEY,
            }, timeout=5)
            items = r.json().get("items", [])
            if not items:
                return None
            item = items[0]
            sn = item["snippet"]
            st = item.get("statistics", {})
            cd = item.get("contentDetails", {})
            ch_id = sn.get("channelId", "")
            return {
                "title": sn.get("title", ""),
                "description": sn.get("description", ""),
                "channel_name": sn.get("channelTitle", ""),
                "channel_id": ch_id,
                "duration": parsedura(cd.get("duration", "")),
                "upload_date": fmt_date(sn.get("publishedAt", "")),
                "view_count": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "channel_icon_url": f"/channel/{ch_id}/icon",
                "profile_url": f"/channel/{ch_id}",
            }
        except Exception as e:
            print(f"[watch] {e}")
            return None
    def _get_recomm_channels(self,hl="en",gl="US",oauth_token=None,maxResults=25):
        if not oauth_token:
            return None
        videos = self._gdata_get_mostpopular(hl,gl,maxResults=25)
        if not videos:
            return []
        channels = []
        seen = set()
        for video in videos:
            snippet = video.get("snippet",{})
            chid = snippet.get("channelId")
            if not chid or chid in seen:
                continue
            seen.add(chid)
            channels.append({
                "channel_id": chid,
                "title": snippet.get("channelTitle",""),
                "url": f"/channel/{chid}",
                "thumbnail": f"/channel/{chid}/icon",
            })
            if len(channels) >= maxResults:
                break
        channelIds = [x["channel_id"] for x in channels]
        stats = self._gdata_getchannelstats(channelIds)
        for c in channels:
            chid = c["channel_id"]
            s = stats.get(chid,{})
            c["subscriber_count"] = s.get("subscriberCount")
            c["video_count"] = s.get("videoCount")
        return channels
    def _get_trending(self, limit=25):
        url = f"{self.GDATA_API_URL}/videos"
        popular = self.yt(
            url,
            {
                "part": "snippet,contentDetails,statistics",
                "chart": "mostPopular",
                "regionCode": "US",
                "maxResults": limit,
                "key": self.GDATA_API_KEY,
            },
            timeout=5,
        )
        items = [
            self._build_video_item(video, video)
            for video in popular.get("items", [])
        ]
        return {
            "items": items
        }
    def _get_channel_info(self,channelId):
        if not self.GDATA_API_KEY:
            return None
        try:
            url = f"{self.GDATA_API_URL}/channels"
            r = requests.get(url,params={
                "part": "snippet,statistics",
                "id": channelId,
                "key": self.GDATA_API_KEY
            },timeout=10)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return None
        items = data.get("items")
        if not items:
            return None
        ch = items[0]
        snippet = ch.get("snippet",{})
        stats = ch.get("statistics",{})
        joined = None
        published_at = snippet.get("publishedAt")
        if published_at:
            try:
                dt = datetime.fromisoformat(published_at.replace("Z","+00:00"))
                joined = f"{dt.day} {dt.strftime('%b %Y')}"
            except ValueError:
                joined = published_at
        description = snippet.get("description","")
        is_auto_generated = "generated automatically" in description
        viewCount = stats.get("viewCount")
        if viewCount:
            viewCount = viewCount.removesuffix(" views")
        return {
            "channel_name": snippet.get("title"),
            "description": description,
            "country": snippet.get("country"),
            "joined_date": joined,
            "auto_generated": is_auto_generated,
            "real_name": snippet.get("customUrl"),
            "subscribers": None if stats.get("hiddenSubscriberCount") else stats.get("subscriberCount"),
            "total_views": viewCount,
            "upload_count": stats.get("videoCount"),
            "age": None,
            "hometown": None,
        }

    # public methods
    def GetVideoCount(self,channelId:str) -> str | int | t.Literal[0]:
        return self._gdata_getvideocount(channelId)
    def GetVideoCountBatch(self,channelIds:list) -> dict | dict[t.Any, t.Any]:
        return self._gdata_getvideocountforsearch(channelIds)
    def GetVideoInfo(self,videoId:str) -> dict[str, t.Any] | None:
        return self._get_video_info(video_id=videoId)
    def RecommendedChannels(self,oauth_token:str,maxResults:int=25,hl:str="en",gl:str="US") -> list | None:
        return self._get_recomm_channels(oauth_token=oauth_token,maxResults=maxResults,hl=hl,gl=gl)
    def GetPopularVideos(self,limit:int=25) -> dict[str, list[dict[str, t.Any]]]:
        return self._get_trending(limit=limit)
    def GetChannelInfo(self,channelId:str) -> dict[str, t.Any] | None:
        return self._get_channel_info(channelId)

class InnerTubeAPI:
    def __init__(self, innerTubeKey:str) -> None:
        self.INNERTUBE_URL = "https://www.youtube.com/youtubei/v1"
        self.INNERTUBE_KEY = innerTubeKey
        self.GDataAPI = GDataAPI(GDataKey=GDATA_API_KEY)
        self._client_version = None
        self._client_version_lock = threading.Lock()
        self._client_version_last_fetch = 0
        self._CLIENT_VERSION_TTL = 3600
        self._visitor_data = None
        self._visitor_data_lock = threading.Lock()
        self._visitor_data_last_fetch = 0
        self._VISITOR_DATA_TTL = 3600
    def _getidfromhandle(self,handle):
        URL = f"{self.INNERTUBE_URL}/navigation/resolve_url"
        payload = {
            "context": self._build_innertube_context(),
            "url": f"https://youtube.com/{handle}"
        }
        headers = self._build_innertube_headers()
        params = self._build_innertube_params()
        try:
            r = requests.post(URL,json=payload,headers=headers,timeout=10,params=params)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return None
        return data.get("endpoint",{}).get("browseEndpoint",{}).get("browseId")
    def _browse(self,browseId,params=None):
        url = f"{self.INNERTUBE_URL}/browse"
        payload = {
            "context": self._build_innertube_context(),
            "browseId": browseId
        }
        if params:
            payload["params"] = params
        headers = self._build_innertube_headers()
        params = self._build_innertube_params()
        try:
            r = requests.post(url,json=payload,headers=headers,timeout=10,params=params)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException,ValueError):
            return None
    @staticmethod
    def _extract_continuation(data):
        def tkn(obj):
            if isinstance(obj,dict):
                if "continuationCommand" in obj:
                    cmd = obj["continuationCommand"]
                    if isinstance(cmd,dict):
                        token = cmd.get("token")
                        if token:
                            return token
                for key in ("nextContinuationData","reloadContinuationData"):
                    val = obj.get(key)
                    if isinstance(val,dict):
                        token = val.get("continuation")
                        if token:
                            return token
                for value in obj.values():
                    token = tkn(value)
                    if token:
                        return token
            elif isinstance(obj,list):
                for v in obj:
                    token = tkn(v)
                    if token:
                        return token
            return None
        return tkn(data)
    @staticmethod
    def _extract_continuation_renderer(data,rtype):
        out = []
        def extr(obj):
            if isinstance(obj,dict):
                renderer = obj.get(rtype)
                if isinstance(renderer,dict):
                    out.append(renderer)
                for value in obj.values():
                    extr(value)
            elif isinstance(obj,list):
                for value in obj:
                    extr(value)
        extr(data)
        return out
    @staticmethod
    def _extract_continuation_from_continuation(data):
        tokens = []
        cmds = data.get("onResponseReceivedCommands",[])
        for cmd in cmds:
            action = cmd.get("appendContinuationItemsAction",{})
            for item in action.get("continuationItems",[]):
                renderer = item.get("continuationItemRenderer")
                if not renderer:
                    continue
                endpoint = renderer.get("continuationEndpoint",{})
                command = endpoint.get("continuationCommand",{})
                token = command.get("token")
                if token:
                    tokens.append(token)
        return tokens[-1] if tokens else None
    @staticmethod
    def _extract_continuation_cnt_pl(data):
        if not isinstance(data,dict):
            return []
        continuation_contents = data.get("continuationContents", {})
        grid = continuation_contents.get("gridContinuation")
        if isinstance(grid,dict):
            return grid.get("items",[])
        playlist = continuation_contents.get("playlistVideoListContinuation")
        if isinstance(playlist,dict):
            return playlist.get("contents",[])
        return []
    @staticmethod
    def _extract_continuation_EX(data):
        if not isinstance(data,dict):
            return None
        for action in data.get("onResponseReceivedActions",[]):
            if not isinstance(action,dict):
                continue
            append = action.get("appendContinuationItemsAction")
            if not isinstance(append,dict):
                continue
            for item in append.get("continuationItems",[]):
                if not isinstance(item,dict):
                    continue
                renderer = item.get("continuationItemRenderer")
                if not isinstance(renderer,dict):
                    continue
                endpoint = renderer.get("continuationEndpoint",{})
                cmd = endpoint.get("continuationCommand",{})
                tkn = cmd.get("token")
                if tkn:
                    return tkn
        return None
    def _searchrenderers(self, data, key):
        if not data:
            return []
        return self._find_all(data, key)
    def _fetch_subscription_activity(self,hl="en",gl="US",oauth_token=None,continuation_token=None):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "TVHTML5",
            "authorization": f"Bearer {oauth_token}",
            "user-agent": TV_USERAGENT,
            "referer": "https://www.youtube.com/tv",
            "origin": "https://www.youtube.com",
        }
        payload = {
            "context": {
                "client": {
                    "originalUrl": "https://www.youtube.com/tv",
                    "hl": hl,
                    "gl": gl,
                    "platform": "TV",
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                },
            },
        }
        params = self._build_innertube_params()
        url = f"{self.INNERTUBE_URL}/browse"
        if continuation_token:
            payload["continuation"] = continuation_token
        else:
            payload["browseId"] = "FEsubscriptions"
        try:
            r = requests.post(url,json=payload,headers=headers,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError):
            return None
    def _build_activity_feed(self,hl="en",gl="US",oauth_token=None,remove_shorts=False):
        if not oauth_token:
            return None
        # no continuation for the all tab, really
        data = self._fetch_subscription_activity(hl,gl,oauth_token,None)
        if not data:
            return []
        try:
            sections = data.get("contents",{}).get("tvBrowseRenderer",{}).get("content",{}).get("tvSecondaryNavRenderer",{}).get("sections",[])
        except (KeyError,TypeError):
            traceback.print_exc()
            return []
        tab_all = None
        for s in sections:
            tabs = s.get("tvSecondaryNavSectionRenderer",{}).get("tabs",[])
            for t in tabs:
                renderer = t.get("tabRenderer",{})
                if (renderer.get("title") == "All" and renderer.get("endpoint", {}).get("browseEndpoint", {}).get("browseId", "").lower() == "fesubscriptions"):
                    tab_all = renderer
                    break
            if tab_all:
                break
        if not tab_all:
            return []
        section_contents = tab_all.get("content",{}).get("tvSurfaceContentRenderer",{}).get("content",{}).get("sectionListRenderer",{}).get("contents",[])
        items = []
        for s in section_contents:
            shelf = s.get("shelfRenderer",{})
            horizontal = shelf.get("content",{}).get("horizontalListRenderer",{})
            items.extend(horizontal.get("items",[]))
        out = []
        seen = set()
        for i in items:
            tile = i.get("tileRenderer")
            if not tile:
                continue
            contentType = tile.get("contentType")
            style = tile.get("style")
            isshort = (contentType == "TILE_CONTENT_TYPE_SHORTS" or style == "TILE_STYLE_YTLR_SHORTS" or "reelWatchEndpoint" in tile.get("onSelectCommand",{}))
            if remove_shorts and isshort:
                print("removing short")
                continue
            vid = tile.get("contentId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            view_count = short_byline = None
            meta = tile.get("metadata",{}).get("tileMetadataRenderer",{})
            title = simpletext(meta.get("title",{}))
            duration = None
            overlays = tile.get("header",{}).get("tileHeaderRenderer",{}).get("thumbnailOverlays",[])
            line = meta.get("lines",[])
            if len(line) > 0:
                lineitems = line[0].get("lineRenderer",{}).get("items",[])
                if lineitems:
                    short_byline = simpletext(lineitems[0].get("lineItemRenderer",{}).get("text",{}))
            if len(line) > 1:
                lineitems = line[1].get("lineRenderer",{}).get("items",[])
                tests = []
                for i in lineitems:
                    text = simpletext(i.get("lineItemRenderer",{}).get("text",{}))
                    if text:
                        tests.append(text)
                for t in tests:
                    if "view" in t.lower():
                        view_count = t.removesuffix("views") if t.endswith("views") else t.removesuffix("view")
            for o in overlays:
                renderer = o.get("thumbnailOverlayTimeStatusRenderer")
                if renderer:
                    duration = simpletext(renderer.get("text",{}))
                    break
            out.append({
                "item_type": "compact_video",
                "action_type": "WL",
                "video": {
                    "video_id": vid,
                    "title": title,
                    "view_count": fmt_view(parsecount(view_count)),
                    "short_byline": short_byline,
                    "public_name": short_byline,
                    "duration": fmt_duration(duration),
                    "watch_link": f"/watch?v={vid}",
                    "thumbnail_info": {
                        "url": funcmod.getThumbnail(vid),
                    }
                }
            })
        return out
    def _fetch_ownvideos(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return {}
        payload = {
            "context": self._build_tv_context(hl,gl)
        }
        if not continuation_token:
            payload["browseId"] = "FEmy_videos"
        else:
            payload["continuation"] = continuation_token
        headers = self._build_tv_headers(oauth_token)
        params = self._build_innertube_params()
        url = f"{self.INNERTUBE_URL}/browse"
        try:
            r = requests.post(url,params=params,json=payload,headers=headers)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return {}
        return data
    def _get_ownvideos(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return {},None
        data = self._fetch_ownvideos(oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
        if not data:
            return {},None
        try:
            items = data.get("contents",{}).get("tvBrowseRenderer",{}).get("content",{}).get("tvSurfaceContentRenderer",{}).get("content",{}).get("gridRenderer",{}).get("items",[])
        except (KeyError,ValueError,TypeError):
            traceback.print_exc()
            return {},None
        out = []
        seen = set()
        if continuation_token:
            next_tkn = self._extract_continuation_from_continuation(data)
        else:
            next_tkn = self._extract_continuation(data)
        for i in items:
            tile = i.get("tileRenderer",{})
            vid = tile.get("contentId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            meta = tile.get("metadata",{}).get("tileMetadataRenderer",{})
            title = simpletext(meta.get("title"))
            public_name = short_byline = simpletext(meta.get("lines",[])[0].get("lineRenderer",{}).get("items",[])[0].get("lineItemRenderer",{}).get("text",{}))
            __view_count = simpletext(meta.get("lines",[])[1].get("lineRenderer",{}).get("items",[])[0].get("lineItemRenderer",{}).get("text",{}))
            _duration = ""
            overlays = tile.get("header",{}).get("tileHeaderRenderer",{}).get("thumbnailOverlays",[])
            for o in overlays:
                renderer = o.get("thumbnailOverlayTimeStatusRenderer")
                if renderer:
                    _duration = simpletext(renderer.get("text",{}))
                    break
            actualduration = fmt_duration(_duration)
            actualviewcount = fmt_view(parsecount(__view_count))
            out.append({
                "item_type": "compact_video",
                "action_type": "WL",
                "video": {
                    "encrypted_id": vid,
                    "title": title,
                    "view_count": actualviewcount,
                    "short_byline": short_byline,
                    "public_name": public_name,
                    "duration": actualduration,
                    "watch_link": f"/watch?v={vid}",
                    "thumbnail_info": {
                        "url": funcmod.getThumbnail(vid),
                    }
                }
            })
        return out,next_tkn
    @staticmethod
    def _lengthtext(video_renderer):
        return simpletext(video_renderer.get("lengthText")) or ""
    def _search_continuation_unauth(self,continuation_token,hl="en",gl="US"):
        payload = {
            "context": self._build_innertube_context(hl=hl,gl=gl),
            "continuation": continuation_token
        }
        headers = self._build_innertube_headers()
        url = f"{self.INNERTUBE_URL}/search"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError) as e:
            print(f"[continuation]: {e}")
            return None
    def _browse_continuation_unauth(self,continuation_token,hl="en",gl="US"):
        payload = {
            "context": self._build_innertube_context(hl=hl,gl=gl),
            "continuation": continuation_token
        }
        headers = self._build_innertube_headers()
        params = self._build_innertube_params()
        url = f"{self.INNERTUBE_URL}/browse"
        try:
            r = requests.post(url,json=payload,headers=headers,params=params,timeout=15)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError) as e:
            print(f"[continuation]: {e}")
            return None
    def _fetch_client_version(self):
        with self._client_version_lock:
            now = time.time()
            if self._client_version and (now-self._client_version_last_fetch)<self._CLIENT_VERSION_TTL:
                return self._client_version
            try:
                r = requests.get("https://www.youtube.com",headers={"User-Agent": API_USERAGENT},timeout=10)
                r.raise_for_status()
                match = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"',r.text)
                if match:
                    self._client_version = match.group(1)
                    self._client_version_last_fetch = now
                    return self._client_version
            except Exception as e:
                print(f"[youtubei] Error fetching client version: {e}")
            self._client_version = "2.20260714.05.00"
            self._client_version_last_fetch = now
            return self._client_version
    def _channel_action(self,oauth_token,channelId,subscribing=False,hl="en",gl="US"):
        if not oauth_token or not channelId:
            return None
        if not re.search(CHANNEL_ID_RE,channelId):
            return None
        payload = {
            "context": {
                "client": {
                    "clientName": "TVHTML5",
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv",
                    "clientVersion": TV_CLIENT_VERSION,
                    "hl": hl,
                    "gl": gl
                }
            },
            "channelIds": [channelId],
            "params": PARAM_SUBSCRIBE if subscribing else PARAM_UNSUBSCRIBE,
        }
        headers = {
            "content-type": "application/json",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "authorization": f"Bearer {oauth_token}"
        }
        base = f"{self.INNERTUBE_URL}/subscription"
        url = f"{base}/{'subscribe' if subscribing else 'unsubscribe'}"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,params=params,json=payload,headers=headers,timeout=15)
            r.raise_for_status()
            return r.ok
        except requests.RequestException:
            return False
    def _fetch_visitor_data(self):
        with self._visitor_data_lock:
            now = time.time()
            if self._visitor_data and (now-self._visitor_data_last_fetch)<self._VISITOR_DATA_TTL:
                return self._visitor_data
            try:
                headers = {
                    "Origin": "https://www.youtube.com",
                    "Referer": "https://www.youtube.com/",
                    "User-Agent": API_USERAGENT,
                }
                resp = requests.get("https://www.youtube.com/sw.js_data",headers=headers,timeout=10)
                resp.raise_for_status()
                text = resp.text
                prefix = ")]}'\n"
                if text.startswith(prefix):
                    text = text[len(prefix):]
                data = json.loads(text)
                self._visitor_data = data[0][2][0][0][13]
                self._visitor_data_last_fetch = now
                return self._visitor_data
            except Exception as e:
                print(f"[youtubei] Error fetching visitor data: {e}")
                self._visitor_data_last_fetch = now
                self._visitor_data = "0"
                return self._visitor_data
    def _fetch_visitor_data_ASSISTANT(self):
        with self._visitor_data_lock:
            now = time.time()
            if self._visitor_data and (now-self._visitor_data_last_fetch)<self._VISITOR_DATA_TTL:
                return self._visitor_data
            headers = {
                "Content-Type": "application/json",
                "X-YouTube-Client-Name": "84"
            }
            URL = f"{self.INNERTUBE_URL}/next"
            params = self._build_innertube_params()
            payload = {
                "context": {
                    "client": {
                        "clientName": "GOOGLE_ASSISTANT",
                        "clientVersion": "0.1",
                        "hl": "en",
                        "gl": "US",
                    }
                }
            }
            try:
                r = requests.post(URL,params=params,headers=headers,json=payload)
                r.raise_for_status()
                data = r.json()
                visitor_data = data.get("responseContext",{}).get("visitorData","0")
                if visitor_data:
                    self._visitor_data = visitor_data
                    self._visitor_data_last_fetch = now
                    return self._visitor_data
            except (ValueError,requests.RequestException):
                return self._visitor_data or "0"
    def _build_innertube_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": API_USERAGENT,
            "X-Goog-Visitor-Id": self._fetch_visitor_data(),
            "X-YouTube-Client-Name": "1",
            "Referer": "https://www.youtube.com/",
            "Origin": "https://www.youtube.com/"
        }
    def _build_innertube_params(self):
        return {
            "key": self.INNERTUBE_KEY,
        }
    def _build_innertube_context(self,hl="en",gl="US",videoId=None,originalUrl=None,graftUrl=None):
        _graft_url = graftUrl if graftUrl else (f"/watch?v={videoId}" if videoId else "/")
        _original_url = originalUrl if originalUrl else "https://youtube.com"
        return {
            "client": {
                "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "browserName": "Chrome",
                "browserVersion": "150.0.0.0",
                "clientFormFactor": "UNKNOWN_FORM_FACTOR",
                "configInfo": {
                    "appInstallData": ""
                },
                "clientName": "WEB",
                "clientVersion": self._fetch_client_version(),
                "hl": hl,
                "gl": gl,
                "visitorData": self._fetch_visitor_data(),
                "deviceMake": "",
                "deviceModel": "",
                "mainAppWebInfo": {
                    "graftUrl": _graft_url,
                    "isWebNativeShareAvailable": True,
                    "pwaInstallabilityStatus": "PWA_INSTALLABILITY_STATUS_CAN_BE_INSTALLED",
                    "webDisplayMode": "WEB_DISPLAY_MODE_BROWSER"
                },
                "memoryTotalKbytes": "8000000",
                "originalUrl": _original_url,
                "osName": "X11",
                "osVersion": "",
                "platform": "DESKTOP",
                "remoteHost": "2003:d2:cf2b:a85e:517a:451f:a30d:fbf5",
                "screenDensityFloat": 1,
                "screenHeightPoints": 953,
                "screenPixelDensity": 1,
                "screenWidthPoints": 974,
                "timeZone": "Europe/Berlin",
                "userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36,gzip(gfe)",
                "userInterfaceTheme": "USER_INTERFACE_THEME_DARK",
                "utcOffsetMinutes": 120,
            },
            "request": {
                "internalExperimentFlags": [],
                "useSsl": True
            },
            "user": {
                "enableSafetyMode": False,
                "lockedSafetyMode": False
            }
        }
    def _build_ps4_tv_context(self,hl="en",gl="US",safe_mode=False,originalUrl="https://www.youtube.com/tv"):
        return {
            "client": {
                "screenWidthPoints": 1920,
                "screenHeightPoints": 1080,
                    "utcOffsetMinutes": 120,
                    "hl": hl,
                    "gl": gl,
                    "deviceMake": "Sony",
                    "deviceModel": "PS4",
                    "userAgent": PS4_TV_USER_AGENT,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "osName": "PlayStation 4",
                    "osVersion": "",
                    "originalUrl": originalUrl,
                    "theme": "CLASSIC",
                    "platform": "GAME_CONSOLE",
                    "clientFormFactor": "UNKNOWN_FORM_FACTOR",
                    "webpSupport": False,
                    "userInterfaceTheme": "USER_INTERFACE_THEME_DARK",
                    "timeZone": "Europe/Rome",
                    "browserName": "Steel",
                    "browserVersion": "01.00.01.75",
                    "platformDetail": "PLATFORM_DETAIL_GAME",
                    "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "screenDensityFloat": 1,
                    "windowWidthPoints": 1920,
                    "windowHeightPoints": 1080,
                    "memoryTotalKBytes": "8000000",
                },
                "user": {
                    "enableLockedSafetyMode": safe_mode,
                }
            }
    def _build_tv_headers(self,oauth_token=None):
        headers = {
            "content-type": "application/json",
            "origin": "https://www.youtube.com",
            "referer": "https://www.youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT,
            "x-goog-visitor-id": self._fetch_visitor_data(),
        }
        if oauth_token:
            headers["authorization"] = f"Bearer {oauth_token}"
        return headers
    def _build_tv_context(self,hl="en",gl="US",safe_mode=False,originalUrl="https://www.youtube.com/tv"):
        return {
            "client": {
                "clientName": "TVHTML5",
                "clientVersion": TV_CLIENT_VERSION,
                "originalUrl": originalUrl,
                "hl": hl,
                "gl": gl,
                "deviceMake": "Samsung",
                "deviceModel": "SmartTV",
                "visitorData": self._fetch_visitor_data(),
                "userAgent": TV_USERAGENT,
                "osName": "Tizen",
                "osVersion": "6.5",
                "theme": "CLASSIC",
                "clientFormFactor": "UNKNOWN_FORM_FACTOR",
                "remoteHost": "2003:d2:cf2b:a85e:517a:451f:a30d:fbf5",
                "webpSupport": False,
                "configInfo": {
                    "appInstallData": ""
                },
                "tvAppInfo": {
                    "appQuality": "TV_APP_QUALITY_LIMITED_ANIMATION",
                    "voiceCapability": {
                        "hasSoftMicSupport": False,
                        "hasHardMicSupport": False
                    },
                    "supportsNativeScrolling": False,
                },
                "userInterfaceTheme": "USER_INTERFACE_THEME_DARK",
                "timeZone": "Europe/Rome",
                "browserName": "SamsungBrowser",
                "browserVersion": "5.0",
                "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "windowWidthPoints": 1920,
                "windowHeightPoints": 1080,
                "screenDensityFloat": 1,
                "memoryTotalKbytes": "8000000"
            },
            "user": {
                "enableSafetyMode": safe_mode,
            },
        }
    def _rate_video(self,oauth_token,videoId,endpoint="like",hl="en",gl="US"):
        if not oauth_token or not videoId or not endpoint:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT
        }
        url_base = f"{self.INNERTUBE_URL}/like/"
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv"
                }
            },
            "target": {
                "videoId": videoId
            }
        }
        url = "%s%s"%(url_base,endpoint)
        params = self._build_innertube_params()
        try:
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=params)
            r.raise_for_status()
        except requests.RequestException:
            return False
        return True
    def _get_video_duration(self,videoId,hl="en",gl="US"):
        context = self._build_innertube_context(hl,gl)
        headers = self._build_innertube_headers()
        params = self._build_innertube_params()
        payload = {
            "context": context,
            "videoId": videoId
        }
        url = f"{self.INNERTUBE_URL}/player"
        try:
            r = requests.post(url,params=params,headers=headers,json=payload)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            return ""
        seconds = data.get("videoDetails",{}).get("lengthSeconds")
        if not seconds:
            return ""
        seconds = int(seconds)
        minutes,seconds = divmod(seconds,60)
        hours,minutes = divmod(minutes,60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    def _get_video_info(self, videoId, hl="en", gl="US"):
        context = self._build_innertube_context(hl,gl)
        headers = self._build_innertube_headers()
        payload = {
            "context": context,
            "videoId": videoId,
        }
        url = f"{self.INNERTUBE_URL}/player"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,params=params,headers=headers,json=payload,timeout=10)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return None
        details = data.get("videoDetails",{})
        if not details:
            return None
        seconds = int(details.get("lengthSeconds",0) or 0)
        return {
            "encrypted_id": details.get("videoId",videoId),
            "title": details.get("title",""),
            "duration": seconds,
            "author": details.get("author",""),
            "view_count": int(details.get("viewCount",0) or 0),
            "description": details.get("shortDescription",""),
            "is_live": details.get("isLiveContent",False),
        }
    def _find_all(self,obj,key):
        results = []
        if isinstance(obj,dict):
            for k,v in obj.items():
                if k == key:
                    results.append(v)
                results.extend(self._find_all(v,key))
        elif isinstance(obj,list):
            for item in obj:
                results.extend(self._find_all(item,key))
        return results
    def _get_playlist_fromsearch(self,playlistId,oauth_token=None,hl="en",gl="US",continuation_token=None):
        if not playlistId:
            return None,[],None
        next_tkn = None
        def _video_count(obj):
            if not obj:
                return None
            if "simpleText" in obj:
                return obj["simpleText"]
            runs = obj.get("runs")
            if runs:
                return "".join(run.get("text","") for run in runs)
            return None
        payload = {
            "context": {
                "client": {
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "originalUrl": "https://youtube.com/tv",
                    "platform": "TV",
                    "hl": hl,
                    "gl": gl,
                }
            },
        }
        url = f"{self.INNERTUBE_URL}/browse"
        params = self._build_innertube_params()
        headers = {
            "content-type": "application/json",
            "user-agent": TV_USERAGENT,
            "referer": "https://www.youtube.com/tv",
            "origin": "https://www.youtube.com",
            "x-youtube-client-name": "TVHTML5"
        }
        if oauth_token:
            headers["authorization"] = f"Bearer {oauth_token}"
        if continuation_token:
            payload["continuation"] = continuation_token
            try:
                # we don't really need authentication, especially for WEB that doesn't accept bearer credentials
                r = requests.post(url,params=params,json=payload,headers=headers,timeout=15)
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException,ValueError):
                return None,[],None
            next_tkn = self._extract_continuation(data)
            rightcol = data
            leftcol = None
            public_name = None
            description = None
            editpermission = False
            videocount = 0
        else:
            payload["browseId"] = f"VL{playlistId}"
            try:
                r = requests.post(url,params=params,json=payload,headers=headers,timeout=15)
                r.raise_for_status()
                data = r.json()
            except (requests.RequestException,ValueError):
                return None,[],None
            next_tkn = self._extract_continuation(data)
            try:
                leftcol = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["twoColumnRenderer"]["leftColumn"]["entityMetadataRenderer"]
                rightcol = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["twoColumnRenderer"]["rightColumn"]["playlistVideoListRenderer"]
            except (KeyError,TypeError,IndexError):
                return None,[],None
            public_name = simpletext(leftcol.get("title"))
            description = simpletext(leftcol.get("description"))
            editpermission = rightcol.get("isEditable",False)
            if isinstance(editpermission,str):
                editpermission = editpermission.lower().strip() == "true"
            videocount = 0
            bylines = leftcol.get("bylines",[])
            for i in bylines:
                for item in i.get("lineRenderer",{}).get("items",[]):
                    text = item.get("lineItemRenderer",{}).get("text",{})
                    testcount = _video_count(text) or ""
                    m = re.search(r"([\d,]+)\s+videos?",testcount,re.I)
                    if m:
                        videocount = int(m.group(1).replace(",",""))
                        break
                if videocount:
                    break
        videos = []
        if continuation_token:
            items = []
            if isinstance(rightcol,dict):
                continuation_contents = rightcol.get("continuationContents",{})
                if isinstance(continuation_contents,dict):
                    playlist_cont = continuation_contents.get("playlistVideoListContinuation")
                    if isinstance(playlist_cont,dict):
                        items = playlist_cont.get("contents",[])
                if not items:
                    items = rightcol.get("contents",[])
            if not isinstance(items,list):
                items = []
        else:
            items = rightcol.get("contents",[])
        for item in items:
            tile = item.get("tileRenderer")
            if not tile:
                continue
            videoId = tile.get("contentId")
            if not videoId:
                continue
            metadata = tile.get("metadata",{})
            tile_metadata = metadata.get("tileMetadataRenderer",{})
            title = simpletext(tile_metadata.get("title")) or ""
            tile_header = tile.get("header",{})
            header_renderer = tile_header.get("tileHeaderRenderer",{})
            length = ""
            overlays = header_renderer.get("thumbnailOverlays",[])
            for o in overlays:
                time_status = o.get("thumbnailOverlayTimeStatusRenderer",{})
                if time_status:
                    length = simpletext(time_status.get("text")) or ""
                    break
            short_byline = ""
            lines = tile_metadata.get("lines",[])
            for l in lines:
                linerender = l.get("lineRenderer",{})
                for i in linerender.get("items",[]):
                    item_renderer = i.get("lineItemRenderer",{})
                    text = item_renderer.get("text",{})
                    value = simpletext(text)
                    if value:
                        short_byline = value
                        break
                if short_byline:
                    break
            gdata_info = self.GDataAPI.GetVideoInfo(videoId)
            if gdata_info:
                view_count_ext = fmt_view(gdata_info["view_count"])
            videos.append({
                "ua": videoId,
                "encrypted_id": videoId,
                "title": title,
                "short_byline": short_byline,
                "nb": short_byline,
                "duration": length,
                "view_count": view_count_ext,
                "Sc": f"/watch?v={videoId}",
                "Jb": {
                    "url": funcmod.getThumbnail(videoId)
                },
                "thumbnail_info": {
                    "url": funcmod.getThumbnail(videoId),
                },
            })
        # if there's a continuation token, don't return a new playlist header, it'd be useless
        if continuation_token:
            return None,videos,next_tkn
        playlistheader = {
            "public_name": public_name,
            "manage_playlist_xsrf_token": "aaa",
            "is_owner_viewing": editpermission,
            "reversed": False,
            "next_url": None,
            "channel_url": None,
            "playlist": {
                "encrypted_id": playlistId,
                "full_encrypted_id": playlistId,
                "name": public_name,
                "title": public_name,
                "type": "PL",
                "video_count": videocount,
                "description": description or None,
            },
        }
        return playlistheader,videos,next_tkn
    @staticmethod
    def _ret_recommandations(data):
        if not data:
            return []
        recom = data.get("contents",{}).get("twoColumnWatchNextResults",{})
        res = recom.get("secondaryResults",{}).get("secondaryResults",{}).get("results")
        if res:
            return res
        res = recom.get("results",{}).get("results",{}).get("contents")
        if res:
            return res
        res = recom.get("results",{}).get("contents")
        if res:
            return res
        return []
    def _gettext(self,obj):
        if obj is None:
            return ""
        if isinstance(obj,str):
            return obj
        if isinstance(obj,dict):
            if "simpleText" in obj:
                return simpletext(obj)
            if "runs" in obj:
                return "".join(run.get("text","")for run in obj["runs"])
            if "content" in obj:
                return self._gettext(obj["content"])
            if "text" in obj:
                return self._gettext(obj["text"])
        return ""
    def _parse_lockup(self,lockup,current_video_id,is_channel_videos=False):
        vid = lockup.get("contentId")
        if not vid or vid == current_video_id:
            return None
        metadata = lockup.get("metadata",{})
        lockup_meta = metadata.get("lockupMetadataViewModel",{})
        title = self._gettext(lockup_meta.get("title"))
        content_meta = lockup_meta.get("metadata",{}).get("contentMetadataViewModel",{})
        rows = content_meta.get("metadataRows",[])
        metadata_parts = []
        for row in rows:
            for part in row.get("metadataParts",[]):
                text = self._gettext(part.get("text"))
                if text:
                    metadata_parts.append(text)
        thumbnail = lockup.get("contentImage",{}).get("thumbnailViewModel",{})
        thumbnail_info = {
            "url": funcmod.getThumbnail(vid),
            "width": 120,
            "height": 190,
        }
        duration = ""
        overlays = thumbnail.get("overlays",[])
        for overlay in overlays:
            bottom = overlay.get("thumbnailBottomOverlayViewModel")
            if not bottom:
                continue
            for badge in bottom.get("badges",[]):
                badge_vm = badge.get("thumbnailBadgeViewModel")
                if not badge_vm:
                    continue
                text = self._gettext(badge_vm.get("text"))
                if text:
                    duration = text
                    break
        public_name = ""
        view_count = ""
        if metadata_parts:
            public_name = metadata_parts[0]
        if not is_channel_videos:
            for r in rows:
                if not isinstance(r,dict):
                    continue
                for p in r.get("metadataParts",[]):
                    text = self._gettext(p.get("text")) or ""
                    accessibleLabel = p.get("accessibilityLabel","") or ""
                    if "view" in accessibleLabel.lower():
                        view_count = text
                        break
        else:
            for text in metadata_parts:
                lower = text.lower()
                if "views" in lower:
                    view_count = text.replace(" views","")
        return {
            "encrypted_id": vid,
            "title": title,
            "description": "",
            "duration": duration,
            "view_count": fmt_view(parsecount(view_count)),
            "public_name": public_name,
            "watch_link": f"/watch?v={vid}",
            "thumbnail_info": thumbnail_info,
        }
    def _fetch_related(self,videoId,hl="en",gl="US",continuation_token=None):
        if not videoId:
            return None
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20210401.08.00",
                    "hl": hl,
                    "gl": gl,
                }
            },
        }
        headers = {
            "content-type": "application/json",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com",
            "x-youtube-client-name": "1",
            "user-agent": API_USERAGENT,
            "x-youtube-client-version": "2.20210401.08.00"
        }
        url = f"{self.INNERTUBE_URL}/next"
        params = self._build_innertube_params()
        if continuation_token:
            payload["continuation"] = continuation_token
        else:
            payload["videoId"] = videoId
        try:
            r = requests.post(url=url,json=payload,headers=headers,params=params,timeout=15)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return None
        return data
    def _get_related(self,videoId:str,hl:str="en",gl:str="US",maxResults:int=30,continuation_token:str=None) -> tuple[list, None] | tuple[list | None]:
        out = []
        data = self._fetch_related(videoId,hl=hl,gl=gl,continuation_token=continuation_token)
        if not data:
            return [],None
        if continuation_token:
            items = []
            items.extend(self._extract_continuation_renderer(data,"compactVideoRenderer"))
            items.extend(self._extract_continuation_renderer(data,"videoRenderer"))
            lockups = self._extract_continuation_renderer(data,"lockupViewModel")
            for lockup in lockups:
                if maxResults <= len(out):
                    break
                result = self._parse_lockup(lockup,videoId)
                if result:
                    if result["encrypted_id"].startswith("PL"):
                        continue
                    out.append(result)
        else:
            items = self._ret_recommandations(data)
        for item in items:
            if maxResults <= len(out):
                break
            lockup = item.get("lockupViewModel")
            if lockup:
                result = self._parse_lockup(lockup,videoId)
                if result:
                    if result["encrypted_id"].startswith("PL"):
                        continue
                    out.append(result)
                continue
            v = item.get("compactVideoRenderer")
            if not v:
                v = item.get("videoRenderer")
            if not v:
                continue
            vid = v.get("videoId")
            if not vid or vid == videoId:
                continue
            thumbnail_info = {
                "url": funcmod.getThumbnail(vid),
                "width": 120,
                "height": 190,
            }
            out.append({
                "encrypted_id": vid,
                "title": simpletext(v.get("title")),
                "description": "",
                "duration": simpletext(v.get("lengthText")),
                "view_count": fmt_view(parsecount(simpletext(v.get("viewCountText")))),
                "public_name": simpletext(v.get("shortBylineText")),
                "watch_link": f"/watch?v={vid}",
                "thumbnail_info": thumbnail_info
            })
        next_tkn = self._extract_continuation(data)
        return out,next_tkn
    def _get_channel_content(self,channelId,hl="en",gl="US",continuation_token=None,currentVideoId=None):
        if not channelId:
            return [],None
        if not re.search(CHANNEL_ID_RE,channelId):
            return [],None
        if continuation_token:
            data = self._browse_continuation_unauth(continuation_token,hl=hl,gl=gl)
            if not data:
                return [],None
            lockups = self._extract_continuation_renderer(data,"lockupViewModel")
            next_tkn = self._extract_continuation_EX(data)
        else:
            data = self._browse(channelId,params="EgZ2aWRlb3MYAyAAcAHyBg0KCzoEIgIIBKIBAggB")
            if not data:
                return [],None
            lockups = self._extract_continuation_renderer(data,"lockupViewModel")
            next_tkn = self._extract_continuation(data)
        seen = set()
        out = []
        for lockup in lockups:
            video = self._parse_lockup(lockup,currentVideoId,is_channel_videos=True)
            if not video:
                continue
            video_id = video.get("encrypted_id")
            if video_id:
                if video_id in seen:
                    continue
                seen.add(video_id)
            out.append(video)
        return out,next_tkn
    def _is_subscribed(self,oauth_token,channelId,hl="en",gl="US"):
        if not oauth_token:
            return None
        valid = re.search(CHANNEL_ID_RE,channelId)
        if not valid:
            return None
        payload = {
            "context": {
                "client": {
                    "platform": "TV",
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "originalUrl": "https://youtube.com/tv",
                    "hl": hl,
                    "gl": gl,
                }
            },
            "browseId": channelId
        }
        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "TVHTML5",
            "referer": "https://youtube.com/tv",
            "origin": "https://youtube.com/",
            "authorization": f"Bearer {oauth_token}",
            "user-agent": TV_USERAGENT
        }
        url = f"{self.INNERTUBE_URL}/browse"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,params=params,json=payload,headers=headers,timeout=15)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            return None
        try:
            buttons = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["header"]["channelHeaderRenderer"]["buttons"]
        except (KeyError,TypeError):
            return None
        for btn in buttons:
            renderer = btn.get("subscribeButtonRenderer")
            if not renderer:
                continue
            if renderer.get("channelId") != channelId:
                continue
            subscribed = renderer.get("subscribed")
            if isinstance(subscribed,bool):
                return subscribed
            return None
        return None
    @staticmethod
    def _get_featured_video(main):
        tabs = main.get("contents",{}).get("twoColumnBrowseResultsRenderer",{}).get("tabs",[])
        for tab in tabs:
            renderer = tab.get("tabRenderer",{})
            if not renderer.get("selected"):
                continue
            section_list = renderer.get("content",{}).get("sectionListRenderer",{})
            for section in section_list.get("contents",[]):
                item_section = section.get("itemSectionRenderer",{})
                for item in item_section.get("contents",[]):
                    actualfeat = item.get("channelVideoPlayerRenderer")
                    if actualfeat:
                        return actualfeat
        return None
    def _extract_metadata_rows(self,about_data):
        rows = self._find_all(about_data,"metadataRows")
        parts = []
        for row_list in rows:
            for row in row_list:
                parts.extend(row.get("metadataParts",[]))
        return [p.get("text",{}).get("content","") for p in parts if p.get("text",{}).get("content")]
    @staticmethod
    def _shelf_title(shelf):
        try:
            runs = shelf["headerRenderer"]["shelfHeaderRenderer"]["avatarLockup"]["avatarLockupRenderer"]["title"]["runs"]
            return runs[0].get("text","")
        except (KeyError,IndexError,TypeError):
            return ""
    def _request_playlists(self,oauth_token,hl="en",gl="US"):
        payload = {
            "context": {
                "client": {
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv",
                    "hl": hl,
                    "gl": gl
                }
            },
            "browseId": "FEplaylist_aggregation"
        }
        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "TVHTML5",
            "authorization": f"Bearer {oauth_token}",
            "user-agent": TV_USERAGENT,
            "origin": "https://youtube.com/",
            "referer": "https://youtube.com/tv"
        }
        url = f"{self.INNERTUBE_URL}/browse"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,headers=headers,timeout=15,json=payload,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError):
            return None
    def _get_playlists(self,oauth_token,hl="en",gl="US",continuation_token=None):
        data = self._request_playlists(oauth_token=oauth_token,hl=hl,gl=gl)
        playlists = {}
        try:
            items = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["gridRenderer"]["items"]
        except (KeyError,TypeError):
            return playlists
        for i in items:
            tile = i.get("tileRenderer")
            if not tile:
                continue
            playlist_id = tile.get("contentId")
            if not playlist_id:
                continue
            try:
                runs = tile["header"]["tileHeaderRenderer"]["thumbnailOverlays"][0]["thumbnailOverlayTimeStatusRenderer"]["text"]["runs"]
                count = int(fmt_view(runs[0]["text"]))
            except (KeyError,IndexError,TypeError,ValueError):
                continue
            meta = tile.get("metadata",{})
            title = simpletext(meta.get("tileMetadataRenderer",{}).get("title",{}))
            visibility = ""
            for line in meta.get("lines",[]):
                for item in line.get("lineRenderer",{}).get("items",[]):
                    text = item.get("lineItemRenderer",{}).get("text",{})
                    visibilityst = simpletext(text)
                    if visibilityst.lower().strip() in ("public","unlisted","private"):
                        visibility = visibilityst.lower().strip()
                        break
                if visibility:
                    break
            public = visibility == "public"
            playlists[playlist_id] = {
                "title": title,
                "video_count": count,
                "is_public": public
            }
        return playlists
    def _remove_from_playlist(self,oauth_token,playlistId,videoId,hl="en",gl="US"):
        if not oauth_token or not playlistId or not videoId:
            return None
        payload = {
            "context": {
                "client": {
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv",
                    "hl": hl,
                    "gl": gl
                }
            },
            "playlistId": playlistId,
            "actions": [
                {
                    "action": "ACTION_REMOVE_VIDEO_BY_VIDEO_ID",
                    "removedVideoId": videoId
                }
            ],
        }
        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "TVHTML5",
            "origin": "https://youtube.com/",
            "referer": "https://youtube.com/tv",
            "authorization": f"Bearer {oauth_token}",
            "user-agent": TV_USERAGENT
        }
        url = f"{self.INNERTUBE_URL}/browse/edit_playlist"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,params=params,headers=headers,json=payload,timeout=15)
            r.raise_for_status()
            data = r.json()
            return data.get("status","STATUS_ERROR")
        except (requests.RequestException,ValueError):
            return "STATUS_ERROR"
    # based on
    # https://github.com/ReviveMii/riivivetube/blob/ed81d5fda29b2c3620f3b741c0d5677e9756a525/youtubei.py#L1002
    def _fetch_liked_videos(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT
        }
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv"
                }
            },
        }
        if not continuation_token:
            payload["browseId"] = "VLLL"
        else:
            payload["continuation"] = continuation_token
        try:
            url = f"{self.INNERTUBE_URL}/browse"
            params = self._build_innertube_params()
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=params)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            return None
        return data
    def _add_to_playlist(self,oauth_token,playlistId,videoId,hl="en",gl="US"):
        if not oauth_token or not playlistId or not videoId:
            return None
        payload = {
            "context": {
                "client": {
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "hl": hl,
                    "gl": gl,
                    "originalUrl": "https://youtube.com/tv"
                }
            },
            "playlistId": playlistId,
            "actions": [
                {
                    "action": "ACTION_ADD_VIDEO",
                    "addedVideoId": videoId,
                }
            ],
        }
        headers = {
            "content-type": "application/json",
            "x-youtube-client-name": "TVHTML5",
            "referer": "https://youtube.com/tv",
            "origin": "https://youtube.com",
            "user-agent": TV_USERAGENT,
            "authorization": f"Bearer {oauth_token}"
        }
        url = f"{self.INNERTUBE_URL}/browse/edit_playlist"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,params=params,headers=headers,json=payload,timeout=15)
            r.raise_for_status()
            data = r.json()
            return data.get("status","STATUS_SUCCEEDED")
        except (requests.RequestException,ValueError):
            return "STATUS_ERROR"
    # based on
    # https://github.com/ReviveMii/riivivetube/blob/ed81d5fda29b2c3620f3b741c0d5677e9756a525/youtubei.py#L474
    def _fetch_river_feed(self,oauth_token,hl="en",gl="US"):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://www.youtube.com",
            "referer": "https://www.youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT,
        }
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "originalUrl": "https://www.youtube.com/tv",
                    "platform": "TV",
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                }
            },
            "browseId": "FEwhat_to_watch"
        }
        url = f"{self.INNERTUBE_URL}/browse"
        params = self._build_innertube_params()
        try:
            r = requests.post(url,json=payload,headers=headers,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError):
            return None
    def _build_river_feed(self,oauth_token,hl="en",gl="US"):
        try:
            data = self._fetch_river_feed(oauth_token=oauth_token,hl=hl,gl=gl)
        except:
            return [],None
        try:
            sections = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["sectionListRenderer"]["contents"]
        except (KeyError,TypeError):
            return [],None
        shelfgroups = []
        seen = set()
        feeditems = []
        for section in sections:
            shelf = section.get("shelfRenderer")
            if not shelf: continue
            title = self._shelf_title(shelf)
            items = shelf.get("content",{}).get("horizontalListRenderer",{}).get("items",[])
            shelfitems = []
            for item in items:
                tile = item.get("tileRenderer")
                if not tile: continue
                shelfitem = self._shelf_item_ex(tile)
                vid = shelfitem["content_item"]["ua"]
                if not vid: continue
                shelfitems.append(shelfitem)
                if vid not in seen:
                    seen.add(vid)
                    feeditems.append(shelfitem["content_item"])
            if shelfitems:
                shelfgroups.append({
                    "title": title,
                    "items": shelfitems,
                    "view_url": ""
                })
        shelves = {
            "shelf_groups": [shelfgroups]
        } if shelfgroups else None
        return feeditems,shelves
    # based on
    # https://github.com/ReviveMii/riivivetube/blob/ed81d5fda29b2c3620f3b741c0d5677e9756a525/youtubei.py#L893
    def _fetch_watch_later(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://youtube.com/",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT
        }
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv"
                }
            },
        }
        if continuation_token:
            payload["continuation"] = continuation_token
        else:
            payload["browseId"] = "FEmy_youtube"
            payload["params"] = WATCH_LATER_PLAYLIST
        try:
            url = f"{self.INNERTUBE_URL}/browse"
            params = self._build_innertube_params()
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError):
            return None
    def _build_wl_playlist(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return [],None
        data = self._fetch_watch_later(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
        if not data:
            return [],None
        tiles = []
        try:
            if continuation_token:
                items = self._extract_continuation_cnt_pl(data)
            else:
                items = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["gridRenderer"]["items"]
            for item in items:
                tile = item.get("tileRenderer")
                if tile:
                    tiles.append(tile)
        except (KeyError,ValueError,AttributeError):
            pass
        seen = set()
        feeditems = []
        shelfitems = []
        for tile in tiles:
            vid = tile.get("contentId")
            if not vid:
                continue
            if vid in seen:
                continue
            seen.add(vid)
            shelfitem = self._shelf_item_ex(tile)
            gdata_info = self.GDataAPI.GetVideoInfo(vid)
            if gdata_info:
                shelfitem["content_item"]["view_count"] = fmt_view(gdata_info["view_count"])
            shelfitems.append(shelfitem)
            feeditems.append(shelfitem["content_item"])
        next_tkn = self._extract_continuation(data)
        return feeditems,next_tkn
    # based on
    # https://github.com/ReviveMii/riivivetube/blob/ed81d5fda29b2c3620f3b741c0d5677e9756a525/youtubei.py#L638
    def _fetch_watch_history(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT
        }
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv"
                }
            },
        }
        if not continuation_token:
            payload["browseId"] = "FEhistory"
        else:
            payload["continuation"] = continuation_token
        try:
            url = f"{self.INNERTUBE_URL}/browse"
            params = self._build_innertube_params()
            r = requests.post(url,json=payload,headers=headers,timeout=20,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (ValueError,requests.RequestException):
            return None
    def _build_watch_history_feed(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return [],None
        data = self._fetch_watch_history(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
        if not data:
            return [],None
        try:
            if continuation_token:
                items = self._extract_continuation_cnt_pl(data)
            else:
                items = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["gridRenderer"]["items"]
        except (KeyError,TypeError):
            return [],None
        seen = set()
        feeditems = []
        shelfitems = []
        for item in items:
            tile = item.get("tileRenderer")
            if not tile:
                continue
            vid = tile.get("contentId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            shelfitem = self._shelf_item_ex(tile)
            shelfitems.append(shelfitem)
            feeditems.append(shelfitem["content_item"])
        next_tkn = self._extract_continuation(data)
        return feeditems,next_tkn
    def _fetch_subscriptions(self,oauth_token,hl="en",gl="US"):
        if not oauth_token:
            return None
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://youtube.com",
            "referer": "https://youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT
        }
        payload = {
            "context": {
                "client": {
                    "hl": hl,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://youtube.com/tv"
                }
            },
            "browseId": "FEchannels"
        }
        try:
            url = f"{self.INNERTUBE_URL}/browse"
            params = self._build_innertube_params()
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=params)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError):
            return None
    def _build_subscriptions_page(self,oauth_token,maxResults=25,hl="en",gl="US"):
        if not oauth_token:
            return None
        data = self._fetch_subscriptions(oauth_token,hl=hl,gl=gl)
        if not data:
            return None
        try:
            sections = data["contents"]["tvBrowseRenderer"]["content"]["tvSecondaryNavRenderer"]["sections"][0]["tvSecondaryNavSectionRenderer"]["tabs"][0]["tabRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["sectionListRenderer"]["contents"]
        except (KeyError,IndexError,TypeError):
            return None
        seen = set()
        out = []
        for section in sections:
            if len(out) >= maxResults:
                break
            shelf = section.get("shelfRenderer")
            if not shelf:
                continue
            items = shelf.get("content",{}).get("horizontalListRenderer",{}).get("items",[])
            for item in items:
                if len(out) >= maxResults:
                    break
                tile = item.get("tileRenderer")
                if not tile:
                    continue
                f = self._flat_channel(tile)
                if not f["channel_id"] or f["channel_id"] in seen:
                    continue
                seen.add(f["channel_id"])
                out.append(f)
        return out
    def _build_favorites_feed(self,oauth_token,hl="en",gl="US",continuation_token=None):
        if not oauth_token:
            return [],None
        data = self._fetch_liked_videos(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
        if not data:
            return [],None
        tiles = []
        try:
            if continuation_token:
                items = self._extract_continuation_cnt_pl(data)
            else:
                items = data["contents"]["tvBrowseRenderer"]["content"]["tvSurfaceContentRenderer"]["content"]["twoColumnRenderer"]["rightColumn"]["playlistVideoListRenderer"]["contents"]
            for i in items:
                tile = i.get("tileRenderer")
                if tile:
                    tiles.append(tile)
        except (KeyError,TypeError):
            pass
        seen = set()
        feeditems = []
        shelfitems = []
        for tile in tiles:
            vid = tile.get("contentId")
            if not vid:
                continue
            if vid in seen:
                continue
            seen.add(vid)
            shelfitem = self._shelf_item_ex(tile)
            shelfitems.append(shelfitem)
            feeditems.append(shelfitem["content_item"])
        next_tkn = self._extract_continuation(data)
        return feeditems,next_tkn
    def _flat_channel(self,tile):
        header = tile.get("header",{}).get("tileHeaderRenderer",{})
        meta = tile.get("metadata",{}).get("tileMetadataRenderer",{})
        channelId = tile.get("contentId","")
        title = meta.get("title",{}).get("simpleText","")
        handle = ""
        sub_count_text = ""
        lines = meta.get("lines",[])
        if len(lines) > 0:
            items = lines[0].get("lineRenderer",{}).get("items",[])
            if items:
                handle = items[0].get("lineItemRenderer",{}).get("text",{}).get("simpleText","")
        if len(lines) > 1:
            items = lines[1].get("lineRenderer",{}).get("items",[])
            if items:
                sub_count_text = items[0].get("lineItemRenderer",{}).get("text",{}).get("simpleText","")
        thumbnails = header.get("thumbnail",{}).get("thumbnails",[])
        thumb_url = thumbnails[-1]["url"] if thumbnails else ""
        if thumb_url.startswith("//"):
            thumb_url = "http:" + thumb_url
        video_count = self.GDataAPI.GetVideoCount(channelId)
        return {
            "channel_id": channelId,
            "title": title,
            "handle": handle,
            "subscriber_count": parsecount(sub_count_text),
            "video_count": video_count,
            "thumbnail": thumb_url,
        }
    @staticmethod
    def _toseconds(text):
        if not text: return 0
        parts = text.strip().split(":")
        try: parts = [int(p) for p in parts]
        except ValueError: return 0
        seconds = 0
        for part in parts: seconds = seconds*60+part
        return seconds
    def _tofield(self,tile):
        header = tile.get("header",{}).get("tileHeaderRenderer",{})
        meta = tile.get("metadata",{}).get("tileMetadataRenderer",{})
        video_id = tile.get("contentId","")
        length_text = ""
        for overlay in header.get("thumbnailOverlays",[]):
            ts = overlay.get("thumbnailOverlayTimeStatusRenderer")
            if ts:
                length_text = ts.get("text",{}).get("simpleText","")
                break
        title = meta.get("title",{}).get("simpleText","")
        author_name = ""
        view_count = ""
        published_text = ""
        lines = meta.get("lines",[])
        if lines:
            first_line_items = lines[0].get("lineRenderer",{}).get("items",[])
            if first_line_items:
                runs = first_line_items[0].get("lineItemRenderer",{}).get("text",{}).get("runs",[])
                if runs: author_name = runs[0].get("text","")
        if len(lines) > 1:
            for li in lines[1].get("lineRenderer",{}).get("items",[]):
                item = li.get("lineItemRenderer",{})
                txt = item.get("text",{})
                simple = txt.get("simpleText","")
                if "Aufruf" in simple or "views" in simple.lower() or "Mio." in simple: view_count = simple
                elif simple.startswith("vor "): published_text = simple
        author_id = ""
        try:
            menu_items = (tile["onLongPressCommand"]["showMenuCommand"]["menu"]["menuRenderer"]["items"])
            for mi in menu_items:
                nav = mi.get("menuNavigationItemRenderer",{}).get("navigationEndpoint",{})
                if "browseEndpoint" in nav:
                    author_id = nav["browseEndpoint"].get("browseId","")
                    break
        except (KeyError,TypeError):
            pass
        return {
            "video_id": video_id,
            "duration_seconds": self._toseconds(length_text),
            "author_name": author_name,
            "author_id": author_id,
            "title": title,
            "view_count": parseViews(view_count),
            "published": (lambda t: (
                (lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"))(
                    datetime.utcnow() - {
                        "seconds": timedelta(seconds=int(m.group(1))),
                        "minutes": timedelta(minutes=int(m.group(1))),
                        "hours": timedelta(hours=int(m.group(1))),
                        "days": timedelta(days=int(m.group(1))),
                        "weeks": timedelta(weeks=int(m.group(1))),
                        "months": timedelta(days=int(m.group(1))*30),
                        "years": timedelta(days=int(m.group(1))*365),
                    }.get(m.group(2),timedelta(0))
                ) if (m := re.search(r"vor\s+(\d+)\s+(seconds|minutes|hours|days|weeks|months|years)",t)) else datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
            ))(published_text),
            "description": title,
        }
    def _shelf_item_ex(self,tile):
        v = self._tofield(tile)
        minutes,seconds = divmod(v["duration_seconds"],60)
        duration = f"{minutes}:{seconds:02d}"
        vid_id = v["video_id"]
        thumb = funcmod.getThumbnail(vid_id)
        return {
            "content_type": 500,
            "content_item": {
                "ua": vid_id,
                "encrypted_id": vid_id,
                "title": v["title"],
                "short_byline": v["author_name"],
                "public_name": v["author_name"],
                "nb": v["author_name"],
                "view_count": fmt_view(v["view_count"]),
                "duration": fmt_duration(duration),
                "Sc": f"/watch?v={v['video_id']}",
                "Jb": {"url": thumb},
                "thumbnail_info": {"url": thumb},
            }
        }
    def _rawsearch(self,query,params=None,hl="en",gl="US"):
        url = f"{self.INNERTUBE_URL}/search"
        payload = {
            "context": self._build_innertube_context(hl=hl,gl=gl),
            "query": query
        }
        if params:
            payload["params"] = params
        headers = self._build_innertube_headers()
        reqparams = self._build_innertube_params()
        try:
            r = requests.post(url,json=payload,headers=headers,timeout=10,params=reqparams)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            return None
    def _videosearch(self,query,order="relevance",limit=15,continuation_token=None,hl="en",gl="US"):
        if continuation_token:
            data = self._search_continuation_unauth(continuation_token,hl=hl,gl=gl)
            if not data:
                return [],None,None
            renderers = self._extract_continuation_renderer(data,"videoRenderer")
            next_tkn = self._extract_continuation_from_continuation(data)
        else:
            data = self._rawsearch(query,SEARCH_VIDEO,hl=hl,gl=gl)
            if not data:
                return [],None,None
            renderers = self._searchrenderers(data,"videoRenderer")
            next_tkn = self._extract_continuation(data)
        out = []
        correction = self._get_search_correction(data)
        for vr in renderers[:limit]:
            vid_id = vr.get("videoId")
            if not vid_id:
                continue
            title = simpletext(vr.get("title"))
            owner = simpletext(vr.get("ownerText")) or simpletext(vr.get("longBylineText"))
            nav = vr.get("ownerText",{}).get("runs",[{}])[0].get("navigationEndpoint",{}).get("browseEndpoint",{})
            ch_id = nav.get("browseId","")
            view_count_text = simpletext(vr.get("viewCountText")) or simpletext(vr.get("shortViewCountText"))
            out.append({
                "video_id": vid_id,
                "title": title or "",
                "channel_id": ch_id,
                "author": owner or "",
                "duration": self._lengthtext(vr),
                "view_count": parsecount(view_count_text),
                "thumbnail": f"/channel/{ch_id}/icon",
            })
        return out,next_tkn,correction
    # for topic channels
    def _ST_topics_Sports(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("sports",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Music(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("music",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_News(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("news",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Gaming(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("gaming",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Autos(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("autos",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Live(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("live",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_TV(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("TV",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Movies(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("movies",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Education(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("education",hl=hl,gl=gl,continuation_token=continuation_token)
    def _ST_topics_Fashion(self,hl="en",gl="US",continuation_token=None):
        return self._videosearch("fashion",hl=hl,gl=gl,continuation_token=continuation_token)
    def _get_topic(self,kw,hl="en",gl="US",continuation_token=None):
        if kw == "sports":
            return self._ST_topics_Sports(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "music":
            return self._ST_topics_Music(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "news":
            return self._ST_topics_News(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "gaming":
            return self._ST_topics_Gaming(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "autos":
            return self._ST_topics_Autos(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "live":
            return self._ST_topics_Live(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw in ["movies"]:
            return self._ST_topics_Movies(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw in ["tv","show","shows"]:
            return self._ST_topics_TV(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw in ["education","edu"]:
            return self._ST_topics_Education(hl=hl,gl=gl,continuation_token=continuation_token)
        elif kw == "fashion":
            return self._ST_topics_Fashion(hl=hl,gl=gl,continuation_token=continuation_token)
        return {}
    def _channelsearch(self,query,limit=10,continuation_token=None):
        if continuation_token:
            data = self._search_continuation_unauth(continuation_token)
            next_tkn = self._extract_continuation_EX(data)
        else:
            data = self._rawsearch(query,SEARCH_CHANNEL)
            next_tkn = self._extract_continuation(data)
        renderers = self._searchrenderers(data,"channelRenderer")
        out = []
        correction = self._get_search_correction(data)
        for cr in renderers[:limit]:
            ch_id = cr.get("channelId")
            if not ch_id:
                continue
            title = simpletext(cr.get("title"))
            thumbnails = cr.get("thumbnail",{}).get("thumbnails",[])
            thumb = thumbnails[0]["url"] if thumbnails else ""
            if thumb.startswith("//"):
                thumb = "http:" + thumb
            sub_text = simpletext(cr.get("videoCountText"))
            handle = simpletext(cr.get("subscriberCountText"))
            out.append({
                "channel_id": ch_id,
                "title": title or "",
                "thumbnail": f"/channel/{ch_id}/icon",
                "subscriber_count": parsecount(sub_text),
                "handle": handle or "",
            })
        return out,next_tkn,correction
    def _playlistsearch(self,query,limit=20,continuation_token=None):
        if continuation_token:
            data = self._search_continuation_unauth(continuation_token)
            next_tkn = self._extract_continuation_from_continuation(data)
        else:
            data = self._rawsearch(query,SEARCH_PLAYLIST)
            next_tkn = self._extract_continuation(data)
        correction = self._get_search_correction(data)
        try:
            contents = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"]
        except (KeyError,TypeError):
            return [],None,correction
        out = []
        for section in contents:
            item_section = section.get("itemSectionRenderer",{})
            for item in item_section.get("contents",[]):
                lockup = item.get("lockupViewModel")
                if not lockup:
                    continue
                if lockup.get("contentType") != "LOCKUP_CONTENT_TYPE_PLAYLIST":
                    continue
                playlist_id = lockup.get("contentId")
                if not playlist_id:
                    continue
                metadata = lockup.get("metadata",{})
                lockup_metadata = metadata.get("lockupMetadataViewModel",{})
                title_obj = lockup_metadata.get("title",{})
                title = simpletext(title_obj) or title_obj.get("content","")
                metadata_obj = lockup_metadata.get("metadata",{})
                rows = metadata_obj.get("contentMetadataViewModel",{}).get("metadataRows",[])
                owner = ""
                video_count = 0
                for row in rows:
                    for part in row.get("metadataParts",[]):
                        text = part.get("text",{})
                        content = text.get("content","")
                        if content and not owner:
                            owner = content
                    if owner:
                        break
                thumbnail = ""
                try:
                    sources = lockup["contentImage"]["collectionThumbnailViewModel"]["primaryThumbnail"]["thumbnailViewModel"]["image"]["sources"]
                    if sources:
                        url = sources[-1].get("url","")
                        m = re.search(r"/vi/([^/]+)/",url)
                        if m:
                            thumbnail = funcmod.getThumbnail(m.group(1))
                except (KeyError,TypeError):
                    pass
                try:
                    badges = lockup["contentImage"]["collectionThumbnailViewModel"]["primaryThumbnail"]["thumbnailViewModel"]["overlays"][0]["thumbnailOverlayBadgeViewModel"]["thumbnailBadges"]
                    for b in badges:
                        badgetext = b.get("thumbnailBadgeViewModel",{}).get("text","")
                        match = re.search(r"([\d,]+)\s+videos?",badgetext,re.I)
                        if match:
                            video_count = int(match.group(1).replace(",",""))
                            break
                except (KeyError,TypeError,IndexError):
                    pass
                out.append({
                    "playlist_id": playlist_id,
                    "title": title or "",
                    "thumbnail": thumbnail,
                    "owner": owner or "",
                    "video_count": video_count
                })
                if len(out) >= limit:
                    return out,next_tkn,correction
        return out,next_tkn,correction
    @staticmethod
    def _get_search_correction(data):
        try:
            sections = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"]
            for s in sections:
                items = s.get("itemSectionRenderer",{}).get("contents",[])
                for i in items:
                    showingresultsfor = i.get("showingResultsForRenderer") or i.get("didYouMeanRenderer")
                    if showingresultsfor:
                        newquery = "".join(r.get("text","") for r in showingresultsfor.get("correctedQuery",{}).get("runs",[]))
                        return newquery
        except (KeyError,TypeError):
            pass
        return None
    def _search_continuation_unauth(self,continuation_token,hl="en",gl="US"):
        context = self._build_innertube_context(hl=hl,gl=gl)
        headers = self._build_innertube_headers()
        rparams = self._build_innertube_params()
        payload = {
            "context": context,
            "continuation": continuation_token
        }
        url = f"{self.INNERTUBE_URL}/search"
        try:
            r = requests.post(url,json=payload,headers=headers,timeout=15,params=rparams)
            r.raise_for_status()
            data = r.json()
            return data
        except (requests.RequestException,ValueError) as e:
            print(f"[continuation]: {e}")
            return None
    def _get_channel_info(self,channelId:str) -> dict[str, t.Any] | None:
        try:
            main = self._browse(channelId)
        except requests.RequestException:
            return None
        metadata = main.get("metadata",{}).get("channelMetadataRenderer")
        if not metadata:
            return None
        try:
            about = self._browse(channelId,ABOUT_PARAMS)
        except requests.RequestException:
            about = {}
        view_count_text = self._find_all(about,"viewCountText")
        total_views = view_count_text[0].get("simpleText") if view_count_text else None
        joined_text = self._find_all(about,"joinedDateText")
        joined = None
        if joined_text:
            j = joined_text[0]
            joined = j.get("simpleText") or (j.get("runs",[{}])[0].get("text") if j.get("runs") else None)
        content_parts = self._extract_metadata_rows(about)
        sub_text = next((p for p in content_parts if "subscriber" in p.lower()),None)
        video_text = next((p for p in content_parts if "video" in p.lower()),None)
        if sub_text is None or video_text is None:
            header_parts = self._extract_metadata_rows(main)
            if sub_text is None:
                sub_text = next((p for p in header_parts if "subscriber" in p.lower()),None)
            if video_text is None:
                video_text = next((p for p in header_parts if "video" in p.lower()),None)
        description = metadata.get("description","")
        is_auto_generated = "generated automatically" in description
        real_name = metadata.get("vanityChannelUrl")
        if real_name:
            real_name = real_name.replace("http://www.youtube.com/","").replace("https://www.youtube.com/","")
        if not is_auto_generated:
            video_text = str(video_text).strip(" videos")
        else:
            real_name = ""
        res = {
            "channel_name": metadata.get("title"),
            "description": description,
            "country": metadata.get("country"),
            "joined_date": joined,
            "auto_generated": is_auto_generated,
            "real_name": real_name,
            "subscribers": sub_text,
            "total_views": total_views.removesuffix(" views") if total_views is not None else total_views,
            "upload_count": video_text,
            "age": None,
            "hometown": None,
            "featured": None
        }
        featured = self._get_featured_video(main)
        if featured:
            vid = featured.get("videoId")
            res["featured"] = {
                "ua": vid,
                "encrypted_id": vid,
                "title": simpletext(featured.get("title")),
                "short_byline": metadata.get("title"),
                "public_name": metadata.get("title"),
                "nb": metadata.get("title"),
                "duration": self._get_video_duration(vid),
                "view_count": fmt_view(parseViews(simpletext(featured.get("viewCountText")))),
                "Sc": f"/watch?v={vid}",
                "thumbnail_info": {
                    "url": funcmod.getThumbnail(vid)
                },
                "wh": funcmod.getThumbnail(vid)
            }
        return res
    def _completesearch(self,query:str,hl:str="en",gl:str="US") -> str:
        url = "https://clients1.google.com/complete/search"
        try:
            r = requests.get(url,timeout=20,params={
                "client": "youtube-reduced",
                "hl": hl,
                "gl": gl,
                "gs_rn": "23",
                "gs_ri": "youtube-reduced",
                "ds": "yt",
                "cp": "3",
                "gs_id": "d",
                "callback": "google.sbox.p50",
                "q": query
            },headers={"User-Agent": TV_USERAGENT})
            r.raise_for_status()
            data = r.text
        except (requests.RequestException,Exception):
            return ""
        return data

    # public methods
    def CompleteSearch(self,query:str,hl:str="en",gl:str="US") -> str:
        return self._completesearch(query=query,hl=hl,gl=gl)
    def RecommendedVideos(self,videoId:str,hl:str="en",gl:str="US",maxResults:int=30,continuation_token:str=None) -> tuple[list, None] | tuple[list | None]:
        return self._get_related(videoId=videoId,hl=hl,gl=gl,maxResults=maxResults,continuation_token=continuation_token)
    def GetChannelInfo(self,channelId:str) -> dict[str, str | None | int] | None:
        return self._get_channel_info(channelId)
    def Favorites(self,oauth_token:str,hl:str="en",gl:str="US",continuation_token:str=None) -> tuple[list, None] | tuple[list, t.Any | None]:
        return self._build_favorites_feed(oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
    def WatchLater(self,oauth_token:str,hl:str="en",gl:str="US",continuation_token:str|None=None) -> tuple[list, None] | tuple[list, t.Any | None]:
        return self._build_wl_playlist(oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
    def WatchHistory(self,oauth_token:str,hl:str="en",gl:str="US",continuation_token:str|None=None) -> tuple[list, None] | tuple[list, t.Any | None]:
        return self._build_watch_history_feed(oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
    def MySubscriptions(self,oauth_token:str,maxResults:int=25,hl:str="en",gl:str="US") -> list | None:
        return self._build_subscriptions_page(oauth_token=oauth_token,maxResults=maxResults,hl=hl,gl=gl)
    def VideoSearch(self,query:str,order:str="relevance",limit:int=15,continuation_token:str|None=None) -> tuple[list, None, None] | tuple[list, t.Any | None, t.LiteralString | None]:
        return self._videosearch(query=query,order=order,limit=limit,continuation_token=continuation_token)
    def ChannelSearch(self,query:str,order:str="relevance",limit:int=15,continuation_token:str|None=None) -> tuple[list, None, None] | tuple[list, t.Any | None, t.LiteralString | None]:
        return self._channelsearch(query=query,limit=limit,continuation_token=continuation_token)
    def PlaylistSearch(self,query:str,limit:int=20,continuation_token:str|None=None) -> t.Any:
        return self._playlistsearch(query=query,limit=limit,continuation_token=continuation_token)
    def WhatToWatch(self,oauth_token:str,hl:str="en",gl:str="US") -> tuple[list, None] | tuple[list, dict[str, list[list]] | None]:
        return self._build_river_feed(oauth_token=oauth_token,hl=hl,gl=gl)
    def AddToPlaylist(self,oauth_token:str,playlistId:str,videoId:str,hl:str="en",gl:str="US") -> t.Any | t.Literal["STATUS_ERROR"] | t.Literal["STATUS_SUCCEEDED"] | None:
        return self._add_to_playlist(oauth_token=oauth_token,playlistId=playlistId,videoId=videoId,hl=hl,gl=gl)
    def RemoveFromPlaylist(self,oauth_token:str,playlistId:str,videoId:str,hl:str="en",gl:str="US") -> t.Any | t.Literal['STATUS_ERROR'] | t.Literal["STATUS_SUCCEEDED"] | None:
        return self._remove_from_playlist(oauth_token=oauth_token,playlistId=playlistId,videoId=videoId,hl=hl,gl=gl)
    def IsSubscribed(self,oauth_token:str,channelId:str,hl:str="en",gl:str="US") -> bool | None:
        return self._is_subscribed(oauth_token=oauth_token,channelId=channelId,hl=hl,gl=gl)
    def GetChannelVideos(self,channelId:str,hl:str="en",gl:str="US",continuation_token:str|None=None) -> tuple[list, None] | tuple[list, t.Any | None]:
        return self._get_channel_content(channelId=channelId,hl=hl,gl=gl,continuation_token=continuation_token)
    def RateVideo(self,oauth_token:str,videoId:str,rating:str="indifferent",hl:str="en",gl:str="US") -> bool | None:
        return self._rate_video(oauth_token=oauth_token,videoId=videoId,endpoint=rating,hl=hl,gl=gl)
    def GetPlaylists(self,oauth_token:str,hl:str="en",gl:str="US"):
        return self._get_playlists(oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=None)
    def GetPlaylistFromSearch(self,playlistId:str,oauth_token:str|None=None,hl:str="en",gl:str="US",continuation_token:str|None=None) -> t.Any:
        return self._get_playlist_fromsearch(playlistId=playlistId,oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
    def ActivityFeed(self,oauth_token:str,remove_shorts:bool=False,hl:str="en",gl:str="US") -> list[dict[str, t.Any]] | None:
        return self._build_activity_feed(oauth_token=oauth_token,hl=hl,gl=gl,remove_shorts=remove_shorts)
    def GetChannelIDFromHandle(self,handle) -> t.Any | None:
        return self._getidfromhandle(handle=handle)
    def GetVideoInfo(self,videoId:str,hl:str="en",gl:str="US") -> dict[str, t.Any] | None:
        return self._get_video_info(videoId=videoId,hl=hl,gl=gl)
    def UnsubscribeOrSubscribe(self,oauth_token:str,channelId:str,subscribing:bool,hl:str="en",gl:str="US") -> bool | None:
        return self._channel_action(oauth_token=oauth_token,channelId=channelId,subscribing=subscribing,hl=hl,gl=gl)
    def MyVideos(self,oauth_token:str,hl:str="en",gl:str="US",continuation_token:str|None=None) -> tuple[dict, str | None] | tuple[list, str | None]:
        return self._get_ownvideos(oauth_token=oauth_token,hl=hl,gl=gl,continuation_token=continuation_token)
    # wrapper of a wrapper
    # topic channels
    def GetTopicVideos(self,keyword:TOPIC_TYPES,hl:str="en",gl:str="US",continuation_token:str|None=None) -> tuple[list, None, None] | tuple[list, t.Any | None, t.LiteralString | None] | dict:
        return self._get_topic(kw=keyword,hl=hl,gl=gl,continuation_token=continuation_token)

class OAuth2API:
    def __init__(self,oauth_id:str,oauth_secret:str,login_scopes:str,device_id:str,device_model:str) -> None:
        self.OAUTH_ID = oauth_id
        self.OAUTH_SECRET = oauth_secret
        self.LOGIN_SCOPE = login_scopes
        self.OVERRIDE_CREDENTIALS = ENABLE_CREDS_OVERRIDE
        self.INNERTUBE_DEVICE_ID = device_id
        self.INNERTUBE_DEVICE_MODEL = device_model
        self.GRANT_TYPE_REFRESH = GRANT_TYPE_REFRESH
        self.GRANT_TYPE_OAUTH2 = GRANT_TYPE
        self.REVOKE_URL = "https://oauth2.googleapis.com/revoke"
        self.GOOGLEAPIS_LOGIN_URL = "https://oauth2.googleapis.com/device/code"
        self.INNERTUBE_LOGIN_URL = "https://www.youtube.com/o/oauth2/device/code"
        self.GLOBAL_REFRESH_URL = "https://oauth2.googleapis.com/token"
        self.GLOBAL_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
        self.GLOBAL_TOKEN_POLL_URL = self.GLOBAL_REFRESH_URL
        self.ACCOUNT_LIST_URL = "https://www.youtube.com/youtubei/v1/account/accounts_list"
    def _request_login_code(self,headers:dict|wd.ImmutableMultiDict|wd.MultiDict|wd.Headers|t.Mapping[str, t.Any]) -> tuple[None, int, None] | tuple[bytes, int, list[tuple[str, str]]]:
        data = {
            "client_id": self.OAUTH_ID,
            "scope": self.LOGIN_SCOPE,
        }
        headers = {key:value for key,value in headers if key.lower().strip() != "host"}
        if self.OVERRIDE_CREDENTIALS:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            URL = self.GOOGLEAPIS_LOGIN_URL
        else:
            headers["Content-Type"] = "application/json"
            URL = self.INNERTUBE_LOGIN_URL
            data["device_id"] = self.INNERTUBE_DEVICE_ID
            data["device_model"] = self.INNERTUBE_DEVICE_MODEL
        try:
            if self.OVERRIDE_CREDENTIALS:
                r = requests.post(URL,data=data,headers=headers,cookies=CONSENT_COOKIES,timeout=10)
            else:
                r = requests.post(URL,json=data,headers=headers,cookies=CONSENT_COOKIES,timeout=10)
            r.raise_for_status()
        except (requests.RequestException,ValueError) as e:
            print(f"oauth2 token err::{e}")
            return None,r.status_code,None
        excluded = ['content-encoding', 'transfer-encoding', 'connection', 'keep-alive']
        headers_fwd = [(k, v) for k, v in r.headers.items() if k.lower() not in excluded]
        return r.content,r.status_code,headers_fwd
    def _poll_login(self,device_code:str|None) -> tuple[dict[str, str], str | None, str | None, int]:
        if not device_code:
            return {
                "status": "error",
                "message": "missing device code"
            },None,None,400
        payload = {
            "client_id": self.OAUTH_ID,
            "client_secret": self.OAUTH_SECRET,
            "device_code": device_code,
            "grant_type": self.GRANT_TYPE_OAUTH2,
        }
        url = self.GLOBAL_TOKEN_POLL_URL
        timeout = 15
        try:
            r = requests.post(url,data=payload,timeout=timeout)
            #r.raise_for_status()
            data = r.json()
        except (requests.Timeout):
            return {
                "status": "error",
                "message": "connection timed out after %s seconds"%(timeout)
            },None,None,400
        except requests.RequestException:
            return {
                "status": "pending"
            },None,None,400
        except ValueError:
            return {
                "status": "error",
                "message": "invalid JSON from server"
            },None,None,400
        except Exception:
            return {
                "status": "error",
                "message": "unknown error"
            },None,None,400
        status = r.status_code
        if status == 200:
            token = data.get("access_token")
            refresh = data.get("refresh_token")
            return {
                "status": "success"
            },token,refresh,200
        elif status == 400:
            error_type = data.get("error")
            if error_type in ["authorization_pending","slow_down"]:
                return {
                    "status": "pending"
                },None,None,400
            elif error_type == "token_expired":
                return {
                    "status": "reload"
                },None,None,400
            elif error_type == "access_denied":
                return {
                    "status": "error",
                    "message": "Access denied"
                },None,None,400
            return {
                "status": "pending"
            },None,None,400
        return {
            "status": "pending"
        },None,None,400
    def _refresh_token(self,refresh_token:str) -> str | None:
        URL = self.GLOBAL_REFRESH_URL
        if self.OVERRIDE_CREDENTIALS:
            try:
                credentials = Credentials(token=None,refresh_token=refresh_token,token_uri=URL,client_id=self.OAUTH_ID,client_secret=self.OAUTH_SECRET)
                credentials.refresh(Request())
                return credentials.token
            except RefreshError as e:
                traceback.print_exc()
                print("googleapis override refresh error:",e)
                return None
        payload = {
            "client_id": self.OAUTH_ID,
            "client_secret": self.OAUTH_SECRET,
            "refresh_token": refresh_token,
            "grant_type": self.GRANT_TYPE_REFRESH,
        }
        try:
            r = requests.post(URL,data=payload,timeout=10)
            data = r.json()
            if r.status_code == 200:
                return data.get("access_token")
            else:
                return None
        except requests.RequestException:
            return None
    def _revoketoken(self,oauth_token:str=None) -> bool:
        if not oauth_token:
            return False
        try:
            url = self.REVOKE_URL
            r = requests.post(url,params={
                "token": oauth_token
            },headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },timeout=25)
            r.raise_for_status()
        except (requests.RequestException,requests.HTTPError):
            pass
        return True
    def _checkistokenvalid(self,oauth_token=None) -> bool:
        if not oauth_token:
            return False
        try:
            url = self.GLOBAL_TOKEN_INFO_URL
            r = requests.get(url,params={"access_token": oauth_token},timeout=15)
            r.raise_for_status()
        except (requests.RequestException,requests.HTTPError):
            return False
        return r.status_code == 200
    def _getsignininfo(self,oauth_token:str,lang:str="en",gl:str="US") -> dict[str | None] | None:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {oauth_token}",
            "origin": "https://www.youtube.com",
            "referer": "https://www.youtube.com/tv",
            "x-youtube-client-name": "TVHTML5",
            "user-agent": TV_USERAGENT,
        }
        payload = {
            "context": {
                "client": {
                    "hl": lang,
                    "gl": gl,
                    "clientName": "TVHTML5",
                    "clientVersion": TV_CLIENT_VERSION,
                    "platform": "TV",
                    "originalUrl": "https://www.youtube.com/tv",
                }
            },
            "accountReadMask": {
                "returnOwner": True,
                "returnBrandAccounts": True,
                "returnPersonaAccounts": True,
                "returnFamilyChildAccounts": True,
                "returnFamilyMembersAccounts": False,
            },
        }
        try:
            url = self.ACCOUNT_LIST_URL
            r = requests.post(url,json=payload,headers=headers,timeout=15)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException,ValueError):
            print("Error: g.INFO will be None!!")
            traceback.print_exc()
            return None
        userId = None
        name = None
        photo = None
        handle = None
        hasChannel = None
        email = None
        fb_name = None
        fb_img = None
        for section in data.get("contents",[]):
            for item_section in section.get("accountSectionListRenderer",{}).get("contents",[]):
                for item in item_section.get("accountItemSectionRenderer",{}).get("contents",[]):
                    ai = item.get("accountItem")
                    if not ai: continue
                    accountname = ai.get("accountName",{}).get("simpleText")
                    accountemail = ai.get("accountByline",{}).get("simpleText")
                    thumbnails = ai.get("accountPhoto",{}).get("thumbnails",[])
                    accountimg = thumbnails[-1]["url"] if thumbnails else None
                    if fb_name is None:
                        fb_name = accountname
                        fb_img = accountimg
                    try:
                        tokens = ai["serviceEndpoint"]["selectActiveIdentityEndpoint"]["supportedTokens"]
                        for tok in tokens:
                            state_token = tok.get("accountStateToken")
                            if state_token and state_token.get("obfuscatedGaiaId"):
                                userId = state_token["obfuscatedGaiaId"]
                                name = accountname
                                photo = accountimg
                                email = accountemail
                                hasChannel = state_token.get("hasChannel")
                                handle = ai.get("channelHandle",{}).get("simpleText")
                                break
                    except (KeyError,TypeError):
                        continue
                    if userId:
                        break
                if userId:
                    break
            if userId:
                break
        if userId is None and fb_name is None:
            return None
        return {
            "name": name if name is not None else fb_name,
            "photo": photo if photo is not None else fb_img,
            "handle": handle,
            "haschannel": hasChannel,
            "email": email,
        }

    # public methods
    def GetUserInfo(self,oauth_token:str,hl:str="en",gl:str="US") -> dict[str | None, t.Any] | None:
        return self._getsignininfo(oauth_token,lang=hl,gl=gl)
    def CheckIsTokenValid(self,oauth_token:str) -> bool:
        return self._checkistokenvalid(oauth_token=oauth_token)
    def RevokeToken(self,oauth_token:str) -> bool:
        return self._revoketoken(oauth_token=oauth_token)
    def RefreshToken(self,refresh_token:str) -> str | None:
        return self._refresh_token(refresh_token=refresh_token)
    def GetLoginCode(self,headers:dict|wd.ImmutableMultiDict|wd.MultiDict|wd.Headers|t.Mapping[str,t.Any]) -> tuple[None, int, None] | tuple[bytes, int, list[tuple[str, str]]]:
        return self._request_login_code(headers=headers)
    def CheckAuthorization(self,device_code:str|None) -> tuple[dict[str, str], str | None, str | None, int]:
        return self._poll_login(device_code=device_code)

class CombinedAPIs:
    def __init__(self,gdataKey:str,innerTubeKey:str) -> None:
        self.DataAPI = GDataAPI(GDataKey=gdataKey)
        self.InnerTubeAPI = InnerTubeAPI(innerTubeKey=innerTubeKey)
    def _get_channel_info_combo(self,channelId:str) -> dict[str, str] | dict[str]:
        PREFER_GDATA_FIELDS = ("subscribers","joined_date")
        result = self.InnerTubeAPI.GetChannelInfo(channelId)
        if result is None:
            gdata = self.DataAPI.GetChannelInfo(channelId)
            if gdata is None:
                return {"error": "channel not found"}
            return gdata
        missing = [k for k,v in result.items() if v is None and k not in ("age","hometown")]
        gdata = self.DataAPI.GetChannelInfo(channelId)
        if gdata:
            for k in missing:
                if gdata.get(k) is not None:
                    result[k] = gdata[k]
            for k in PREFER_GDATA_FIELDS:
                if gdata.get(k) is not None:
                    result[k] = gdata[k]
        return result

    # public methods
    def GetChannelInfoCombo(self,channelId:str) -> dict[str, str] | dict[str]:
        return self._get_channel_info_combo(channelId)

class LoungeAPI:
    def __init__(self) -> None:
        self.base_loungeURL = "https://www.youtube.com/api/lounge/pairing"
        self.base_loungeURL_screens = "https://www.youtube.com/api/lounge/screens"
        self.base_browserChannelURL = "https://www.youtube.com/api/lounge/bc"
        self.__browserChannelEndpoints = ["bind","test"]
        self.__loungeAPItypes = ["screens","pairing"]
        self.__loungeURL_endpoints = ["get_lounge_token_batch","get_screen_availability","get_screen",]
        self.__API_TYPE_SCREENS = "screens"
        self.__API_TYPE_PAIRING = "pairing"
        self.__LOUNGE_GET_TOKEN_BATCH = "get_lounge_token_batch"
        self.__LOUNGE_GET_IS_SCREEN_AVAILABLE = "get_screen_availability"
        self.__LOUNGE_GET_SCREEN = "get_screen"
    def _check_allowed(self,requestmethod:str,apitype:str,endpoint:str|None) -> tuple[bool, int]:
        if apitype not in self.__loungeAPItypes:
            return False,404
        if apitype == self.__API_TYPE_PAIRING:
            if endpoint not in self.__loungeURL_endpoints:
                return False,404
            if requestmethod != "POST":
                return False,404
        elif apitype == self.__API_TYPE_SCREENS:
            if endpoint is None:
                if requestmethod not in ["GET","POST"]:
                    return False,405
            else:
                if requestmethod not in ["PUT","DELETE","POST"]:
                    return False,405
        return True,200
    def _do_lounge_request(
            self,
            apiType:str,
            endpoint:str|None,
            method:str,
            subpath:str|None=None,
            paircd:str|None=None,
            loungeToken:str|None=None,
            scrIds:str|None=None,
            params:dict | wd.ImmutableMultiDict | wd.MultiDict | None=None,
            headers:dict | wd.MultiDict | wd.ImmutableMultiDict | wd.Headers | t.Mapping[str,t.Any] | None=None,
            form:dict | wd.ImmutableMultiDict | wd.MultiDict | None=None
        ) -> tuple[str, int, str]:
        allowed,httpcd = self._check_allowed(method,apiType,endpoint)
        if not allowed:
            return "Bad request",httpcd,"text/plain"
        reqparams = wd.MultiDict(params or {}).to_dict(flat=False)
        reqheaders = dict(headers) if headers else {}
        reqform = wd.MultiDict(form or {}).to_dict(flat=False)
        apiurl = self.base_loungeURL
        if apiType == self.__API_TYPE_SCREENS:
            apiurl = self.base_loungeURL_screens
        if subpath:
            apiurl = f"{apiurl}/{subpath}"
        try:
            if method == "GET":
                r = requests.get(apiurl,params=reqparams,headers=reqheaders)
            elif method == "POST":
                data = {
                    "pairing_code": paircd,
                    "lounge_token": loungeToken,
                }
                if endpoint == self.__LOUNGE_GET_SCREEN:
                    if not paircd:
                        return "Bad request",400,"text/plain"
                    data = {
                        "pairing_code": paircd,
                    }
                elif endpoint == self.__LOUNGE_GET_IS_SCREEN_AVAILABLE:
                    if not loungeToken:
                        return "Bad request",400,"text/plain"
                    data = {
                        "lounge_token": loungeToken,
                    }
                elif endpoint == self.__LOUNGE_GET_TOKEN_BATCH:
                    if not scrIds:
                        return "Bad request",400,"text/plain"
                    data = {
                        "screen_ids": scrIds,
                    }
                elif apiType == self.__API_TYPE_SCREENS:
                    data = reqform
                r = requests.post(apiurl,params=reqparams,headers=reqheaders,data=data)
            elif method == "PUT":
                r = requests.put(apiurl,params=reqparams,headers=reqheaders,data=reqform)
            elif method == "DELETE":
                r = requests.delete(apiurl,params=reqparams,headers=reqheaders)
            else:
                return "Method not allowed",405,"text/plain"
            r.raise_for_status()
            return r.text,r.status_code,r.headers.get("Content-Type", "application/json")
        except requests.RequestException:
            return "Upstream server error",502,"application/json"
    def _do_bc_request(
        self,
        endpoint:str,
        method:str,
        params:dict | wd.ImmutableMultiDict | wd.MultiDict,
        headers:dict| wd.ImmutableMultiDict | wd.MultiDict | wd.Headers | t.Mapping[str, t.Any],
        form:dict | wd.ImmutableMultiDict | wd.MultiDict | None=None,
        is3DS:bool=False
    ) -> tuple[str, int, str]:
        if endpoint not in self.__browserChannelEndpoints:
            return "Not found",404,"text/plain"
        if method not in ["GET","POST"]:
            return "Method not allowed",405,"text/plain"
        _params = wd.MultiDict(params)
        if is3DS:
            _params.setlist("name",["Nintendo 3DS"])
        requestsparams = _params.to_dict(flat=False)
        requestsheaders = dict(headers)
        fullURL = f"{self.base_browserChannelURL}/{endpoint}"
        try:
            if method == "GET":
                r = requests.get(fullURL,params=requestsparams,headers=requestsheaders,timeout=35)
            else:
                data = wd.MultiDict(form or {}).to_dict(flat=False)
                r = requests.post(fullURL,params=requestsparams,headers=requestsheaders,data=data,timeout=35)
            r.raise_for_status()
            return r.text,r.status_code,r.headers.get("Content-Type", "application/json")
        except requests.RequestException:
            return "Upstream server error",502,"text/plain"

    # public methods
    def Lounge(
        self,
        apitype:str,
        endpoint:str|None,
        method:str,
        subpath:str|None=None,
        paircd:str|None=None,
        loungetoken:str|None=None,
        scrids:str|list|None=None,
        params:dict | wd.ImmutableMultiDict | wd.MultiDict | None=None,
        headers:dict | wd.MultiDict | wd.ImmutableMultiDict | wd.Headers | t.Mapping[str,t.Any] | None=None,
        form:dict | wd.ImmutableMultiDict | wd.MultiDict |None=None,
    ) -> tuple[str, int, str]:
        return self._do_lounge_request(
            apiType=apitype,
            endpoint=endpoint,
            method=method,
            subpath=subpath,
            paircd=paircd,
            loungeToken=loungetoken,
            scrIds=scrids,
            params=params,
            headers=headers,
            form=form,
        )

    def BrowserChannel(
        self,
        endpoint:str,
        method:str,
        params:dict | wd.ImmutableMultiDict | wd.MultiDict,
        headers:dict| wd.MultiDict | wd.ImmutableMultiDict | wd.Headers | t.Mapping[str,t.Any],
        form:dict | wd.ImmutableMultiDict | wd.MultiDict | None=None,
        is3DS:bool=False,
    ) -> tuple[str, int, str]:
        return self._do_bc_request(
            endpoint=endpoint,
            method=method,
            params=params,
            headers=headers,
            form=form,
            is3DS=is3DS,
        )

class Utils:
    def __init__(self,innertubeKey:str) -> None:
        self.InnerTubeAPI = InnerTubeAPI(innerTubeKey=innertubeKey)

    def shelf_title(shelf):
        try:
            runs = shelf["headerRenderer"]["shelfHeaderRenderer"]["avatarLockup"]["avatarLockupRenderer"]["title"]["runs"]
            return runs[0].get("text","")
        except (KeyError,IndexError,TypeError): return ""
    @staticmethod
    def shelf_item_ex(tile):
        v = InnerTubeAPI._tofield(tile)
        minutes,seconds = divmod(v["duration_seconds"],60)
        duration = f"{minutes}:{seconds:02d}"
        vid_id = v["video_id"]
        thumb = funcmod.getThumbnail(vid_id)
        return {
            "content_type": 500,
            "content_item": {
                "ua": vid_id,
                "encrypted_id": vid_id,
                "title": v["title"],
                "short_byline": v["author_name"],
                "public_name": v["author_name"],
                "nb": v["author_name"],
                "view_count": fmt_view(v["view_count"]),
                "duration": fmt_duration(duration),
                "Sc": f"/watch?v={v['video_id']}",
                "Jb": {"url": thumb},
                "thumbnail_info": {"url": thumb},
            }
        }
    @staticmethod
    def flat_playlist_item(k):
        vid_id = k["encrypted_id"]
        thumb = funcmod.getThumbnail(vid_id)
        return {
            "encrypted_id": vid_id,
            "video_id": vid_id,
            "title": k["title"],
            "author": k["short_byline"],
            "short_byline": k["short_byline"],
            "public_name": k["public_name"],
            "view_count": k["view_count"],
            "views": k["view_count"],
            "duration": k["duration"],
            "length_string": k["duration"],
            "Sc": f"/watch?v={vid_id}",
            "thumbnail_url": thumb,
            "thumbnail_info": {
                "url": thumb
            }
        }
    @staticmethod
    def flat_item_tab(k):
        vid = k["encrypted_id"]
        return {
            "item_type": "compact_video",
            "action_type": "WL",
            "type": 500,
            "content_type": 500,
            "content_item": {
                "length": k["duration"],
                "url": f"/watch?v={vid}",
                "encrypted_id": vid,
                "title": k["title"],
                "view_count": k["view_count"],
                "duration": k["duration"],
                "watch_link": f"/watch?v={vid}",
                "thumbnail_info": k["thumbnail_info"],
            }
        }
    @staticmethod
    def flat_topic_video(k):
        vid = k["video_id"]
        return {
            "item_type": "compact_video",
            "action_type": "WL",
            "type": 500,
            "content_type": 500,
            "content_item": {
                "length": k["duration"],
                "url": f"/watch?v={vid}",
                "encrypted_id": vid,
                "title": k["title"],
                "view_count": fmt_view(k["view_count"]),
                "duration": k["duration"],
                "watch_link": f"/watch?v={vid}",
                "thumbnail_info": {
                    "url": funcmod.getThumbnail(vid),
                }
            }
        }
    @staticmethod
    def flat_playlist(plid,feplaylist):
        if plid == "WL" or plid == "LL":
            return None
        return {
            "encrypted_id": plid,
            "title": feplaylist.get("title"),
            "video_count": feplaylist.get("video_count"),
            "is_watch_later": False,
            "description": "",
            "is_public": feplaylist.get("is_public")
        }
