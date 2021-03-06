#!/usr/bin/env python
import sys, os
import random
import pickle
import numpy as np
from collections import namedtuple
from math import fabs

# Add the parent directory into search paths so that we can import perc
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import bleu


def reranker_train(nbest_candidates, refdir, epochs=5, alpha=0.04, tau=10000, xi=1000, eta=0.1):
    # initialization
    print >> sys.stderr, "Initializing training data"
    candidate = namedtuple("candidate", "sentence, features, bleu, smoothed_bleu")
    ref = [line.strip().split() for line in open(refdir)]
    nbests = []
    for n, line in enumerate(nbest_candidates):
        (i, sentence, features) = line.strip().split("|||")
        i = int(i)
        sentence = sentence.strip()
        features = np.array([float(h) for h in features.strip().split()])

        # calculate bleu score and smoothed bleu score
        stats = tuple(bleu.bleu_stats(sentence.split(), ref[i]))
        bleu_score = bleu.bleu(stats)
        smoothed_bleu_score = bleu.smoothed_bleu(stats)

        while len(nbests) <= i:
            nbests.append([])
        nbests[i].append(candidate(sentence, features, bleu_score, smoothed_bleu_score))

        if n % 2000 == 0:
            sys.stderr.write(".")
    sys.stderr.write("Done.\n")

    # set weights to default
    w = np.array([1.0/len(nbests[0][0].features)] * len(nbests[0][0].features))
    weights = np.zeros(len(nbests[0][0].features))

    # training
    random.seed()
    for i in range(epochs):
        print >> sys.stderr, "Training epoch %d:" % i
        mistakes = 0
        for nbest in nbests:
            if len(nbest) < 2:
                continue

            sample = []
            for j in range(tau):
                (s1, s2) = (nbest[k] for k in random.sample(range(len(nbest)), 2))
                if fabs(s1.smoothed_bleu - s2.smoothed_bleu) > alpha:
                    if s1.smoothed_bleu > s2.smoothed_bleu:
                        sample.append((s1, s2))
                    else:
                        sample.append((s2, s1))
                else:
                    continue

            sample.sort(key=lambda s: s[0].smoothed_bleu - s[1].smoothed_bleu, reverse=True)
            for (s1, s2) in sample[:xi]:
                if np.dot(w, s1.features) <= np.dot(w, s2.features):
                    mistakes += 1
                    w += eta * (s1.features - s2.features)  # this is vector addition!

        weights += w
        print >> sys.stderr, "Number of mistakes: %d" % mistakes

    w = weights / float(epochs)
    return w
