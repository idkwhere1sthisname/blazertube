from __future__ import print_function, with_statement, absolute_import
from flask import Flask, send_from_directory, abort, request, Response
from flask_cors import cross_origin
from flask_limiter import Limiter
from flask_ipban import IpBan
from flask_limiter.util import get_remote_address
from pathlib import Path
from xml.sax.saxutils import escape as esc
from xml.etree import ElementTree as ET
import sys
from werkzeug.serving import WSGIRequestHandler
from werkzeug.middleware.proxy_fix import ProxyFix
import time
import base64

from shared import *
from functions import clearscreen,showlanip
import debug as debugmodule

BASE = Path(__file__).resolve().parent
METADIR = BASE/"meta"

allowedfile = METADIR/"allowed.yml"
nuisancefile = METADIR/"nuisances.yml"

app = Flask("Netflix 3DS Server",static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)
limiter = Limiter(app=app,key_func=get_remote_address,default_limits=["100 per minute"],storage_uri="memory://")
ipban = IpBan(app)
ipban.load_allowed(allowedfile if allowedfile.is_file() else None)
ipban.load_nuisances(nuisancefile if nuisancefile.is_file() else None)
NS = "http://www.netflix.com/eds/nccp/2.8.1"

config = BASE/"config.xml"
cfgexist = False

port         = -1
debugmode    = False
host         = "!.!.!.!"

def loadcfg():
    global host,port,debugmode,config,cfgexist
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
    host = safeget("netflix_host","!.!.!.!")
    if host is None:
        host = "!.!.!.!"
    elif host == "localip":
        host = "0.0.0.0"
    try:
        port = safeget("netflix_port","-1")
        if port is None:
            port = -1
        port = int(port)
    except (Exception,ValueError,TypeError):
        port = -1
    debugmode = bool(safeget("debugging","false").lower().strip() == "true")

@app.route("/<string:regionCode>/nrd/3ds/<string:image>")
@cross_origin()
def cdn0(regionCode,image):
    if not image or not regionCode:
        return abort(404)
    if regionCode not in ["en_CA","us"]:
        return abort(404)
    baseImages = BASE/"static"/"images"/"netflix"/"ctr"/regionCode
    imagepath = baseImages/image
    if not imagepath.is_file():
        return abort(404)
    return send_from_directory(baseImages,image)

@app.route("/nccp/controller/<string:AppVersion>/<string:Endpoint>",methods=["POST","GET"],strict_slashes=False)
@cross_origin()
def nccpcontroller(AppVersion,Endpoint):
    print("debug module doesn't play well with XML forms...")
    print("app version:",AppVersion)
    print("endpoint:",Endpoint)
    now = int(time.time())
    if Endpoint == "nasverify":
        payload = """<nccp:clientservertimes>
<nccp:servertime>1270001</nccp:servertime>
<nccp:clienttime>1270002</nccp:clienttime>
</nccp:clientservertimes>"""
        inner = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        resp = f"""<?xml version="1.0" encoding="UTF-8"?>
<nccp:response xmlns:nccp="{esc(NS)}" encrypted="false" version="2.8.1" method="nasverify">
\t<nccp:responseheader>
\t\t<nccp:result>
\t\t\t<nccp:success>true</nccp:success>
\t\t\t<nccp:code>0</nccp:code>
\t\t</nccp:result>
\t\t<nccp:parameters>
\t\t\t<nccp:protocolversion>0</nccp:protocolversion>
\t\t\t<nccp:retrycontrol>
\t\t\t\t<nccp:mintimeout>4</nccp:mintimeout>
\t\t\t\t<nccp:lowfrequencypollinterval>60</nccp:lowfrequencypollinterval>
\t\t\t\t<nccp:mediumfrequencypollinterval>30</nccp:mediumfrequencypollinterval>
\t\t\t\t<nccp:highfrequencypollinterval>10</nccp:highfrequencypollinterval>
\t\t\t\t<nccp:hightomediumpollswitchinterval>120</nccp:hightomediumpollswitchinterval>
\t\t\t\t<nccp:mediumtolowpollswitchinterval>300</nccp:mediumtolowpollswitchinterval>
\t\t\t</nccp:retrycontrol>
\t\t\t<nccp:loginterval>3600</nccp:loginterval>
\t\t\t<nccp:loglevel>7</nccp:loglevel>
\t\t\t<nccp:supportphone>000-000-0000</nccp:supportphone>
\t\t</nccp:parameters>
\t</nccp:responseheader>
\t<nccp:result>
\t\t<nccp:payload encrypted="true">{inner}</nccp:payload>
\t\t<nccp:method name="nasverify" encrypted="false" nccp:servertime="{now}" nccp:clienttime="{now}"></nccp:method>
\t</nccp:result>
</nccp:response>
"""
    print(resp)
    return Response(resp,status=200,mimetype="text/xml; charset=utf-8")

@app.route("/favicon.ico")
@app.route("/static/favicon.ico")
def favicon():
    return send_from_directory("static","favicon_netflix.ico")

@app.route("/static/configuration.xsd")
@app.route("/static/favicon_hulu.ico")
def routes404(subpath=None):
    return abort(404)

@app.route("/robots.txt")
def robotstxt():
    robotstxtfile = METADIR/"robots.txt"
    if robotstxtfile.is_file():
        return send_from_directory(METADIR,"robots.txt")
    else:
        return abort(404)

@app.before_request
def before_request():
    debugmodule.request_dump(request,request.get_data(as_text=True,cache=True))

if __name__ == "__main__":
    WSGIRequestHandler.protocol_version = "HTTP/1.1"
    context = None
    loadcfg()
    if not cfgexist:
        print("Please run main.py to setup a configuration file first.")
        sys.exit(-1)
    if host == "!.!.!.!" or port < 0:
        clearscreen()
        localip = showlanip()
        if host == "!.!.!.!":
            host = input(f"On what host should the Netflix server run? (leave blank for 0.0.0.0): ")
            if not host:
                host = "0.0.0.0"
        if port < 0:
            port = None
            while port is None:
                try:
                    port_in = input("On what port should the Netflix server run? (leave blank for 80): ")
                    if not port_in:
                        port_in = 80
                    port_in = int(port_in)
                    port = port_in
                    if not 1 <= port <= 65535:
                        raise TypeError
                    break
                except ValueError:
                    print("Please enter a valid integer.")
                    time.sleep(2.00)
                except TypeError:
                    port = None
                    print("The port must be higher than 1 and lower than 65535.")
                    time.sleep(2.00)
        parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
        tree = ET.parse(config,parser=parser)
        root = tree.getroot()
        ET.register_namespace("",CFG_NAMESPACE_STR)
        nethost = root.find("cfg:netflix_host",CFG_NAMESPACE)
        netport = root.find("cfg:netflix_port",CFG_NAMESPACE)
        nethost.text = host
        nethost.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        netport.text = str(port)
        netport.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        tree.write(config,encoding="utf-8",xml_declaration=True)
    app.run(host=host,port=port,debug=debugmode,ssl_context=context)
