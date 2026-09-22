# script to redirect NASC URLs (pretendo, Nintendo) to a local server
# useful for Hulu if you don't want error 002-0110 thrown at your face every 2 seconds
# We originally used Charles' Proxy
from __future__ import print_function, absolute_import
from mitmproxy import http
from pathlib import Path
from xml.etree import ElementTree as ET
import subprocess as sp
import sys
import time

from shared import *
from functions import clearscreen,showlanip
from main import config

cfgexist          = False
naschost          = "!.!.!.!"
nascport          = -1
proxyport         = -1

NASC_URLS         = ["nasc.pretendo.cc","nasc.nintendowifi.net"]
KEY_HEADERS       = ["-----begin private key-----","bag attributes","-----begin rsa private key-----"]
PEM_HEADERS       = ["-----begin certificate-----","bag attributes"]

base              = Path(__file__).parent
ssl               = base/"ssl"
proxycerts        = ssl/"proxy"
ctr_common_Pem    = proxycerts/"ctr-common-1.pem"
ctr_common_Key    = proxycerts/"ctr-common-1.key"
ctr_common_combo  = proxycerts/"ctr-common-1_combo.pem"

def loadcfg():
    global naschost,nascport,config,cfgexist,proxyport
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
    naschost = safeget("nasc_host","0.0.0.0")
    if naschost is None:
        naschost = "!.!.!.!"
    elif naschost == "localip" or naschost == "0.0.0.0":
        naschost = showlanip()
    try:
        nascport = safeget("nasc_port","-1")
        if nascport is None:
            nascport = -1
        else:
            nascport = int(nascport)
    except (Exception,ValueError,TypeError):
        nascport = -1
    try:
        proxyport = safeget("proxy_port","-1")
        if proxyport is None:
            proxyport = -1
        else:
            proxyport = int(proxyport)
    except:
        proxyport = -1

loadcfg()

class NASCRedirect:
    def request(self,flow:http.HTTPFlow)->None:
        if flow.request.pretty_host in NASC_URLS:
            flow.request.scheme = "https"
            flow.request.host = naschost
            flow.request.port = nascport
            print("Redirecting %s to %s:%s/%s"%(flow.request.pretty_host,naschost,nascport,flow.request.path))

addons = [NASCRedirect()]

if __name__ == "__main__":
    if not cfgexist:
        print("Please run main.py then nasc.py to set up a configuration file.")
        sys.exit(-1)
    if naschost == "!.!.!.!" or nascport<0:
        print("Please run nasc.py to set up the configuration file to be used with NASC.")
        sys.exit(-1)
    clearscreen()
    if proxyport<0:
        proxyport = None
        while proxyport is None:
            clearscreen()
            try:
                port_in = input("Please enter a proxy port (default: 8080): ")
                if port_in is None or port_in.strip() == "": port_in = "8080"
                proxyport = int(port_in)
                if not 1 <= proxyport <= 65535:
                    raise TypeError
            except ValueError:
                print("Please enter a valid integer.")
                time.sleep(2.00)
            except TypeError:
                proxyport = None
                print("The port must be higher than 1 and lower than 65535.")
                time.sleep(2.00)
        parser = ET.XMLParser(target=PARSER_KEEP_COMMENTS())
        tree = ET.parse(config,parser=parser)
        root = tree.getroot()
        ET.register_namespace("",CFG_NAMESPACE_STR)
        proxyportelem = root.find("cfg:proxy_port",CFG_NAMESPACE)
        proxyportelem.attrib.pop(f"{{{XMLSCHEMA_INSTANCE_NS}}}nil",None)
        proxyportelem.text = str(proxyport)
        tree.write(config,encoding="utf-8",xml_declaration=True)
    if not ctr_common_Pem.is_file():
        print("Please extract the CTR Common 1 certificate in PEM form and place it in /%s"%(str(ctr_common_Pem.relative_to(base)).replace("\\","/")))
        sys.exit(-1)
    if not ctr_common_Key.is_file():
        print("Please extract the CTR Common 1 certificate's private key and place it in /%s"%(str(ctr_common_Key.relative_to(base)).replace("\\","/")))
        sys.exit(-1)
    if not ctr_common_combo.is_file():
        keycnt = ctr_common_Key.read_text()
        pemcnt = ctr_common_Pem.read_text()
        if not any(header in keycnt.lower() for header in KEY_HEADERS):
            print("This doesn't look like a valid private key.")
            sys.exit(-1)
        if not any(header in pemcnt.lower() for header in PEM_HEADERS):
            print("This doesn't look like a valid certificate.")
            sys.exit(-1)
        ctr_common_combo.write_text(f"{keycnt}\n{pemcnt}")
        print("Key+Combo certificate created.")
    cmd = [
        "mitmweb",
        "-s",__file__,
        "--listen-host=0.0.0.0",
        f"--listen-port={str(proxyport)}",
        f"--certs=*={str(ctr_common_combo)}",
        "--ssl-insecure",
        "--set=ciphers_client=ALL:@SECLEVEL=0",
        "--set=ciphers_server=ALL:@SECLEVEL=0",
    ]
    try:
        print(f"To fix 006-0803, open the Web Dashboard (usually http://127.0.0.1:{proxyport+1} + a key generated by mitmweb), then go to OPTIONS, EDIT OPTIONS,")
        print("Search for \"TLS_\", and set TLS_VERSION_CLIENT_MIN, TLS_VERSION_CLIENT_MAX, TLS_VERSION_SERVER_MIN, TLS_VERSION_SERVER_MAX to TLS1")
        print("You can ignore the OpenSSL errors that will get printed here.")
        sp.run(cmd,check=True,stderr=sp.DEVNULL)
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)
