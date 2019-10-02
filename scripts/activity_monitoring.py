#!/usr/bin/env python

'''
USAGE
    activity_monitoring.py [OPTION] [VIDEOFILE]

DESCRIPTION
    Measure the activity in a video by comparing successive frames.

OPTIONS
    --dilatation=INT
        Use the dilatation algorithm on the difference image with INT
         iterations.
    --each=INT
        Compute the difference between FRAME(i) and FRAME(i+INT).
    --erosion=INT
        Use the erosion algorithm on the difference image with INT
         iterations.
    -e, --end=TIME
        Set the end time for the tracking
    --gaussian-blur-radius=INT
        Blur the image to remove noize with a gaussian blur radius of INT
         pixels. Default is 1/25 of image width. Valid only if option
         --noize-removal took the value "gaussian".
    --min-area=INT
        When doing image difference, considers contours encompassing a
         minimum of INT pixels. Default is 1/4 of image width.
    --opening
        Set --erosion and --dilatation to 1.
    --organizer=FILE
        FILE is a TSV table. The first column contains paths the to video 
        files. Additionnal columns contains information that will be
        append in each line of the output. You can call various
        information read from the video file using the following syntax:
            <dimension>     ::  Video dimension in pixel (image width x 
                                 image height)
            <fps>    ::  Video frame rate
    -s, --start=TIME
        Set the start time for the tracking
    --show
        Display the delta video.
    --help
        Display this message

'''

import getopt, sys, fileinput, cv2, os
from os import path
from threading import Event
from blunt import open_video, VideoStream, VideoTime
from math import sqrt

class Options(dict):
    '''
    Handle options with getopt from an argument vector and store the
    values.
    '''
    
    def __init__(self, argv):
        
        # set default
        self.set_default()
        
        # handle options with getopt
        try:
            opts, args = getopt.getopt(argv[1:], "e:s:", 
                                                ['dilatation=',
                                                 'each=',
                                                 'erosion=',
                                                 'end=',
                                                 'gaussian-blur-radius=',
                                                 'min-area=',
                                                 'opening',
                                                 'organizer=',
                                                 'start=',
                                                 'show',
                                                 'help'])
        except getopt.GetoptError, e:
            sys.stderr.write(str(e) + '\n\n' + __doc__)
            sys.exit(1)

        for o, a in opts:
            if o == '--help':
                sys.stdout.write(__doc__)
                sys.exit(0)
            elif o == '--dilatation':
                self['dilatation'] = int(a)
            elif o == '--each':
                self['each'] = int(a)
            elif o == '--erosion':
                self['erosion'] = int(a)
            elif o in ('-e', '--end'):
                self['end'] = a
            elif o == '--gaussian-blur-radius':
                self['gaussian_blur_radius'] = int(a)
            elif o == '--min-area':
                self['min_area'] = int(a)
            elif o in ('-s', '--start'):
                self['start'] = a
            elif o == '--organizer':
                self['organizer'] = Organizer(a)
            elif o == '--show':
                self['show'] = True
        
        # overrider options
        if ('--opening', '') in opts:
            self['dilatation'] = 1
            self['erosion'] = 1
        
        self.args = args
        if args:
            self['videos'] = args

    def set_default(self):
    
        # default parameter value
        self['dilatation'] = 0
        self['each'] = 1
        self['erosion'] = 0
        self['end'] = None
        self['gaussian_blur_radius'] = None
        self['min_area'] = None
        self['organizer'] = None
        self['start'] = "00:00:00.0"
        self['show'] = False

class Organizer(object):
    '''
    Read an input table and map information to video files.
    '''
    
    def __init__(self, fname, sep="\t"):
        
        with open(fname) as f:
            
            # get header
            self.header = f.readline().strip().split(sep)

            # check header
            if not all(self.header):
                raise ValueError("organizer's header contains empty values")
            
            # update values
            self.values = dict()
            self.fnames = []
            
            for line in f:
                options = Options([])
                values = line.strip().split(sep)
                
                # check values
                for i in xrange(len(values)):
                    
                    # check the video file
                    if i == 0:
                        if values[i] in self.values:
                            raise ValueError("this file appears more than"
                                             " one time in the organizer:"
                                             " {}.".format(values[i]))
                        stream = None
                        
                        # try opening the video and wrapping the 
                        # VideoStream instance
                        try:
                            sys.stderr.write("checking '{}'...".format(
                                             values[i]))
                            stream = VideoStream(values[i])
                        
                        # raise the error after indicating the file name
                        except:
                            sys.stderr.write("Problem with file '{}':"
                                             "\n".format(values[i]))
                            raise
                        
                        # close the video file
                        finally:
                            if stream is not None:
                                stream.camera.release()

                        sys.stderr.write("ok!\n")
                                
                    # lookup for values to be substituted
                    elif values[i].startswith("<") and values[i].endswith(">"):
                        if values[i] == "<dimension>":
                            values[i] = "{}x{}".format(int(stream.width),
                                                       int(stream.height))
                        elif values[i] == "<fps>":
                            values[i] = str(stream.fps)
                        else:
                            raise ValueError("unknown expression:"
                                             " {}".format(values[i]))
                
                # store fnames in an ordered list
                self.fnames.append(values[0])

                # store tuple accessible with the file name
                self.values[self.fnames[-1]] = tuple(values[1:])

        
    def get(self, fname):
        '''
        Retrieve information for the given (video) file name.
        '''
        
        return self.values[fname]
    
