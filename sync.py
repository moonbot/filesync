#!/usr/bin/env python
# encoding: utf-8
'''
filesync.sync

Created by Brennan Chapman and Bohdon Sayre on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.
'''

import os, stat, re, time, sys
import shutil, filecmp
import logging

from diff import Diff
from utils import *

LOG = logging.getMbotLogger(__name__)

__all__ = [
    'FileSyncError',
    'Sync',
    'Diff',
]

class Sync(object):
    '''
    Sync is a class for synchronizing or updating one directory with another.
    The class operates one directionally, so a true sync would require multiple
    Syncs that do not purge files.
    
    Optionally, a file path list can be supplied to limit the sync between
    the src and dst.  This file list can either be relative paths or include
    the src or dst prefixes in their file paths.

    The basic setup is to pass a src and dst path then run the ``diff`` method.
    This will generate a Diff instance that will provide information about
    which files would be created/updated/purged if the sync was run. The diff
    can then be trimmed using ``difftrim``. Once the difference reflects the
    desired changes, run the ``sync`` or ``update`` methods depending on if
    files/dirs should be created and updated, or only updated.

    TODO: describe the diff settings and run settings here
    '''
    
    def __init__(self, src=None, dst=None, **kwargs):
        self.src = None if src is None else os.path.normpath(src)
        self.dst = None if dst is None else os.path.normpath(dst)
        self.origdiff = None
        self.trimdiff = None
        self.ops = ['create', 'update', 'purge']
        self.diffstngs = {
            'filters':[],
            'excludes':['.DS_Store','Thumbs.db','.place-holder'],
            'filelist':[],
            'regexfilters':False,
            'includedirs':True, 
            'timeprecision':3,
            'recursive':True,
            'newer':True,
            'forceUpdate':False,
            'sizeLimit':0,
        }
        self.runstngs = {
            'maketarget':True,
            'trimmed':True,
            'create':False,
            'update':False,
            'purge':False,
            'forceOwnership':False,
            'errorsToDebug':False,
        }
        self.progressfnc = None
        self.progresscheck = None
        self.progressamt = 0
        
        self.stats = {
            'stime':0.0,
            'etime':0.0,
            'creates':[],
            'createfails':[],
            'updates':[],
            'updatefails':[],
            'purges':[],
            'purgefails':[],
        }
        self.__hasrun = False
        self.__hasrundiff = False
        self.__diffcurrent = False
        
        for k, v in kwargs.items():
            if k in self.diffstngs.keys():
                self.diffstngs[k] = v
            elif k in self.runstngs.keys():
                self.runstngs[k] = v

    def getopts(self):
        '''
        Return a list of options and their values
        '''
        result = {}
        for k in self.diffstngs.keys():
            result[k] = self.diffstngs[k]
        for k in self.runstngs.keys():
            result[k] = self.runstngs[k]
        return result

    def __validate(self):
        if self.src is None or self.dst is None:
            return False
        return True
    
    def diff(self, **kwargs):
        '''Compile a difference list of files between src and dst directories'''
        if self.__validate():
            # TODO: filter kwargs
            self.diffstngs.update(kwargs)
            self.origdiff = Diff(self.src, self.dst, **self.diffstngs)
            self.trimdiff = self.origdiff.copy()
            self.__hasrundiff = True
            self.__diffcurrent = True
    
    def difftrim(self, create=[], update=[], purge=[]):
        '''
        Removes items from ``origdiff`` and saves the results in ``trimdiff``
        
        ``create`` -- a list of full paths to remove from the create diff list
        ``update`` -- a list of full paths to remove from the update diff list
        ``purge`` -- a list of full paths to remove from the purge diff list
        '''
        for path in create:
            self.trimdiff.remove_create(path)
        for path in update:
            self.trimdiff.remove_update(path)
        for path in purge:
            self.trimdiff.remove_purge(path)

    def sync(self, refreshDiff=False, dry_run=False, **kwargs):
        '''
        Copy any new files and update any existing files from src to dst
        directories using the compiled dirdiff list
        '''
        self.runstngs['create'] = True
        self.runstngs['update'] = True
        self.runstngs.update(kwargs)
        self.run(refreshDiff=refreshDiff, dry_run=dry_run)
    
    def update(self, refreshDiff=False, dry_run=False, **kwargs):
        '''Update only files that already exist in both src and dst'''
        self.runstngs['create'] = False
        self.runstngs['update'] = True
        self.runstngs.update(kwargs)
        self.run(refreshDiff=refreshDiff, dry_run=dry_run)
    
    def run(self, refreshDiff=False, dry_run=False, **kwargs):
        '''
        Run the directory sync given the current run settings
        
        ``refreshDiff`` -- re-runs diff() after syncing
        '''
        if kwargs.has_key('no_update'):
            LOG.warning('Filesync Deprecation Warning: \'no_update\' is no longer supported, use \'refreshDiff\' instead')
            refreshDiff = not kwargs['no_update']

        if not self.__diffcurrent:
            LOG.warning('diff is not current; it\'s recommended to run diff again before updating/synching')
        
        self.stats['stime'] = time.time()
        self.__run(dry_run=dry_run)
        self.stats['etime'] = time.time()
        
        self.__hasrun = True
        self.__diffcurrent = False
        if refreshDiff:
            self.diff()
    
    def __run(self, dry_run=False):
        # reset stats
        self.stats['creates'] = []
        self.stats['createfails'] = []
        self.stats['updates'] = []
        self.stats['updatefails'] = []
        self.stats['purges'] = []
        self.stats['purgefails'] = []
        # determine the diff to use (trimmed or untrimmed)
        d = self.trimdiff if self.runstngs['trimmed'] else self.origdiff
        if d is None:
            return
        return self.runwithdiff(d, dry_run)

    def runwithdiff(self, diff, dry_run=False):
        if not isinstance(diff, Diff):
            raise TypeError('expected Diff, got {0}'.format(type(diff).__name__))
        # run through all 'create' files
        if self.runstngs['create']:
            LOG.debug('creating...')
            items = sorted(diff.create.items())
            for path, files in items:
                if self.progresscheck is not None:
                    if not self.progresscheck():
                        return
                relpath = os.path.relpath(path, self.src)
                if relpath == '.':
                    relpath = ''
                srcdir = os.path.join(self.src, relpath)
                dstdir = os.path.join(self.dst, relpath)
                # make the destination dir if it doesn't exist
                if not os.path.isdir(dstdir):
                    self.__makedirs(dstdir, self.stats['creates'], self.stats['createfails'], dry_run)
                for f in files:
                    srcp = os.path.join(srcdir, f)
                    dstp = os.path.join(dstdir, f)
                    if os.path.isdir(srcp):
                        self.__copydir(srcp, dstp, self.stats['creates'], self.stats['createfails'], dry_run)
                    elif os.path.isfile(srcp):
                        self.__copy(srcp, dstp, self.stats['creates'], self.stats['createfails'], dry_run)
        # run through all 'update' files
        if self.runstngs['update']:
            LOG.debug('updating...')
            items = sorted(diff.update.items())
            for path, files in items:
                if self.progresscheck is not None:
                    if not self.progresscheck():
                        return
                relpath = os.path.relpath(path, self.src)
                if relpath == '.':
                    relpath = ''
                srcdir = os.path.join(self.src, relpath)
                dstdir = os.path.join(self.dst, relpath)
                for f in files:
                    # updates never include dirs
                    srcp = os.path.join(srcdir, f)
                    dstp = os.path.join(dstdir, f)
                    self.__copy(srcp, dstp, self.stats['updates'], self.stats['updatefails'], dry_run)
        # run through all 'purge' files
        if self.runstngs['purge']:
            LOG.debug('purging...')
            items = sorted(diff.purge.items())
            for path, files in items:
                if self.progresscheck is not None:
                    if not self.progresscheck():
                        return
                relpath = os.path.relpath(path, self.dst)
                if relpath == '.':
                    relpath = ''
                dstdir = os.path.join(self.dst, relpath)
                for f in files:
                    dstp = os.path.join(dstdir, f)
                    if os.path.isdir(dstp):
                        self.__rmdir(dstp, self.stats['purges'], self.stats['purgefails'], dry_run)
                    elif os.path.isfile(dstp):
                        self.__remove(dstp, self.stats['purges'], self.stats['purgefails'], dry_run)
                    else:
                        LOG.debug('file/folder not found: {0}'.format(dstp))

    def __makedirs(self, dir_, passes=None, fails=None, dry_run=False):
        '''
        Make the given dir_ including any parent dirs
        Append dir_ to ``fails`` on error
        '''
        try:
            os.makedirs(dir_)
        except Exception as e:
            LOG.error(e)
            if fails is not None:
                fails.append(dir_)
        else:
            if passes is not None:
                passes.append(dir_)
            LOG.debug('made dirs: {0}'.format(dir_))
    
    def __getProgPercent(self):
        '''
        Get a progress percentage and return it.
        '''
        self.progressamt += 1
        return float(self.progressamt) / float(self.origdiff.totalcount) * 100

    def __copydir(self, src, dst, passes=None, fails=None, dry_run=False):
        '''
        Make the given dst directory and copy stats from src
        Append dst to ``fails`` on error
        '''
        if self.progressfnc:
            self.progressfnc('Copying {0}'.format(dst), self.__getProgPercent())
        try:
            if not dry_run:
                os.mkdir(dst)
        except Exception as e:
            LOG.error(e)
            if fails is not None:
                fails.append(dst)
        else:
            if os.path.exists(dst) and self.runstngs['forceOwnership']:
                # make writable
                fileAtt = os.stat(dst)[0]
                if (not fileAtt & stat.S_IWRITE):
                    try:
                        os.chmod(dst, stat.S_IWRITE)
                    except Exception as e:
                        LOG.error('could not make file writable {0}: {1}'.format(dst, e))
                        return False
            shutil.copystat(src, dst)
            if passes is not None:
                passes.append(dst)
            LOG.debug('made dir: {0}'.format(dst))
    
    def __copy(self, src, dst, passes=None, fails=None, dry_run=False):
        '''
        Copy the given src file to dst
        Append dst to ``fails`` on error
        '''
        if self.progressfnc:
            self.progressfnc('Copying {0}'.format(dst), self.__getProgPercent())
        try:
            if not dry_run:
                if os.path.exists(dst) and self.runstngs['forceOwnership']:
                    # make writable
                    fileAtt = os.stat(dst)[0]
                    if (not fileAtt & stat.S_IWRITE):
                        try:
                            os.chmod(dst, stat.S_IWRITE)
                        except Exception as e:
                            LOG.error('could not make file writable {0}: {1}'.format(dst, e))
                            return False
                shutil.copy2(src, dst)
        except (IOError, OSError) as e:
            if self.runstngs['errorsToDebug']:
                LOG.debug(e)
            else:
                LOG.error(e)
            if fails is not None:
                fails.append(dst)
        else:
            if passes is not None:
                passes.append(dst)
            LOG.debug('copied: {0}'.format(dst))
    
    def __rmdir(self, dir_, passes=None, fails=None, dry_run=False):
        '''
        Remove the given dir_.
        Append dir_ to ``fails`` on error
        '''
        if self.progressfnc:
            self.progressfnc('Deleting {0}'.format(dir_), self.__getProgPercent())
        if not os.path.isdir(dir_):
            LOG.warning('dir does not exist: {0}'.format(dir_))
            return
        try:
            if not dry_run:
                shutil.rmtree(dir_)
        except Exception as e:
            LOG.error(e)
            if fails is not None:
                fails.append(dir_)
        else:
            if passes is not None:
                passes.append(dir_)
            LOG.debug('removed dir: {0}'.format(dir_))
    
    def __remove(self, f, passes=None, fails=None, dry_run=False):
        '''
        Delete the given file
        Append f to ``fails`` on error
        '''
        if self.progressfnc:
            self.progressfnc('Deleting {0}'.format(f), self.__getProgPercent())
        if not os.path.isfile(f):
            LOG.warning('file does not exist: {0}'.format(f))
            return
        try:
            if not dry_run:
                os.remove(f)
        except OSError as e:
            LOG.error(e)
            if fails is not None:
                fails.append(f)
        else:
            if passes is not None:
                passes.append(f)
            LOG.debug('deleted: {0}'.format(f))
        
    def report(self, diff=False):
        if not self.__hasrun or diff:
            if not self.__diffcurrent:
                LOG.warning('diff is not current')
            return self.diffreport()
        else:
            self.runreport()
    
    def diffreport(self, **kwargs):
        '''
        Return a report from the current diff
        ``trimmed`` -- if True, returns the trimmed diff's report
        '''
        if self.origdiff is None:
            return
        if self.runstngs['trimmed']:
            return self.trimdiff.report(**kwargs)
        else:
            return self.origdiff.report(**kwargs)
    
    def runreport(self):
        '''
        Print a report for the last update/sync/run.
        '''
        if self.src is None:
            LOG.info('No source path is defined')
            return
        if self.dst is None:
            LOG.info('No destination path is defined')
            return
        # build title
        title = 'Sync report ({0} -> {1}):'.format(self.src, self.dst)
        dashes = '-'*len(title)
        result = '\n{0}\n{1}\n'.format(title, dashes)
        # loop through all attributes
        attrs = ['create', 'update', 'purge']
        for attr in attrs:
            fails = self.stats['{0}fails'.format(attr)]
            passes = self.stats['{0}s'.format(attr)]
            result += ('\n{attr}: ({0})\n'.format(len(passes), attr=(attr.title() + ' Passes')))
            result += ('{attr}: ({0})\n'.format(len(fails), attr=(attr.title() + ' Fails')))
            for item in fails:
                result += ('  {0}\n'.format(item))
        LOG.info(result)
        return result