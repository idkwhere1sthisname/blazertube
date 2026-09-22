from __future__ import print_function, annotations, with_statement, absolute_import
import tempfile
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, IpBlocked, RequestBlocked
from xml.sax.saxutils import escape
from pathlib import Path
from pytubefix import YouTube
from xml.sax.saxutils import escape
import traceback

from shared import *

TEMPDIR = Path(tempfile.gettempdir())
CACHE_DIR = TEMPDIR/"subtitles_cache"
CACHE_DIR.mkdir(exist_ok=True)

class Captions:
    def __init__(self):
        self.ytt_api = YouTubeTranscriptApi()
    def getLanguages(self, video_id):
        try:
            transcript_list = self.ytt_api.list(video_id)
            languages = {}
            for transcript in transcript_list:
                languages[transcript.language_code] = {
                    "name": transcript.language,
                    "is_generated": transcript.is_generated
                }
            return languages
        except NoTranscriptFound as e:
            return {}
        except TranscriptsDisabled as e:
            return {}
        except (IpBlocked, RequestBlocked) as e:
            print(f"IpBlocked/RequestBlocked exception:",e)
            return {}
        except Exception as e:
            return {}
    def getLanguages_pytube(self, video_id):
        try:
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            langs = {}
            captions = yt.captions
            for c in captions:
                langcd = c.code
                langs[langcd] = {
                    "name": c.name,
                    "is_generated": c.code.startswith("a.")
                }
            return langs
        except Exception as e:
            print("EXCEPTION:",e)
            traceback.print_exc()
    def getCaption(self, video_id, language):
        cache_file = CACHE_DIR/f"{video_id}_{language}.xml"
        if cache_file.is_file():
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        try:
            fetched = self.ytt_api.fetch(video_id, languages=[language])
            transcript = fetched.to_raw_data()
            xml_content = Captions.buildXMLFromTranscript(transcript, language)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(xml_content)
            return xml_content
        except NoTranscriptFound:
            return Captions.buildEmptyTranscript()
        except TranscriptsDisabled:
            return Captions.buildEmptyTranscript()
        except Exception as e:
            traceback.print_exc()
            return Captions.buildEmptyTranscript()
    def getCaption_pytube(self, video_id, language):
        cache_file = CACHE_DIR/f"{video_id}_{language}.xml"
        if cache_file.is_file():
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        try:
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            captions = yt.captions[language]
            if captions is None:
                return Captions.buildEmptyTranscript()
            xmlcaptions = captions.xml_captions
            with open(cache_file,"w",encoding="utf-8") as f:
                f.write(xmlcaptions)
            return xmlcaptions
        except Exception as e:
            print("exception occurred!",e)
            return Captions.buildEmptyTranscript()
    def buildXMLFromTranscript(self, transcript, language):
        xml = f'<?xml version="1.0" encoding="utf-8"?>\n<transcript lang_code="{escape(language)}">\n'
        for entry in transcript:
            start = entry.get('start', 0)
            duration = entry.get('duration', 0)
            text = escape(entry.get('text', ""))
            xml += f'  <text start="{start}" dur="{duration}">{text}</text>\n'
        xml += "</transcript>"
        return xml

    @staticmethod
    def buildEmptyTranscript():
        return '''<?xml version="1.0" encoding="utf-8" ?>
<transcript empty="true">
  <text start="0" dur="0.1"> </text>
</transcript>'''

    def buildXMLList(self, languages, videoId, lang_param):
        xml = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<transcript_list>\n"
        for index, (lang_code, info) in enumerate(languages.items()):
            if lang_param in languages:
                lang = lang_param
            else:
                lang = next(iter(languages))
            is_default = "true" if lang_code == lang else "false"
            xml += (
                f'  <track id="{index}" lang_code="{lang_code}" '
                f'name="{info["name"]}" lang_original="{lang_code}" '
                f'lang_translated="{info["name"]}" '
                f'lang_default="{is_default}" '
                f'kind="subtitles" '
                f'cantran="false" />\n'
            )
        xml += "</transcript_list>"
        return xml
