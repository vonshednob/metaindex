import os
import stat
import datetime
import errno
import pathlib
import collections

import trio
import pyfuse3

from metaindex import query
from metaindex import logger
from metaindex.cache import Cache


# OpenFileHandle is a filehandle for this inode (flags are optional)
OpenFileHandle = collections.namedtuple('OpenFileHandle', ['fh', 'inode', 'flags'])
# TreeNode is any tree node.
# - children is a list of TreeNodes, may be None if this node has not been initialized
# - parent is the inode of the parent
# - inode is its own inode number
# - lookup_count is the lookup count (increased by things like open, and readdir, decreased by forget)
# - name is the visible name in the file tree
class TreeNode:
    ROOT = 0
    SEARCHES = 1
    SEARCH_RESULT = 2
    TAGS_BASE = 3
    FILE = 4

    def __init__(self, name, inode, parent, kind, children=None):
        self.name = name
        self.inode = inode
        self.parent = parent
        self.kind = kind
        self.children = children
        self.lookup_counter = 0
        self.uid = 0
        self.gid = 0
        self.filehandle = None

    def getattr(self):
        attrs = pyfuse3.EntryAttributes()
        attrs.st_ino = self.inode
        attrs.generation = 0
        attrs.entry_timeout = 300
        attrs.attr_timeout = 300

        attrs.st_nlink = 1
        attrs.st_rdev = 0
        attrs.st_size = 0
        attrs.st_blksize = 512
        attrs.st_blocks = 0
        attrs.st_uid = self.uid
        attrs.st_gid = self.gid
        attrs.st_mode = stat.S_IFDIR + 0o550
        attrs.st_atime_ns = 0
        attrs.st_mtime_ns = 0
        attrs.st_ctime_ns = 0

        return attrs

# TreeLeaf is the same as a tree node except it has no children and
# - ref is the file on the filesystem that this entry refers to
class TreeLeaf(TreeNode):
    def __init__(self, name, inode, parent, ref):
        super().__init__(name, inode, parent, TreeNode.FILE, None)
        self.ref = ref

    def getattr(self):
        stat = os.stat(self.ref)

        attrs = pyfuse3.EntryAttributes()
        attrs.st_ino = self.inode
        attrs.generation = 0
        attrs.entry_timeout = 300
        attrs.attr_timeout = 300

        attrs.st_nlink = 1
        attrs.st_rdev = 0
        attrs.st_size = stat.st_size
        attrs.st_blksize = stat.st_blksize
        attrs.st_blocks = stat.st_blocks

        attrs.st_uid = stat.st_uid
        attrs.st_gid = stat.st_gid
        attrs.st_mode = stat.st_mode
        attrs.st_atime_ns = stat.st_atime_ns
        attrs.st_ctime_ns = stat.st_ctime_ns
        attrs.st_mtime_ns = stat.st_mtime_ns
        return attrs


