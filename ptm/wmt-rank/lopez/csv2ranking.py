#!/usr/bin/env python
#
# Converts the output of ans2csv.sh to a csv with a global ranking.
#
# The global ranking is computing according to the Minimum Feedback
# Arc Set solver described by Lopez (2012).
#
#
import sys
import csv
import os
from collections import namedtuple,defaultdict,Counter
from argparse import ArgumentParser
from csv import DictReader

# pip install BitVector
from BitVector import BitVector

import mfas_solver

# Output format
RankRow = namedtuple('RankRow', 'src_id sys_id rank')

class Ranking:
    """ Semantics are the relation sysA "better than" sysB, except when
        rank == 0, which indicates equality.
    """
    def rank_to_int(self, rank):
        """ Convert ans2csv.sh ranking values to __cmp__ values.
             a<b indicates that a is better than b.
        """
        if rank == '<':
            return -1
        elif rank == '>':
            return 1
        elif rank == '=':
            return 0
        else:
            raise RuntimeError('Invalid ranking: ' + str(rank))
        
    def __init__(self, src_id, sys1_id, sys2_id, rank):
        self.src_id = int(src_id)
        sys1_id = sys1_id
        sys2_id = sys2_id
        self.rank = self.rank_to_int(rank)
        if self.rank < 0:
            # A is better than B
            self.sysA = sys1_id
            self.sysB = sys2_id
            self.rank *= -1
        else:
            # B is better than or equal to A
            self.sysA = sys2_id
            self.sysB = sys1_id

    def __str__(self):
        return '[src:%d sys1:%s sys2:%s rank:%d]' % (self.src_id,
                                                         self.sysA,
                                                         self.sysB,
                                                         self.rank)

def parse_answer_file(answer_file):
    """
    Returns the following data structures:
      segmentId -> list of rankings

    Args:
    Returns:
    Raises:
    """
    src2rank = defaultdict(list)
    with open(answer_file) as infile:
        for i,row in enumerate(DictReader(infile)):
            ranking = Ranking(row.get('segmentId'),
                              row.get('system1'),
                              row.get('system2'),
                              row.get('cmp'))
            src2rank[ranking.src_id].append(ranking)
        sys.stderr.write('Read: %d rows%s' % (i, os.linesep))
    return src2rank


def uncovered(bv):
    """ Uncovered bits in a coverage set.
    """
    return [i for i in xrange(len(bv)) if bv[i] == 0]


def run_lopez_mfas_solver(di_edges, vertices):
    """ Ranks the targets according to the MFAS
    algorithm of Lopez (2012). 

    Args:
      vertices -- a list of vertex labels
      di_edges -- dictionary of weighted edges
    Returns:
      ranking -- ranking of vertices input list
      tie_with_prev -- True if the corresponding index in ranking
                       is equal to its predecessor.
    Raises:
    """
    goal = BitVector(bitlist=[1]*len(vertices))
    initial_state = BitVector(intVal=0,size=len(vertices))
    hypothesis = namedtuple("hypothesis", "cost, state, predecessor, vertex")
    initial_hypothesis = hypothesis(0, initial_state, None, None)
    agenda = {}
    agenda[initial_state] = initial_hypothesis

    while len(agenda) > 0:
        h = sorted(agenda.itervalues(), key=lambda h:h.cost)[0]
        if h.state == goal:
            break
        del agenda[h.state]
        print str(h.state),h.cost
        print uncovered(h.state)
        for u in uncovered(h.state):
            # Append u to create new hypothesis
            new_state = BitVector(intVal=int(h.state), size=len(vertices))
            new_state[u] = 1
            u_id = vertices[u]
            added_cost = 0
            # Sum up costs of outgoing edges from u
            print ' ',uncovered(new_state)
            for v in uncovered(new_state):
                uv_edge = (u_id, vertices[v])
                if uv_edge in di_edges:
                    added_cost += di_edges[uv_edge]
            new_cost = h.cost + added_cost
            if new_state not in agenda or agenda[new_state].cost > new_cost:
                agenda[new_state] = hypothesis(new_cost, new_state, h, u_id)
        
    # h is the goal. Extract the 1-best ranking.
    ranking = []
    while h.vertex:
        ranking.append(h.vertex)
        h = h.predecessor

    return ranking


