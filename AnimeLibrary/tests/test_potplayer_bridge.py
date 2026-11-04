import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'player'))
import unittest
from urllib.parse import quote
from potplayer_bridge import parse_uri


class BridgeTests(unittest.TestCase):
    def test_chinese_spaces_and_ampersand(self):
        path = 'X:/动漫/电影/轻音 & 测试 [1080p].mkv'
        self.assertEqual(parse_uri('playbridge://' + quote(path, safe='/')), path.replace('/', '\\'))
        self.assertEqual(parse_uri('playbridge:///' + quote(path, safe='/')), path.replace('/', '\\'))

    def test_outside_paths_and_commands(self):
        for path in ['C:/Windows/cmd.exe', 'X:/other/a.mkv', 'X:/动漫/../other/a.mkv',
                     'X:/动漫/a.mkv:evil', 'X:/动漫/a.exe', '//server/a.mkv',
                     'X:/动漫/a.mkv" /evil', 'X:/动漫/a.mkv\ncmd', 'X:/动漫库/a.mkv']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                parse_uri('playbridge://' + quote(path, safe='/'))

    def test_queries_and_other_protocols(self):
        for uri in ['https://example.com/a.mkv', 'playbridge://X%3A/动漫/a.mkv?token=secret',
                    'playbridge://X%3A/动漫/a.mkv#extra']:
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                parse_uri(uri)


if __name__ == '__main__':
    unittest.main()
