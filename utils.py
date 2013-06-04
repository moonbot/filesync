#!/usr/bin/env python
# encoding: utf-8
'''
filesync.utils

Created by Brennan Chapman and Bohdon Sayre on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.
'''

import os
import stat
import logging

try:
    LOG = logging.getMbotLogger(__name__)
except:
    LOG = logging.getLogger(__name__)

def _isfile(p):
    if not os.path.islink(p):
        return stat.S_ISREG(os.stat(p).st_mode)
    else:
        return False

def _isdir(p):
    try:
        return stat.S_ISDIR(os.stat(p).st_mode)
    except:
        return False

def _cmp_mtime(fileA, fileB, precision=3, newer=True):
    '''
    Return True if file A is newer than file B
    ``precision`` -- how many floating point digits to compare the times with.
        precision of 0 compares to seconds
    '''
    stA = os.stat(fileA)
    stB = os.stat(fileB)
    a = round(stA.st_mtime, precision)
    b = round(stB.st_mtime, precision)
    if newer:
        return a > b
    else:
        return a != b