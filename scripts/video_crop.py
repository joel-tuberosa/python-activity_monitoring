#!/usr/bin/env python

'''
USAGE
    video_crop.py [OPTION] CROPS [FILE...]

DESCRIPTION
    Given a list of coordinates (CROPS), output different cropping of a 
    video file.
    
    CROP: X:Y:W:H
    
OPTIONS
    --bw
        Output black and white videos.
    -e, --end=HH:MM:SS.m
        Set the end time of the input
    --fourcc=STR
        Output video codec in four character code (default: H264)
    --fps=INT
        Frame per second rate of the output video. (default: 25)
    -s, --start=HH:MM:SS.mmm
        Set the start time of the input 
    --splits=HH:MM:SS.mmm[,HH:MM:SS.mmm ...]
        Split the output in several parts, at the given timestamps.
    --help
        Display this message

'''

import getopt, sys, fileinput, cv2
from os import path
from blunt import VideoStream, VideoCropper, TimeStamp

class Options(dict):

    def __init__(self, argv):
        
        # set default
        self.set_default()
        
        # handle options with getopt
        try:
            opts, args = getopt.getopt(argv[1:], "e:s:", ['bw',
                                                          'end=',
                                                          'fourcc=',
                                                          'fps=',
                                                          'splits=',
                                                          'start=',
                                                          'help'])
        except getopt.GetoptError, e:
            sys.stderr.write(str(e) + '\n\n' + __doc__)
            sys.exit(1)

        for o, a in opts:
            if o == '--help':
                sys.stdout.write(__doc__)
                sys.exit(0)
            elif o == '--bw':
                self['color'] = False
            elif o in ('-e', '--end'):
                self['end'] = a
            elif o == '--fourcc':
                self['fourcc'] = a
            elif o == '--fps':
                self['fps'] = int(a)
            elif o in ('-s', '--start'):
                self['start'] = TimeStamp(a)
            elif o == '--splits':
                self['splits'] = map(lambda x: TimeStamp(x), a.split(","))
        
        self.args = args
        
    def set_default(self):
    
        # default parameter value
        self['color'] = True
        self['end'] = None
        self['fourcc'] = 'MJPG'
        self['fps'] = 25
        self['start'] = TimeStamp("00:00:00.0")
        self['splits'] = []

def read_crops(f):
    d = {}
    for line in f:
        coordinates, video_fname = line.strip().split("\t")
        x, y, w, h = map(int, coordinates.strip().split(":"))
        d[video_fname] = (x, y, w, h)
    return d

def get_croppers_array(crops, fourcc, fps, color, prefix=""):
    a = []
    for fname in crops:
        x, y, w, h = crops[fname]
        a.append(VideoCropper(prefix + fname, 
                              fourcc, 
                              x, y, w, h,
                              fps,
                              color))
    return a
                
def main(argv=sys.argv):
    
    # read options and remove options strings from argv (avoid option 
    # names and arguments to be handled as file names by
    # fileinput.input().
    options = Options(argv)
    crops_fname, video_fnames = options.args[0], options.args[1:]
    
    # display option values
    sys.stderr.write(
        "Input info:  \n"
        "   start:  {}\n"
        "   end:    {}\n"
        "   splits: {}\n"
        "Output info: \n"
        "   codec   {}\n"
        "   fps     {}\n"
        "   color   {}\n".format(options['start'],
                                 options['end'],
                                 ", ".join(map(str, options['splits'])),
                                 options['fourcc'],
                                 options['fps'],
                                 'Yes' if options['color'] else 'No'))
    
    # handle the crop organization
    with open(crops_fname) as f:
        crops = read_crops(f)
    
    # in case of an error or a KeyboardInterrupt, always end up by 
    # stopping the threads
    try:

        # initialize the writers
        prefix = "part1_" if options['splits'] else ""
        croppers = get_croppers_array(crops, 
                                      options['fourcc'], 
                                      options['fps'], 
                                      options['color'], 
                                      prefix=prefix)
        j = 1        
        
        # start the writers
        map(lambda cropper: cropper.start(), croppers)    
        
        # read video input files one by one
        n = len(video_fnames)
        elapsed_seconds = options['start'].seconds
        
        for i in xrange(n):
            start = options['start'] if i == 0 else None
            end = options['end'] if i == n-1 else None
            stream = VideoStream(video_fnames[i], start, end)
            stream.start()
            for frame in stream:
                elapsed_seconds += 1.0/stream.fps
                if ( options['splits'] and 
                     elapsed_seconds >= options['splits'][0].seconds ):
                    map(lambda cropper: cropper.stop(), croppers)
                    j += 1
                    prefix = "part" + str(j) + "_"
                    croppers = get_croppers_array(crops, 
                                                  options['fourcc'], 
                                                  options['fps'], 
                                                  options['color'], 
                                                  prefix=prefix)
                    options['splits'] = options['splits'][1:]
                    
                    # restart the new writers
                    map(lambda cropper: cropper.start(), croppers)  
                map(lambda cropper: cropper.write(frame), croppers)
    finally:
        map(lambda cropper: cropper.stop(), croppers)
        if stream.running(): stream.stop()
        
    # return 0 if everything succeeded
    return 0

# does not execute main if the script is imported as a module
if __name__ == '__main__': sys.exit(main())

