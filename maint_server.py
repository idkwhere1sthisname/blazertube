from __future__ import print_function, annotations, absolute_import
from flask import Flask, redirect, render_template, request, Response, send_from_directory, abort
from flask_cors import cross_origin
from flask_compress import Compress
from flask_ipban import IpBan
from werkzeug.serving import WSGIRequestHandler
from werkzeug.middleware.proxy_fix import ProxyFix
from pathlib import Path
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sys
import ssl
from xml.etree import ElementTree as ET

from shared import *
import debug
from functions import disable_warnings

BASE = Path(__file__).resolve().parent
METADIR = BASE/"meta"
config      = BASE/"config.xml"

app = Flask("BlazerTube Maintenance",static_folder="static",template_folder="templates")
app.wsgi_app = ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)
limiter = Limiter(app=app,key_func=get_remote_address,default_limits=["100 per minute"],storage_uri="memory://")
compress = Compress(app)
ipban = IpBan(app)
WSGIRequestHandler.protocol_version = "HTTP/1.1"

app.config["COMPRESS_REGISTER"] = True
app.config["COMPRESS_STREAMS"] = False

allowedfile = METADIR/"allowed.yml"
nuisancesfile = METADIR/"nuisances.yml"

ipban.load_allowed(allowedfile if allowedfile.is_file() else None)
ipban.load_nuisances(nuisancesfile if nuisancesfile.is_file() else None)

# defaults
port         = 80
debugmode    = False
host         = "0.0.0.0"
pempath      = BASE/"ssl"/"rootCA.crt"
keypath      = BASE/"ssl"/"rootCA.key"
secureserver = False
maint        = False

cfgexist          = False

def loadcfg():
    global host,port,debugmode,secureserver,keypath,pempath,config,cfgexist,maint,huluhost,huluport
    if not config.is_file():
        cfgexist = False
        return
    else:
        cfgexist = True
    ET.register_namespace("",CFG_NAMESPACE_STR)
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

@app.get("/")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
@limiter.limit("30 per minute")
def maint():
    return Response(render_template("maintenance.html"),status=200,headers={"Content-Type":"text/html; charset=utf-8"})

@app.route("/status",methods=["GET","HEAD"])
@cross_origin(methods=["GET","HEAD","OPTIONS"],origins=["*"])
def status():
    return Response(status=503)

@app.get("/favicon.ico")
@app.get("/static/favicon.ico")
@cross_origin(origins=["http://embedded.ctr","http://embedded.wii"],expose_headers=["Date"])
def favicon():
    return send_from_directory("static","favicon.ico")

@app.route("/static/configuration.xsd")
@app.route("/static/favicon_hulu.ico")
@app.route("/static/favicon_netflix.ico")
@app.route("/static/images/netflix/<string:netflixpath>",strict_slashes=False)
def routes404(netflixpath=None):
    return abort(404)

@app.route("/robots.txt")
def robotstxt():
    robotstxtfile = METADIR/"robots.txt"
    if robotstxtfile.is_file():
        return send_from_directory(METADIR,"robots.txt")
    else:
        return abort(404)

@app.before_request
def before_request_redirect():
    if debugmode:
        debug.request_dump(request,request.get_data(as_text=True,cache=True))
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
            return redirect(request.url.replace("https://","http://",1))
    if request.path != "/" and not request.path.startswith("/static/") and not request.path == "/favicon.ico" and not request.path == "/robots.txt" and not request.path == "/status":
        return redirect("/",code=302)

@app.after_request
def after_request(response:Response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if response.status_code == 204:
        response.headers.pop("Content-Type",None)
    return response

@app.route(403)
def forbidden(err):
    return Response(render_template("errors/403.html"))

@app.errorhandler(429)
def toomanyrequests(err):
    return Response(render_template("errors/429.html"))

@app.errorhandler(500)
def servererror(err):
    return Response(render_template("errors/500.html"))

@app.errorhandler(502)
@app.errorhandler(503)
def unavailable(err):
    return Response(render_template("errors/502.html"))

if __name__ == "__main__":
    loadcfg()
    if not cfgexist:
        print("Please run main.py to set up a configuration file.")
        sys.exit(-1)
    if not maint:
        print("Cannot run maintenance server when maintenance mode is not enabled.")
        sys.exit(-1)
    context = None
    if secureserver:
        disable_warnings(DeprecationWarning)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_ciphers("ALL:@SECLEVEL=0")
        context.minimum_version = ssl.TLSVersion.TLSv1
        context.maximum_version = ssl.TLSVersion.TLSv1
        if not pempath.is_file():
            print("PEM certificate not found.")
            sys.exit(-1)
        if not keypath.is_file():
            print("Private key not found.")
            sys.exit(-1)
        context.load_cert_chain(certfile=pempath,keyfile=keypath)
    app.run(host=host,port=port,debug=debugmode,threaded=True,ssl_context=context,extra_files=["config.xml",".env"])
