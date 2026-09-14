#!/usr/bin/env python
# docs
"""
Netflix is entirely API based unlike previous VOD apps (Hulu Plus/YouTube/Crunchyroll (Wii)/etc..).
v1 version of the Wii channel had a DOL inside the main DOL!
It also uses Rendez Vous, which might be the same for the 3DS app.
It is ZLIB compressed, just like the HTML launcher inside the VOD apps.
Known endpoints:
- logblob
- ping
- nasverify
- preregister
- register
- authenticationrenewal
- license
- usermoviemetadata(?)
- queuechange
- queue
- ecclinkprovision(?)
- webapienroll
- bdcpspermission(?)
- webapiproxy
- npticketprovision
Nonetheless, this patcher simply creates a patched binary with different URLs.
The application only released in America

UPDATE 22/08/2026 (dd.mm.yyyy): WE GOT PAST PING ON THE NETFLIX WII DISK!!!
IT IS NOW STUCK AT REGISTER (after ecclinkprovision and preregister).
Not much on 3DS Netflix unfortunately.
"""
from __future__ import print_function
import ips
from pathlib import Path
import sys
import shutil
import stat

from lib.patcher_shared import *

localip = showlanip()
base = Path(__file__).resolve().parent

clearscreen()
host = input(f"What should the host be? (ONLY HTTP IS SUPPORTED) (leave empty for http://{localip}): http://")
if not host:
    host = f"http://{localip}"
else:
    host = f"http://{host}"
maxlen = 0x10 #dec. 16
host_nohttp_prefix = host.removeprefix("http://")
host_nohttp = host.removeprefix("http")
host_nohttp_prefix_bytes = host.removeprefix("http://").encode("utf-8")
host_nohttp_bytes = host.removeprefix("http").encode("utf-8")
if len(host_nohttp_prefix) > maxlen:
    print("The chosen host or domain is too long.\nPlease enter a shorter one.")
    sys.exit(-1)
port = None
while port is None:
    try:
        port_in = input("What should the port be (leave empty for 80): ")
        if not port_in: port_in = 80
        port = int(port_in)
    except ValueError:
        print("Please enter a valid integer.")
if port == 80 or port == 443:
    host = f"{host}"
else:
    host = f"{host}:{port}/"
binpath = base/"bin"/"netflix"/"USAOnly.bin"
if not binpath.is_file():
    print("Base binary not found.\nPlease redownload it.")
    sys.exit(-1)
