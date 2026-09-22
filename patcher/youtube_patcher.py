from __future__ import print_function, with_statement, absolute_import
import os
import sys
import shutil
from pathlib import Path
import ips

from lib.patcher_shared import *
from lib import inject as inj

localip = showlanip()

base = Path(__file__).resolve().parent

clearscreen()
host = input(f"What should the host be? (leave blank for http://{localip}): ")
if host.strip() == "" or host == None: host = f"http://{localip}"
port = None
while port is None:
    try:
        port_in = input("Choose a port (must match the server's): ")
        port = int(port_in)
    except ValueError:
        print("Please enter a valid integer.")
port = int(port_in)
if port == 80 or port == 443:
    host = f"{host}/"
else:
    host = f"{host}:{port}/"
print(f"Host is {host}")
print("Select a region")
i = 1
regions = {1:"Europe",2:"USA",3:"Japan"}
while i<4:
    print(f"{i}: {regions.get(i)}")
    i += 1
regionchoice = None
while regionchoice is None:
    regionchoice_in = input("Your choice: ")
    try:
        regionchoice_test = int(regionchoice_in)
        if regionchoice_test>=4: raise ValueError
        regionchoice = regionchoice_test
    except ValueError:
        print("Please enter a valid choice.")
isIps = None
while isIps is None:
    ipsIn = input("Should the output be an IPS file instead of a binary (\"y\" is recommended)? (Y/N): ").lower().strip()
    if ipsIn not in ["y","n"]:
        print("Invalid input, please enter either Y or N")
    else:
        isIps = ipsIn == "y"
        break
print("Patching...")
regionchoice = int(regionchoice_test)
# constants
offsets     = {1:0x00D215A8,2:0x00D215A8,3:0x00D205A8}
titleIds    = {1:0x00040000000CCD00,2:0x00040000000B0F00,3:0x00040000000D3000}
magic       = 0x78DA9555 # zlib (deflate, best compression)
filemap     = {1:"EUR",2:"USA",3:"JPN"}
# fix for the User-Agent header to match the patch's region
regionhdr   = {1:"EU",2:"US",3:"JP"}
hdroffsets  = {
    1: {
        0x00AACD9F,
        0x00AACDF6,
    },
    2: {0x0,0x0},
    3: {
        0x00AABB5F,
        0x00AABBB6,
    }
}
temppath    = base/"temp"
localeContents     = {1:"""EUR EN""",2:"""USA EN""",3:"""JPN JP"""}

# this HTML template removes console.log and useless statements, it should never overflow unless an user has a long ass domain
filepath    = base/"html"/"youtube"/f"{filemap.get(regionchoice)}.html"
binpath     = base/"bin"/"youtube"/f"{filemap.get(regionchoice)}.bin"

if not filepath.is_file():
    print(f"HTML template for region {regions.get(regionchoice).lower()} not found.")
    sys.exit()
if not binpath.is_file():
    print(f"Binary file for region {regions.get(regionchoice).lower()} not found.")
    sys.exit()
with open(filepath,"r",encoding="utf-8") as f:
    html = f.read()

targetoff = offsets.get(regionchoice)

with open(binpath,"rb") as f:
    stream = f.read()
    f.seek(targetoff)
    magic_infile = f.read(0x04)
    magic_infile = int.from_bytes(magic_infile,byteorder="big")
    # check if zlib magic equals the one stored in our template
    if magic != magic_infile:
        print(f"magic bytes don't match zlib deflate (expected: {hex(magic).upper()}, got: {hex(magic_infile).upper()})")
        sys.exit()
    # reseek to 0x00 for full file
    f.seek(0x00)
    stream = f.read()
os.makedirs("temp",exist_ok=True)

html = html.replace("{{host}}",str(host).lower().strip())
htmltmp = f"{targetoff:08X}.html"
temphtmlpath = base/"temp"/htmltmp

with open(temphtmlpath,"w",encoding="utf-8") as htmldest:
    htmldest.write(html)
inj.inject_html_streams(binpath,temppath,"youtube")

if temppath.is_dir():
    shutil.rmtree(temppath,onerror=fixreadonly)

patchpath = base/"patch"/"luma"/"titles"/f"{titleIds.get(regionchoice):016X}"
localepath = patchpath/"locale.txt"
os.makedirs(patchpath,exist_ok=True)
binpatchpath = base/"bin"/"youtube"/f"{filemap.get(regionchoice)}_patched.bin"
if not binpatchpath.is_file():
    print("Patched binary not found, please re-run the patcher.")
    sys.exit()
FINAL = base/patchpath/"code.bin"
FINAL_IPS = base/patchpath/"code.ips"
shutil.move(binpatchpath,FINAL)

print("Patching User-Agent header...")
with open(FINAL,"r+b") as f:
    for off in hdroffsets.get(regionchoice):
        if off == 0x0:
            continue
        f.seek(off)
        f.write(regionhdr.get(regionchoice).encode("ascii"))
mvhtmlpath = base/"html"/"youtube"/f"mv_{filemap.get(regionchoice)}.html"
if mvhtmlpath.is_file():
    print("Patching Miiverse HTML...")
    inj.inject_mv_html(mvhtmlpath,FINAL,host,regionchoice)

try:
    with open(localepath,"x",encoding="utf-8") as f:
        cnt = localeContents.get(regionchoice,None)
        if cnt is None:
            f.close()
            localepath.unlink()
        else:
            print("Writing locale file...")
            f.write(localeContents.get(regionchoice,None))
except FileExistsError:
    pass

if isIps:
    print("Writing IPS...")
    with open(str(FINAL),"rb") as patchedbin, open(str(binpath),"rb") as originalbin:
        p = ips.Patch.create(originalbin,patchedbin)
    with open(FINAL_IPS,"wb") as f:
        f.write(bytes(p))
    FINAL.unlink()

print("Done!")
print("Be sure to enable Game Patching in Luma3DS's settings.")
print("Then add the contents of the patch folder on your SD Card's root.")
print("If you don't want the locale to be overridden, delete /%s"%(str(localepath.relative_to(base/"patch")).replace("\\","/")))
print("If you're not going to use Pretendo, remember to run the NASC server too.")
