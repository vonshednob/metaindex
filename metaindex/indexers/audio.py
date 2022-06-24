"""Audio/video indexer"""
try:
    import mutagen
except ImportError:
    mutagen = None

from metaindex import logger
from metaindex.indexer import IndexerBase, only_if_changed


if mutagen is not None:
    class MutagenIndexer(IndexerBase):
        """Audio/video indexer using mutagen"""
        NAME = 'mutagen'
        ACCEPT = ['audio/', 'video/']
        PREFIX = ('id3', 'audio')

        @only_if_changed
        def run(self, path, metadata, _):
            logger.debug(f"[mutagen] processing {path.name}")

            try:
                meta = mutagen.File(path, easy=True)
            except KeyboardInterrupt:
                raise
            except:
                return

            if meta is not None:
                for key, values in meta.items():
                    if not isinstance(values, list):
                        values = [values]
                    for value in values:
                        metadata.add('id3.' + key, value)
                if hasattr(meta, 'info') and hasattr(meta.info, 'length') and \
                   meta.info.length > 0:
                    metadata.add('audio.length', meta.info.length)
