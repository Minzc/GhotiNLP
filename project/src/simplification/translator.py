import sys, optparse
import models
import decode
import reranker_train
import rerank
import scorereranker

optparser = optparse.OptionParser()
optparser.add_option("-i", "--input", dest="input", default="data/dev/all.cn-en.cn", help="File containing sentences to translate (default=data/input)")
optparser.add_option("-e", "--eval", dest="eval", default="data/test/all.cn-en.cn", help="File containing sentences to translate (default=data/input)")
optparser.add_option("-r", "--reference", dest="reference", default="data/dev/all.cn-en.en0", help="English reference sentences")
optparser.add_option("-t", "--translation-model", dest="tm", default="data/large/phrase-table/test-filtered/rules_cnt.final.out", help="File containing translation model (default=data/tm)")
optparser.add_option("-l", "--language-model", dest="lm", default="data/lm/en.gigaword.3g.filtered.train_dev_test.arpa.gz", help="File containing ARPA-format language model (default=data/lm)")
optparser.add_option("-k", "--translations-per-phrase", dest="k", default=3, type="int", help="Limit on number of translations to consider per phrase (default=1)")
optparser.add_option("-s", "--stack-size", dest="s", default=100, type="int", help="Maximum stack size (default=1)")
optparser.add_option("-v", "--verbose", dest="verbose", action="store_true", default=False,  help="Verbose mode (default=off)")
optparser.add_option("-f", "--feedback-loop", dest="loop", default=10,  help="The number of times the weight vector loops between decoder and reranker")

opts = optparser.parse_args()[0]

lm = models.LM(opts.lm)

weights = [1, 1, 1, 1, 1]
for i in range(opts.loop):
    tm = models.TM(opts.tm, opts.k, weights[0:-1])
    nbest_list = decode.get_candidates(opts.input, tm, lm, weights, s=opts.s)
    weights = reranker_train.reranker_train(nbest_list, opts.reference)
    print weights
    results = rerank.rerank(weights, nbest_list)
    print >> sys.stderr, "BLEU SCORE: %f:" % scorereranker.score(results, opts.reference)

nbest_list = decode.get_candidates(opts.eval, tm, lm, weights)
results = rerank.rerank(weights, nbest_list)
file = open("output1", "w")
file.write("\n".join(results))
file.close()
