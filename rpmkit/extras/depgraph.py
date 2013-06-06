#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from rpmkit.memoize import memoize
from itertools import count

import rpmkit.rpmutils as RU
import rpmkit.utils as U

import logging
import networkx as NX
import networkx.readwrite.json_graph as JS


def _make_dependency_graph_with_nx(root, reversed=True, rreqs=None):
    """
    Make RPM dependency graph with using Networkx.DiGraph for given root.

    :param root: RPM Database root dir
    :param reversed: Resolve reversed dependency from required to requires
    :param rreqs: A dict represents RPM dependencies;
        {x: [package_requires_x]} or {x: [package_required_by_x]}.

    :return: networkx.DiGraph instance
    """
    G = NX.DiGraph()

    if rreqs is None:
        rreqs = RU.make_requires_dict(root, reversed) 

    G.add_nodes_from(rreqs.keys())
    for k, vs in rreqs.iteritems():
        G.add_edges_from([(k, v) for v in vs])

    return G


make_dependency_graph_with_nx = memoize(_make_dependency_graph_with_nx)


def list_strongly_connected_rpms(root, limit=1, reversed=True, rreqs=None):
    """
    :param root: RPM Database root dir
    :param limit: Results of which length of list of RPM names less than this
        ``limit`` + 1 will be ignored.
    :param reversed: Resolve reversed dependency from required to requires
    :param rreqs: A dict represents RPM dependencies;
        {x: [package_requires_x]} or {x: [package_required_by_x]}.

    :return: [[rpm_name]]; Each list represents strongly connected RPMs.
    """
    G = make_dependency_graph_with_nx(root, reversed, rreqs)
    return [xs for xs in NX.strongly_connected_components(G) if len(xs) > 1]


def list_rpms_having_cyclic_dependencies(root, reversed=True, rreqs=None):
    """
    :param root: RPM Database root dir
    :param reversed: Resolve reversed dependency from required to requires
    :param rreqs: A dict represents RPM dependencies;
        {x: [package_requires_x]} or {x: [package_required_by_x]}.

    :return: [[rpm_name]]; Each list represents strongly connected RPMs.
    """
    G = make_dependency_graph_with_nx(root, reversed, rreqs)
    return NX.simple_cycles(G)


def _degenerate_node(nodes, sep='|'):
    """
    :param nodes: List of strongly connected nodes :: [str]
    :return: Degenerated node :: str
    """
    return sep.join(nodes)


def _degenerate_nodes(G, nodes, reqs, rreqs, sep='|'):
    """
    For each node, remove edges from/to that node and the node from the graph
    ``G`` and then add newly 'degenerated' node and relevant edges again.

    :param G: Dependency graph of nodes
    :param nodes: Node (name) list
    """
    for node in nodes:
        G.remove_edges_from([(node, p) for p in rreqs.get(node, [])])
        G.remove_edges_from([(r, node) for r in reqs.get(node, [])])

    G.remove_nodes_from(nodes)

    dnode = _degenerate_node(nodes)
    G.add_node(dnode)

    dnode_rreqs = U.uconcat([p for p in rreqs.get(node, []) if p not in nodes]
                            for node in nodes)
    dnode_reqs = U.uconcat([r for r in reqs.get(node, []) if r not in nodes]
                           for node in nodes)

    if dnode_rreqs:
        G.add_edges_from([(dnode, p) for p in dnode_rreqs])

    if dnode_reqs:
        G.add_edges_from([(r, dnode) for r in dnode_reqs])

    return G


def list_root_nodes(G):
    """
    List root nodes of given graph ``G``.

    Alternative: [n for n,d in G.in_degree().items() if d == 0]

    :param G: networkx.DiGraph instance
    """
    return [n for n in G if not G.predecessors(n) and G.successors(n)]


def list_standalone_nodes(G):
    """
    List standalone nodes don't have any edges and not connected to others.

    :param G: networkx.DiGraph instance
    """
    return [n for n in G if not G.predecessors(n) and not G.successors(n)]


def make_rpm_dependencies_dag(root, reqs=None, rreqs=None):
    """
    Make direct acyclic graph from RPM dependencies.

    see also:

    * http://en.wikipedia.org/wiki/Directed_acyclic_graph
    * http://en.wikipedia.org/wiki/Strongly_connected_component

    :param root: RPM Database root dir
    :param rreqs: A dict represents RPM dependencies;
        {x: [package_requires_x]} or {x: [package_required_by_x]}.

    :return: networkx.DiGraph instance represents the dag of rpm deps.
    """
    if rreqs is None:
        rreqs = RU.make_reversed_requires_dict(root)

    if reqs is None:
        reqs = RU.make_requires_dict(root)

    G = make_dependency_graph_with_nx(root, rreqs=rreqs)

    # Remove edges of self cyclic nodes:
    G.remove_edges_from(G.selfloop_edges())

    # Degenerate strongly connected components:
    for scc in NX.strongly_connected_components(G):
        scc = sorted(U.uniq(scc))

        if len(scc) == 1:  # Ignore sccs of which length is 1.
            continue

        G = _degenerate_nodes(G, scc, reqs, rreqs, '|')

    # Degenerate cyclic nodes:
    for cns in NX.simple_cycles(G):
        cns = sorted(U.uniq(cns))

        # Should not happen as selc cyclic nodes were removed in advance.
        assert len(cns) != 1, "Self cyclic node: " + cns[0]

        G = _degenerate_nodes(G, cns, reqs, rreqs, ',')

    assert NX.is_directed_acyclic_graph(G), \
           "I'm still missing something to make depgraph to dag..."

    return G


_ID_CNTR = count()


def _clone_nodeid(node, counter=_ID_CNTR):
    return "%s__%d" % (node, counter.next())


def tree_from_dag(G, root_node, serialized=False):
    """
    Make tree from DAG ``G``.

    :param G: networkx.DiGraph instance of DAG, direct acyclic graph.
    :param root_node: Root node
    :param serialized: Return JSON-serialized data instead of graph obj.

    :return: networkx.DiGraph instance or its JSON representation.
    """
    assert NX.is_directed_acyclic_graph(G), "Given graph is not DAG."

    g = NX.DiGraph()
    g.add_node(root_node, name=root_node)

    visited = set([root_node])
    parents = [root_node]

    while parents:
        next_parents = set()

        for parent in parents:
            successors = G.successors(parent)

            for s in successors:
                if s in visited:
                    news = _clone_nodeid(s)
                    logging.warn("Duplicated node=%s, cloned=%s" % (s, news))

                    g.add_node(news, name=s)
                    g.add_edge(parent, news)
                else:
                    logging.warn("Node=" + s)
                    visited.add(s)
                    next_parents.add(s)

                    g.add_node(s, name=s)
                    g.add_edge(parent, s)

        parents = next_parents

    return JS.tree_data(g, root_node) if serialized else g


def make_rpm_dependencies_trees(root, serialized=False):
    """
    Make dependency trees of RPMs.

    :param root: RPM Database root dir
    :param serialized: Return JSON-serialized data instead of graph obj.

    :return: List of networkx.DiGraph instance or its JSON representation.
    """
    g = make_rpm_dependencies_dag(root)
    root_nodes = list_root_nodes(g)

    logging.debug("%d nodes, %d edges and %d roots" %
                  (g.number_of_nodes(), g.number_of_edges(), len(root_nodes)))

    return [tree_from_dag(g, rn, serialized) for rn in root_nodes]


# vim:sw=4:ts=4:et:
