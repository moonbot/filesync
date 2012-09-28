#!/usr/bin/env python
# encoding: utf-8
'''
filesync

Created by Brennan Chapman and Bohdon Sayre on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.
'''

from sync import Sync
import logging

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

def _setupLog():
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('%(name)s:%(levelname)s: %(message)s'))
    LOG.addHandler(sh)
_setupLog()