"""Testing the rule-based indexer"""
import unittest
import datetime
import tempfile
from pathlib import Path

from metaindex import CacheEntry, Configuration
from metaindex.indexer import IndexerRunner
from metaindex.indexers import RuleIndexer


RULES = """
match /[0-9]+\\/[0-9]+\\/[0-9]{4}/
    find day /[0-9]+\\/([0-9]+)\\/[0-9]{4}/
    find year /[0-9]+\\/[0-9]+\\/([0-9]{4})/
    find month /([0-9]+)\\/[0-9]+\\/[0-9]{4}/
    set date "{year}-{month}-{day}"

match /\\$ [0-9]+\\.[0-9]+/
    set amount /\\$ ([0-9]+\\.[0-9]+)/
    set currency "USD"

match /Fancy Union/
    set publisher "Fancy Union Bank"
    set account /(FU[0-9-]+)/
    final

match /Fancy/
    set style fancy
"""

BANK_LETTER = """
Fancy Union                          7/14/2009
Some City

Hi, this is your bank Fancy Union.
Regarding your account FU-1234-567-8-9, we're happy
to inform you that you have saved $ 0.00 by using
our services.

FU Services ltd.
"""


class TestRuleIndexer(unittest.TestCase):
    def setUp(self):
        self.rule_file = tempfile.NamedTemporaryFile("wt",
                                                     encoding="utf-8",
                                                     suffix=".txt",
                                                     delete=False)
        self.rule_file.write(RULES)
        self.rule_file.close()

        self.config = Configuration()
        self.config.set('Indexer:rule-based',
                        'rules',
                        self.rule_file.name)
        self.runner = IndexerRunner(self.config)

        self.path = Path('a')
        self.entry = CacheEntry(self.path,
                                [('extra.title', 'Your bank statement'),
                                 ('ocr.fulltext', BANK_LETTER)],
                                datetime.datetime.now())

        indexer = RuleIndexer(self.runner)
        indexer.run(self.path, self.entry, CacheEntry(self.path))

    def tearDown(self):
        Path(self.rule_file.name).unlink()

    def test_everything(self):
        self.assertEqual([str(v) for v in self.entry['rules.publisher']], ['Fancy Union Bank'])
        self.assertEqual([str(v) for v in self.entry['rules.currency']], ['USD'])
        self.assertEqual([str(v) for v in self.entry['rules.amount']], ['0.00'])
        self.assertEqual([str(v) for v in self.entry['rules.style']], [])
        self.assertEqual([str(v) for v in self.entry['rules.account']],
                         ['FU-1234-567-8-9'])
        self.assertEqual(self.entry['rules.date'], ['2009-7-14'])