def blur(frame, radius=21):
    return cv2.GaussianBlur(frame, (radius, radius), 0)
            
def gray(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

def threshold(frame, erosion=0, dilatation=0):
    frame = cv2.adaptiveThreshold(frame, 255,
                                  cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV, 11, 3)
    
def delta(frame0, frame1, min_area=0, erosion=0, dilatation=0, radius=21, show=False):
    '''
    Calculate a delta between two grayscaled images.
    '''
    
    # blur the image
    if radius > 0:
        frame0, frame1 = blur(frame0), blur(frame1)
    
    # compute the absolute difference between the frames
    frameDelta = cv2.absdiff(frame0, frame1)
    
    # compute a black and white image given a difference threshold
    thresh = cv2.threshold(frameDelta, 5, 255, cv2.THRESH_BINARY)[1]
    
    # erode the image
    if erosion > 0:
        thresh = cv2.erode(thresh, None, iterations=erosion)
    
    # dilate the image
    if dilatation > 0:
        thresh = cv2.dilate(thresh, None, iterations=dilatation)
    
    # find contours on thresholded image
    #(cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,
    #    cv2.CHAIN_APPROX_SIMPLE) 
    
    # sum up the areas
    #s = sum(( x for x in map(cv2.contourArea, cnts) if x >= min_area ))
    
    # sum up the total of different pixels
    s = ( thresh == 255 ).sum()
    
    # show the thresholded difference image
    if show:
        cv2.putText(thresh,str(s),(0,thresh.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,(255,255,255))
        cv2.imshow("delta", thresh)
        cv2.waitKey(25)
        
    # return the total area of the contours encompassing more pixels than
    # min_area
    return s

def main(argv=sys.argv):
    
    # read options and remove options strings from argv (avoid option 
    # names and arguments to be handled as file names by
    # fileinput.input().
    options = Options(argv)
    sys.argv[1:] = options.args
    
    # list video files to be analyzed
    if options['organizer']:
        videos = options['organizer'].fnames
        sys.stdout.write("\t".join(("frame", "activity")) + "\t" +
                         "\t".join(options['organizer'].header[1:]) + "\n")
    else:
        videos = options['videos']
        sys.stdout.write("\t".join(("frame", "activity")) + "\n")
        
    # process videos one by one
    for video in videos:
        
        # format the output line
        if options['organizer']:
            line_format = ("{}\t{}\t" + 
                           "\t".join(options['organizer'].get(video)) +
                           "\n")
        else:
            line_format = "{}\t{}\n"
        
        # read the video
        with open_video(video, "r", options['start'], options['end']) as stream:
        #stream = VideoStream(video, options['start'], options['end'])
        
            # store the total number of pixels in one frame
            pixels = float(stream.height * stream.width)
            
            # parameter tuning
            if options['gaussian_blur_radius'] is None:
               options['gaussian_blur_radius'] = int(stream.width / 25.0)
            if options['min_area'] is None:
                options['min_area'] = int(stream.width / 4.0)
            
            # display these parameter values
            sys.stderr.write(
                "Parameters\n"
                "    Dilatation:           {}\n"
                "    Erosion:              {}\n"
                "    Gaussian blur radius: {}\n"
                "    Minimum area:         {}\n".format(
                options['dilatation'], options['erosion'], 
                options['gaussian_blur_radius'], options['min_area']))        
            
            # spacer...
            sys.stderr.write("\n")
            
            # display video information
            sys.stderr.write(
                "Video input\n"
                "    File name:            {}\n"
                "    Resolution:           {}x{}\n".format(
                os.path.split(stream.fname)[1], int(stream.width), int(stream.height)))
            
            # spacer...
            sys.stderr.write("-----\n")    
                
            # start the stream
            #stream.start()
            
            try:
            
                # get the first frame
                frame0 = stream.read()
                if frame0 is None: return 0
                gray0 = gray(frame0)
                
                # loop over the frames of the video
                for frame1 in stream:
                    if stream.frame_number % options['each']: continue
                    if options['show']: cv2.imshow("raw", frame1)
                    gray1 = gray(frame1)
                    d = delta(gray0, gray1, 
                              min_area=options['min_area'], 
                              erosion=options['erosion'],
                              dilatation=options['dilatation'],
                              radius=options['gaussian_blur_radius'],
                              show=options['show'])
                    sys.stdout.write(line_format.format(stream.frame_number, d))
                    gray0 = gray1
            
            finally:

                # delete video window
                cv2.destroyAllWindows()
                
                # stop the stream
                #stream.stop()

    # return 0 if everything succeeded
    return 0

# does not execute main if the script is imported as a module
if __name__ == '__main__': sys.exit(main())

