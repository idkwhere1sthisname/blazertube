from __future__ import print_function, absolute_import
from flask import Flask, Response, request, abort, render_template, redirect, send_from_directory
from xml.etree import ElementTree as ET
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import cross_origin
from flask_compress import Compress
from flask_ipban import IpBan
import ssl
import time
import sys
from werkzeug.serving import WSGIRequestHandler
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timezone
from email.utils import format_datetime

from main import config,secureserver,pempath,keypath,METADIR
import debug as debugmodule
from shared import *
from functions import clearscreen, disable_warnings

allowedfile     = METADIR/"allowed.yml"
nuisancesfile   = METADIR/"nuisances.yml"

app             = Flask("Hulu Plus 3DS",template_folder="templates/hulu")
app.wsgi_app    = ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)
limiter         = Limiter(app=app,key_func=get_remote_address,default_limits=["100 per minute"],storage_uri="memory://")
compress        = Compress(app)
ipban           = IpBan(app)
WSGIRequestHandler.protocol_version = "HTTP/1.1"

ipban.load_nuisances(nuisancesfile if nuisancesfile.is_file() else None)
ipban.load_allowed(allowedfile if allowedfile.is_file() else None)
app.config["COMPRESS_REGISTER"] = True
app.config["COMPRESS_STREAMS"] = False

huluhost        = "!.!.!.!"
huluport        = -1

debugmode       = False
maint           = False

def loadcfg():
    global huluhost,huluport,debugmode,config,cfgexist,maint
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
    huluhost = safeget("hulu_host","!.!.!.!")
    if huluhost is None:
        huluhost = "!.!.!.!"
    elif huluhost == "localip":
        huluhost = "0.0.0.0"
    try:
        huluport = safeget("hulu_port","-1")
        if huluport is None:
            huluport = -1
        else:
            huluport = int(huluport)
    except (Exception,ValueError,TypeError):
        huluport = -1
    debugmode = bool(safeget("debugging","false").lower() == "true")
    maint = bool(safeget("maint","false").lower() == "true")

@app.route("/time.php")
@app.route("/time")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def timeroute():
    u = datetime.now(timezone.utc)
    Date = format_datetime(u,usegmt=True)
    return Response("",200,{"Date":Date,"Content-Type":"text/plain;charset=UTF-8"})

@app.route("/hulu/index.html")
def index():
    return Response(render_template("index.html"),status=200)

@app.route("/")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def indexredirect():
    return redirect("/hulu/index.html")

@app.route("/status",methods=["GET","HEAD"])
def status():
    s = 204
    if maint:
        s = 502
    return Response(status=s)

@app.before_request
def before_request():
    if debugmode:
        debugmodule.request_dump(request,request.get_data(as_text=True,cache=True))

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
@app.errorhandler(502)
def badgateway(err):
    return render_template("errors/502.html"),502
@app.errorhandler(500)
def internalerror(err):
    return render_template("errors/500.html"),500

@app.route("/static/favicon.ico")
@app.route("/favicon.ico")
def favicon_hulu():
    return send_from_directory("static","favicon_hulu.ico"),200,{"Content-Type":"image/x-icon"}

@app.route("/robots.txt")
def robotstxt():
    robotstxtfile = METADIR/"robots.txt"
    if robotstxtfile.is_file():
        return send_from_directory(METADIR,"robots.txt")
    else:
        return abort(404)

@app.route("/static/configuration.xsd")
@app.route("/static/favicon_netflix.ico")
@app.route("/static/images/netflix/<string:subpath>",strict_slashes=False)
def routes404(subpath=None):
    return abort(404)

@app.route("/debug.html")
@app.route("/debug")
def debugpage():
    if debugmode:
        return render_template("debug.html")
    else:
        return abort(404)

if __name__ == "__main__":
    loadcfg()
    if not cfgexist:
        print("Please run main.py to create a configuration file first.")
        sys.exit(-1)
    if huluport<0 or huluhost == "!.!.!.!":
        if huluport<0:
            huluport = None
            while huluport is None:
                clearscreen()
                try:
                    port_in = input("Choose a server port (default: 80): ")
                    if port_in is None or port_in.strip() == "": port_in = "80"
                    huluport = int(port_in)
                    if not 1 <= huluport <= 65535:
                        raise TypeError
                except ValueError:
                    print("Please enter a valid integer")
                    time.sleep(2.00)
                except TypeError:
                    huluport = None
                    print("The port must be greater than 1 and lower than 65535.")
                    time.sleep(2.00)
        if huluhost == "!.!.!.!":
            huluhost = input("Where should the server run? (default: 0.0.0.0)")
            if huluhost is None or huluhost.strip() == "": huluhost = "0.0.0.0"
        parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
        tree = ET.parse(config,parser=parser)
        root = tree.getroot()
        ET.register_namespace("",CFG_NAMESPACE_STR)
        huluh = root.find("cfg:hulu_host",CFG_NAMESPACE)
        hulup = root.find("cfg:hulu_port",CFG_NAMESPACE)
        huluh.text = huluhost
        huluh.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        hulup.text = str(huluport)
        hulup.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        tree.write(config,encoding="utf-8",xml_declaration=True)
    context = None
    if secureserver:
        disable_warnings(DeprecationWarning)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_ciphers("ALL:@SECLEVEL=0")
        context.minimum_version = ssl.TLSVersion.TLSv1
        context.maximum_version = ssl.TLSVersion.TLSv1
        context.load_cert_chain(certfile=pempath,keyfile=keypath)
    app.run(host=huluhost,port=huluport,debug=debugmode,ssl_context=context)
