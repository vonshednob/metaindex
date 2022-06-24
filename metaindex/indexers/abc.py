"""abc notation file indexer"""
from metaindex import logger
from metaindex.indexer import IndexerBase, only_if_changed


class ABCNotationIndexer(IndexerBase):
    """Indexer for abc music notation files"""
    NAME = 'abcnotation'
    ACCEPT = ['text/vnd.abc', '.abc']
    PREFIX = ('abc',)

    @only_if_changed
    def run(self, path, metadata, _):
        logger.debug("[%s] processing %s", self.NAME, path.name)

        with open(path, 'rt', encoding="utf-8") as filehandle:
            for line in filehandle:
                if line.startswith('T:'):
                    metadata.add('abc.title', line[2:].strip())
                if line.startswith('M:'):
                    metadata.add('abc.meter', line[2:].strip())
                if line.startswith('C:'):
                    metadata.add('abc.composer', line[2:].strip())
                if line.startswith('Z:'):
                    metadata.add('abc.transcription', line[2:].strip())
                if line.startswith('G:'):
                    metadata.add('abc.group', line[2:].strip())
                if line.startswith('K:'):
                    metadata.add('abc.key', line[2:].strip())
                    break
