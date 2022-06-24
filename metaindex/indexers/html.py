"""HTML file indexer"""
import html.parser

from metaindex import logger
from metaindex.shared import DUBLINCORE_TAGS
from metaindex.indexer import IndexerBase, only_if_changed


class HTMLIndexer(IndexerBase):
    """HTML file indexer"""
    NAME = 'html'
    ACCEPT = ['text/html', '.html', '.htm']
    PREFIX = ('html',)

    @only_if_changed
    def run(self, path, metadata, _):
        logger.debug('[%s] processing %s', self.NAME, path)
        metaparser = MetadataExtractor(metadata)
        metaparser.feed(path.read_text())


class MetadataExtractor(html.parser.HTMLParser):
    """HTML parser that extracts metadata from meta tags"""
    PREFIX = HTMLIndexer.PREFIX[0] + '.'

    def __init__(self, metadata, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata = metadata

    def handle_starttag(self, tag, attrs):
        if tag != 'meta':
            return
        name = ''
        content = ''
        for key, value in attrs:
            if not isinstance(value, str):
                continue
            if key == 'name':
                name = value
            if key == 'content':
                content = value

        if len(name) == 0 or len(content) == 0:
            return

        if name in ['author', 'description', 'creator', 'publisher']:
            self.metadata.add(self.PREFIX + name, content)

        elif name == 'keywords':
            for keyword in content.split(','):
                self.metadata.add(self.PREFIX + 'keyword', keyword)

        elif name.lower().startswith('dc.') and \
             name.lower()[3:] in DUBLINCORE_TAGS:
            self.metadata.add(self.PREFIX + name.lower()[3:], content)
