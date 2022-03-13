With *metaindex* you can index and find files on your disk based on their
metadata, like the title of a PDF, the keywords of an ebook, or the model
of a camera that a photo was taken with.

The following types of files are supported by default:

 - Images (anything that has EXIF, IPTC, or XMP information),
 - Audio (audio file formats that have ID3 header or similar),
 - Video (most video file formats have an ID3 header),
 - PDF,
 - ebooks (epub natively, calibre metadata files are understood, too),
 - ABC notation.

More file types can be supported through the use of Addons.

User provided extra metadata is supported, if it’s provided in the same
directory as the file and the metadata file is ``.metadata.json``.

