import configparser
import pathlib
import unittest
import logging
import tempfile

from metaindex import logger
from metaindex import cache
from metaindex import configuration
from metaindex import indexers as _

HERE = pathlib.Path(__file__).resolve().parent
BASEDIR = HERE.parent


class TestCollect(unittest.TestCase):
    def setUp(self):
        logger.setup(logging.ERROR)
        conf = configparser.ConfigParser(interpolation=None)
        conf.read_dict(configuration.CONF_DEFAULTS)
        conf.set(configuration.SECTION_GENERAL,
                 configuration.CONFIG_CACHE,
                 ':memory:')
        conf.set(configuration.SECTION_GENERAL,
                 configuration.CONFIG_IGNORE_DIRS,
                 "System Volume Information\na")
        self.config = configuration.Configuration(conf)
        self.cache = cache.Cache(self.config)

    def test_sidecar_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)

            (tmppath / "file.txt").write_text("A file with content")
            (tmppath / "file.json").write_text('{"title": "unit test file"}')
            (tmppath / "file.opf").write_text('{"title": "unit test file"}')

            paths = list(self.config.find_all_sidecar_files(tmppath / "file.txt"))
            self.assertEqual(len(paths), 2)
            self.assertEqual({tmppath / "file.json", tmppath / "file.opf"},
                             {p[0] for p in paths})

    def test_ignore_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)

            (tmppath / "a" / ".git" / "c").mkdir(parents=True)
            (tmppath / "a" / ".git" / "c" / "text.txt").write_text("Unique string")
            (tmppath / "other.txt").write_text("Other file")

            results = self.cache.refresh(tmppath)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].path, tmppath / "other.txt")

    def test_ignore_non_sidecar_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)

            (tmppath / "text.json").write_text('{"test": "yes"}')
            (tmppath / "other.txt").write_text("Other file")
            (tmppath / "other.json").write_text('{"is_meta": "yes"}')

            results = self.cache.refresh(tmppath)

            self.assertEqual(len(results), 2)

            other = self.cache.find("extra.is_meta?")

            self.assertEqual(len(other), 1)