class DoctagFS(pyfuse3.Operations):

    INODE_SEARCH = pyfuse3.ROOT_INODE + 1
    INODE_NR_BASE = pyfuse3.ROOT_INODE + 2

    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = Cache(config)

        self.uid = os.geteuid()
        self.gid = os.getegid()
        self.created = datetime.datetime.now()

        # all open file handles, mapping to nodes
        self.filehandles = {}
        # directory read operations, mapping token -> list of entries
        self.dir_read = {}

        # inode lookup table
        self.inodes = {}
        self._inode_counter = DoctagFS.INODE_NR_BASE

        ## initial file tree structure
        # Root node
        self.tree = TreeNode(b'', pyfuse3.ROOT_INODE, None, TreeNode.ROOT, [])
        self.tree.gid = self.gid
        self.tree.uid = self.uid
        self.inodes[self.tree.inode] = self.tree

        # all searches
        self._new_node(b'search', self.tree, TreeNode.SEARCHES, DoctagFS.INODE_SEARCH)

        # synonyms as a good basis
        for synonym in config['Synonyms']:
            self._create_keyword_folder(bytes(synonym, 'utf-8'), self.tree)

    def _next_inode_nr(self):
        """Return the next free inode number"""
        nextinode = self._inode_counter + 1
        if nextinode < self._inode_counter:
            raise pyfuse3.FUSEError(errno.ENFILE)
        self._inode_counter = nextinode
        return self._inode_counter

    def _new_node(self, name, parent, kind, inode=None):
        """Register a new node in the virtual file tree structure"""
        if inode is None:
            inode = self._next_inode_nr()

        if inode in self.inodes:
            # TODO - not the best choice for error number
            raise pyfuse3.FUSEError(errno.EFAULT)

        node = TreeNode(name, inode, parent.inode, kind, None)
        node.gid = self.gid
        node.uid = self.uid
        self.inodes[inode] = node
        parent.children.append(node)

        return node

    def _new_leaf(self, name, parent, ref):
        """Register a new leaf in the virtual file tree structure"""
        inode = self._next_inode_nr()

        if inode in self.inodes:
            # TODO - not the best choice for error number
            raise pyfuse3.FUSEError(errno.EFAULT)

        self.inodes[inode] = TreeLeaf(name, inode, parent.inode, ref)
        if parent.children is None:
            parent.children = []
        parent.children.append(self.inodes[inode])

        return self.inodes[inode]

    def _next_fh(self, node):
        """Get the next fh for node"""
        next_fh = 1

        while next_fh in self.filehandles:
            i = next_fh + 1
            if i < next_fh:
                raise pyfuse3.FUSEError(errno.EMFILE)
            next_fh = i

        self.filehandles[next_fh] = node
        node.filehandle = next_fh
        return next_fh

    def _make_name_unique(self, name, treenode):
        """Produce a unique version of name in the context of the given treenode"""
        if treenode.children is None:
            return bytes(str(name), 'utf-8')

        counter = ""
        while True:
            new_name = bytes(name.stem + counter + name.suffix, 'utf-8')
            has_clashes = any([that.name == new_name for that in treenode.children])
            if not has_clashes:
                break

            if len(counter) == 0:
                counter = " (1)"
            else:
                counter = f" ({int(counter[2:-1])+1})"
        return new_name

    def _create_keyword_folder(self, keyword, parent):
        """Create a folder 'keyword' at 'parent' with this structure:

        +- parent
           +- <keyword>
              + <value1>
              | +- <file1>
              | +- <file2>
              |
              + <value2>
              | +- <file3>
              | +- <file4>
              |
              + <…>
        """
        node = self._new_node(keyword, self.tree, TreeNode.SEARCH_RESULT)
        node.children = []

        qry = query.Query(query.Sequence([query.KeyExistsTerm(str(keyword, 'utf-8'), query.Term.AND)]))
        for ref, meta in self.cache.find(qry):
            target_nodes = []
            ref = pathlib.Path(ref)
            strkeyword = str(keyword, 'utf-8')

            for name in meta.getall(strkeyword):
                name = bytes(meta.get(strkeyword), 'utf-8')
                result_node = [child for child in node.children if child.name == name]
                if len(result_node) == 0:
                    result_node = self._new_node(name, node, TreeNode.SEARCH_RESULT)
                else:
                    result_node = result_node[0]
                target_nodes.append(result_node)

            for subnode in target_nodes:
                name = self._make_name_unique(pathlib.Path(ref.name), subnode)
                self._new_leaf(name, subnode, ref)

    # directory opening and reading

    async def opendir(self, inode, ctx=None):
        # logger.debug(f"opendir {inode}")
        if inode not in self.inodes:
            raise pyfuse3.FUSEError(errno.ENOENT)

        node = self.inodes[inode]

        # TODO - check context

        if node.children is None:
            if node.kind == TreeNode.SEARCHES:
                # TODO - maybe keep a history of all searches and fill it here?
                node.children = []

            elif node.kind == TreeNode.SEARCH_RESULT:
                pass
            # TODO - fill child nodes!

        if node.filehandle is not None:
            return node.filehandle

        return self._next_fh(node)

    async def readdir(self, fh, offset, token):
        # logger.debug(f"readdir {fh} starting at {offset}")
        node = self.filehandles.get(fh, None)
        if node is None:
            raise pyfuse3.FUSEError(errno.EBADF)

        for nr, child in enumerate(node.children):
            nr += 1

            if nr <= offset:
                continue
            if child is None:
                continue

            if pyfuse3.readdir_reply(token, child.name, child.getattr(), nr):
                child.lookup_counter += 1
            else:
                break

    async def releasedir(self, fh):
        # logger.debug(f"releasedir {fh}")

        node = self.filehandles.get(fh, None)
        if node is None:
            raise pyfuse3.FUSEError(errno.EBADF)

        node.filehandle = None
        del self.filehandles[fh]

    # file handling

    async def open(self, inode, flags, ctx=None):
        # logger.debug(f"open {inode} with {flags}")
        if flags & os.O_CREAT > 0:
            raise pyfuse3.FUSEError(errno.EPERM)

        node = self.inodes.get(inode, None)
        if node is None:
            raise pyfuse3.FUSEError(errno.ENOENT)

        if node.kind != TreeNode.FILE:
            raise pyfuse3.FUSEError(errno.EISDIR)

        if node.filehandle is not None:
            return pyfuse3.FileInfo(fh=node.filehandle)

        node.filehandle = os.open(node.ref, flags)
        self.filehandles[node.filehandle] = node

        return pyfuse3.FileInfo(fh=node.filehandle)

    async def read(self, fh, offset, size):
        # logger.debug(f"read from {fh} at {offset} with {size} bytes")
        node = self.filehandles.get(fh, None)
        if node is None:
            raise pyfuse3.FUSEError(errno.EPERM)

        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, size)

    async def write(self, fh, off, buf):
        logger.debug(f"write {len(buf)} bytes at {off} into {fh}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def release(self, fh):
        # logger.debug(f"release {fh}")
        node = self.filehandles.get(fh, None)
        if node is None:
            logger.debug(f"Trying to release {fh}, but it's not there")
            return

        node.filehandle = None
        del self.filehandles[fh]
        try:
            os.close(fh)
        except OSError as exc:
            raise pyfuse3.FUSEError(exc.errno)

    # general access

    async def access(self, inode, mode, ctx=None):
        logger.debug(f"access to {inode}, {mode}")
        node = self.inodes.get(inode, None)
        if node is None:
            return False

        if ctx is None:
            return False

        if isinstance(node, TreeLeaf):
            return os.access(node.ref, mode)

        if ctx.uid == node.uid:
            return True

        # TODO - this is obviously not good

        return False

    async def lookup(self, parent_inode, name, ctx=None):
        # logger.debug(f"lookup {name} in {parent_inode}")
        parent = self.inodes.get(parent_inode, None)
        if parent is None:
            raise pyfuse3.FUSEError(errno.ENOENT)
        if parent.children is None:
            raise pyfuse3.FUSEError(errno.ENOENT)

        if name == b'.':
            return await self.getattr(parent.inode)

        if name == b'..':
            if parent.parent is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            return await self.getattr(parent.parent.inode)

        for child in parent.children:
            if child.name == name:
                child.lookup_counter += 1
                return await self.getattr(child.inode)

        raise pyfuse3.FUSEError(errno.ENOENT)

    async def forget(self, inodes):
        # list of inodes to forget; decrease their lookup counters
        # if lookup count is == 0 and no directories point to it, it can
        # be removed
        # upon unmount all lookup counters must be brought down to zero
        # MUST NOT RAISE

        for inode, amount in inodes:
            node = self.inodes.get(inode, None)
            if node is None:
                logger.debug(f"Forgetting inode {inode} that is not/no longer registered")
                continue

            node.lookup_counter = max(0, node.lookup_counter - amount)
            # TODO - check for deletion if lookup_count is 0 and the node was deleted

    async def getattr(self, inode, ctx=None):
        # logger.debug(f"getattr {inode}")
        if inode not in self.inodes:
            raise pyfuse3.FUSEError(errno.ENOENT)

        if isinstance(self.inodes[inode], TreeLeaf):
            return self.inodes[inode].getattr()

        elif isinstance(self.inodes[inode], TreeNode):
            return self.inodes[inode].getattr()

        else:
            raise pyfuse3.FUSEError(errno.EPERM)

        return attrs

    async def statfs(self, ctx=None):
        # logger.debug(f"statfs")

        statvfs = pyfuse3.StatvfsData()
        statvfs.f_bsize = 512
        statvfs.f_frsize = 512
        statvfs.f_bfree = 0
        statvfs.f_bavail = 0
        statvfs.f_blocks = 0
        statvfs.f_files = 3
        statvfs.f_favail = 0
        statvfs.f_namemax = 500

        return statvfs

    # other stuff

    async def create(self, parent_inode, name, mode, flags, ctx=None):
        # create file with name, permissions mode, and open it with flags
        # return (FileInfo, EntryAttributes) tuple
        # increase inode lookup counter
        logger.debug(f"create {name} in {parent_inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.ENOENT)

    async def flush(self, fh):
        # handle close() call; decrease inode lookup counter
        logger.debug(f"flush {fh}")
        # TODO

    async def fsync(self, fh, datasync):
        # flush buffers for fh
        if not datasync:
            # flush metadata
            pass
        # flush content
        # TODO
        logger.debug(f"fsync {fh}")
    
    async def fsyncdir(self, fh, datasync):
        # flush buffers for directory fh
        if not datasync:
            # flush metadata
            pass
        # flush content
        # TODO
        logger.debug(f"fsyncdir {fh}")

    async def link(self, inode, new_parent_inode, new_name, ctx=None):
        # create a new link from inode to new_parent_inode with new_name
        # return EntryAttributes
        logger.debug(f"link {inode} to {new_parent_inode} with {new_name}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def mkdir(self, parent_inode, name, mode, ctx=None):
        # create a new directory with name in parent_inode with permissions mode
        # increase inode lookup counter and return EntryAttributes
        logger.debug(f"mkdir {name} in {parent_inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def mknod(self, parent_inode, name, mode, rdev, ctx=None):
        # create a new (possibly special) file in parent_inode
        logger.debug(f"mknod {name} in {parent_inode} with {mode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def readlink(self, inode, ctx=None):
        logger.debug(f"readlink {inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def rename(self, parent_inode_old, name_old, parent_inode_new, name_new, flags, ctx=None):
        # fairly complex, rtfm https://www.rath.org/pyfuse3-docs/operations.html#pyfuse3.Operations.rename
        logger.debug(f"rename {name_old} in {parent_inode_old} to {name_new} in {parent_inode_new}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def rmdir(self, parent_inode, name, ctx=None):
        # raise FUSEError(errno.ENOTEMPTY) if not empty
        logger.debug(f"rmdir {name} in {parent_inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def setattr(self, inode, attr, fields, fh, ctx=None):
        # change attributes of inode
        # return EntryAttributes with both changed and unchanged attributes
        logger.debug(f"setattr {inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def symlink(self, parent_inode, name, target, ctx=None):
        # return EntryAttributes and increase lookup count on success
        logger.debug(f"symlink {target} into {parent_inode} with {name}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    async def unlink(self, parent_inode, name, ctx=None):
        # remove a (possibly special) file
        # rather forget than delete, ie. decrease lookup count
        logger.debug(f"unlink {name} from {parent_inode}")
        # TODO
        raise pyfuse3.FUSEError(errno.EPERM)

    # xattr handling down here

    async def setxattr(self, inode, name, value, ctx=None):
        # logger.debug(f"setxattr {name} of {inode}")
        raise pyfuse3.FUSEError(errno.ENOSYS)

    async def removexattr(self, inode, name, ctx=None):
        # remove xattr
        # logger.debug(f"removexattr {name} of {inode}")
        raise pyfuse3.FUSEError(errno.ENOSYS)

    async def listxattr(self, inode, ctx=None):
        # return list of extended attributes
        # logger.debug(f"listxattr of {inode}")
        raise pyfuse3.FUSEError(errno.ENOSYS)

    async def getxattr(self, inode, name, ctx=None):
        # return extended attribute
        # logger.debug(f"getxattr {name} of {inode}")
        raise pyfuse3.FUSEError(errno.ENOSYS)


def metaindex_fs(config, args):
    if args.action == 'mount':
        mountpoint = pathlib.Path(args.mountpoint).expanduser().resolve()

        if not mountpoint.is_dir():
            logger.fatal(f"{mountpoint} is not a directory")
            return 1

        logger.debug(f"Mounting metaindex_fs to {mountpoint}")

        operations = DoctagFS(config)
        options = set(pyfuse3.default_options)
        options.add("fsname=metaindex")

        pyfuse3.init(operations, str(mountpoint), options)
        try:
            trio.run(pyfuse3.main)
        except KeyboardInterrupt:
            pass
        except:
            pyfuse3.close()
            raise

        pyfuse3.close()
        return 0

    return 1

