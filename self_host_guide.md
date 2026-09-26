<!-- markdownlint-disable MD007 MD009 MD033 MD059 -->
# Self hosting your own instance

## Requirements (applies to every guide here)

- [Python](https://python.org/downloads) 3.12 or newer and [pip](https://pip.pypa.io/en/stable/installation)
- [Node.js](https://nodejs.org/) 26 or newer (to install [Deno](https://docs.deno.com/runtime/getting_started/installation/))
- [ffmpeg](https://ffmpeg.org/)

## Prerequisites

1. Install Node.js, Python and ffmpeg if you haven't already.
2. Install Deno and pip too, if you haven't already.
3. Clone the repo or download it from GitHub:
    - `git clone https://github.com/idkwhere1sthisname/blazertube`
    - To download the repo from GitHub, press Code, then Download as ZIP
4. Install the Python dependencies by running `pip install -r requirements.txt`
    - Setting up a [virtual environment](https://docs.python.org/3/library/venv.html) is recommended before running this
5. Rename `.env.example` to `.env` and add a YouTube Data API v3 key
    - **Despite most of the server being InnerTube-based, some functions are Data API based. (e.g. browsing recommended channels)**
6. **Run `main.py` to create a basic configuration file**
7. Once done, add a secret Flask key (that you shouldn't share!) to `.env` (the server automatically gives you one if it doesn't detect it), it must be added to `.env` with this syntax:

```env
FLASK_SECRET_KEY=[...]
```

> [!IMPORTANT]
> It is recommended to clone the repository instead of downloading the ZIP from GitHub, as you can simply run `git pull origin master` to fetch the latest updates

## Self hosting BlazerTube (YouTube 3DS)

> [!IMPORTANT]
> To avoid YouTube blocking your IP, you should also export your own [cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
> 
> Using the 3DS app while HTTPS is enabled has not been tested

### Self hosting (Pretendo Network)

> [!NOTE]
> This guide applies if you're using [Pretendo Network](https://pretendo.network), if you don't plan on using Pretendo, please scroll down!

1. Obtain the latest YouTube app (must match your console's region)
    - It is available on a certain _green eShop_ website
    - `v2096` is the latest version for the American and Japanese app, while `v2080` is the latest for the European one
2. Run `/patcher/patcher.py` to create a patched binary or IPS for 3DS consoles.
3. Follow the instructions shown there
4. Once done, run `main.py` to start the server

### Self hosting (without Pretendo Network)

> [!IMPORTANT]
> This guide applies only if you're not going to use Pretendo, which isn't recommended! It's more steps for something that is unnecessary.

1. Obtain the latest YouTube app (must match your console's region)
    - It is available on a certain _green eShop_ website
    - `v2096` is the latest version for the American and Japanese app, while `v2080` is the latest for the European one
2. Run `/patcher/patcher.py` to create a patched binary or IPS for 3DS consoles.
3. Follow the instructions shown there
4. Run `nasc.py`, then choose the port (default and recommended port is `9000`)
5. Run `proxy.py`, then choose the port (default and recommended port is `8080`), then follow the instructions there
6. Then, You must setup the proxy settings on your 3DS to point to the IP shown there
7. Finally, run `main.py` to start the server

### Self hosting (using Revision 1 of the app)

> [!IMPORTANT]
> The Revision 1 of the app allows a DNS server to redirect `m.youtube.com` to a custom server (e.g. `192.168.0.22`) instead of placing a patched IPS/binary or installing a patched app on the system.
>
> This is also **dangerous** and meant for local development and testing only, as this app version is **vulnerable to RCE** (this is also how the [tubehax exploit](https://www.3dbrew.org/wiki/Tubehax) worked before the forced app update was released)

1. Obtain the Revision 1 of the 3DS YouTube app
    - Due to the app not being on Nintendo's CDN anymore, it might be hard to find, that's why you should instead use the latest version of the app and an IPS/binary patch
    - Revision 1 is equivalent to `v1056` for the American and Japanese(?) app, while `v1040` is for the European one
2. Run `nasc.py`, then choose the port (default and recommended port is `9000`)
3. Run `proxy.py`, then choose the port (default and recommended port is `8080`), then follow the instructions there
4. Run `dns.py` (default hardcoded port is `53`)
5. Then, You must setup the proxy and DNS settings on your 3DS to point to the IP shown there
6. Finally, run `main.py` to start the server

## Self hosting Hulu Plus (3DS)

> [!IMPORTANT]
> The Hulu Plus app doesn't have any functionality.

1. Obtain the latest Hulu Plus app (must match your console's region)
    - It is available on a certain _green eShop_ website
    - If you're on an European console, you can get either the American or Japanese app, just remember to place the `locale.txt` file if you aren't installing from that _green eShop_ site
    - `v0` is the latest version for the American app, while `v32` is the latest for the Japanese one
2. Run `hulu_server.py` to further setup the configuration file for the Hulu Plus server and to run the Hulu Plus server itself
3. Run `/patcher/hulu_patcher.py` to create a patched binary, then follow the instructions there
4. Once done, run `nasc.py`, then choose a port (default and recommended port is `9000`)
5. Once done, run `proxy.py`, then choose a port (default and recommended port is `8080`)
6. You must setup the proxy settings on your 3DS to point to the IP shown there

> [!NOTE]
> Setting up a custom proxy and NASC server is required since Pretendo has not enabled NASC for Hulu Plus or Netflix
> 
> You could theoretically use Hulu Plus without a custom NASC server, but it'll show error code 002-0110 every 2-3 seconds

## Self hosting Netflix (3DS)

> [!IMPORTANT]
> The Netflix app doesn't have any functionality besides showing the login screen and the [hidden Konami code screen](https://youtu.be/1ePh39fYAG8).

1. Obtain the latest Netflix app
    - It is available on a certain _green eShop_ website
    - `v1088` is the latest version for the app
    - If you're on an European or Japanese console, you can get the app anyway, just remember to place the `locale.txt` file in the SD if you aren't installing from that _green eShop_ site
2. Run `netflix_server.py` to further setup the configuration file for the Netflix server and to run the Netflix server itself
3. Run `/patcher/netflix_patcher.py` to create a patcher binary, then follow the instructions there
4. Once done, run `nasc.py`, then choose a port (default and recommended port is `9000`)
5. Once done, run `proxy.py`, then choose a port (default and recommended port is `8080`)
6. Finally, you must setup the proxy settings on your 3DS to point to the IP shown there

> [!IMPORTANT]
> Setting up a custom proxy and NASC server is required since Pretendo has not enabled NASC for Hulu Plus or Netflix

## Setting up a production server

> [!IMPORTANT]
> You must run the development server of the app you want to run at least once before running the production server

1. **Run `main.py` to create a basic configuration file first** (if you haven't already done so)
2. When prompted, do not enable debug mode
    - If you already ran the main Python server, open `config.xml` and be sure to have set `debugging` to `false`
3. Run `main.prod.py`, then follow the instructions there
4. Optionally use another server software as a reverse proxy (e.g. [Nginx](https://nginx.org/))
