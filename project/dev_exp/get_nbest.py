#!/usr/bin/env python
import optparse
import os
import sys
from collections import namedtuple 
from math import log, sqrt

# Add the parent directory into search paths so that we can import perc
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import models

# Parameter constants
alpha = 0.95  #reordering parameter

optparser = optparse.OptionParser()
optparser.add_option("-i", "--input", dest="input", default="data/all.cn-en.cn", help="File containing sentences to translate (default=data/input)")
optparser.add_option("-t", "--translation-model", dest="tm", default="phrase-table/rules_cnt.final.out", help="File containing translation model (default=data/tm)")
optparser.add_option("-l", "--language-model", dest="lm", default="data/en.gigaword.3g.filtered.train_dev_test.arpa.gz", help="File containing ARPA-format language model (default=data/lm)")
optparser.add_option("-n", "--num_sentences", dest="num_sents", default=sys.maxint, type="int", help="Number of sentences to decode (default=no limit)")
optparser.add_option("-k", "--translations-per-phrase", dest="k", default=1, type="int", help="Limit on number of translations to consider per phrase (default=1)")
optparser.add_option("-s", "--stack-size", dest="s", default=1, type="int", help="Maximum stack size (default=1)")
optparser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False,  help="Verbose mode (default=off)")
opts = optparser.parse_args()[0]

tm = models.TM(opts.tm, opts.k)
weight = models.weight
lm = models.LM(opts.lm)
french = [tuple(line.strip().split()) for line in open(opts.input).readlines()[:opts.num_sents]]

# tm should translate unknown words as-is with probability 1
for word in set(sum(french,())):
  if (word,) not in tm:
    tm[(word,)] = [models.phrase(word, 0.0, 0.0, 0.0, 0.0)]


def generate_phrase_cache(f):
  cache = []
  for i in xrange(0, len(f)):
    entries = []
    bitstring = 0
    for j in xrange(i+1, len(f)+1):
      bitstring += 1 << (len(f) - j)
      if f[i:j] in tm:
        entries.append({'end': j, 'bitstring': bitstring, 'phrase': tm[f[i:j]]})
    cache.append(entries)
  return cache


def enumerate_phrases(f_cache, coverage):
  for i in xrange(0, len(f_cache)):
    bitstring = 0
    for entry in f_cache[i]:
      if (entry['bitstring'] & coverage) == 0:
        yield ((i, entry['end']), entry['bitstring'], entry['phrase'])


def precalcuate_future_cost(f):
  phraseCheapestTable = {}
  futureCostTable = {}
  for i in xrange(0,len(f)):
    for j in xrange(i+1,len(f)+1):
      if f[i:j] in tm:
        phraseCheapestTable[i,j] = -sys.maxint
        for phrase in tm[f[i:j]]:
          probability = weight[0] * phrase.logprob1 + weight[1] * phrase.logprob2 + weight[2] * phrase.logprob3 + weight[3] * phrase.logprob4 
          if probability > phraseCheapestTable[i,j]:
            phraseCheapestTable[i,j] = probability
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


def get_future_list(bitstring):
  bitList = bin(bitstring)[2:]
  futureList = []
  count = 0
  index = 0
  findZeroBit = False
  for i in range(len(bitList)):
    if bitList[i] == '0':
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


def get_future_cost(bitList, futureCostTable):
  cost = 0
  for item in bitList:
    cost = cost + futureCostTable[item]
  return cost

def extract_english(h): 
  return "" if h.predecessor is None else "%s%s " % (extract_english(h.predecessor), h.phrase.english)