def make_rows(id_list, tie_with_prev):
    """ Converts the sorted id list to a list
    of RankedRow namedtuples for output.

    Rankings are 1-indexed

    Args:
    Returns:
    Raises:
    """
    row_list = []
    last_rank = 0
    for i,sys_id in enumerate(id_list):
        rank = last_rank if tie_with_prev[i] else i + 1
        row_list.append(RankRow(src_id=None,
                                sys_id=sys_id,
                                rank=rank))
        last_rank = rank
    return row_list


def mark_ties(ranking, edges):
    """ TODO(spenceg): This is naive! Transitivity
    is not checked.

    Args:
    Returns:
    Raises:
    """
    tie_with_prev = [False]*len(ranking)
    for i in xrange(1,len(ranking)):
        prev_v = ranking[i-1]
        v = ranking[i]
        if (prev_v,v) in edges and edges[(prev_v,v)] == 0:
            tie_with_prev[i] = True
    return tie_with_prev


def sort_tgts(ranking_list):
    """ Use the ranking list to build a total ordering
    of the ranked translations (indicated by Ranking.sys{1,2}_id

    Args:
    Returns:
    Raises:
    """
    # Aggregate ranking counts
    di_edges = Counter()
    eq_edges = Counter()
    edge_counts = Counter()
    vertices = set()
    for ranking in ranking_list:
#        print str(ranking)
        vertices.add(ranking.sysA)
        vertices.add(ranking.sysB)
        edge = (ranking.sysA,ranking.sysB)
        edge_counts[edge] += 1
        if ranking.rank == 0:
            eq_edges[edge] += 1
        else:
            di_edges[edge] += 1

    # SPECIAL CASE: Equality
    # TODO(spenceg): A. Lopez discarded this data as a pre-processing
    # step. That is clearly bad since a single pairwise ranked judgment could
    # subsume all equality judgments.
    # Do naive approach and assert equality if equality is the majority
    # pairwise ranking
    for (a,b),n_eq in eq_edges.iteritems():
        n_eq += eq_edges[(b,a)]
        total = edge_counts[(a,b)] + edge_counts[(b,a)]
        perc_eq = float(n_eq) / float(total)
        if perc_eq >= 0.5:
            del di_edges[(a,b)]
            del di_edges[(b,a)]
        #if not (a,b) in di_edges:
        #    di_edges[(a,b)] = 0
        #if not (b,a) in di_edges:
        #    di_edges[(a,b)] = 0

    # Filter edges by only allowing one directed edge between
    # vertices. Edge weights are non-negative, and indicate
    # victories.
    tournament = Counter()
    for (a,b) in di_edges.keys():
        ab_cost = di_edges[(a,b)]
        assert ab_cost >= 0
        if (b,a) in di_edges:
            ba_cost = di_edges[(b,a)]
            cost_diff = ab_cost - ba_cost
            if cost_diff > 0:
                tournament[(a,b)] = cost_diff
            elif cost_diff < 0:
                tournament[(b,a)] = -1 * cost_diff
        else:
            tournament[(a,b)] = ab_cost
            
    # Generate the ranking
    vertices = list(vertices)
    #vertices = run_lopez_mfas_solver(tournament, vertices)
    ranking = mfas_solver.lopez_solver(tournament, vertices)

    # Sanity check
    assert len(ranking) == len(vertices)

    # Return a vector of Booleans identifying if
    # the corresponding vertex is tied with the previous vertex.
    # This is naive (and wrong) since transitivity cannot be asserted
    # from the rankings.
    tie_with_prev = mark_ties(ranking, di_edges)
    
    return make_rows(ranking, tie_with_prev)


def rank(answer_file):
    """ Reads the input file and applies ranking. Results
    are printed to stdout.

    Args:
    Returns:
    Raises:
    """
    # Build data structures
    src2rank = parse_answer_file(answer_file)
    
    # Iterate over each source sentence and rank
    # Write to stdout
    write_header = True
    csv_out = csv.writer(sys.stdout)
    for src_id in sorted(src2rank.keys()):
        row_list = sort_tgts(src2rank[src_id])
        for row in row_list:
            if write_header:
                csv_out.writerow(list(row._fields))
                write_header = False
            # sort_tgts does not set the src_id field
            row = row._replace(src_id=src_id)
            columns = [x for x in row._asdict().itervalues()]
            csv_out.writerow(columns)

def main():
    desc='Converts the output of wmtformat.py to a global ranking using the algorithm of Lopez (2012).'
    parser = ArgumentParser(description=desc)
    parser.add_argument('answer_csv',
                        help='Output of wmtformat.py')
    args = parser.parse_args()

    rank(args.answer_csv)

if __name__ == '__main__':
    main()
