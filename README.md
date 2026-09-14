# <div align="center">BlazerTube</div><p>

<div align="center">
A (Work in Progress) Native YouTube 3DS app Revival
<br>
<br>
<img src="static/images/branding/logo_BETA.png" width="360" alt="logo" />
<br><br>
<a href="https://github.com/idkwhere1sthisname/blazertube#installation">Jump to installation guide</a>
<br>

### Screenshots

<img src="unistore/images/youtube/5-t.png" alt="image2-top" height="240" />
<br/>
<img src="unistore/images/youtube/5-b.png" alt="image2-bottom" height="240" />
</div>
<br>
<hr>

## Installation

### Manual install

Instructions are available [here](https://drive.google.com/drive/folders/1LzL-bQ5w_wqftXQo9PqupN4Zr16YdcoM), in the `README` file

### UniStore install (recommended)

You can alternatively scan this QR code with [Universal Updater](https://universal-team.net/projects/universal-updater)

<div align="center"><img src="http://unistore.3ds.idkwh.ct8.pl/frame.png" alt="UniStore QR" /></div>

This allows you to install updates to BlazerTube without having to manually replace the binary in your system.

## Self hosting your own instance

Requirements:

- Python 3.11 or newer
- Node.js 26.00 or newer
- ffmpeg

1. Install the Python dependencies using `pip install -r requirements.txt`
2. Rename `.env.example` to `.env` and add a YouTube GDATA v3 API key
    - **Despite most of the server being InnerTube-based, some functions are GDATA API based.**
3. Optionally run `/patcher/patcher.py` to create a patched binary.
4. To avoid YouTube blocking your IP, you should also export your own [cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).
5. Run the Python server to create a configuration file
    - `python main.py`
6. Once done, add a secret Flask key (that you shouldn't share!) to `.env` (the server automatically gives you one if it doesn't detect it), it must be added to `.env` with this syntax:

```env
FLASK_SECRET_KEY=[...]
```

## Credits

[idkwh](https://github.com/idkwhere1sthisname): Developer

[NebulaGamez](https://github.com/nebnebgamez): Developer

[Tanjirokamado12](https://github.com/Tanjirokamado12): [Inject](https://github.com/idkwhere1sthisname/blazertube/blob/main/patcher/lib/inject.py) portion of the patcher

[Liinback](https://github.com/liinbacklite): [Video loader](https://github.com/idkwhere1sthisname/blazertube/blob/main/video.py), [captions](https://github.com/idkwhere1sthisname/blazertube/blob/main/captions.py), [debug](https://github.com/idkwhere1sthisname/blazertube/blob/main/debug.py) and small portions of [youtubei.py](https://github.com/idkwhere1sthisname/blazertube/blob/main/youtubei.py). The captions and video modules are based off of [Liinback 3.5](https://github.com/liinbacklite/Liinback)'s implementation, while the debug module is based on Liinback 3.0's implementation.

[RiiviveTube](https://github.com/ReviveMii/RiiviveTube): Portions of [youtubei.py](https://github.com/idkwhere1sthisname/blazertube/blob/main/youtubei.py)
