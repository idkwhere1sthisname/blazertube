# script used for development before Pretendo enabled NASC for YouTube
# useful if you don't want error 002-0110 thrown at your face every 2 seconds while using Hulu Plus
from __future__ import print_function, annotations, absolute_import
from flask import Flask, Response, request, abort
from flask_ipban import IpBan
from flask_cors import cross_origin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import base64
import os
from xml.etree import ElementTree as ET
from werkzeug.serving import WSGIRequestHandler
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import time
import sys
import ssl

from shared import *
from functions import clearscreen, disable_warnings
from main import BASE,config,METADIR

nuisancesfile   = METADIR/"nuisances.yml"
allowedfile     = METADIR/"allowed.yml"

app             = Flask("NASC Server")
app.wsgi_app    = ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)
ipban           = IpBan(app)
limiter         = Limiter(app=app,key_func=get_remote_address,default_limits=["70 per minute"],storage_uri="memory://")
WSGIRequestHandler.protocol_version = "HTTP/1.1"

ipban.load_allowed(allowedfile if allowedfile.is_file() else None)
ipban.load_nuisances(nuisancesfile if nuisancesfile.is_file() else None)

def make_token():
    return base64.b64encode(os.urandom(16)).decode().replace("=", "").replace("/","-") # NASC

def b64encode_val(val: str) -> str:
    return base64.b64encode(val.encode()).decode().replace("=", "*").replace("/","-") # NASC

def make_date():
    now = datetime.now()
    dt_fmt = now.strftime("%Y%m%d%H%M%S")
    enc = b64encode_val(dt_fmt)
    return enc

def b64(s: bytes) -> str:
    return base64.b64encode(s).decode()

@app.route("/ac", methods=["POST"],strict_slashes=False)
@cross_origin()
def ac():
    if request.method != "POST":
        print(f"Invalid request method: {request.method}")
        return abort(405)
    
    date = make_date()
    retry_cd = b64encode_val("0") # -> MA**
    return_cd = b64encode_val("001") # -> MDA3
    tkn = make_token()
    form = request.form.get
    action = form("action") # TE9HSU4*
    print(f'BOSS ID: {form("bssid").replace("*","=").replace("/","-")}')
    print(f'Title ID: {form("titleid").replace("*","=").replace("/","-")}')
    print(f"NASC action: {action}")
    locator = b64encode_val("0.0.0.0:00") # app doesn't verify the locator, token or anything
    if action == "TE9HSU4*": # LOGIN
        print("NASC requested LOGIN")
        response = (
            f"locator={locator}"
            f"&retry={retry_cd}"
            f"&returncd={return_cd}"
            f"&token={tkn}"
            f"&datetime={date}"
        )
        return Response(response,mimetype="text/plain",headers={
            "Content-Type": "text/plain;charset=ISO-8859-1",
            "NODE": "wifi-authserver-service.wifi-authserver.svc.cluster.local",
            "Server": "Nintendo"
        })
    elif action == "U1ZDTE9D": # SVCLOC
        print("NASC requested SVCLOC")
        return_cd = b64encode_val("007")
        svchost = b64encode_val("0.0.0.0")
        response = (
            f"retry={retry_cd}"
            f"&returncd={return_cd}"
            f"&servicetoken={tkn}"
            f"&svchost={svchost}"
            f"&datetime={date}"
        )

        return Response(response=response, mimetype="text/plain", headers={
            "Content-Type": "text/plain;charset=ISO-8859-1",
            "NODE": "wifi-authserver-service.wifi-authserver.svc.cluster.local",
            "Server": "Nintendo"
        })
    elif action == "TE9HSU4*":
        print("NASC requested ACCESS") # DEFAULT
        response = (
            f"retry={retry_cd}"
            f"&returncd={return_cd}"
            f"&datetime={date}"
        )

        return Response(response=response, mimetype="text/plain;charset=ISO-8859-1", headers={
            "Content-Type": "text/plain;charset=ISO-8859-1",
            "X-GameId": "000B0F00",
            "NODE": "wifi-authserver-service.wifi-authserver.svc.cluster.local",
            "Server": "Nintendo"
        })
    else:
        print(f"Unknown NASC action:\nACTION: {action}")
        return Response(f"retry={retry_cd}&returncd=MA**&datetime={date}","text/plain")

