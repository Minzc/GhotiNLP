#!/usr/bin/env python
import optparse
import os
import sys
from collections import namedtuple
from math import log, sqrt

# Add the parent directory into search paths so that we can import perc
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import models


alpha = 0.95 #reordering parameter
maxDis = 2

def ph(state, f, tm): 
  returnlist = []
  for i in xrange(0,len(f)):
    for j in xrange(i+1,len(f)+1):
      if(i - state.r > maxDis):
        break
      if f[i:j] in tm:
        bitstring = 0
        for k in xrange(i,j):
          bitstring += pow(2,len(f)-1-k)
          # print futureCostCalculation(bitstring, f)
        if ((bitstring & state.bitString) == 0): 
          returnlist.append((i,j,tm[f[i:j]],bitstring)) 
  return returnlist

def calculateFutureCost(bitList, futureCostTable):
  cost = 0
  for item in bitList:
    cost = cost + futureCostTable[item]
  return cost

def getFutureList(bitString):
  bitList = []
  futureList = []
  bitStr = bitString
  count = 0
  index = 0
  findZeroBit = False
  for i in xrange(0,len(f)):
    bitList.append(bitStr % 2)
    bitStr = bitStr / 2
  bitList.reverse()
  for i in range(len(bitList)):
    if bitList[i] == 0:
      if not findZeroBit:
        index = i
      findZeroBit = True
      count = count + 1
    else:
      if findZeroBit:
        futureList.append((index, count))
      findZeroBit = False
      count = 0
  if findZeroBit:
    futureList.append((index, count))
  return futureList

def futureCost(f):
  phraseCheapestTable = {}
  futureCostTable = {}
  for i in xrange(0,len(f)):
    for j in xrange(i+1,len(f)+1):
      phraseCheapestTable[i,j] = -sys.maxint
      if f[i:j] in tm:
        for phrase in tm[f[i:j]]:
          if phrase.logprob > phraseCheapestTable[i,j]:
            phraseCheapestTable[i,j] = phrase.logprob
      if phraseCheapestTable[i,j] == -sys.maxint:
        del phraseCheapestTable[i,j]
  for i in xrange(0,len(f)):
    futureCostTable[i,1] = phraseCheapestTable[i,i+1]
    for j in xrange(2,len(f)+1-i):
      if (i,i+j) in  phraseCheapestTable:
        futureCostTable[i,j] = phraseCheapestTable[i,i+j]
      else:
        futureCostTable[i,j] = -sys.maxint
      for k in xrange(1, j):
        if(((i+k,i+j) in phraseCheapestTable) and (futureCostTable[i,j] < futureCostTable[i,k] + phraseCheapestTable[i+k,i+j])):
          futureCostTable[i,j] = futureCostTable[i,k] + phraseCheapestTable[i+k,i+j]
  return futureCostTable

    
def next(phraseTuple, lm_state, p_state, length): 
  state = namedtuple("state", "e1, e2, bitString, r")
  bitstring = p_state.bitString
  e1 = None
  e2 = None
  if len(lm_state) == 1:
    e2 = (lm_state[0],)
  elif len(lm_state) == 2:
    e1 = (lm_state[0],)
    e2 = (lm_state[1],)
  for k in xrange(phraseTuple[0],phraseTuple[1]):
    bitstring = bitstring | pow(2,length-1-k)
  return state(e1,e2,bitstring,phraseTuple[1])

optparser = optparse.OptionParser()
optparser.add_option("-i", "--input", dest="input", default="data/input", help="File containing sentences to translate (default=data/input)")
optparser.add_option("-t", "--translation-model", dest="tm", default="data/tm", help="File containing translation model (default=data/tm)")
optparser.add_option("-l", "--language-model", dest="lm", default="data/lm", help="File containing ARPA-format language model (default=data/lm)")
optparser.add_option("-n", "--num_sentences", dest="num_sents", default=sys.maxint, type="int", help="Number of sentences to decode (default=no limit)")
optparser.add_option("-k", "--translations-per-phrase", dest="k", default=1, type="int", help="Limit on number of translations to consider per phrase (default=1)")
optparser.add_option("-s", "--stack-size", dest="s", default=1, type="int", help="Maximum stack size (default=1)")
optparser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False,  help="Verbose mode (default=off)")
opts = optparser.parse_args()[0]

tm = models.TM(opts.tm, opts.k)
lm = models.LM(opts.lm)
french = [tuple(line.strip().split()) for line in open(opts.input).readlines()[:opts.num_sents]]

# tm should translate unknown words as-is with probability 1
for word in set(sum(french,())):
  if (word,) not in tm:
    tm[(word,)] = [models.phrase(word, 0.0)]

count = 0
sys.stderr.write("Decoding %s...\n" % (opts.input,))
for f in french:
  # The following code implements a monotone decoding
  # algorithm (one that doesn't permute the target phrases).
  # Hence all hypotheses in stacks[i] represent translations of 
  # the first i words of the input sentence. You should generalize
  # this so that they can represent translations of *any* i words.
  hypothesis = namedtuple("hypothesis", "logprob, state, predecessor, phrase")
  state = namedtuple("state", "e1, e2, bitString, r")
  initial_state = state(None,lm.begin(),0,0)
  initial_hypothesis = hypothesis(0.0, initial_state, None, None)
  stacks = [{} for _ in f] + [{}]
  stacks[0][initial_state] = initial_hypothesis
  futureCostTable = futureCost(f)
  # print futureCostTable
  for i, stack in enumerate(stacks[:-1]):
    for h in sorted(stack.itervalues(),key=lambda h: -h.logprob)[:opts.s]: # prune
      state = h.state
      for phraseTuple in ph(state, f, tm):
        # print phraseTuple[0], phraseTuple[1]
        for phrase in phraseTuple[2]:
          bitString = phraseTuple[3]
          futureList = getFutureList(bitString)
          futurecost = calculateFutureCost(futureList, futureCostTable)
          logprob = h.logprob + phrase.logprob + log(alpha)*sqrt(abs(phraseTuple[0]-state.r)) + 2 * futurecost

          lm_state = ()
          lm_state += state.e1 if state.e1 is not None else ()
          lm_state += state.e2 if state.e2 is not None else ()

          for word in phrase.english.split():
            (lm_state, word_logprob) = lm.score(lm_state, word)
            logprob += word_logprob
          next_state = next(phraseTuple, lm_state, state, len(f))
          length = bin(next_state.bitString).count("1") 
          logprob += lm.end(lm_state) if length == len(f) else 0.0
          new_hypothesis = hypothesis(logprob, next_state, h, phrase)
          if next_state not in stacks[length] or stacks[length][next_state].logprob < logprob: # second case is recombination
            stacks[length][next_state] = new_hypothesis 
            count = count + 1
 
  winner = max(stacks[len(f)].itervalues(), key=lambda h: h.logprob)
  def extract_english(h): 
    return "" if h.predecessor is None else "%s%s " % (extract_english(h.predecessor), h.phrase.english)
    
  # print count
  # print futureCost(f)
  print extract_english(winner)

  if opts.verbose:
    def extract_tm_logprob(h):
      return 0.0 if h.predecessor is None else h.phrase.logprob + extract_tm_logprob(h.predecessor)
    tm_logprob = extract_tm_logprob(winner)
    sys.stderr.write("LM = %f, TM = %f, Total = %f\n" % 
      (winner.logprob - tm_logprob, tm_logprob, winner.logprob))
