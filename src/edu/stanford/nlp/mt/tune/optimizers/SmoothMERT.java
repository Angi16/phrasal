package edu.stanford.nlp.mt.tune.optimizers;

import java.util.Iterator;
import java.util.List;

import edu.stanford.nlp.mt.base.FeatureValue;
import edu.stanford.nlp.mt.base.IString;
import edu.stanford.nlp.mt.base.RichTranslation;
import edu.stanford.nlp.mt.base.ScoredFeaturizedTranslation;
import edu.stanford.nlp.mt.base.Sequence;
import edu.stanford.nlp.mt.metrics.SentenceLevelMetric;
import edu.stanford.nlp.stats.ClassicCounter;
import edu.stanford.nlp.stats.Counter;
import edu.stanford.nlp.stats.Counters;

/**
 * Smooth MERT (Och 2003, Cherry and Foster 2012)
 * 
 * Optimizes: E_p_w(y|x) Loss(y) latex: \mathbb{E}_{p_\theta(y|x)} \ell (y)
 * 
 * The loss function, \ell, can be any machine translation evaluation metric 
 * that operates over individual translations such as smooth BLEU or TER.
 * 
 * The derivative of this objective is given by:
 * 
 * dL/dw_i = E_p_w(y|x) [Loss(y) * f_i(x,y)] - 
 *               E_p_w(y|x) [Loss(y)] *  E_p_w(y|x) [f_i(x,y)]
 * 
 * Latex:     \mathbb{E}_{p_\theta(y|x)} (\ell (y) f_i(x,y)) - 
 *              \mathbb{E}_{p_\theta(y|x)} \ell (y) \mathbb{E}_{p_\theta(y|x)}  f_i(x,y)
 *              
 * @author Daniel Cer 
 *
 */
public class SmoothMERT extends AbstractOnlineOptimizer {

   static public boolean VERBOSE = true;
   
	public SmoothMERT(int tuneSetSize, int expectedNumFeatures, String[] args) {
		super(tuneSetSize, expectedNumFeatures, args);
	}	

	public SmoothMERT(int tuneSetSize, int expectedNumFeatures,
			int minFeatureSegmentCount, int gamma, int xi, double nThreshold,
			double sigma, double rate, String updaterType, double L1lambda,
			String regconfig) {
		super(tuneSetSize, expectedNumFeatures, minFeatureSegmentCount, sigma, rate, updaterType, L1lambda, regconfig);
	}

   private double logZ(
         List<RichTranslation<IString, String>> translations,
         Counter<String> wts) {
       double scores[] = new double[translations.size()];
       int max_i = 0;

       Iterator<RichTranslation<IString, String>> iter = translations
           .iterator();
       for (int i = 0; iter.hasNext(); i++) {
         ScoredFeaturizedTranslation<IString, String> trans = iter.next();
         scores[i] = OptimizerUtils.scoreTranslation(wts, trans);
         if (scores[i] > scores[max_i])
           max_i = i;
       }

       double expSum = 0;
       for (int i = 0; i < scores.length; i++) {
         expSum += Math.exp(scores[i] - scores[max_i]);
       }

       return scores[max_i] + Math.log(expSum);
   }
   
   @Override
   public Counter<String> getUnregularizedGradiant(Counter<String> weights,
         Sequence<IString> source, int sourceId,
         List<RichTranslation<IString, String>> translations,
         List<Sequence<IString>> references, double[] referenceWeights,
         SentenceLevelMetric<IString, String> scoreMetric) {
      Counter<String> expectedLossF = new ClassicCounter<String>();
      Counter<String> expectedF = new ClassicCounter<String>();
      double expectedLoss = 0;
      
      double logZ = logZ(translations, weights);
      double argmaxScore = Double.NEGATIVE_INFINITY;
      double argmaxP = 0;
      double argmaxEval = 0;
      for (RichTranslation<IString,String> trans: translations) {
         double score =  OptimizerUtils.scoreTranslation(weights, trans);
         double logP = score - logZ;
         double p = Math.exp(logP);
         double eval = scoreMetric.score(sourceId, references, referenceWeights, trans.translation);
         System.err.printf("score: %.3f p: %.3f eval %.3f\n", score, p, eval);
         double Eeval = p*eval;
         expectedLoss += Eeval;
         for (FeatureValue<String> feat : trans.features) {
            double EfeatEval = Eeval*feat.value;
            double Efeat = p*feat.value;
            expectedLossF.incrementCount(feat.name, EfeatEval);
            expectedF.incrementCount(feat.name, Efeat);
         }
         
         if (score > argmaxScore) {
            argmaxScore = score;
            argmaxP = p;
            argmaxEval = eval; 
         }
      }
      Counter<String> expectedLossExpectedF = new ClassicCounter<String>(expectedF);
      Counters.multiplyInPlace(expectedLossExpectedF, expectedLoss);
      Counter<String> gradient = new ClassicCounter<String>(expectedLossF);
      Counters.subtractInPlace(gradient, expectedLossExpectedF);
      
      if (VERBOSE) {
         System.err.println("======================");
         System.err.printf("Argmax score: %.3f P: %.3f Eval: %.3f\n", argmaxScore, argmaxP, argmaxEval);
         System.err.printf("Expected Loss: %.3f\n", expectedLoss);
         
         System.err.printf("Expected Feature Values: %s\n", expectedF);
         System.err.printf("Expected Feature Values * Expected Loss: %s\n", expectedLossF);
         
         System.err.println("Gradient: ");
         System.err.println(gradient);
         System.err.println();
      }
      
      Counters.multiplyInPlace(gradient, -1);
      return gradient;
   }
}
