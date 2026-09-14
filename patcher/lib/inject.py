# based off of Vii No Ma's Hulu Plus HTML injector
from __future__ import print_function
import zlib
import os
import re
from pathlib import Path
import zopfli.zlib as zopfli_zlib

debug = False

def get_stream_size(data:bytes,offset:int)->int|None:
    d = zlib.decompressobj()
    try:
        d.decompress(data[offset:offset + 500000])
        d.flush()
        unused = len(d.unused_data)
        total_fed = min(500000, len(data) - offset)
        return total_fed - unused
    except:
        return None

def best_compress(data:bytes)->bytes|None:
    """Try zopfli first (best), then fall back to all zlib combos."""
    best = None

    # zopfli: much better compression, still valid zlib output
    try:
        result = zopfli_zlib.compress(data)
        if best is None or len(result) < len(best):
            best = result
            if debug:
                print(f"zopfli: {len(result)} bytes")
    except Exception as e:
        print(f"zopfli failed: {e}")

    # fallback: all zlib combos
    strategies = [
        zlib.Z_DEFAULT_STRATEGY,
        zlib.Z_FILTERED,
        zlib.Z_HUFFMAN_ONLY,
        zlib.Z_RLE,
        zlib.Z_FIXED,
    ]
    for wbits in range(9, 16):
        for strategy in strategies:
            for level in range(1, 10):
                try:
                    c = zlib.compressobj(
                        level=level,
                        method=zlib.DEFLATED,
                        wbits=wbits,
                        strategy=strategy
                    )
                    result = c.compress(data) + c.flush()
                    if best is None or len(result) < len(best):
                        best = result
                except:
                    pass

    return best

def safe_minify(html_bytes:str)->str:
    html = html_bytes.decode('utf-8', errors='replace')
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)    # HTML/XML comments
    html = re.sub(r'/\*.*?\*/', '', html, flags=re.DOTALL)     # CSS/JS block comments
    #html = re.sub(r'//[^\n]*', '', html)                       # JS line comments
    html = re.sub(r'[ \t]+', ' ', html)                        # collapse spaces/tabs
    html = re.sub(r'\n\s*\n', '\n', html)                      # collapse blank lines
    html = re.sub(r'>\s+<', '><', html)                        # whitespace between tags
    html = html.strip()
    return html.encode('utf-8')

def inject_html_streams(app_path:Path, html_dir:Path='temp',app:str="youtube")->None:
    with open(app_path, 'rb') as f:
        data = bytearray(f.read())
    if debug:
        print("Scanning for zlib HTML streams...\n")
    streams = []
    i = 0
    while i < len(data) - 2:
        b1, b2 = data[i], data[i+1]
        if b1 == 0x78 and (b1 * 256 + b2) % 31 == 0:
            try:
                decompressed = zlib.decompress(data[i:i + 500000])
                if b'<html' in decompressed.lower() or b'<!doctype' in decompressed.lower():
                    stream_size = get_stream_size(bytes(data), i)
                    streams.append({
                        'offset': i,
                        'compressed_size': stream_size,
                    })
                    if debug:
                        print(f"[+] Found HTML stream at 0x{i:08X} (compressed: {stream_size} bytes)")
            except:
                pass
        i += 1
    if debug:
        print(f"\nFound {len(streams)} HTML stream(s). Starting injection...\n")

    patched = 0
    skipped = 0

    for stream in streams:
        offset = stream['offset']
        orig_size = stream['compressed_size']
        filename = f"{offset:08X}.html"
        filepath = os.path.join(html_dir, filename)

        if not os.path.exists(filepath):
            if app != "hulu":
                print(f"  [~] {filename} not found, skipping.")
                skipped += 1
            continue

        with open(filepath, 'rb') as f:
            new_html = f.read()

        # try raw first
        new_compressed = best_compress(new_html)
        slack = orig_size - len(new_compressed)
        if debug:
            print(f"[?] {filename}: compressed to {len(new_compressed)} bytes (slot: {orig_size}, slack: {slack})")

        # if still too large, try minified version
        if len(new_compressed) > orig_size:
            print(f"Trying minified version...")
            minified = safe_minify(new_html)
            new_compressed_mini = best_compress(minified)
            slack_mini = orig_size - len(new_compressed_mini)
            if debug:
                print(f"Minified: {len(new_compressed_mini)} bytes (slack: {slack_mini})")
                print("This might not work... Try with a shorter domain")
            if len(new_compressed_mini) <= orig_size:
                new_compressed = new_compressed_mini
                slack = slack_mini
                print(f"Minification worked!")
            else:
                over = len(new_compressed_mini) - orig_size
                print(f"[!] Still {over} bytes too large after minification — skipping.")
                skipped += 1
                continue

        padded = new_compressed + b'\x00' * slack
        assert len(padded) == orig_size
        data[offset:offset + orig_size] = padded
        if debug:
            print(f"[+] Patched! ({slack} null padding bytes free)")
        patched += 1

    out_path = app_path.with_name(app_path.stem+"_patched"+app_path.suffix)
    with open(out_path, 'wb') as f:
        f.write(data)

def inject_mv_html(mvHTMLpath:Path,binpath:Path,host:str,region:int)->None:
    # 1: EUR, 2: USA, 3: JPN
    mvhtmlsize = 0x217C
    mvoffsets = {
        1: 0x00D3EEA0,
        2: 0x00D3EEA0,
        3: 0x00D3DEA0,
    }
    if not mvHTMLpath.is_file() or not binpath.is_file():
        return None
    mvhtml = mvHTMLpath.read_text("utf-8")
    mvhtml = mvhtml.replace("{{host}}",str(host).lower().strip())
    start = mvoffsets.get(region)
    if start is None:
        print(f"Unknown region: {region}, skipping...")
        return None
    htmlb = mvhtml.encode("utf-8")
    # it should be shorter than the original out of the box
    # debug logging was removed
    if len(htmlb) > mvhtmlsize:
        print("Skipping Miiverse HTML inject")
        print("Final HTML is too large")
        return None
    with open(binpath,"r+b") as f:
        f.seek(start)
        f.write(htmlb)
        f.write(b"\x00"*(mvhtmlsize-len(htmlb)))
