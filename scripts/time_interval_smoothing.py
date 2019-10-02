#!/usr/bin/env python

'''
USAGE
    time_interval_smoothing.py [interval|peak] START:END [OPTION] [FILE...]

DESCRIPTION
    Performs transformation on an episode track.
        interval   Define a frame size and report the consensus episode for each
                    frame of the track.
        peak       Merge close peaks of the same episodes to redefine larger 
                    bouts.
        START:END  Start time and end time.
    
OPTIONS
    -b, --baseline=STR
        For peak detection and merging, define the baseline.
    -c, --consensus=[level|longest|maximum]
        For interval mode, consensus is the way which episode is chosen to
        represent each frame.
    -h, --header
        Input has header, ignore the first line.
    -i, --interval=INT
        Interval size.
    -l, --levels=STR[:STR...]
        For interval mode and level consensus, define the importance level of
        the episode. The most important episode will found in a given time frame 
        will represent the whole time frame.
    --help
        Display this message

'''

import getopt, sys, fileinput
from os import path
from functools import partial

class Options(dict):

    def __init__(self, argv):
        
        # set default
        self.set_default()
        
        # handle options with getopt
        if "--help" not in argv:
            self["mode"] = argv.pop(1)
            if self["mode"] not in ("interval", "peak"):
                raise getopt.GetoptError("mode must be either 'interval' or 'peak'")
            self["start"], self["end"] = map(float, argv.pop(1).split(":"))
        try:
            opts, args = getopt.getopt(argv[1:], "b:c:hi:l:t:", 
                                                 ['baseline='
                                                  'consensus=',
                                                  'header',
                                                  'interval=', 
                                                  'levels=', 
                                                  'help'])
        except getopt.GetoptError, e:
            sys.stderr.write(str(e) + '\n\n' + __doc__)
            sys.exit(1)

        for o, a in opts:
            if o == '--help':
                sys.stdout.write(__doc__)
                sys.exit(0)
            elif o == '-b':
                self['baseline'] = a
            elif o in ('-c', '--consensus'):
                self['consensus'] = a
            elif o == '-h':
                self['header'] = True
            elif o == '-i':
                self['interval'] = float(a)
            elif o in ('-l', '--levels'):
                self['levels'] = a.split(":")
            elif o == '-t':
                self['time_threshold'] = float(a)

        self.args = args
    
        if self["mode"] == "peak" and self["baseline"] is None:
            raise getopt.GetoptError("you must define --baseline in mode 'peak'")
        if self["mode"] == "interval" and self["interval"] is None:
            raise getopt.GetoptError("you must define -i in mode 'interval'")
        if self["mode"] == "interval":
            if self["consensus"] not in ("levels", "longest", "maximum"):
                raise getopt.GetoptError(
                 "consensus must be either 'levels', 'longest' or 'maximum'")
            elif self["consensus"] == "levels" and not self["levels"]:
                raise getopt.GeneratorExit(
                 "you must define values for --levels")
    
    def set_default(self):
    
        # default parameter value
        self['baseline'] = None
        self['consensus'] = "longest"
        self['header'] = False
        self['interval'] = None
        self['levels'] = []
        self['time_threshold'] = 0

class Episode(object):
    
    def __init__(self, name, start, end):
        self.name = name
        self.start = start
        self.end = end
        self.duration = self.end - self.start
        
    def __repr__(self):
        s = "Episode: '{}' {}-{}".format(self.name, self.start, self.end)
        return s
        
    def values(self):
        return (self.name, self.start, self.end)
    
def read_activity_tracking(f, start, end, header=False):
    
    if header: f.readline()
    line0 = f.readline()
    t0, x0 = map(lambda x: x.strip(), line0.split())
    t0 = float(t0)
    for line1 in f:
        t1, x1 = map(lambda x: x.strip(), line1.split())
        t1 = float(t1)
        if t1 < start: continue
        elif t0 < start: t0 = start
        yield Episode(x0, t0, t1)
        t0, x0 = t1, x1
    yield Episode(x0, float(t0), end)

def episode_counter(episodes, start, end, merge=False):
    '''
    Return the longer episode that occured within start and end. If merge
    is true, sum the times for episodes of the same name.
    '''
    
    if merge:
        d = {}
        for episode in episodes:
            if start < episode.end or end > episode.start:
                a = start if episode.start < start else episode.start
                b = end if episode.end > end else episode.end
                duration = b-a
                try: d[episode.name] += duration
                except KeyError: d[episode.name] = duration
        longest = max(( (k, d[k]) for k in d ), key=lambda x: x[1] )[0]
        return Episode(longest, start, end)
    longest = (None, 0)
    for episode in episodes:
        a = start if episode.start < start else episode.start
        b = end if episode.end > end else episode.end
        duration = b-a
        if longest[1] < duration:
            longest = (episode, duration)
    return Episode(longest[0].name, start, end)

