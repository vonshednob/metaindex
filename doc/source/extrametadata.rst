Extra Metadata
==============

Not all filetypes support metadata (plain text files, for example) and
using extra files on the side (but in the same directory as the file to be
tagged) is used. These files on the side are called "sidecar files".

Sidecar files are expected to have the same filename as the file that they
are describing, but with a different extension, based on how the
description is provided. So, if you want to add additional metadata to your
``moose.jpg``, you could create a ``moose.json`` sidecar file or a
``moose.opf`` file.

All metadata provided by extra sidecar files is cached with the ``extra.``
prefix. For example, if your metadata file tags a file with ``title``, you
can search for it by looking for ``extra.title``.

metaindex supports sidecar files in JSON format like this when the file is
used for several files::

  {
   "file.ext": {
    "title": "An example file",
    "authors": ["dr Gumby", "The Bishop"],
    "Xmp.dc.title": null
   }
  }

If you set the metadata for only one file, for example
``a_long_story.pdf``, this could be the content of the corresponding sidecar file
``a_long_story.json``::

  {
    "title": [
      "long story, A",
      "A long story"
    ],
    "date": 2012-05-01
  }

**Beware**, if you create a sidecar metadata file with the above content
and name it ``metadata.json`` (or any other filename that’s covered by the
``collection-metadata`` option), all files in the folder will be given
these metadata tags, as if you had used the ``*`` notation! See `Collection
Metadata`_ for details.

The special value of ``null`` allows you to ignore a metadata tag from that
file, i.e. if that file has the ``Xmp.dc.title`` tag, it will be ignored.

Calibre style sidecar files, usually called ``metadata.opf`` are also
supported.

If you installed metaindex with the ``[yaml]`` option, YAML style metadata
files are supported, too. An example of a YAML sidecar file for 


Collection Metadata
-------------------

Sometimes all files in a directory should receive the same set of metadata.
This is called "Collection metadata" and can be accomplished in JSON
sidecar files (like ``.metadata.json``) by adding an entry ``"*"``.

Suppose you have this ``.metadata.json`` in a directory with two files
other ``file.tif`` and ``other.csv``::

  {
    "*": {
      "tags": ["tag1", "tag2"]
    },
    "file.tif": {
      "tags": ["tag3"]
    }
  }

In this example all (both) files in the folder will receive the tags
``tag1`` and ``tag2``, but only ``file.tif`` will have all three tags.

**Beware**, if you leave the ``*`` out and do not specify any metadata
specific to any file, metaindex will assume you meant that this metadata
applies to all files in the directory. Like this::

  {
   "tags": ["tag1", "tag2"],
   "author": "Arthur Pewty"
  }

The above example is equivalent to::

  {
   "*": {
    "tags": ["tag1", "tag2"],
    "author": "Arthur Pewty"
   }
  }

For collection metadata to work properly, the general option
``collection-metadata`` must be set to the names of sidecar files that are
allowed to define collection metadata.

By default files like ``.metadata.json``, and ``metadata.opf``
are expected to contain extra metadata.
If your metadata files are called
differently, for example ``meta.json`` and ``.extra.json``, you can
configure that in the metaindex configuration file::

  [General]
  collection-metadata = meta, .extra

The filenames listed in ``collection-metadata`` will be excluded from indexing,
so they will not show up when you search for them (e.g. via ``metaindex find
filename:metadata``)!

If metaindex has been installed with the ``yaml`` option, metadata
files in the yaml format are understood and used.


Recursive Collection Metadata
-----------------------------

If you want to apply the collection metadata not only to the files of the
sidecar’s directory, but also in all subdirectories, you can use the
"recursive collection metadata" ``"**"``.

This is useful if you already have your data structured in directories, for
example in this way: ``pictures/nature/animals/duck.jpg``.

Here you could add a ``.metadata.json`` file in the ``nature`` directory
with this recursive directive::

  {
    "**": {
      "tags": ["nature"]
    }
  }

Now not only the files in ``nature`` are tagged as ``nature``, but also
all files in ``animals``.

You can disable this functionality entirely by setting the general
option ``recursive-collection-metadata`` to an empty string::

  [General]
  recursive-collection-metadata =

**Caveat**: you can not defined both, a recursive and a non-recursive set
of collection metadata in the same directory::

  {
    "*": {
      "description": "BROKEN EXAMPLE: this does not work!"
    },
    "**": {
      "title": "BROKEN EXAMPLE! 'title' AND 'description' will be applied to all
      subdirectories!"
    }
  }

