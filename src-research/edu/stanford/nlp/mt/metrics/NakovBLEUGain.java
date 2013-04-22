package edu.stanford.nlp.mt.metrics;

import java.util.List;

import edu.stanford.nlp.mt.base.Sequence;

/**
 * Extension to Lin and Och (2004) described by Nakov et al. (2012) and evaluated
 * by Kevin Gimpel in the addendum to his NAACL 2012 conference paper:
 * 
 * http://ttic.uchicago.edu/~kgimpel/papers/gimpel+smith.naacl12.addendum.pdf
 * 
 * NOTE: This metric returns a pseudo-percentage in the range [0,100.0], i.e.,
 * 100 * BLEU.
 * 
 * @author Spence Green
 *
 * @param <TK>
 * @param <FV>
 */
public class NakovBLEUGain<TK,FV> implements SentenceLevelMetric<TK, FV> {

  private static final int DEFAULT_ORDER = 4;

  private final int order;

  public NakovBLEUGain() {
    this(DEFAULT_ORDER);
  }

  public NakovBLEUGain(int order) {
    this.order = order;
  }

  @Override
  public double score(int sourceId, List<Sequence<TK>> references,
      Sequence<TK> translation) {
    return 100.0 * BLEUMetric.computeLocalSmoothScore(translation, references, order, true);
  }

  @Override
  public void update(int sourceId, List<Sequence<TK>> references,
      Sequence<TK> translation) {
  }

  @Override
  public boolean isThreadsafe() {
    return true;
  }
}
