#!/usr/bin/env python3
"""Inline examples/<name>_anim.png into index.html's welcome screen as animated WebP data URIs.

Re-run after re-recording an example; it replaces the block between the examples:start/end markers.
"""

import base64
import io
import pathlib
import re

from PIL import Image, ImageSequence

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORIES = [('distance', 'measure distances'), ('area', 'measure area'), ('angle', 'measure angles')]
QUALITY = 70


def webp_uri(path):
    frames = [(f.convert('RGB'), f.info.get('duration', 50)) for f in ImageSequence.Iterator(Image.open(path))]
    images, durations = zip(*frames)
    buf = io.BytesIO()
    images[0].save(buf, 'WEBP', save_all=True, append_images=list(images[1:]), duration=list(durations),
                   loop=0, quality=QUALITY, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()


def main():
    figures = '\n'.join(
        f'      <figure><img class="shot" alt="{caption}" src="{webp_uri(ROOT / "examples" / f"{name}_anim.png")}">'
        f'<figcaption>{caption}</figcaption></figure>'
        for name, caption in STORIES)
    block = f'<!-- examples:start -->\n    <div class="stories">\n{figures}\n    </div>\n    <!-- examples:end -->'
    page = ROOT / 'index.html'
    html, n = re.subn(r'<!-- examples:start -->.*?<!-- examples:end -->', lambda m: block, page.read_text(), flags=re.S)
    if n != 1:
        raise SystemExit('examples:start/end markers not found exactly once in index.html')
    page.write_text(html)
    print(f'embedded {len(STORIES)} examples; index.html is now {len(html) // 1024} KB')


if __name__ == '__main__':
    main()
