Addons
======

You can extend the capabilities of metaindex to index additional file types
(indexers) and to format raw metadata values in a human readable form (humanizers)
by writing addons.

These should be placed in ``~/.local/share/metaindex/addons/`` and will be
loaded upon start of metaindex.

**Beware** that these addons can do whatever they want. They might encrypt
all your files or even first upload them to the internet. **Never copy
untrusted python files into the addons folder.**


Additional Indexers
-------------------

Addons must be derived from ``metaindex.indexer.IndexerBase``. Here is a
very stupid example of a working indexer that adds the subject ``stupid``
to every file::

    from metaindex.indexer import IndexerBase, Order


    class StupidIndexer(IndexerBase):
        NAME = 'stupid'
        ACCEPT = '*'
        ORDER = Order.FIRST
        PREFIX = 'extra'

        def run(self, path, metadata, last_cached):
            metadata.add(self.PREFIX + '.subject', 'stupid')

``path`` is the ``pathlib.Path`` to the file that is to be indexed,
``info`` is a ``CacheEntry``  of already obtained metadata from previously run
indexers, and ``last_cached`` is the metadata information of ``path`` as it
is currently in the cache (in case you need to compare to previous values).

If you want your indexer to only run if the file at ``path`` has changed
since the last run of the indexers (any indexers, really), you can use the
``@only_if_changed`` decorator.

If your indexer can extract the full (human readable) text from the file,
be sure to query ``self.should_fulltext(path)`` if you should do it.

The same goes for OCR'ing images of the file being indexed. Please query
``self.should_ocr(path)`` if the user really wanted this to go through OCR.

Any extracted fulltext should by convention be stored in a metadata tag
that ends with ``.fulltext``, e.g. ``msdoc.fulltext`` if your indexer uses
the prefix ``msdoc``.

Please see ``metaindex.indexer.IndexerBase`` for more details and
``metaindex.indexers`` for existing indexers as examples.


Additional Humanizers
---------------------

A humanizer is a simple function that turns a raw metadata value into a
human-readable form.

Here is an example of a humanizer that would render any ``.round`` tag as
``π`` if the value is a ``float`` and close enough to ``3.14``::

    from metaindex.humanizer import register_humanizer, Priority

    @register_humanizer('*.round', Priority.HIGH)
    def format_pi(value):
        if isinstance(value, float) and abs(3.14 - value) < 0.001:
            return 'π'
        return None

Have a look at the API of ``register_humanizer`` for all details on what
options you have to write your own humanizers.

