#!/usr/bin/env python

'''
USAGE
    timestamp.py [OPTION] X

DESCRIPTION
    Transform X seconds in a timestamp value like HH:MM:SS.mmm

OPTIONS
    --help
        Display this message

'''

import getopt, sys, fileinput, blunt
from os import path


class Options(dict):

    def __init__(self, argv):
        
        # set default
        self.set_default()
        
        # handle options with getopt
        try:
            opts, args = getopt.getopt(argv[1:], "", ['help'])
        except getopt.GetoptError, e:
            sys.stderr.write(str(e) + '\n\n' + __doc__)
            sys.exit(1)

        for o, a in opts:
            if o == '--help':
                sys.stdout.write(__doc__)
                sys.exit(0)

        self.args = args
    
    def set_default(self):
    
        # default parameter value
        pass
    
def main(argv=sys.argv):
    
    # read options and remove options strings from argv (avoid option 
    # names and arguments to be handled as file names by
    # fileinput.input().
    options = Options(argv)
    sys.argv[1:] = options.args
    
    # organize the main job...
    for x in options.args:
        sys.stdout.write("{}\n".format(blunt.seconds_timestamp(float(x))))
    
    # return 0 if everything succeeded
    return 0

# does not execute main if the script is imported as a module
if __name__ == '__main__': sys.exit(main())
