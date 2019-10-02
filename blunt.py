#!/usr/bin/env python

'''
Blunt

Basic video utilities for python.

Requires OpenCV <= 2.4
'''

import getopt, sys, fileinput, cv2
from os import path
from Queue import Queue
from threading import Event, Thread

### CONSTANTS
if int(cv2.__version__[0]) >= 3:
    CAP_PROP_FPS = cv2.CAP_PROP_FPS
    CAP_PROP_FRAME_COUNT = cv2.CAP_PROP_FRAME_COUNT
    CAP_PROP_POS_FRAMES = cv2.CAP_PROP_POS_FRAMES
else:
    CAP_PROP_FPS = cv2.cv.CV_CAP_PROP_FPS
    CAP_PROP_FRAME_COUNT = cv2.cv.CV_CAP_PROP_FRAME_COUNT
    CAP_PROP_POS_FRAMES = cv2.cv.CV_CAP_PROP_POS_FRAMES


### CLASSES
# Video I/O
class VideoStream(object):
    '''
    Use two threads to read a video stream, a child thread decompresses 
    the video in background and put the frame in a queue that are 
    accessible for processing in the main program.
    '''
    
    def __init__(self, fname, beginning=None, end=None, quiet=True):
        '''
        Initialize the stream with the video file name and optional 
        beginning and end timestamps.
        '''
        
        # save the input file name
        self.fname = fname
        
        # initialize the camera
        self.camera = cv2.VideoCapture(self.fname)
        
        # store the fps value
        self.fps = self.camera.get(CAP_PROP_FPS)
        
        # store the length of the video (in frames)
        self.length = self.camera.get(CAP_PROP_FRAME_COUNT)
        
        # store video dimensions
        self.width = self.camera.get(3)
        self.height = self.camera.get(4)
        
        # set the time of the first frame to be read
        self.set_beginning(beginning)
        
        # set the time of the last frame to be read
        self.set_end(end)
        
        # set the quiet parameter
        self.quiet = quiet

        # this is the number of frames that have been yielded by the read
        # method
        self.frame_number = 0
        
        # this is the cap position of the reader method
        self.cap_position = self.beginning.frame_number
        
        # the queue allow the reader method to store read frames
        self.Q = Queue(maxsize=128)
        
        # the stopped value is set when the stop method is called or
        # within the reader thread, when all the input frames has been
        # processed
        self.stopped = Event()
        
        # the released value is set when the camera has been released
        self.released = Event()
        
        # this is the reader thread, ###it is a daemon thread
        self.t = Thread(target=self.reader, args=())
        #self.t.daemon = True
    
    def __iter__(self):
        return self

    def next(self):
        frame = self.read()
        if frame is None:
            raise StopIteration
        return frame
        
    def set_beginning(self, timestamp=None):
        if timestamp is None: timestamp = "0:0:0"
        self.beginning = VideoTime(timestamp, self.fps)
        self.camera.set(CAP_PROP_POS_FRAMES, 
                        self.beginning.frame_number)
        
    def set_end(self, timestamp=None):
        if timestamp is None:
            self.end = frame_videotime(self.length, self.fps)
        else:
            self.end = VideoTime(timestamp, self.fps)
    
    def running(self):
        return not self.stopped.is_set()
        
    def start(self):
        self.t.start()
    
    def stop(self):
        self.stopped.set()
        self.t.join()
        
    def read(self):
        while not self.Q.qsize():
            if not self.t.is_alive(): 
                return
            if self.stopped.is_set(): 
                return
        self.frame_number += 1
        return self.Q.get()
        
    def before(self):
        return self.cap_position < self.beginning.frame_number
        
    def after(self):
        return ( self.end is not None and
                 self.cap_position >= self.end.frame_number )
    
    def in_range(self):
        return not (self.before() and self.after())
    
    def reader(self):
        while not self.stopped.is_set():
            if not self.Q.full():

                # the cap reached the video's end
                if self.cap_position >= self.end.frame_number:
                    self.stopped.set()
                    break

                # get the next frame's index
                self.cap_position = self.camera.get(1)
                
                # the cap exceeded the portion of the video to be decoded
                if self.after():
                    self.stopped.set()
                    break          

                # grab the next frame
                grabbed = self.camera.grab()

                # sometimes, the frame is not grabbed... if this happens too
                # often, consider working with another video format.
                while not grabbed:
                    if not self.quiet:
                        sys.stderr.write(
                            ("Video file '{}': error while trying to grab"
                             " frame number {}... trying again\n").format(
                                self.fname, self.cap_position))
                    grabbed = self.camera.grab()

                # to circumvent possible issue when trying to set the cap 
                # with some compressed stream, the video is decoded and the
                # frames skipped until it reaches self.camera.beginning, where
                # they start to be added to the queue (self.Q)               
                (grabbed, frame) = self.camera.retrieve()
                if not self.before(): self.Q.put(frame)
        self.camera.release()  
        self.released.set()

# To read from a video
#------------------------------------------------------------------------
# > with VideoInput(fname[, beginning=None][, end=None]) as video:
# >     for frame in video:
# >         ...process the frame...
#------------------------------------------------------------------------
class VideoInput(VideoStream):  
    def __enter__(self):
        self.start()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.stopped.is_set():
            self.stop()
        