print("Patching...")
titleId = 0x0004000000057700
localeContents = """USA EN"""
# main URLs
# these use HTTPS
URLoffsets = {
    (0x00FD4A8, 0x3C), # NCCP URL
    (0x003438EC, 0x18), # login URL
    (0x003C6550, 0x2C), # moviecontrol URL
    (0x0044406C, 0x2C), # moviecontrol URL again
}
httpOnlyURLS = {
    (0x0033CEB3, 0x34), # instant sorting
    (0x0033CEF7, 0x33), # search URL (term_matches/starts_with)
    (0x0033CF3F, 0x2D), # format search (disc)
    (0x0033CF7F, 0x30), # format search (instant)
    (0x0033FD9F, 0x2D), # title formats (disc)
    (0x0033FDDF, 0x3C), # title formats (instant)
}
# other patches
otherPatches = {
    (0x00756398, 0x04), # https:// -> http://
}
# embedded images/assets URLs
# these URLs are very similar to the Wii channel ones
cdnURLS_USA = {
    (0x002F1BDB, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_1_upper.jpg
    (0x002F1C17, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_1_lower.jpg
    (0x002F1C53, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_2_upper.jpg
    (0x002F1C8F, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_2_lower.jpg
    (0x002F1CCB, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_3_upper.jpg
    (0x002F1D07, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_3_lower.jpg
    (0x002F1D43, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_4_upper.jpg
    (0x002F1D7F, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_4_lower.jpg
    (0x002F1DBB, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_5_upper.jpg
    (0x002F1DF7, 0x34), # http://cdn-0.nflximg.com/us/nrd/3ds/nfp_us_page_5_lower.jpg
}

# Canadian assets URLs
# For some reason these exist
cdnURLS_CAN = {
    (0x002F1EAF, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_1_upper.jpg
    (0x002F1EEB, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_1_lower.jpg
    (0x002F1F27, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_2_upper.jpg
    (0x002F1F63, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_2_lower.jpg
    (0x002F1F9F, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_3_upper.jpg
    (0x002F1FDB, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_3_lower.jpg
    (0x002F2017, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_4_upper.jpg
    (0x002F2053, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_4_lower.jpg
    (0x002F208F, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_5_upper.jpg
    (0x002F20CB, 0x34), # http://cdn-0.nflximg.com/en_CA/nrd/3ds/nfp_page_5_lower.jpg
}

with open(binpath,"rb") as f:
    bincontents = bytearray(f.read())

print("Patching main URLs..")
mainpatchret = httpOnlypatchesret = otherPatchesret = cdnURLSret = cdnURLSCANret = 0
for offset,patchlength in URLoffsets:
    ogbytes = bytes(bincontents[offset:offset+patchlength])
    url = ogbytes.split(b"\x00")[0]
    if url.startswith(b"s://"):
        pathstart = url.find(b"/",4)
        path = url[pathstart:] if pathstart != -1 else b""
        newurl = host_nohttp_bytes+path
        if len(newurl) <= patchlength:
            padded = newurl.ljust(patchlength,b"\x00")
            bincontents[offset:offset+patchlength] = padded
            mainpatchret += 1
print("Patching HTTP URLs...")
for offset,patchlength in httpOnlyURLS:
    ogbytes = bytes(bincontents[offset:offset+patchlength])
    url = ogbytes.split(b"\x00")[0]
    pathstart = url.find(b"/",0)
    path = url[pathstart:] if pathstart != -1 else b""
    newurl = host_nohttp_prefix_bytes+path
    if len(newurl) <= patchlength:
        padded = newurl.ljust(patchlength,b"\x00")
        bincontents[offset:offset+patchlength] = padded
        httpOnlypatchesret += 1
print("Applying miscellanous patches...")
for offset,patchlength in otherPatches:
    newprotocol = b"://".ljust(patchlength,b"\x00")
    bincontents[offset:offset+patchlength] = newprotocol
    otherPatchesret += 1
print("Patching CDN URLs (USA)...")
for offset,patchlength in cdnURLS_USA:
    ogbytes = bytes(bincontents[offset:offset+patchlength])
    url = ogbytes.split(b"\x00")[0]
    pathstart = url.find(b"/",7)
    path = url[pathstart:] if pathstart != -1 else b""
    newurl = host_nohttp_prefix_bytes+path
    if len(newurl) <= patchlength:
        padded = newurl.ljust(patchlength,b"\x00")
        bincontents[offset:offset+patchlength] = padded
        cdnURLSret += 1
print("Patching CDN URLs (Canada)...")
for offset,patchlength in cdnURLS_CAN:
    ogbytes = bytes(bincontents[offset:offset+patchlength])
    url = ogbytes.split(b"\x00")[0]
    pathstart = url.find(b"/",7)
    path = url[pathstart:] if pathstart != -1 else b""
    newurl = host_nohttp_prefix_bytes+path
    if len(newurl) <= patchlength:
        padded = newurl.ljust(patchlength,b"\x00")
        bincontents[offset:offset+patchlength] = padded
        cdnURLSCANret += 1

print("All done!")
print(f"Endpoints patched: {mainpatchret+httpOnlypatchesret} (HTTPOnly: {httpOnlypatchesret}, mainUrls: {mainpatchret})")
print(f"CDN Urls patched: {cdnURLSret+cdnURLSCANret} (USA: {cdnURLSret}, Canada: {cdnURLSCANret})")
print(f"Miscellanous patched applied: {otherPatchesret}")
print(f"Overall: {mainpatchret+httpOnlypatchesret+cdnURLSret+cdnURLSCANret+otherPatchesret}")

os.makedirs("temp",exist_ok=True)
tempdir = base/"temp"
bintemp = tempdir/"tmpbin"
with open(bintemp,"wb") as f:
    f.write(bincontents)

print("Finalizing...")
patchpath = base/"patch"
finalpath = patchpath/"luma"/"titles"/f"{titleId:016X}"
localepath = finalpath/"locale.txt"
finalbin = finalpath/"code.bin"
os.makedirs(finalpath,exist_ok=True)

shutil.move(bintemp,finalbin)
with open(localepath,"w") as f:
    f.write(localeContents)

if tempdir.is_dir():
    shutil.rmtree(tempdir,onerror=fixreadonly)

print("Done!")
print("Be sure to enable Game Patching in Luma3DS's settings.")
print("Then add the contents of the patch folder on your SD Card's root.")
print("If you don't want the locale to be overridden, delete /%s"%(str(localepath.relative_to(base/"patch")).replace("\\","/")))
print("Remember to run the NASC server too, otherwise it won't work.")
