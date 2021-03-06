import sys, codecs, optparse, os
import math
from heapq import heappush, heappop

optparser = optparse.OptionParser()
optparser.add_option("-c", "--unigramcounts", dest='counts1w', default=os.path.join('data', 'count_1w.txt'), help="unigram counts")
optparser.add_option("-b", "--bigramcounts", dest='counts2w', default=os.path.join('data', 'count_2w.txt'), help="bigram counts")
optparser.add_option("-i", "--inputfile", dest="input", default=os.path.join('data', 'input'), help="input file to segment")
(opts, _) = optparser.parse_args()

class BiPdist(dict):
    "A probability distribution estimated from counts in datafile."
    
    def __init__(self, filename, sep='\t', N=None):
	self.maxlen = 0
        for line in file(filename):
            (key, freq) = line.split(sep)
            (word1,word2)=key.split()
            try:
                utf8key1 = unicode(word1, 'utf-8')
                utf8key2 = unicode(word2, 'utf-8')
            except:
                raise ValueError("Unexpected error %s" % (sys.exc_info()[0]))
            self[(utf8key1,utf8key2)] = self.get((utf8key1,utf8key2), 0) + int(freq)
	    self.maxlen = max(len(utf8key1), self.maxlen)
	    self.maxlen = max(len(utf8key2), self.maxlen)
        self.N = float(N or sum(self.itervalues()))

    def __call__(self, key1, key2, pw1):
        if (key1,key2) in self: return (float(self[(key1,key2)])/float(self.N))/pw1(key1)
        else: return None

class UniPdist(dict):
    "A probability distribution estimated from counts in datafile."

    def __init__(self, filename, sep='\t', N=None, missingfn=None):
        self.maxlen = 0 
        for line in file(filename):
            (key, freq) = line.split(sep)
            try:
                utf8key = unicode(key, 'utf-8')
            except:
                raise ValueError("Unexpected error %s" % (sys.exc_info()[0]))
            self[utf8key] = self.get(utf8key, 0) + int(freq)
            self.maxlen = max(len(utf8key), self.maxlen)
        self.N = float(N or sum(self.itervalues()))
        self.missingfn = missingfn or (lambda k, N: 1./N)

    def __call__(self, key):
        if key in self: return float(self[key])/float(self.N)
        #else: return self.missingfn(key, self.N)
        elif len(key) == 1: return self.missingfn(key, self.N)
        else: return None

class Segmenter():
    def __init__(self, pw1, pw2,maxlen):
        self.pw1 = pw1
	self.pw2 = pw2
        self.maxlen = maxlen

    def segment(self, input):
        self.chart = [None for i in range(len(input))]
        self.heap = []
        self.ans = []

        # Initialize the heap
        for i in range(min(len(input), self.maxlen)):
            word = input[0: i + 1]
            if self.pw1(word) is not None:
                heappush(self.heap, (0, math.log(self.pw1(word)), word, None))

        # Iteratively fill in chart[i] for all i
        while self.heap:
            entry = heappop(self.heap)
            endindex =  entry[0] + len(entry[2]) - 1

            if self.chart[endindex] is not None:
                if entry[1] > self.chart[endindex][1]:
                    self.chart[endindex] = entry
                else:
                    continue
            else:
                self.chart[endindex] = entry

            for i in range(min(len(input) - 1 - endindex, self.maxlen)):
                newword = input[endindex + 1 : endindex + 2 + i]
                if self.pw1(newword) is not None:
		    if self.pw2(entry[2],newword,self.pw1) is not None:
			newentry = (endindex + 1, entry[1] + math.log(self.pw2(entry[2],newword,self.pw1)), newword, entry)
		    else:
                    	newentry = (endindex + 1, entry[1] + math.log(self.pw1(newword)), newword, entry)
                    if not newentry in self.heap:
                        heappush(self.heap, newentry)

        # Get the best segmentation
        entry = self.chart[len(input) - 1]
        while entry is not None:
            self.ans = [entry[2]] + self.ans
            entry = entry[3]

        return self.ans

Pw1  = UniPdist(opts.counts1w)
Pw2 = BiPdist(opts.counts2w)
seg = Segmenter(Pw1,Pw2,max(Pw1.maxlen,Pw2.maxlen))

old = sys.stdout
sys.stdout = codecs.lookup('utf-8')[-1](sys.stdout)

with open(opts.input) as f:
    for line in f:
        utf8line = unicode(line.strip(), 'utf-8')
        output = seg.segment(utf8line)
        print " ".join(output)
sys.stdout = old
