"""Download the optional third-party meme library for a local prototype."""
import io
import json
import urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

def main():
    directory = ROOT / 'real-cats'
    directory.mkdir(exist_ok=True)
    manifest = json.loads((ROOT / 'CAT_SOURCES.json').read_text(encoding='utf-8'))
    failures = 0
    for item in manifest:
        path = directory / Path(item['file']).name
        if path.exists():
            continue
        try:
            request = urllib.request.Request(item['image_url'], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024:
                raise ValueError('Image exceeds download size limit')
            with Image.open(io.BytesIO(raw)) as source:
                image = source.convert('RGB')
                image.thumbnail((1200, 1200))
                image.save(path, format='PNG')
            print('Downloaded', path.name)
        except Exception as error:
            failures += 1
            print('Could not download', path.name, str(error))
    print('Library:', len(list(directory.glob('*.png'))), 'images;', failures, 'download failures')
    if not list(directory.glob('*.png')):
        raise SystemExit('No images available. Add your own PNGs to real-cats/.')

if __name__ == '__main__':
    main()
