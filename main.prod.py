from __future__ import print_function, with_statement, division, absolute_import
import waitress
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
import colorama
import time
import threading
import secrets
import logging

from main import app as yt_prodapp, set_external_API_url, set_version_subpath, set_versioned_xlb_subpath, COOKIESPATH
from maint_server import app as yt_maintapp
from hulu_server import app as huluapp
from netflix_server import app as netflixapp
from functions import showlanip, clearscreen, update_innertube_key
from shared import *
from video import GetVideo

logging.Formatter.converter = time.gmtime
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)

# defaults
port         = 80
debugmode    = False
host         = "0.0.0.0"
secureserver = False
maint        = False

hulu_host    = "!.!.!.!"
hulu_port    = -1

netflix_host = "!.!.!.!"
netflix_port = -1

cfgexist     = False
cookiesexist = False
cookiesvalid = False
base         = Path(__name__).resolve().parent
config       = base/"config.xml"

def cleanup_schedule():
    print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Cleaning up in 6 seconds...",flush=True)
    time.sleep(6.00)
    schedulevideo = GetVideo()
    while True:
        print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Cleaning up videos older than 1 day...",flush=True)
        schedulevideo.cleanup()
        sleepfor = 86400
        sleepfor_min = sleepfor//86400
        print("%s[cleanup]%s Done! Next cleanup in %s day%s (%s second%s)..."%(Fore.MAGENTA,Fore.RESET,sleepfor_min,'' if abs(sleepfor_min) == 1 else 's',sleepfor,'' if abs(sleepfor) == 1 else 's'),flush=True)
        time.sleep(sleepfor)

def loadcfg():
    global host,port,debugmode,secureserver,config,cfgexist,maint,hulu_host,hulu_port,netflix_host,netflix_port,cookiesexist,cookiesvalid
    if not config.is_file():
        cfgexist = False
        return
    else:
        cfgexist = True
    parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
    root = ET.parse(config,parser=parser).getroot()
    def safeget(name,default=None):
        elem = root.find(f"cfg:{name}",CFG_NAMESPACE)
        if elem is None:
            return default
        if elem.get(XSI_NIL) == "true":
            return None
        return elem.text
    host = safeget("yt_host","0.0.0.0")
    if host == "localip":
        host = "0.0.0.0"
    try:
        port = int(safeget("yt_port","80"))
    except (ValueError,TypeError):
        port = 80
    debugmode = bool(safeget("debugging","false").lower().strip() == "true")
    secureserver = bool(safeget("secure","false").lower().strip() == "true")
    maint = safeget("maint","false").lower().strip() == "true"
    cookiesexist = COOKIESPATH.is_file()
    if cookiesexist:
        cookies_content = COOKIESPATH.read_text("utf-8")
        if not cookies_content.startswith("# Netscape HTTP Cookie File"): # standard header for cookies
            cookiesvalid = False
        else:
            cookiesvalid = True
    hulu_host = safeget("hulu_host","!.!.!.!")
    if hulu_host is None:
        hulu_host = "!.!.!.!"
    try:
        hulu_port = safeget("hulu_port","-1")
        if hulu_port is None:
            hulu_port = -1
        else:
            hulu_port = int(hulu_port)
    except (ValueError,TypeError):
        hulu_port = -1
    netflix_host = safeget("netflix_host","!.!.!.!")
    if netflix_host is None:
        netflix_host = "!.!.!.!"
    try:
        netflix_port = safeget("hulu_port","-1")
        if netflix_port is None:
            netflix_port = -1
        else:
            netflix_port = int(netflix_port)
    except (ValueError,TypeError):
        netflix_port= -1