def split_episode(episode, start, end, interval):
    if episode.end <= start: return []
    elif episode.start < start:
        return split_episode(Episode(episode.name, start, episode.end), start, end, interval)
    elif episode.start >= start+interval:
        return split_episode(episode, start+interval, end, interval)
    elif episode.end <= start+interval:
        return [Episode(episode.name, episode.start, episode.end)]
    else:
        return [Episode(episode.name, episode.start, start+interval)] + split_episode(Episode(episode.name, start+interval, episode.end), start+interval, end, interval)

def find_longest_episode(a):
    longest = None
    for x in a:
        if longest is None or longest.duration < x.duration:
            longest = x
    return longest.name if a else None
    
def find_highest_episode(a, levels=[]):
    highest = None
    for x in a:
        if highest is None or levels.index(highest) < levels.index(x.name):
            highest = x.name
    return highest    

def find_maximum(a):
    return max(( float(x.name) for x in a ))
    
def consensus_episode(tracking, start, end, interval, levels=[], consensus="longest"):
    
    consensus = { "levels" :  partial(find_highest_episode, levels=levels),
                  "longest": find_longest_episode,
                  "maximum": find_maximum
                  }[consensus]
    frame = []
    i = start
    
    try:
        episode = tracking.next()
    except StopIteration:
        yield []
    
    while True:
        if episode.end > start:
            if episode.start < start:
                episode = Episode(episode.name, start, episode.end)
            if episode.end > end:
                episode = Episode(episode.name, episode.start, end)
            start = episode.start - episode.start%interval
            if start == end: break
            episodes = split_episode(episode, start, end, interval)
            frame.append(episodes.pop(0))
            for episode in episodes:                
                yield Episode(consensus(frame), start, start+interval)
                frame = [episode]
                start += interval
            if episode.end == start+interval:
                yield Episode(consensus(frame), start, start+interval)
                frame = []
        if start == end: break
        try:
            episode = tracking.next()
        except StopIteration:
            break
    if frame:
        yield Episode(consensus(frame), start, start+interval)

def main(argv=sys.argv):
    
    # read options and remove options strings from argv (avoid option 
    # names and arguments to be handled as file names by
    # fileinput.input().
    options = Options(argv)
    sys.argv[1:] = options.args
    
    # input
    tracking = read_activity_tracking(fileinput.input(),
                                      options['start'],
                                      options['end'],
                                      options['header'])
    
    # interval mode
    if options["mode"] == "interval":
        if options["consensus"] == "levels":
            episodes = consensus_episode(tracking, 
                                      options['start'], 
                                      options['end'], 
                                      options['interval'], 
                                      consensus="levels",
                                      levels=options['levels'])
        elif options["consensus"] == "longest":
            episodes = consensus_episode(tracking, 
                                      options['start'], 
                                      options['end'], 
                                      options['interval'], 
                                      consensus="longest")
        elif options["consensus"] == "maximum":
            episodes = consensus_episode(tracking, 
                                      options['start'], 
                                      options['end'], 
                                      options['interval'], 
                                      consensus="maximum")            
        
    # peak mode
    if options["mode"] == "peak":
        pass
    
    # read episodes and merge the same
    try: episode0 = episodes.next()
    except StopIteration: return 0
    buffered_lines, buffer_size = [], 128
    for episode1 in episodes:
        if episode0.name == episode1.name:
            episode0 = Episode(episode0.name, episode0.start, episode1.end)
        else:
            line = "{}\t{}\t{}\n".format(*episode0.values())
            buffered_lines.append(line)
            if len(buffered_lines) == buffer_size:
                sys.stdout.writelines(buffered_lines)
                sys.stdout.flush()
                buffered_lines = []
            episode0 = episode1
    if episode0.name == episode1.name:
        line = "{}\t{}\t{}\n".format(*episode0.values())
    else:
        line = "{}\t{}\t{}\n".format(*episode1.values())
    buffered_lines.append(line)        
    sys.stdout.writelines(buffered_lines)
    sys.stdout.flush()    

    # return 0 if everything succeeded
    return 0

# does not execute main if the script is imported as a module
if __name__ == '__main__': sys.exit(main())

