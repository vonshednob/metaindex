"""Various indexer test cases"""
import configparser
import unittest
import pathlib

from metaindex import MemoryCache, index_files
from metaindex.configuration import Configuration, CONF_DEFAULTS


TEST_FILES = pathlib.Path(__file__).parent / 'test_files'


class TestBasicIndexer(unittest.TestCase):
    def setUp(self):
        baseconf = configparser.ConfigParser(interpolation=None)
        baseconf.read_dict(CONF_DEFAULTS)
        baseconf.set('General', 'cache', ':memory:')
        self.conf = Configuration(baseconf)
        self.cache = MemoryCache(self.conf)
        self.cache.wait_for_reload()

    def test_index_unknown(self):
        files = [f for f in TEST_FILES.iterdir()
                 if not self.conf.is_sidecar_file(f)]
        results = index_files(files, self.conf)
        self.assertEqual({str(result.filename.name) for result in results},
                         {'image.png', 'same_image.jpeg', 'unrelated.json'})

        for result in results:
            self.assertEqual(len(result.info['last_modified']), 1)
            if result.filename.name == 'image.png':
                self.assertEqual(result.info.metadata['mimetype'],
                                 ['image/png'])
            elif result.filename.name == 'same_image.jpeg':
                self.assertEqual(result.info.metadata['image.resolution'],
                                 ['640x480'])
            elif result.filename.name == 'unrelated.json':
                self.assertEqual(result.info.metadata['mimetype'],
                                 ['application/json'])
                self.assertEqual(result.info.metadata['size'], [39])
