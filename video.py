from __future__ import print_function, annotations, division, with_statement
from flask import request, Response, redirect, send_file
import tempfile
import re
import subprocess
import time
import json
import yt_dlp
from pathlib import Path
from xml.etree import ElementTree as ET
import stat
import uuid
import colorama
import typing as t

from shared import PARSER_KEEP_COMMENTS, CFG_NAMESPACE

base = Path(__file__).resolve().parent
config = base/"config.xml"
colorama.init(True)
Fore = colorama.Fore
Back = colorama.Back

class GetVideo:
    def __init__(self) -> None:
        self.debugmode = self.getIsDebugMode()
        self.cookies = self.initCookies()
        self.tempdir = Path(tempfile.gettempdir())
        self.videocache = self.tempdir/"vid_cache"
    def createviddir(self) -> None:
        fmtdir = str(self.videocache).replace("\\","/")
        if not self.videocache.is_dir():
            self.videocache.mkdir(mode=511,parents=True,exist_ok=True)
            if self.debugmode:
                print(f"{Fore.GREEN}[vidcache]{Fore.RESET} video cache directory created (path: {fmtdir})")
            else:
                print(f"{Fore.GREEN}[vidcache]{Fore.RESET} video cache directory created")
        else:
            if self.debugmode:
                print(f"{Fore.GREEN}[vidcache]{Fore.RESET} video cache directory already exists (path: {fmtdir})")
            else:
                print(f"{Fore.GREEN}[vidcache]{Fore.RESET} video cache directory exists")
    @staticmethod
    def getIsDebugMode() -> bool:
        # user shouldve already created a config at this point, but let's be sure
        if not config.is_file():
            return False
        parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
        root = ET.parse(config,parser=parser).getroot()
        def safeget(name,default=None):
            elem = root.find(f"cfg:{name}",CFG_NAMESPACE)
            return elem.text if elem is not None else default
        debugmode = bool(safeget("debugging","false").lower().strip() == "true")
        return debugmode
    def cleanup(self) -> None:
        now = time.time()
        count = 0
        filettl = 86400 # in seconds
        filettl_days = filettl//86400
        for name in self.videocache.iterdir():
            if not name.is_file():
                continue
            if not (name.name.endswith(".webm") or name.name.endswith(".mp4")) or (not name.name.startswith("bt3ds_")):
                continue
            try:
                if now - name.stat().st_mtime >= filettl:
                    name.unlink()
                    count += 1
            except OSError:
                self.fixreadonly(name)
        print("%s[cleanup]%s Deleted %s file%s older than %s day%s"%(Fore.MAGENTA,Fore.RESET,count,'' if abs(count) == 1 else 's',filettl_days,'' if abs(filettl_days) == 1 else 's'))
    def completecleanup(self) -> None:
        count = 0
        for name in self.videocache.iterdir():
            if not name.is_file():
                continue
            if not (name.name.endswith(".webm") or name.name.endswith(".mp4")) or (not name.name.startswith("bt3ds_")):
                continue
            try:
                name.unlink()
                count += 1
            except OSError:
                self.fixreadonly(name)
        print("%s[cleanup]%s Deleted %s file%s"%(Fore.MAGENTA,Fore.RESET,count,'' if abs(count) == 1 else 's'))
    @staticmethod
    def initCookies() -> Path:
        cookiesfile = base/"cookies.txt"
        if not cookiesfile.is_file():
            return None
        return cookiesfile
    @staticmethod
    def fixreadonly(path:Path) -> None:
        try:
            path.chmod(path.stat().st_mode | stat.S_IWRITE)
            path.unlink()
        except OSError:
            pass
    def fetchStream(self, lang:str, country:str, videoId:str, oauthToken:str | None = None, new3DS:bool = False) -> str:
        url = f"https://www.youtube.com/watch?v={videoId}"
        verbose = no_warnings = self.debugmode
        quiet = not self.debugmode
        def extract(client):
            request_fmt = "92/91/18/best[height<=360]" if not new3DS and client == "web_safari" else "18/best[height<=360]"
            ydl_opts = {
                "format": request_fmt,
                "quiet": quiet,
                "no_warnings": no_warnings,
                "verbose": verbose,
                "cookiefile": self.cookies,
                "js_runtimes": {
                    "deno": {},
                    "node": {},
                },
                "extractor_args": {
                    "youtube": {
                        "player_client": [client],
                    }
                }
            }
            if not self.cookies:
                ydl_opts.pop("cookiefile",None)
            else:
                ydl_opts["cookiefile"] = str(self.cookies)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if "url" in info:
                    return info["url"]
                formats = info.get("formats", [])
                formats = sorted(formats, key=lambda x: x.get("height", 0))
                for f in formats:
                    if f.get("height", 0) <= 360 and f.get("url"):
                        return f["url"]
            return None
        clients = ["web","web_safari","web_embedded","android","ios","android_vr","vision_os","tv","tv_simply","tv_downgraded","mweb"]
        for cl in clients:
            try:
                stream = extract(cl)
                if stream:
                    return stream
            except Exception as e:
                fmtclient = cl.upper().replace("_"," ")
                if self.debugmode:
                    print(f"{Fore.RED}[stream]{Fore.RESET} {fmtclient} client failed:", e)
                else:
                    print(f"{Fore.RED}[stream]{Fore.RESET} {fmtclient} client failed. This might happen sometimes.")
                    if fmtclient.lower() == "mweb":
                        print(f"{Fore.RED}[stream]{Fore.RESET} every client failed. The video might be unavailable.\n{e}")
        return None
    def getVideoOrientation(self, source: Path | str) -> t.Literal["standard", "vertical"]:
        probe_cmd = ['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',source]
        try:
            result = subprocess.run(probe_cmd,capture_output=True,text=True,timeout=45)
        except subprocess.TimeoutExpired:
            if self.debugmode:
                print(f"{Fore.RED}[orientation]{Fore.RED} ffprobe timeout expired")
            return "standard"
        if result.returncode != 0:
            if self.debugmode:
                print(f"{Fore.RED}[orientation]{Fore.RESET} ffprobe error: {result.stderr}, (returned {result.returncode})")
            return "standard"
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            if self.debugmode:
                print(f"{Fore.RED}[orientation]{Fore.RESET} ffprobe returned invalid JSON")
            return "standard"
        streams = data.get("streams")
        if not streams:
            if self.debugmode:
                print(f"{Fore.RED}[orientation]{Fore.RESET} ffprobe returned no streams")
            return "standard"
        width = streams[0].get('width')
        height = streams[0].get('height')
        if width <= 0 or height <= 0:
            if self.debugmode:
                print(f"{Fore.RED}[orientation]{Fore.RESET} invalid width or height ({width}x{height})")
            return "standard"
        if self.debugmode:
            print(f"{Fore.BLUE}[orientation]{Fore.RESET} got {width}x{height}")
        return "vertical" if height > width else "standard"
    @staticmethod
    def qualityLabel(probejson: list | dict | t.Mapping[str, t.Any]) -> t.Literal["tiny","small"]:
        h = probejson.get("height")
        if not h:
            return None
        if h >= 144:
            return "tiny"
        elif h >= 240:
            return "small"
        return "small"
    @staticmethod
    def getScale(orientation, quality: str) -> t.Literal["scale=-2:240", "scale=256:240", "scale=-2:144", "scale=160:144"]:
        if quality == "small":
            return "scale=-2:240" if orientation == "vertical" else "scale=256:240"
        return "scale=-2:144" if orientation == "vertical" else "scale=160:144"
    def sendFileRange(self, path: Path | str, mime:str="video/mp4") -> Response:
        _actualpath = Path(path)
        file_size = _actualpath.stat().st_size
        range_header = request.headers.get("Range", None)
        unit = "bytes"
        headers = {"Accept-Ranges": "bytes"}
        if not range_header:
            resp = send_file(path,mimetype=mime)
            resp.headers["Content-Length"] = file_size
            resp.headers["Accept-Ranges"] = unit
            return resp
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            return Response(status=416, headers=headers)
        start_str, end_str = match.groups()
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        if start >= file_size or end >= file_size:
            return Response(status=416, headers=headers)
        length = end - start + 1
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(length)
        resp = Response(data, status=206, mimetype=mime, direct_passthrough=True)
        resp.headers.update({**headers,"Content-Range": f"{unit} {start}-{end}/{file_size}","Content-Length": str(length),})
        if self.debugmode:
            print(f"{Fore.CYAN}[range]{Fore.RESET} {unit} {start}-{end}/{file_size}")
        return resp
    def fetchAndLoadStreamOnly_New3DSOnly(self, lang:str, country:str, videoId:str, quality:t.Literal["tiny","small"]="tiny") -> Response:
        self.cleanup()
        stream_url = self.fetchStream(lang, country, videoId, new3DS=True)
        if not stream_url:
            return Response("Error fetching video stream", status=500)
        return redirect(stream_url)
    def fetchAndLoadStreamOnly_DLEncode(self, lang:str, country:str, videoId:str, quality:t.Literal["tiny","small"]="tiny") -> Response:
        self.cleanup()
        smallpath = self.videocache/f"bt3ds_{videoId}_small.mp4" # 240p
        tinypath = self.videocache/f"bt3ds_{videoId}_tiny.mp4" # 144p
        stderr = stdout = subprocess.DEVNULL
        if self.debugmode:
            stderr = stdout = subprocess.PIPE
        if quality == "tiny" and tinypath.exists():
            if self.debugmode:
                print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} 144p (tiny) video for id {videoId} is cached, returning that instead...")
            return self.sendFileRange(str(tinypath), mime="video/mp4")
        if quality == "small" and smallpath.exists():
            if self.debugmode:
                print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} 240p (small) video for id {videoId} is cached, returning that instead...")
            return self.sendFileRange(str(smallpath), mime="video/mp4")
        # strings from ExeFS/HTML (forgot honestly):
        # video/mp4; codecs="avc1.42E01E, mp4a.40.2"
        # video/webm; codecs="vp9, opus"
        # video/webm; codecs="vp8, vorbis"
        # audio/webm; codecs="opus"
        # audio/mp4; codecs="mp4a.40.2"
        # video/mp4; codecs="avc1.42E01E, mp4a.40.2"
        if quality == "tiny" and smallpath.exists():
            tmpout = self.videocache/f"bt3ds_{videoId}_tiny.{uuid.uuid4().hex}.tmp.mp4"
            orientation = self.getVideoOrientation(smallpath)
            scale = self.getScale(orientation,"tiny")
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(smallpath),
                "-vf", scale,
                "-c:v", "libx264",
                "-profile:v", "baseline",
                "-level:v", "3.0",
                "-preset", "veryfast",
                "-b:v", "120k",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart",
                "-g", "30",
                str(tmpout),
            ]
            proc = subprocess.run(
                cmd,
                stdout=stdout,
                stderr=stderr,
                text=True
            )
            if self.debugmode:
                print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stdout: {proc.stdout}")
                print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stderr: {proc.stderr}")
                print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Encoding tiny video...")
            if proc.returncode != 0:
                print(f"{Fore.RED}[dl+encode]{Fore.RESET} error encoding small video (144p) (see above for stderr)")
                if tmpout.exists():
                    try:
                        tmpout.unlink()
                    except OSError:
                        self.fixreadonly(tmpout)
                return Response("error encoding 144p (TINY) video", status=500)
            tmpout.replace(tinypath)
            if self.debugmode:
                print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Done! Returning Range and video...")
            return self.sendFileRange(str(tinypath),mime="video/mp4")
        stream_url = self.fetchStream(lang,country,videoId,new3DS=False)
        if not stream_url:
            return Response("Error fetching video stream", status=500)
        orientation = self.getVideoOrientation(stream_url)
        scale = self.getScale(orientation,"small")
        tmp_small = self.videocache/f"bt3ds_{videoId}_small.{uuid.uuid4().hex}.tmp.mp4"
        # "master" command
        cmd = [
            "ffmpeg",
            "-y",
            "-i", stream_url,
            "-c:v", "libx264",
            "-vf", scale,
            "-profile:v", "baseline",
            "-level:v", "3.0",
            "-preset", "veryfast",
            "-b:v", "200k",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "96k",
            "-movflags", "+faststart",
            "-g", "30",
            str(tmp_small),
        ]
        proc = subprocess.run(
            cmd,
            stdout=stdout,
            stderr=stderr,
            text=True
        )
        if self.debugmode:
            print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stdout: {proc.stdout}")
            print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stderr: {proc.stderr}")
            print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Encoding small video...")
        if proc.returncode != 0:
            if self.debugmode:
                print(f"{Fore.RED}[dl+encode]{Fore.RESET} error encoding small video (240p) (see above for stderr)")
            if tmp_small.exists():
                try:
                    tmp_small.unlink()
                except OSError:
                    self.fixreadonly(tmp_small)
            return Response("Error encoding SMALL (240p) video", status=500)
        tmp_small.replace(smallpath)
        if quality == "small":
            if self.debugmode:
                print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Done! returning Range...")
            return self.sendFileRange(str(smallpath),mime="video/mp4")
        tmp_tiny = self.videocache/f"bt3ds_{videoId}_tiny.{uuid.uuid4().hex}.tmp.mp4"
        orientation = self.getVideoOrientation(smallpath)
        scale = self.getScale(orientation,"tiny")
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(smallpath),
            "-vf", scale,
            "-c:v", "libx264",
            "-profile:v", "baseline",
            "-level:v", "3.0",
            "-preset", "veryfast",
            "-b:v", "120k",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-g", "30",
            str(tmp_tiny),
        ]
        proc = subprocess.run(
            cmd,
            stdout=stdout,
            stderr=stderr,
            text=True
        )
        if self.debugmode:
            print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stdout: {proc.stdout}")
            print(f"{Fore.YELLOW}[ffmpeg]{Fore.RESET} stderr: {proc.stderr}")
            print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Encoding tiny video...")
        if proc.returncode != 0:
            if self.debugmode:
                print(f"{Fore.RED}[dl+encode]{Fore.RESET} error encoding tiny (144p) video (see above for stderr)")
            if tmp_tiny.exists():
                try:
                    tmp_tiny.unlink()
                except OSError:
                    self.fixreadonly(tmp_tiny)
            return Response("Error encoding TINY (144p) video", status=500)
        tmp_tiny.replace(tinypath)
        if self.debugmode:
            print(f"{Fore.BLUE}[dl+encode]{Fore.RESET} Done! returning Range...")
        return self.sendFileRange(str(tinypath),mime="video/mp4")
    def getVideo(self,videoId:str,country:str,lang:str,quality:t.Literal["tiny","small"],model:t.Literal["3ds","new3ds","unk"]="unk",vendor:t.Literal["NINTENDO","UNKNOWN"]="UNKNOWN") -> Response:
        vendors = ["NINTENDO"]
        models = ["3ds","new3ds"]
        if vendor in vendors and model in models:
            if model == "new3ds":
                return self.fetchAndLoadStreamOnly_New3DSOnly(lang,country,videoId,quality)
            elif model == "3ds":
                return self.fetchAndLoadStreamOnly_DLEncode(lang,country,videoId,quality)
        else:
            return self.fetchAndLoadStreamOnly_New3DSOnly(lang,country,videoId,quality)
