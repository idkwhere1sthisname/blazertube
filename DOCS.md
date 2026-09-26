<!-- markdownlint-disable MD007 MD009 MD033 MD059 -->
# Server & apps documentation

| Documentation                                       |
|-----------------------------------------------------|
| [Server docs](DOCS.md#server-docs)                  |
| [YouTube 3DS docs](DOCS.md#youtube-3ds-docs)        |
| [Hulu Plus 3DS docs (todo)](DOCS.md#hulu-plus-docs) |

## Server docs

> [!NOTE]
> For documentation on the configuration file, see [this file](static/configuration.xsd).

### Advanced configuration

Found in `shared.py` as booleans

```py
ENABLE_CREDS_OVERRIDE: Literal[True, False] = False
```

Enables the use of custom credentials instead of using the default InnerTube ones. Useful if you want to use a custom OAuth2 application instead. Requires valid credentials to be placed in `.env`:

- `OVERRIDE_CLIENT_ID`: The client ID of the Google Cloud application
- `OVERRIDE_CLIENT_SECRET`: The client secret of the Google Cloud application
- `OVERRIDE_LOGIN_SCOPES`: The login scopes of the Google Cloud app (recommended is `https://www.googleapis.com/auth/youtube.force-ssl` or `https://www.googleapis.com/auth/youtube`, but if the app is not verified by Google, this will trigger an "Unverified developer" screen). Must match the actual app's login scopes

```py
SIGNINDISABLED: Literal[True, False] = False
```

Disables the sign in feature

```py
SIGNINDISABLED_REASON: LiteralString = "Sign-Ins are disabled by an administrator."
```

Shown in the sign in disabled page, and only applies when sign ins are disabled

```py
ENABLE_CLEAR_MEMORY_BTN: Literal[True, False] = False
```

Enables a "Clear Memory" button shown when the user is signed out, it deletes every cookie from the browser (3DS only)

```py
ENABLE_DUMMY_SIGNIN: Literal[True, False] = False
```

Uses fake credentials and does NOT contact YouTube for the OAuth2 activation code. This option was used to design the sign in page

## YouTube 3DS docs

> [!NOTE]
> Also check out this [3DBrew](https://3dbrew.org/wiki/YouTube) page! it has info about how the DNS redirection works on Revision 1 of the app, but not on the newer versions, and more.

The 3DS YouTube app (similar to the Wii VOD apps such as Crunchyroll or Amazon Instant Video) uses a downgraded WebKit port by [FactorY Media Production GmbH](https://www.northdata.de/FactorY%20Media%20Production%20GmbH,%20K%C3%B6ln/HRB%2070454) ([source](https://github.com/search?q=repo%3Ayoutube%2Fh5vcc_hh+FactorY+Media+Production&type=code)). Again, similar to the Wii VOD apps, it has a Netscape Plugin embedded in the app.

Most of the functions don't do anything (presumably because the class has been ported 1:1 from the Wii apps), but a few actually do something:

### Built-in functions

> [!NOTE]
> To see every function, open the debug page on a 3DS system

```js
vod.setTime(dateHeaderFromXHR.getTime()); // accepts time in milliseconds as an argument
```

Possibly sets the system-wide date and time, it is ran each time the app is opened

```js
vod.triggerOnScreenKeyboard();
```

Opens the on screen keyboard (this is useless though, it already does that with input fields)

```js
vod.showProgressSpinner(show);
```

Shows a spinner on the top screen under the YouTube logo, it is hidden by calling the same function with `false` as an argument

```js
vod.showSpinnerWithoutBackground({xpos:...,ypos:...});
```

Shows a spinner on the bottom screen, it is hidden by calling the same function with `0` as an argument

```js
vod.setMiiverseLink(mvID);
```

Sets a post ID

```js
vod.getMiiverseLink();
```

Gets a Miiverse post ID set by `setMiiverseLink`

```js
vod.launchMiiverse();
```

Launches Miiverse. If no post ID is specified, it opens the home page. With Juxtaposition, it sometimes freezes on a black screen.

```js
vod.n3ds_IsNew3DS();
```

Checks whether the console is a New 3DS or not. Possibly only compatible with American consoles

### Constants

```js
vod.deviceChipset(); // -> "3DS"
vod.deviceFirmware(); // -> "yt100"
vod.screenWidth(); // -> 1073741824
vod.screenHeight(); // -> 1073741824
vod.screenResolution(); // -> JSON, {"width": 320, "isWidescreen": false, "height": 240}
vod.connectionStrength(); // -> 1 (might vary)
vod.connectionType(); // -> "Wi-Fi"
vod.jsbVersion(); // -> "ctr - Sep 28 2015 18:11:56" (this page has a few build strings: https://tcrf.net/YouTube_(Nintendo_3DS) ), tested on latest European version
vod.isDistributedVideoRestricted(); // -> false
vod.token(); // -> (returns the SVCLOC token from NASC, never gets validated)
vod.consumerData(); // -> ???
vod.udid(); // -> (returns the 3DS MAC address)
vod.clientIP(); // -> (returns the 3DS IP)
```

See [common.js](static/js/common.js) for the full FlexView/InputMask constants (they might vary between device)

### Embedded pages

The app also has some built in pages (e.g. the white page with the loading screen) running on a pseudo-web server (`http://embedded.ctr`). Any invalid URL will refuse to load

| Page              | Description                                                                                                                                         |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| launcher.html     | App launcher, it's the only ZLIB compressed HTML in the binary, it is responsible for opening the app URL and setting the time from the server      |
| miiverse.html     | Blank page, but has a Miiverse icon on top (X = Miiverse?), it was never used in the app, but it was probably a planned feature                     |
| playbackctrl.html | Houses the little seek bar, play and subtitles icon when you play a video on the app, if you access it directly, it will be broken                  |
| choice.html       | Contains and saves the subtitles options when you play a video, it will be broken if accessed directly                                              |
| error.html        | Blank page                                                                                                                                          |
| error-min.html    | Blank page, even though it might be able to show something (`http://embedded.ctr/error-min.html?error=%s&arg=%d`, `Ui::DoDisplayError(): %s, %d`)   |
| pdchoice.html     | Blank page and untested, may be trying to contact a defunct server (`http://172.18.1.30/youtube/videoControls/choice.html`)                         |
| loading.html      | Blank page                                                                                                                                          |

> [!NOTE]  
> On previous VOD apps, you were able to delete your cookies by visiting `http://embedded.wii/?clear_local_data=1`, this is why the `ENABLE_CLEAR_MEMORY_BTN` [advanced option](#advanced-configuration) was implemented in the first place.

### User agent strings

`Mozilla/5.0 (Nintendo 3DS; U; Factory Media Production; en) Version/1.7498.US`

User-Agent request header for Old 3DS systems, it is almost identical to the Wii's apps. The region is always US, no matter the actual console's region

`Mozilla/5.0 (Nintendo 3DS New3DS; U; Factory Media Production; en) Version/1.7499.US`

User-Agent request header for New 3DS systems, it is only shown if the console is American and is an actual New 3DS. Otherwise the Old 3DS User-Agent is used. The browser's version is more updated, even though it's unclear what changed
