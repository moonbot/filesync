#!/usr/bin/env python
# encoding: utf-8
"""
filesync.watch

Created by Brennan Chapman on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.

Watch folder components
"""

import os
import sys
import time
import threading

from sync import Sync

class WatchFolder(threading.Thread):
    def __init__(self, src, dst, **kwargs):
        threading.Thread.__init__(self)
        self.src = src
        self.dst = dst
        self.freq = 5
        if kwargs.has_key('watchFreq'):
            self.freq = kwargs['watchFreq']
            del kwargs['watchFreq']
        self.kwargs = kwargs

    def pathWalk(self, path):
        """
        Walk through the supplied directory.
        Return a list of all the file and folder paths.
        """
        result = []
        for root, dirs, files in os.walk(path):
            for name in files:
                result.append(os.path.join(root, name))
            for name in dirs:
                result.append(os.path.join(root, name))
        return result

    def loadInitContents(self, s):
        self.initContents = s.origdiff.create
        init = []
        for folder in s.origdiff.create:
            for item in s.origdiff.create[folder]:
                # Store the mtime in case anything get's updated
                path = os.path.join(folder, item)
                mtime = os.stat(path).st_mtime
                init.append([path, mtime])
        self.initContents = init

    def getInitContents(self):
        """
        Check the initital contents for any updates
        based on modification time.
        Return a list of paths that haven't been updated.
        """
        result = []
        for item in self.initContents:
            try:
                mtime = os.stat(item[0]).st_mtime
                if mtime <= item[1]:
                    result.append(item[0])
            except:
                pass
        return result

    def progress(self, msg, perc):
        """
        Display the progress messages from the sync
        """
        sys.stdout.write("\n" + msg.replace(self.dst, ''))
        sys.stdout.flush()

    def run(self):
        """
        Thread: Run
        """
        s = Sync(self.src, self.dst, **self.kwargs)
        s.diff()
        self.loadInitContents(s)
        s.progressfnc = self.progress
        while True:
            s.diff()
            s.difftrim(create=self.getInitContents())
            s.run()
            time.sleep(self.freq)