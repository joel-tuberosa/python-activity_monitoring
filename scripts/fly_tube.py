#!/usr/bin/env python

'''
USAGE
    fly_tube.py [OPTIONS] X:Y:W:H[:n][,...] [FILE...]
    
DESCRIPTION
    Read the video FILE, count the number of small round objects within 
    horizontal segments of an area defined by X:Y:W:H, at each time
    point.
    
OPTIONS
    
    --end=HH:MM:SS.mmm
        End of the video analysis.

    --open-filter=A:B
        Apply an opening algorithm to the image to remove noise and 
        merge close shapes. A is the number of iteration of the erosion
        filter application, B is the number of iteration of the 
        dilatation filter application. A and B are set to 1 by default.

    --segments=INT
        Number of division of the analyzed tube.

    --show
        Display the analyzed images.
        
    --start=HH:MM:SS.mmm
        Start of the video analysis.
    
    --tubes=
        Tube coordinate(s). If not passed, it will analyze the whole
        image. You can add the expected number of flies in each tube with
        the optional n, which is by default 1.
    
    --each=INT
        measure each INT frame (default=1)
        
    --help
        Display this message

'''

import getopt, sys, fileinput, cv2, os
import numpy as np
from threading import Event
from blunt import open_video, VideoInput, VideoTime, VideoCropper, TimeStamp

class Options(dict):
    '''
    Handle the script's command line arguments and store the parameter 
    values.
    '''
    
    def __init__(self, argv):
        
        # set default
        self.set_default()
        
        # handle options with getopt
        try:
            opts, args = getopt.getopt(argv[1:], "", ['help',
                                                      'each=',
                                                      'end=',
                                                      'open-filter=',
                                                      'segments=',
                                                      'show',
                                                      'start='])
        except getopt.GetoptError, e:
            sys.stderr.write(str(e) + '\n\n' + __doc__)
            sys.exit(1)

        for o, a in opts:
            if o == '--help':
                sys.stdout.write(__doc__)
                sys.exit(0)
            elif o == "--each":
                self["each"] = int(a)
            elif o == "--end":
                self["end"] = TimeStamp(a)
            elif o == "--open-filter":
                self["open_filter"] = map(int, a.split(":"))
            elif o == "--segments":
                self["segments"] = int(a)
            elif o == "--show":
                self["show"] = True
            elif o == "--start":
                self["start"] = TimeStamp(a)

        self.args = args
        self["tubes"] = get_tubes(args[0])
    
    def set_default(self):
    
        # default parameter value
        self["each"] = 1
        self["end"] = None
        self["open_filter"] = (1, 1)
        self["show"] = False
        self["segments"] = 1
        self["start"] = None

def get_tubes(s):
    '''
    Sort coordinates given as "x:y:w:h[:n][, ...]"
    '''
    
    return [ tuple(tube) + (1,) if len(tube) == 4 else tuple(tube)
             for tube in [ map(int, x.strip().split(":"))
                           for x in s.split(",") ] ]

def opening(frame, erode_iter, dilate_iter):
    '''
    Apply an image opening algorithm to the frame.
    '''
    
    frame = cv2.erode(frame, None, iterations=erode_iter)
    frame = cv2.dilate(frame, None, iterations=dilate_iter)
    return frame

def centroid(cnt):
    '''
    Calculate the centroid of a contour object. If the contour is a line
    (the volume is null), the centroid x and y are calculated as the 
    means of all x and all y, respectively.
    '''
    
    if len(cnt) > 2:
        M = cv2.moments(cnt)
        if M['m00'] == 0:
            cx = np.rint(cnt[:, 0, 0].mean()).astype(np.int32)
            cy = np.rint(cnt[:, 0, 1].mean()).astype(np.int32)
        else:
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])
    elif len(cnt) > 1:
        cx = np.rint((cnt[0, 0, 0] + cnt[1, 0, 0])/2.0).astype(np.int32)
        cy = np.rint((cnt[0, 0, 1] + cnt[1, 0, 1])/2.0).astype(np.int32)
    else:
        cx, cy = cnt[0, 0, 0], cnt[0, 0, 1]
    return (cx, cy)

def centroid_and_area(cnt):

    if len(cnt) > 2:
        M = cv2.moments(cnt)
        
        # If the contour is a line, the area is simplify as the Manhattan
        # distance between the two extremes
        if M['m00'] == 0: 
            lx = cnt[:, 0, 0].amax() - cnt[:, 0, 0].amin()
            if lx < 1: lx = 1
            ly = cnt[:, 0, 1].amax() - cnt[:, 0, 1].amin()
            if ly < 1: ly = 1
            area = lx + ly
            cx = np.rint(cnt[:, 0, 0].mean()).astype(np.int32)
            cy = np.rint(cnt[:, 0, 1].mean()).astype(np.int32)
        
        # Otherwise take the moment M00 
        else:
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])
            area = M['m00']
    
    # If the contour is a straight line between two points, the area is
    # the Manhattan distance between these two points
    elif len(cnt) > 1:
        cx = np.rint((cnt[0, 0, 0] + cnt[1, 0, 0])/2.0).astype(np.int32)
        cy = np.rint((cnt[0, 0, 1] + cnt[1, 0, 1])/2.0).astype(np.int32)
        area = abs(cnt[0, 0, 0] - cnt[1, 0, 0]) + abs(cnt[0, 0, 1] - cnt[1, 0, 1])
    
    # If the contour is one point, then the area is 1
    else:
        cx, cy = cnt[0, 0, 0], cnt[0, 0, 1]
        area = 1
    return (cx, cy, area)
    
