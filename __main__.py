#!/usr/bin/env python
# encoding: utf-8
'''
filesync.__main__

Created by Brennan Chapman on 2012-08-07.
Copyright (c) 2012 Moonbot Studios. All rights reserved.
'''

import os
import logging
import optparse

from sync import Sync
from watch import WatchFolder

try:
    LOG = logging.getMbotLogger(__name__)
except:
    LOG = logging.getLogger(__name__)

def _setupLog():
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    level = logging.DEBUG if True else logging.INFO
    LOG.setLevel(level)
    LOG.addHandler(sh)
_setupLog()

LOG.setLevel(logging.INFO)
def getBool(value):
    if value.lower() in ['false','0','off']:
        return False
    else:
        return True

if __name__ == "__main__":

    usage = 'usage: %prog [options] search location - Watch Folder '
    description = ('Watchs the source folder for changes and '
                   'mirrors them to the destination folder.')
    parser = optparse.OptionParser(usage, description=description)

    # Required
    group = optparse.OptionGroup(parser, 'Required')
    group.add_option('-s', '--source', help='(Required) Source folder', \
                       dest='source', action='store', default='')
    group.add_option('-d', '--destination', help='(Required) Destination folder',
                       dest='dest', action='store', default='')
    parser.add_option_group(group)

    # Operations
    group = optparse.OptionGroup(parser, 'Operations', 'Type of sync to run, only supply one.')
    group.add_option('--watch', help='Watch the source folder for changes and sync them to the destination folder',
                       dest='watch', action='store_true', default=False)
    group.add_option('--run', help='Run sync with custom flags specified below',
                       dest='run', action='store_true', default=False)
    parser.add_option_group(group)

    help = {'update':'Update files that are changed in the source folder to the destination',
            'newer':'Only update if the source file is newer than the destination',
            'create':'Create files that don\'t currently exist in destination',
            'purge':'Delete files that don\'t currently exist in destination',
            'watch':'Keep the sync alive and monitor source folder for changes'}

    # Flags
    s = Sync()
    opts = s.getopts()
    group = optparse.OptionGroup(parser, 'Flags', 'Flags to adjust sync')
    for k in opts.keys():
        typ = 'string'
        kwargs = {}
        if isinstance(opts[k], bool):
            typ = 'choice'
            kwargs['choices'] = ['True', 'False']
        group.add_option('--{0}'.format(k), help=(help[k] + ' ' if help.has_key(k) else '') + 'Default: {0}'.format(opts[k]),
                          dest=k, action='store', default=None, type=typ, **kwargs)
    del s
    parser.add_option_group(group)

    # Watch folder customization
    group = optparse.OptionGroup(parser, 'Watch Folder Attributes')
    group.add_option('--watchTitle', help='Title to use for the watch folder display',
                     dest='watchTitle', action='store', default="", type='string')
    group.add_option('--watchMessage', help='Message to use for the watch folder display',
                     dest='watchMessage', action='store', default="", type='string')
    parser.add_option_group(group)

    # Parse
    (options, args) = parser.parse_args()

    # Convert all of the csv into lists
    for option in opts:
        if type(opts[option]) == list:
            val = getattr(options, option)
            if val:
                l = getattr(options, option).split(',')
                setattr(options, option, l)

    # Process Results
    if not options.source and not options.dest:
        parser.print_help()
        print '\n'
        LOG.error('Please supply both a source and destination folder.')
    elif not options.watch and not options.run:
        parser.print_help()
        print '\n'
        LOG.error('Please select an operation to perform.')
    else:
        kwargs = {}
        for item in opts:
            val = getattr(options, item)
            if val: kwargs[item] = getBool(val)
        
        title = options.watchTitle
        msg = options.watchMessage.replace("\\n", "\n")

        sources = options.source.split(",")
        dests = options.dest.split(",")

        if len(sources) != len(dests):
            LOG.error('Number of sources and destinations don\'t match.')
        else:
            # Setup and print the message to the user
            os.system('cls')
            if not title:
                title = 'File Sync Watch Folder'
            if not msg:
                msg = 'Mirroring changes from source folder to destination folder.'
            title = "---------------------- {0} ----------------------".format(title)
            msg = "{0}".format(msg)

            paths = []
            for index, source in enumerate(sources):
                paths.append("Source: {0}\nDestination: {1}".format(source, dests[index]))
            print "{0}\n{1}\n{0}\n{2}\n{0}\n{3}\n{0}".format("-"*len(title), title, msg, '\n'.join(paths))

            # Start the watch folders
            for index, source in enumerate(sources):
                w = WatchFolder(source, dests[index], **kwargs)
                w.run()