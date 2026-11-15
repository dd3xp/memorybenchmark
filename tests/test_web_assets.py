"""Current pages must not reference the deleted prototype UI assets."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

from memorybenchmark.web_assets import WEB_ASSETS, CONTENT_TYPES


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets=[]

    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value and value.startswith('/') and Path(value).suffix in ('.css','.js','.svg','.png'):
                self.assets.append(value)


class WebAssetTests(unittest.TestCase):
    def test_self_hosted_fonts_are_packaged_woff2(self):
        static=Path(__file__).resolve().parents[1]/'memorybenchmark/static'
        for name in ('atlas-chinese.woff2', 'atlas-serif.woff2', 'atlas-sans.woff2'):
            self.assertEqual((static/name).read_bytes()[:4], b'wOF2')
            self.assertEqual(WEB_ASSETS['/'+name], name)
        self.assertEqual(CONTENT_TYPES['.woff2'], 'font/woff2')
        self.assertIn('SIL OPEN FONT LICENSE', (static/'font-license.txt').read_text(encoding='utf-8'))

    def test_all_current_pages_and_assets_exist_without_legacy_references(self):
        static=Path(__file__).resolve().parents[1]/'memorybenchmark/static'
        for name in set(WEB_ASSETS.values()):
            self.assertTrue((static/name).is_file(),name)
            if name.endswith('.html'):
                parser=References();parser.feed((static/name).read_text(encoding='utf-8'))
                for reference in parser.assets:
                    self.assertIn(reference,WEB_ASSETS,(name,reference))
        for path in ('/scene.js','/maps.js','/app.js','/design.js','/play.css','/terrain-ground.png'):
            self.assertNotIn(path,WEB_ASSETS)


if __name__=='__main__':
    unittest.main()
