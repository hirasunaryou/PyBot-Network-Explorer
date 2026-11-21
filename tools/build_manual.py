"""Build a genuinely standalone HTML guide: CSS and ACTUAL screenshots embedded."""
import base64
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs"
SOURCE=DOCS/"MANUAL.source.html"
OUTPUT=DOCS/"MANUAL.html"
STYLES=DOCS/"manual.css"
TOKEN="<!--EMBED_STYLES-->"
IMAGE_PATTERN=re.compile(r'(?P<prefix>src=")images/(?P<name>[a-zA-Z0-9_-]+\.png)"')


def build():
    html=SOURCE.read_text(encoding="utf-8")
    if html.count(TOKEN)!=1:
        raise RuntimeError("Manual stylesheet insertion marker missing or duplicated")
    html=html.replace(TOKEN,"<style>\n"+STYLES.read_text(encoding="utf-8")+"\n</style>")
    used=set()
    def insert(match):
        name=match.group("name")
        file=DOCS/"images"/name
        if not file.is_file():
            raise RuntimeError("Real screenshot is missing: "+str(file))
        used.add(name)
        return match.group("prefix")+"data:image/png;base64,"+base64.b64encode(file.read_bytes()).decode("ascii")+'"'
    html=IMAGE_PATTERN.sub(insert,html)
    if used!={"overview.png","trace.png"}:
        raise RuntimeError("Missing real UI screenshots: "+repr(used))
    if 'src="images/' in html:
        raise RuntimeError("Unbundled image reference remains")
    return "<!-- Generated standalone edition. Edit MANUAL.source.html and manual.css. -->\n"+html


def main():
    result=build()
    if "--check" in sys.argv:
        assert OUTPUT.read_text(encoding="utf-8")==result,"Generated manual is outdated"
        print("Standalone manual verified.")
    else:
        OUTPUT.write_text(result,encoding="utf-8")
        print("Generated",OUTPUT,"bytes",len(result.encode("utf-8")))


if __name__=="__main__":
    main()