def which_segment(x, segments):
    '''
    Return the first interval index (elements of segments) in which x is
    found.
    '''
    
    i = 0
    for a, b in segments:
        if x >= a and x < b: return i
        i += 1
    return -1

### TO BE TESTED
def fly_finder(cnts, n):
    '''
    Merge the closest contours when they exceed n, by adding their areas 
    and finding a new centroid. Returns only the coordinates and the
    areas of theses objects. If several points are equidistant, there is
    no rule for priority: the first found closest neighbor are 
    aggregated.
    '''
    
    flies = [ centroid_and_area(cnt) for cnt in cnts ]
    while len(flies) > n:
        
        # put the coordinates in a numpy array
        pts = np.array([ [x, y] for x, y, a in flies ])
        
        # compute the pairwise Manhattan distance matrix
        m = np.sum(abs(pts[None, :] - pts[:, None]), -1)
        
        # find the shortest distance
        min = (np.inf, 0, 0)
        for i in xrange(1, len(flies)):
            for j in xrange(0, i):
                if m[i,j] < min[0]: min = (m[i,j], i, j)
        i, j = min[1:]

        # merge the flies
        xi, xj = flies[i][0], flies[j][0]
        yi, yj = flies[i][1], flies[j][1]
        ai, aj = flies[i][2], flies[j][2]
        a = float(ai + aj)
        
        dx, dy = abs(xi-xj), abs(yi-yj)
        
        cx = round(xi + dx*(aj/a)) if xi < xj else round(xj + dx*(ai/a))
        cy = round(yi + dy*(aj/a)) if yi < yj else round(yj + dx*(ai/a))
        
        # replace the flies
        flies[i] = (int(cx), int(cy), int(a))
        flies.pop(j)
    return flies
    
def main(argv=sys.argv):
    
    # read options and remove options strings from argv (avoid option 
    # names and arguments to be handled as file names by
    # fileinput.input().
    options = Options(argv)
    sys.argv[1:] = options.args[1:]
        
    # organize the main job...
    segment_lengths = [ w/float(options["segments"])
                        for x, y, w, h, n in options["tubes"] ]
                        
    # segments
    segments = []
    i = 0
    for x, y, w, h, n in options["tubes"]:
        l = w/float(options["segments"])
        assert l >= 1
        segments.append((l, []))
        for a in np.floor(np.arange(x, x+w, l)):
            b = a+l 
            if b > x+w: b = x+w
            segments[i][1].append((a, b))
        i += 1
    
    # output header
    sys.stdout.write("video.file,frame,tube,segment,n\n")
    for fname in options.args:
        with VideoInput(fname, options["start"], options["end"]) as video:
            frame_i = 0
            for frame in video:

                # frame selection
                if frame_i % options["each"]:
                    frame_i += 1
                    continue
                
                # tubes
                if options["tubes"] is not None:
                    tubes = ( frame[y:y+h, x:x+w]
                              for x, y, w, h, n in options["tubes"] )
                else:
                    tubes = [frame]
                
                # find the position of flies in each tube
                i = 0
                for subframe in tubes:

                    # show the analyzed image and wait a key stroke 
                    # before continuing
                    # https://docs.opencv.org/3.0-beta/doc/py_tutorials/py_gui/py_image_display/py_image_display.html
                    if options["show"]:
                        cv2.imshow("tube" + str(i), subframe)
                        cv2.waitKey(0) 

                    # convert to grayscale
                    subframe = cv2.cvtColor(subframe, cv2.COLOR_BGR2GRAY)
                    
                    # adaptive thresholding
                    # https://pythonprogramming.net/thresholding-image-analysis-python-opencv-tutorial/
                    subframe = cv2.adaptiveThreshold(subframe, 255,
                                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 11, 3)
                                        
                    # image opening
                    # https://docs.opencv.org/3.4/d9/d61/tutorial_py_morphological_ops.html
                    subframe = opening(subframe, *options["open_filter"])
                                          
                    # show the analyzed image and wait a key stroke 
                    # before continuing
                    # https://docs.opencv.org/3.0-beta/doc/py_tutorials/py_gui/py_image_display/py_image_display.html
                    if options["show"]:
                        cv2.imshow("tube" + str(i), subframe)
                        cv2.waitKey(0)                                              
                                              
                    # find contours on thresholded image
                    # https://docs.opencv.org/3.4/d4/d73/tutorial_py_contours_begin.html
                    _cnts = cv2.findContours(subframe.copy(), 
                                             cv2.RETR_EXTERNAL,
                                             cv2.CHAIN_APPROX_SIMPLE)
                    cnts = _cnts[1] if cv2.__version__[0] == "3" else _cnts[0]

                    # count the number of flies in each segment of the 
                    # tube using the centroid of each contour to locate
                    # the flies
                    # https://www.learnopencv.com/find-center-of-blob-centroid-using-opencv-cpp-python/
                    results = []
                    
                    for fly in fly_finder(cnts, options["tubes"][i][-1]):
                        x = fly[0] + options["tubes"][i][0]
                        results.append(which_segment(x, segments[i][1]))
                    for segment in set(results):
                        c = results.count(segment)
                        sys.stdout.write(",".join(map(str, 
                                                          (fname, 
                                                           frame_i,
                                                           i,
                                                           segment, 
                                                           c))) + "\n")
                    i += 1   
                frame_i += 1
                
    # return 0 if everything succeeded
    return 0

# does not execute main if the script is imported as a module
if __name__ == '__main__': sys.exit(main())

