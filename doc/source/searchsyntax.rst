Search Query Syntax
===================

If the search term only contains a simple word, like ``albatross``, all
files will be found that contain this word in any metadata field.

To search for a phrase containing spaces, you have to enclose the phrase in
blockquotes or single quotes, like ``"albatross flavour"``.

To search for "albatross" in a specific metadata field, like in the title,
you have to search for ``title:albatross``. Again, the phrase search
requires quotes: ``title:"albatross flavour"``.

You can search files by the existance of a metadata tag by adding a ``?``
after the name of the metadata tag. For example, to find all files that
have the ``resolution`` metadata tag: ``resolution?``.

When the search includes the tag name, you have to provide the full
case-sensitive name of the tag. ``artist`` and ``Artist`` are very
different tag names and just searching for ``artist:tim`` when you mean to
search for ``albumartist`` will not result in the same search results.

Have a look at the Synonyms feature to find out how to search
conveniently for more complex tag names.

When searching for multiple terms, you can choose to connect the terms with
``and`` or ``or``. ``and`` is the default if none is provided, so these two
search queries, to find all photos made with a Canon camera and with a
width of 1024 pixels, are the same::

  resolution:1024x Exif.Image.Model:canon

  resolution:1024x and Exif.Image.Model:canon

To search for all pictures that are made with a Canon camera or have that
width, you have to use ``or``::

  resolution:1024x or Exif.Image.Model:canon


Metadata tags
-------------

These metadata tags are always available:

  ``last_accessed``
    A timestamp when the file was accessed the last time (if the OS
    supports it).

  ``filename``
    The name of the file on disk including extensions.

  ``size``
    The file size in bytes.

  ``mimetype``
    The mimetype of the file, if it could be detected.