results = []
sys.stderr.write("Decoding %s...\n" % (opts.input,))
for sentenceIndex, f in enumerate(french):
  # Generate cache for phrase segmentations.
  f_cache = generate_phrase_cache(f)
  # Pre-calculate future cost table
  future_cost_table = precalcuate_future_cost(f)
  # logprob = log_lmprob + log_tmprob + distortion_penalty
  # predecessor = previous hypothesis
  # lm_state = N-gram state (the last one or two words)
  # last_frange = (i, j) the range of last translated phrase in f
  # phrase = the last TM phrase object (correspondence to f[last_frange])
  # coverage = bit string representing the translation coverage on f
  # future_cost
  hypothesis = namedtuple("hypothesis", "logprob, lm_state, predecessor, last_frange, phrase, coverage, future_cost, tm_prob1, tm_prob2, tm_prob3, tm_prob4, lm_prob")
  initial_hypothesis = hypothesis(0.0, lm.begin(), None, (0, 0), None, 0, 0, 0, 0, 0, 0, 0)
  # stacks[# of covered words in f] (from 0 to |f|)
  stacks = [{} for _ in xrange(len(f) + 1)]
  # stacks[size][(lm_state, last_frange, coverage)]:
  # recombination based on (lm_state, last_frange, coverage).
  # For different hypotheses with the same tuple, keep the one with the higher logprob.
  # lm_state affects LM; last_frange affects distortion; coverage affects available choices.
  stacks[0][(lm.begin(), None, 0)] = initial_hypothesis
  for i, stack in enumerate(stacks[:-1]):
    if opts.verbose:
      print >> sys.stderr, "Stack[%d]:" % i

    # Top-k pruning
    for h in sorted(stack.itervalues(),key=lambda h: -h.logprob-h.future_cost)[:opts.s]:
      if opts.verbose:
        print >> sys.stderr, h.logprob, h.lm_state, bin(h.coverage), unicode(' '.join(f[h.last_frange[0]:h.last_frange[1]]), 'utf8'), h.future_cost

      for (f_range, delta_coverage, tm_phrases) in enumerate_phrases(f_cache, h.coverage):
        # f_range = (i, j) of the enumerated next phrase to be translated
        # delta_coverage = coverage of f_range
        # tm_phrases = TM entries corresponding to fphrase f[f_range]
        length = i + f_range[1] - f_range[0]
        coverage = h.coverage | delta_coverage
        distance = f_range[0] - h.last_frange[1]

        # TM might give us multiple candidates for a fphrase.
        for phrase in tm_phrases:
          log_tmprob1 = 0
          log_tmprob2 = 0
          log_tmprob3 = 0
          log_tmprob4 = 0

          log_lmprob = 0
          # log_tmprob and distortion
          probability = weight[0] * phrase.logprob1 + weight[1] * phrase.logprob2 + weight[2] * phrase.logprob3 + weight[3] * phrase.logprob4 
          logprob = h.logprob + probability + log(alpha)*sqrt(abs(distance))
          log_tmprob1 = h.tm_prob1 + phrase.logprob1
          log_tmprob2 = h.tm_prob2 + phrase.logprob2
          log_tmprob3 = h.tm_prob3 + phrase.logprob3
          log_tmprob4 = h.tm_prob4 + phrase.logprob4

          # log_lmprob (N-gram)
          lm_state = h.lm_state
          for word in phrase.english.split():
            (lm_state, word_logprob) = lm.score(lm_state, word)
            logprob += word_logprob
            log_lmprob += word_logprob
          # Don't forget the STOP N-gram if we just covered the whole sentence.
          logprob += lm.end(lm_state) if length == len(f) else 0.0
          log_lmprob += lm.end(lm_state) if length == len(f) else 0.0

          # Future cost.
          future_list = get_future_list(delta_coverage)
          future_cost = get_future_cost(future_list, future_cost_table)

          new_state = (lm_state, f_range, coverage)
          new_hypothesis = hypothesis(logprob, lm_state, h, f_range, phrase, coverage, future_cost, log_tmprob1, log_tmprob2, log_tmprob3, log_tmprob4, log_lmprob)
          if new_state not in stacks[length] or \
              logprob + future_cost > stacks[length][new_state].logprob + stacks[length][new_state].future_cost:  # recombination
            stacks[length][new_state] = new_hypothesis

  winner = sorted(stacks[len(f)].itervalues(), key=lambda h: h.logprob, reverse=True)[0:100]
  for i in range(len(winner)):
    print sentenceIndex,"|||",extract_english(winner[i]),"|||",winner[i].lm_prob, winner[i].tm_prob1, winner[i].tm_prob2, winner[i].tm_prob3, winner[i].tm_prob4