if __name__ == "__main__":
    try:
        loadcfg()
        video = GetVideo()
        colorama.init(autoreset=True)
        Fore = colorama.Fore
        clearscreen()
        if not cfgexist:
            print("Please run main.py to create a configuration file first.")
            sys.exit(-1)
        if debugmode:
            print("Cannot host a production server while debug mode is on")
            sys.exit(-1)
        prot = "https" if secureserver else "http"
        print_host = showlanip()
        if host != "0.0.0.0":
            print_host = host
        servers = {1:"YouTube"}
        if (hulu_port>0 and hulu_host != "!.!.!.!") and (netflix_host != "!.!.!.!" and netflix_port>0):
            servers = {1:"YouTube",2:"Hulu Plus",3:"Netflix"}
        elif (hulu_port>0 and hulu_host != "!.!.!.!"):
            servers = {1:"YouTube",2:"Hulu Plus"}   
        choice = None
        while choice is None:
            print("What server do you want to run?")
            for i in servers:
                print(f"{i}: {servers[i]}")
            mesg = ""
            if len(servers) == 2:
                mesg = f"{colorama.Fore.CYAN}If you don't see Netflix, please run netflix_server.py to setup the server."
            elif len(servers) == 1:
                mesg = f"{colorama.Fore.CYAN}If you don't see Hulu Plus please run hulu_server.py to setup the server."
            print(mesg)
            choice_in = input("Enter your choice: ")
            try:
                choice = int(choice_in)
            except ValueError:
                print("Please enter a valid integer.")
                time.sleep(2.00)
                clearscreen()
        clearscreen()
        serveapp = None
        if str(servers.get(choice)).lower().strip() == "youtube":
            if maint:
                serveapp = yt_maintapp
            else:
                serveapp = yt_prodapp
                if not cookiesexist:
                    print(f"{Fore.RED}[err]{Fore.RESET} Cannot continue without cookies, they are required for production.")
                    print(f"{Fore.BLUE}[info]{Fore.RESET} For more info on how to export cookies, refer to this guide: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")
                    print(f"{Fore.BLUE}[info]{Fore.RESET} Once done, place the exported cookies in this directory with the filename \"cookies.txt\"")
                    sys.exit(-1)
                elif not cookiesvalid:
                    print(f"{Fore.RED}[err]{Fore.RESET} The cookies provided are invalid.")
                    print(f"{Fore.BLUE}[info]{Fore.RESET} For more info on how to re-export cookies, refer to this guide: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")
                    sys.exit(-1)
            serveapp.secret_key = FLASK_SECRET_KEY
            if not serveapp.secret_key:
                thistmpkey = secrets.token_hex(32)
                print(f"{Fore.RED}[err]{Fore.RESET} No Flask secret key has been configured")
                print(f"{Fore.BLUE}[info]{Fore.RESET} Open your environment (.env) file and add:")
                print(f"FLASK_SECRET_KEY={thistmpkey}",flush=True)
                sys.exit(-1)
            else:
                serveapp.secret_key = FLASK_SECRET_KEY
                policy = "Strict" if secureserver else "Lax"
                serveapp.config.update({
                    "SESSION_COOKIE_HTTPONLY": True,
                    "SESSION_COOKIE_SECURE": secureserver,
                    "SESSION_COOKIE_SAMESITE": policy,
                })
        elif str(servers.get(choice)).lower().strip() == "hulu plus":
            serveapp = huluapp
        elif str(servers.get(choice)).lower().strip() == "netflix":
            serveapp = netflixapp
        print(f"Serving {servers.get(choice)} on {prot}://{print_host}:{port}\n{Fore.YELLOW}Press CTRL+C to quit.")
        if maint and str(servers.get(choice)).lower().strip() == "youtube":
            print(f"{Fore.RED}Maintenance mode is enabled.")
        elif maint and str(servers.get(choice)).lower().strip() != "youtube":
            print(f"{Fore.RED}Maintenance mode is enabled, but it doesn't have any effect on the {str(servers.get(choice)).lower().strip()} server.")
        if servers.get(choice).lower().strip() == "youtube":
            video.createviddir()
            print(f"{Fore.MAGENTA}[cleanup]{Fore.RESET} Starting video cleanup thread..")
            thread = threading.Thread(target=cleanup_schedule,daemon=True,name="btvidcleanupd")
            thread.start()
            if not ENABLE_CREDS_OVERRIDE:
                update_innertube_key(INNERTUBE_KEY)
            set_external_API_url("https","lbl-api.idkwh.ct8.pl","443")
            set_version_subpath("api/ctr/GetVersion.php")
            set_versioned_xlb_subpath("api/ctr/GetVersionedXLB.php")
        trusted_proxies = f"127.0.0.1 localhost {print_host}" if print_host and print_host != "0.0.0.0" else "127.0.0.1 localhost"
        proxy_headers = "X-Forwarded-For X-Forwarded-Proto X-Forwarded-Host X-Forwarded-Port".lower()
        waitress.serve(
            app=serveapp,
            host=host,
            port=port,
            threads=7,
            trusted_proxy=trusted_proxies,
            trusted_proxy_headers=proxy_headers,
            clear_untrusted_proxy_headers=True,
            url_scheme=prot,
        )
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
