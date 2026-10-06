from __future__ import print_function, with_statement, absolute_import
import os
import sys
import shutil
from pathlib import Path
import ips

from lib import inject as inj
from lib.patcher_shared import *

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
if port == 443 or port == 80:
    host = f"{host}/"
else:
    host = f"{host}:{port}/"
print(f"Host is {host}")
print("Select a region")
i = 1
regions = {1:"USA",2:"Japan"}
while i<3:
    print(f"{i}: {regions.get(i)}")
    i += 1
regionchoice = None
while regionchoice is None:
    regionchoice_in = input("Your choice: ")
    try:
        regionchoice_test = int(regionchoice_in)
        if regionchoice_test>=3: raise ValueError
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
offsets     = {1:0x0027BD48,2:0x0037C4C8}
titleIds    = {1:0x0004000000081700,2:0x00040000000FC400}
magic       = 0x78DA8D55 # zlib (deflate, best compression)
filemap     = {1:"USA",2:"JPN"}
temppath    = base/"temp"

localeContents     = {1:"""USA EN""",2:"""JPN JP"""}

filepath    = base/"html"/"hulu"/f"{filemap.get(regionchoice)}.html"
binpath     = base/"bin"/"hulu"/f"{filemap.get(regionchoice)}.bin"

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
inj.inject_html_streams(binpath,temppath,app="hulu")

if temppath.is_dir():
    shutil.rmtree(temppath,onerror=fixreadonly)

patchpath = base/"patch"/"luma"/"titles"/f"{titleIds.get(regionchoice):016X}"
localepath = patchpath/"locale.txt"
os.makedirs(patchpath,exist_ok=True)
binpatchpath = base/"bin"/"hulu"/f"{filemap.get(regionchoice)}_patched.bin"
if not binpatchpath.is_file():
    print("Patched binary not found, please re-run the patcher.")
    sys.exit()
FINAL = base/patchpath/"code.bin"
FINAL_IPS = base/patchpath/"code.ips"
shutil.move(binpatchpath,FINAL)

try:
    with open(localepath,"x",encoding="utf-8") as f:
        cnt = localeContents.get(regionchoice,None)
        if cnt is None:
            f.close()
            localepath.unlink()
        else:
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
print("Remember to run the NASC server too.")
