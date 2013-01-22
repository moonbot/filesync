#!/usr/bin/env python
# encoding: utf-8
'''
filesync.diff

Created by Brennan Chapman and Bohdon Sayre on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.
'''

import os
import re
import stat
import time
import sys
import shutil
import filecmp
import logging

import utils

LOG = logging.getLogger(__name__)

class Diff(object):
    '''
    Diff compares two directories (src and dst) and compiles a list of
    all files and directories that are either only in src, or have been updated
    in src. Diff operates one directionally, so multiple Diffs would be
    needed to check differences bidirectionally.

    Optionally, a file path list can be supplied to limit the sync between
    the src and dst.  This file list can either be relative paths or include
    the src or dst prefixes in their file paths.
    
    If both a src and dst path are passed on creation, the comparison is run
    automatically, otherwise the run() method must be called manually once
    both paths are set.
    
    Main attributes are:
        ``create`` -- a dictionary of files/dirs that only exist in src
        ``update`` -- a dictionary of files/dirs that are newer in src
        ``purge`` -- a dictionary of files/dirs that only exist in dst
    
    >>> d = Diff(srcDir, dstDir)
    >>> d.report()
    '''
    
    filters = []
    excludes = []
    regexfilters = True
    includedirs = True
    timeprecision = 3
    recursive = True
    newer = True
    opts = ['filters', 'excludes', 'regexfilters', 'includedirs', 'timeprecision', 'recursive',\
            'newer', 'forceUpdate', 'filelist', 'sizeLimit']
    

    def __init__(self, src=None, dst=None, **kwargs):
        self.src = os.path.normpath(src) if src is not None else None
        self.dst = os.path.normpath(dst) if src is not None else None
        self.create = {}
        self.createcount = 0
        self.update = {}
        self.updatecount = 0
        self.purge = {}
        self.purgecount = 0
        self.totalcount = 0
        # update options
        self.filelist = None
        for k, v in kwargs.items():
            if k in self.opts:
                setattr(self, k, v)
        # run the comparison
        if self.src is not None and self.dst is not None:
            self.run()
    

    def makeFileListRelative(self, relativeFileList, srcFolder, dstFolder):
        '''
        Return a list of files with the srcFolder and dstFolder
        removed from the beginning of the file name.
        '''

        srcFolder = os.path.normpath(srcFolder)
        dstFolder = os.path.normpath(dstFolder)

        # Make sure there is a trailing slash to make sure the
        # entire folder name matches
        if srcFolder[-1] != "\\":
            srcFolder += "\\"
        if dstFolder[-1] != "\\":
            dstFolder += "\\"

        result = []
        for path in relativeFileList:
            # Compare paths using the file systems case sensitivity
            rel = os.path.normcase(os.path.normpath(path))
            rel = rel.replace(os.path.normcase(srcFolder), '')
            rel = rel.replace(os.path.normcase(dstFolder), '')

            # Substitute the original path case into the result
            rel = path[-len(rel):]

            result.append(rel)
        return result


    def copy(self):
        '''Return a deep copy of self'''
        from copy import deepcopy
        d = Diff()
        d.__dict__ = deepcopy(self.__dict__)
        return d
    
    def __tmpdir(self):
        '''Return an empty directory created in the users tmp dir'''
        tmp = None
        if os.environ.has_key('TMP'):
            tmp = os.environ['TMP']
        elif os.environ.has_key('TMPDIR'):
            tmp = os.environ['TMPDIR']
        else:
            tmp = os.path.expanduser('~')
        tmpdir = os.path.join(tmp, '__dirdiff_tmp')
        if not os.path.exists(tmpdir):
            os.mkdir(tmpdir)
        return tmpdir
    

    def __norm(self, x):
        return os.path.normpath(x)
    

    def __asdir(self, x):
        return '{0}{1}'.format(x.rstrip('/\\'), os.sep)

    def clearFiles(self):
        self.create = {}
        self.update = {}
        self.purge = {}

    def _add(self, op, path):
        # rstrip the path so we ensure a common starting point
        path = path.rstrip('/\\')
        if not op in ['create', 'update', 'purge']:
            return
        dir_, base = os.path.split(path)
        # normalize the parent directory
        dir_ = self.__norm(dir_)
        # get the list corresponding to the given mode
        attr = getattr(self, op)
        if not attr.has_key(dir_):
            attr[dir_] = []
        # make the base look like a dir if it is
        if utils._isdir(path):
            base = self.__asdir(base)
        attr[dir_].append(base)
    

    def add_create(self, path):
        self._add('create', path)
    

    def add_update(self, path):
        self._add('update', path)
    

    def add_purge(self, path):
        self._add('purge', path)
    
    
    def _remove(self, op, path):
        '''Remove the given path from the given attribute'''
        # rstrip the path so we ensure a common starting point
        path = path.rstrip('/\\')
        if not op in ['create', 'update', 'purge']:
            return
        dir_, base = os.path.split(path)
        dir_ = self.__norm(dir_)
        # get the list corresponding to the given mode
        attr = getattr(self, op)
        # Make sure the path exists
        if os.path.exists(path):
            # make the base look like a dir if it is
            if utils._isdir(path):
                base = self.__asdir(base)
            if attr.has_key(dir_):
                if base in attr[dir_]:
                    attr[dir_].remove(base)
                    if len(attr[dir_]) == 0:
                        del attr[dir_]
            self.update_counts(ops=[op])
    

    def remove_create(self, path):
        self._remove('create', path)
    

    def remove_update(self, path):
        self._remove('update', path)
    

    def remove_purge(self, path):
        self._remove('purge', path)
    
    
    def getSrcPath(self, relPath):
        '''Return a full source path for supplied relative path.'''
        return os.path.normpath(self.src + "\\" + relPath)


    def getDstPath(self, relPath):
        '''Return a full destination path for supplied relative path.'''
        return os.path.normpath(self.dst + "\\" + relPath)


    def compareFileList(self, relativeFileList, srcFolder, dstFolder):
        '''
        Compare a list of relative file paths to a
        source and destination folder.
        '''
        result = {}
        result['left_only'] = []
        result['common'] = []
        result['right_only'] = []
        result['missing'] = []

        for relPath in relativeFileList:
            srcPath = self.getSrcPath(relPath)
            dstPath = self.getDstPath(relPath)
            srcExists = os.path.exists(srcPath)
            dstExists = os.path.exists(dstPath)
            if srcExists and dstExists:
                result['common'].append(relPath)
            elif srcExists and not dstExists:
                result['left_only'].append(relPath)
            elif not srcExists and dstExists:
                result['right_only'].append(relPath)
            else:
                result['missing'].append(relPath)

        # Wrap the results in a simple class
        return type("FileCmp", (), result)


    def run(self):
        # compile filters and excludes
        tmpFilters = self.filters[:]
        if tmpFilters:
            if not self.regexfilters:
                tmpFilters = [re.escape(x) for x in tmpFilters]
            tmpFilters = [re.compile(x) for x in tmpFilters]
        tmpExcludes = self.excludes[:]
        if tmpExcludes:
            if not self.regexfilters:
                tmpExcludes = [re.escape(x) for x in tmpExcludes]
            tmpExcludes = [re.compile(x) for x in tmpExcludes]
        

        def __filter(name, path=None):
            result = False
            # filter with filters
            if not tmpFilters:
                result = True
            else:
                for f in tmpFilters:
                    if f.search(name):
                        result = True
            # filter with excludes
            if tmpExcludes:
                for e in tmpExcludes:
                    if e.search(name):
                        result = False
            # filter with size
            if path:
                if self.sizeLimit and self.sizeLimit > 0:
                    size = os.path.getsize(path) / 1024
                    if size < self.sizeLimit:
                        result = False
            return result
        

        def processCmp(cmp, src, dst, tmpdir, **kwargs):
            '''
            Process the results from a comparison.
            Compare should include:
                left_only
                common
                right_only
            '''
            diff = Diff(**kwargs)

            # create files
            if cmp.left_only:
                for x in sorted(cmp.left_only):
                    x = os.path.normpath(re.sub(r"^[\\/]+", "", x))
                    srcp = os.path.join(src, x)
                    if utils._isfile(srcp):
                        if __filter(x, srcp):
                            diff.add_create(srcp)
                    elif utils._isdir(srcp):
                        if self.includedirs:
                            if __filter(x, srcp):
                                diff.add_create(srcp)
                        if self.recursive:
                            # recurse into the dir
                            d = __dirdiff(srcp, None, tmpdir, **kwargs)
                            diff.create.update(d.create)
            
            # update files
            if cmp.common:
                for x in sorted(cmp.common):
                    x = os.path.normpath(re.sub(r"^[\\/]+", "", x))
                    srcp = os.path.join(src, x)
                    dstp = os.path.join(dst, x)
                    if utils._isfile(srcp):
                        if utils._cmp_mtime(srcp, dstp, self.timeprecision, self.newer):
                            if __filter(x, srcp):
                                diff.add_update(srcp)
                        if self.forceUpdate:
                            diff.add_update(srcp)
                    elif utils._isdir(srcp) and self.recursive:
                        # recurse into the dir; the dir itself never gets added
                        d = __dirdiff(srcp, dstp, tmpdir, **kwargs)
                        # during an existing dir scan we may come across more info
                        diff.create.update(d.create)
                        diff.update.update(d.update)
                        diff.purge.update(d.purge)
            
            # purge files
            if cmp.right_only:
                for x in sorted(cmp.right_only):
                    x = os.path.normpath(re.sub(r"^[\\/]+", "", x))
                    dstp = os.path.join(dst, x)
                    if utils._isfile(dstp):
                        if __filter(x):
                            diff.add_purge(dstp)
                    elif utils._isdir(dstp):
                        # always include purge directories
                        if __filter(x):
                            diff.add_purge(dstp)
                        if self.recursive:
                            d = __dirdiff(None, dstp, tmpdir, **kwargs)
                            diff.purge.update(d.purge)

            return diff


        def __dirdiff(src, dst, tmpdir, **kwargs):
            '''
            Recursively compare src and dst directories and compile the
            results using dummy Diff instances.
            
            Returns a Diff instance with accurate create/update attributes
            ``tmpdir`` -- an empty directory used for performing null comparisons
            '''
            if src is None:
                src = tmpdir
            if dst is None:
                dst = tmpdir
            # compare directories
            LOG.debug('{0}, {1}'.format(src, dst))
            c = filecmp.dircmp(src, dst)
            return processCmp(c, src, dst, tmpdir)


        def __filediff(relFileList, src, dst, tmpdir, **kwargs):
            '''
            Compare a relative file path list between
            source and destination directories
            '''
            if src is None:
                src = tmpdir
            if dst is None:
                dst = tmpdir
            # compare file lists
            c = self.compareFileList(relFileList, src, dst)
            return processCmp(c, src, dst, tmpdir)
        
        # run the recursive function
        tmp = self.__tmpdir()
        kw = {}
        for opt in self.opts:
            kw[opt] = getattr(self, opt)

        src = self.src
        dst = self.dst
        if src is None:
            src = tmp
        if dst is None:
            dst = tmp
        if self.filelist is not None and len(self.filelist) > 0:
            self.filelist = self.makeFileListRelative(self.filelist, src, dst)
            d = __filediff(self.filelist, self.src, self.dst, tmp, **kw)
        else:
            d = __dirdiff(self.src, self.dst, tmp, **kw)
        if os.path.isdir(tmp):
            if os.path.exists(tmp):
                os.rmdir(os.path.normpath(tmp))
        # update this instance's attributes
        self.create = d.create
        self.update = d.update
        self.purge = d.purge
        self.update_counts()
    

    def update_counts(self, ops=['create', 'update', 'purge']):
        if 'create' in ops:
            self.createcount = len([x for y in self.create.values() for x in y])
        if 'update' in ops:
            self.updatecount = len([x for y in self.update.values() for x in y])
        if 'purge' in ops:
            self.purgecount = len([x for y in self.purge.values() for x in y])
        self.totalcount = self.createcount + self.updatecount + self.purgecount
    

    def report(self, create=True, update=True, purge=True):
        '''Print a report of the difference that has been compiled'''
        if self.filelist is None:
            LOG.info('No relative file list is defined')
        if self.src is None:
            LOG.info('No src path is defined')
            return
        if self.dst is None:
            LOG.info('No dst path is defined')
            return
        # build title
        title = 'Diff report ({0} -> {1}):'.format(self.src, self.dst)
        dashes = '-'*len(title)
        result = '\n{0}\n{1}\n'.format(title, dashes)
        # loop through all attributes
        attrs = []
        if create:
            attrs.append('create')
        if update:
            attrs.append('update')
        if purge:
            attrs.append('purge')
        for attr in attrs:
            count = getattr(self, '{0}count'.format(attr))
            result += ('\n{attr}: ({0})\n'.format(count, attr=attr.title()))
            items = sorted(getattr(self, attr).items())
            for path, files in items:
                result += ('  {0}{1}\n'.format(path, os.sep))
                for f in files:
                    result += ('    {0}\n'.format(f))
        LOG.info(result)
        return result