class VideoWriter(object):
    '''
    Threaded video encoding. Images are put in a queue and encoded in
    a background process.
    '''
    
    def __init__(self, fname, fourcc, w, h, fps, color=True):
        self.fname = fname
        if cv2.__version__[0] == "3":
            self.fourcc = cv2.VideoWriter_fourcc(*fourcc)
        else:
            self.fourcc = cv2.VideoWriter_fourcc(*fourcc)
        self.dimension = (w, h)
        self.fps = fps
        self.color = color
        self.vw = cv2.VideoWriter(fname, self.fourcc, self.fps, self.dimension, self.color)
        self.Q = Queue(maxsize=128)
        self.stopped = Event()
        self.t = Thread(target=self.writer, args=())
        #self.t.daemon = True
        self.frame_number = 0
    
    def running(self):
        return not self.stopped.is_set()
    
    def start(self):
        self.t.start()
    
    def stop(self):
        self.stopped.set()
        self.t.join()
    
    def write(self, frame):
        if self.t.is_alive():
            while self.Q.full(): pass
            self.Q.put(frame)
        else:
            raise IOError("The writer is not ready")
        
    def writer(self):
        while self.running(): 
            if not self.Q.empty():
                frame = self.Q.get()
                self.frame_number += 1 
                self.vw.write(frame)
        while not self.Q.empty():
            frame = self.Q.get()
            self.frame_number += 1 
            self.vw.write(frame)        
        self.vw.release()

# To write in a video
#------------------------------------------------------------------------
# > with VideoOutput(fname, fourcc, w, h, fps[, color=True]) as video:
# >     for frame in [...]:
# >         video.write(frame)
#------------------------------------------------------------------------        
class VideoOutput(VideoWriter):  
    def __enter__(self):
        self.start()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        
class VideoCropper(VideoWriter):
    '''
    Similar to the VideoWriter, except that it crops the input images 
    before writing it.
    '''
    
    def __init__(self, fname, fourcc, x, y, w, h, fps, color=True):
        VideoWriter.__init__(self, fname, fourcc, w, h, fps, color)
        self.x, self.y = x, y
        self.w, self.h = self.dimension
        
    def write(self, frame):
        if self.t.is_alive():
            while self.Q.full(): pass
            self.Q.put(frame[self.y:self.y+self.h, self.x:self.x+self.w])
        else:
            raise IOError("The writer is not ready")
        
# Timestamp
class TimeStamp(object):
    '''
    Store a time stamp value.
    '''
    
    def __init__(self, e):
        '''
        Init with a timestamp expression (HH:MM:SS.mmm).
        '''
        
        if type(e) is TimeStamp: e = str(e)
        elif type(e) is VideoTime: e = str(e).split(" ")[0]
        elif type(e) is not str:
            raise TypeError('{} object init from a str, a TimeStamp'
                            ' or a VideoTime.'.format(type(self).__name__))
        hours, minutes, seconds = map(float, e.split(":"))
        self.hours = hours + minutes/60 + seconds/3600
        self.minutes = hours*60 + minutes + seconds/60
        self.seconds = hours*3600 + minutes*60 + seconds
    
    def __str__(self):
        hours = int(self.hours)
        minutes = int(self.minutes) - hours*60
        seconds = self.seconds - hours*3600 - minutes*60
        return "{}:{:02d}:{:02.3f}".format(hours, minutes, seconds)
    
    def __add__(self, x):
        x = self._compatible(x)
        return seconds_timestamp(self.seconds + x.seconds)
    
    def __sub__(self, x):
        x = self._compatible(x)
        return seconds_timestamp(self.seconds - x.seconds)
    
    def _compatible(self, x):
        if type(self) != type(x):
            raise TypeError('only a TimeStamp can be added to another'
                            ' TimeStamp.')
        return x    

class VideoTime(TimeStamp):
    '''
    Store a time stamp and deduce the corresponding frame.
    '''
    
    def __init__(self, e, fps):
        '''
        Init with a timestamp (HH:MM:SS.mmm) and the a frame per second
        value.
        '''
        
        TimeStamp.__init__(self, e)
        self.fps = fps
        self.frame_number = int(self.seconds * self.fps) + 1
    
    def __str__(self):
        return TimeStamp.__str__(self) + " ({} frame/s)".format(self.fps)
    
    def __add__(self, x):
        x = self._compatible(x)
        return VideoTime(seconds_timestamp(self.seconds + x.seconds), self.fps)
    
    def __sub__(self, x):
        x = self._compatible(x)
        return VideoTime(seconds_timestamp(self.seconds - x.seconds), self.fps)
    
    def _compatible(self, x):
        if type(self) != type(x):
            raise TypeError('only a VideoTime can be added to another'
                            ' VideoTime.')
        if self.fps != x.fps:
            raise ValueError('VideoTimes does not have the same fps'
                             ' value.')
        return x
        
### FUNCTIONS
def open_video(*args, **kwargs):
    try:
        mode = kwargs["mode"]
        del kwargs["mode"]
    except KeyError:
        if len(args) > 1:
            mode = args[1]
            args = (args[0],) + args[2:]
        else: mode = "r"
    if mode == "r":
        return VideoInput(*args, **kwargs)
    elif mode == "w":
        return VideoOutput(*args, **kwargs)
    else:
        raise ValueError("mode string must be 'r' or 'w',"
                         " not '{}'".format(mode))
                         
def seconds_timestamp(seconds):
    '''
    Returns the corresponding TimeStamp to a given number of seconds.
    '''
    
    hours = int(seconds/3600)
    minutes = int(seconds/60) - hours*60
    seconds = seconds - hours*3600 - minutes*60
    return TimeStamp("{}:{}:{}".format(hours, minutes, seconds))
        
def frame_videotime(frame_number, fps):
    '''
    Takes a frame number and fps value in argument, returns the
    corresponding VideoTime instance.
    '''
    
    t = VideoTime("0:0:0", fps)
    t.seconds = frame_number / float(fps)
    t.minutes = t.seconds / 60
    t.hours = t.minutes / 60
    t.frame_number = frame_number
    return t
    