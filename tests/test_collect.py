import pathlib
import unittest
import logging

import multidict

from metaindex import logger
from metaindex import cache
from metaindex import configuration

HERE = pathlib.Path(__file__).resolve().parent
BASEDIR = HERE.parent
TEST_METADATA = BASEDIR / ".metadata.json"


class TestCollect(unittest.TestCase):
    def setUp(self):
        logger.setup(logging.ERROR)
        self.config = configuration.load(HERE / 'test.conf')
        self.cache = cache.Cache(self.config)
        TEST_METADATA.write_text("""{"README.md": {"subject": "test"}}""")

    def tearDown(self):
        TEST_METADATA.unlink()

    def parse_sidecar_files(self, sidecarfiles):
        result = multidict.MultiDict()
        for filepath in set(sidecarfiles):
            result.extend(self.cache.parse_extra_metadata(filepath))
        return result

    def find_sidecar_files(self, paths):
        sidecarfiles = sum(self.cache._find_collection_sidecar_files(paths).values(), start=[])
        sidecarfiles = sum(self.cache._find_sidecar_files(paths).values(), start=[])
        return sidecarfiles

    def _disabled_test_single_file(self):
        paths = self.find_sidecar_files([BASEDIR / "README.md"])
        self.assertEqual(len(paths), 1)
        self.assertIn(BASEDIR / ".metadata.json", paths)