@app.route("/pr",methods=["POST"])
@cross_origin()
def pr():
    if request.method != "POST":
        print(f"Invalid request method: {request.method}")
        return abort(405)
    
    print("NOTE: pr is a stub in NASC")
    resp = (
        "prwords=0"
        "&returncd=000"
        f"&datetime={make_date()}"
    )

    return Response(resp,"text/plain",{
        "Content-Type": "text/plain;charset=ISO-8859-1",
        "NODE": "wifi-authserver-service.wifi-authserver.svc.cluster.local",
        "Server": "Nintendo"
    })

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
    host = safeget("nasc_host","0.0.0.0")
    if host is None:
        host = "!.!.!.!"
    elif host == "localip":
        host = "0.0.0.0"
    try:
        port = safeget("nasc_port","9000")
        if port is None:
            port = -1
        else:
            port = int(port)
    except (Exception,ValueError,TypeError):
        port = 9000
    debugmode = bool(safeget("debugging","false").lower() == "true")

if __name__ == "__main__":
    if not config.is_file():
        print("Please run main.py to create a configuration file first.")
        sys.exit(-1)
    choice = None
    while choice is None and not config.is_file():
        print("If you're going to use Pretendo, there is no need to run this server")
        print("Unless you plan to use Hulu Plus or Netflix")
        choice_in = input("Enter \"y\" to continue, or \"n\" to exit: ").lower().strip()
        if choice_in not in ["y","n"]:
            print("Please enter a valid choice.")
        else:
            choice = choice_in
            break
    if choice == "n":
        sys.exit(0)
    else: pass
    loadcfg()
    if port<0 or host == "!.!.!.!":
        if port<0:
            port = None
            while port is None:
                clearscreen()
                try:
                    port_in = input("Please choose a NASC port (default: 9000): ").lower().strip()
                    if port_in == "": port_in = "9000"
                    port = int(port_in)
                    if not 1 <= port <= 65535:
                        raise TypeError
                except ValueError:
                    print("Please enter a valid integer.")
                    time.sleep(2.00)
                except TypeError:
                    port = None
                    print("The port must be greater than 1 and lower than 65535.")
                    time.sleep(2.00)
        if host == "!.!.!.!":
            host = input("Where should the NASC server run? (default: 0.0.0.0): ").strip().lower()
            if host == "": host = "0.0.0.0"
        parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
        tree = ET.parse(config,parser=parser)
        root = tree.getroot()
        ET.register_namespace("",CFG_NAMESPACE_STR)
        nashost = root.find("cfg:nasc_host",CFG_NAMESPACE)
        nasport = root.find("cfg:nasc_port",CFG_NAMESPACE)
        nashost.text = host
        nashost.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        nasport.text = str(port)
        nasport.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        tree.write(config,encoding="utf-8",xml_declaration=True)
    # HTTPS is required here
    ctr_common_Key = BASE/"ssl"/"proxy"/"ctr-common-1.key"
    ctr_common_Pem = BASE/"ssl"/"proxy"/"ctr-common-1.pem"
    KEY_HEADERS       = ["-----begin private key-----","bag attributes","-----begin rsa private key-----"]
    PEM_HEADERS       = ["-----begin certificate-----","bag attributes"]
    if not ctr_common_Pem.is_file():
        print("Please extract the CTR Common 1 certificate in PEM form and place it in /%s"%(str(ctr_common_Pem.relative_to(BASE)).replace("\\","/")))
        sys.exit(-1)
    if not ctr_common_Key.is_file():
        print("Please extract the CTR Common 1 certificate's private key and place it in /%s"%(str(ctr_common_Key.relative_to(BASE)).replace("\\","/")))
        sys.exit(-1)
    keycnt = ctr_common_Key.read_text()
    pemcnt = ctr_common_Pem.read_text()
    if not any(header in keycnt.lower() for header in KEY_HEADERS):
        print("This doesn't look like a valid private key.")
        sys.exit(-1)
    if not any(header in pemcnt.lower() for header in PEM_HEADERS):
        print("This doesn't look like a valid certificate.")
        sys.exit(-1)
    print("The certificates are valid! Proceeding...")
    disable_warnings(DeprecationWarning)
    context = None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.set_ciphers("ALL:@SECLEVEL=0")
    context.minimum_version = ssl.TLSVersion.TLSv1
    context.maximum_version = ssl.TLSVersion.TLSv1
    keypath = ctr_common_Key.resolve()
    pempath = ctr_common_Pem.resolve()
    context.load_cert_chain(certfile=pempath,keyfile=keypath)
    app.run(host,port,debugmode,ssl_context=context)
