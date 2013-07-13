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


_E_ATTRS = dict(weight=1.0, )


def _make_dependency_graph_with_nx(root, reversed=True, rreqs=None,
                                   edge_attrs=_E_ATTRS):
    """
    Make RPM dependency graph with using Networkx.DiGraph for given root.

    :param root: RPM Database root dir
    :param reversed: Resolve reversed dependency from required to requires
    :param rreqs: A dict represents RPM dependencies;
        {x: [package_requires_x]} or {x: [package_required_by_x]}.
    :param edge_attrs: Default edge attributes :: dict

    :return: networkx.DiGraph instance
    """
    g = NX.DiGraph()

    if rreqs is None:
        rreqs = RU.make_requires_dict(root, reversed)

    for k, vs in rreqs.iteritems():
        g.add_node(k, names=[k])
        g.add_edges_from([(k, v, edge_attrs) for v in vs])

    return g


make_dependency_graph_with_nx = memoize(_make_dependency_graph_with_nx)


def _degenerate_node(nodes, reason):
    """
    :param nodes: List of nodes to degenerate :: [str]
    :param reason: Reason to degenerate nodes

    :return: Degenerated node, (name :: str, attr :: dict)
    """
    assert nodes, "Empty node list was given!"

    return ("%s..." % nodes[0], dict(names=nodes, reason=reason))


def _degenerate_nodes(g, nodes, reason, edge_attrs=_E_ATTRS):
    """
    For each node, remove edges from/to that node and the node from the graph
    ``g`` and then add newly 'degenerated' node and relevant edges again.

    Note: This is effectful function, that is, given graph ``g`` will be
    modified.

    :param g: Dependency graph of nodes :: NX.DiGraph
    :param nodes: Node list :: [str]
    :param reason: Reason to degenerate nodes
    :param edge_attrs: Default edge attributes :: dict
    """
    if not nodes or len(nodes) == 1:
        return  # do nothing with empty or single item list.

    (dnode, attrs) = _degenerate_node(nodes, reason)
    g.add_node(dnode, **attrs)

    ucat = U.uconcat
    successors = ucat([s for s in g.successors_iter(n) if s not in nodes]
                      for n in nodes)
    predecessors = ucat([p for p in g.predecessors_iter(n) if p not in nodes]
                        for n in nodes)

    if successors:
        g.add_edges_from([(dnode, s, edge_attrs) for s in successors])

    if predecessors:
        g.add_edges_from([(p, dnode, edge_attrs) for p in predecessors])

    # Remove old edges and nodes:
    for node in nodes:
        g.remove_edges_from([(node, s) for s in g.successors_iter(node)])
        g.remove_edges_from([(p, node) for p in g.predecessors_iter(node)])

    g.remove_nodes_from(nodes)


def list_root_nodes(g):
    """
    List root nodes of given graph ``g``.

    Alternative: [n for n,d in g.in_degree().items() if d == 0]

    :param g: networkx.DiGraph instance
    :return: List of nodes :: [str]
    """
    return [n for n in g if not g.predecessors(n) and g.successors(n)]


def list_leaf_nodes(g):
    """
    List leaf nodes of given graph ``g``.

    :param g: networkx.DiGraph instance
    :return: List of nodes
    """
    return [n for n in g if not g.successors(n)]


def make_rpm_dependencies_dag(root, reqs=None, rreqs=None):
    """
    Make directed acyclic graph of RPM dependencies.

    see also:

    * http://en.wikipedia.org/wiki/Directed_acyclic_graph
    * http://en.wikipedia.org/wiki/Strongly_connected_component

    :param root: RPM Database root dir
    :param reqs: A dict represents RPM deps, {x: [package_requires_x]}.
    :param rreqs: A dict represents RPM deps, {x: [package_required_by_x]}.

    :return: networkx.DiGraph instance represents the dag of rpm deps.
    """
    if rreqs is None:
        rreqs = RU.make_reversed_requires_dict(root)

    if reqs is None:
        reqs = RU.make_requires_dict(root)

    g = make_dependency_graph_with_nx(root, rreqs=rreqs)

    # Remove edges of self cyclic nodes:
    g.remove_edges_from(g.selfloop_edges())

    # Degenerate strongly connected components:
    for scc in NX.strongly_connected_components(g):
        scc = sorted(U.uniq(scc))  # TODO: Is this needed?

        if len(scc) == 1:  # Ignore sccs of which length is 1.
            continue

        _degenerate_nodes(g, scc, "Strongly Connected Components")

    # Degenerate cyclic nodes:
    for cns in NX.simple_cycles(g):
        cns = sorted(U.uniq(cns))  # TODO: Likewise

        # Should not happen as selc cyclic nodes were removed in advance.
        assert len(cns) != 1, "Self cyclic node: " + cns[0]

        _degenerate_nodes(g, cns, "Cyclic nodes")

    assert NX.is_directed_acyclic_graph(g), \
        "I'm still missing something to make graph to dag..."

    return g


def _clone_nodeid(node, ids):
    return "%s__%d" % (node, ids.get(node, count()).next())


def tree_from_dag(g, root_node, fmt=False, edge_attrs=_E_ATTRS):
    """
    Make tree from DAG ``g``.

    :param g: networkx.DiGraph instance of DAG, direct acyclic graph.
    :param root_node: Root node
    :param fmt: Return data in tree format that is suitable for JSON
        serialization.
    :param edge_attrs: Default edge attributes :: dict

    :return: networkx.DiGraph instance or its JSON representation.
    """
    assert NX.is_directed_acyclic_graph(g), "Given graph is not DAG."

    nsattrs = NX.get_node_attributes(g, "names")

    g = NX.DiGraph()
    g.add_node(root_node, name=root_node,
               names=nsattrs.get(root_node, [root_node]))

    visited = set([root_node])
    parents = [root_node]

    ids = {root_node: count()}

    while parents:
        next_parents = set()

        for parent in parents:
            for s in g.successors_iter(parent):
                names = nsattrs.get(s, [s])

                if s in visited:
                    new_s = _clone_nodeid(s, ids)
                    logging.debug("Duplicated node=%s, cloned=%s" % (s, new_s))

                    g.add_node(new_s, name=s, names=names)
                    g.add_edge(parent, new_s, edge_attrs)
                else:
                    logging.debug("Node=" + s)
                    visited.add(s)
                    next_parents.add(s)
                    ids[s] = count()

                    g.add_node(s, name=s, names=names)
                    g.add_edge(parent, s, edge_attrs)

        parents = next_parents

    return JS.tree_data(g, root_node) if fmt else g


def _tree_size(tree):
    """
    Returns max length of longest paths of tree graph.

    Warning: This function needs a lot of computation and very slow.

    :param tree: NX.DiGraph instance of tree.
    """
    rnode = [n for n in tree if not tree.predecessors(n)][0]
    leaves = [n for n in tree if not tree.successors(n)]
    _paths = lambda leaf: NX.all_simple_paths(tree, rnode, leaf)

    return max(len(list(_paths(leaf))[0]) for leaf in leaves)


tree_size = memoize(_tree_size)


def make_rpm_dependencies_trees(root, fmt=False, compute_size=False):
    """
    Make dependency trees of RPMs.

    :param root: RPM Database root dir
    :param fmt: Return data in tree format that is suitable for JSON
        serialization.
    :param compute_size: Compute size from all paths in the tree

    :return: List of networkx.DiGraph instance or its JSON representation.
    """
    g = make_rpm_dependencies_dag(root)
    root_nodes = list_root_nodes(g)

    def _get_tree(graph, root_node, fmt):
        tree = tree_from_dag(graph, root_node, False)  # tree :: nx.DiGraph
        if fmt:
            size = tree_size(tree) if compute_size else tree.size()
            tree = JS.tree_data(tree, root_node)  # tree :: ! nx.DiGraph
            tree["size"] = size

        return tree

    logging.debug("%d nodes, %d edges and %d roots" %
                  (g.number_of_nodes(), g.number_of_edges(), len(root_nodes)))

    return [_get_tree(g, rn, fmt) for rn in root_nodes]


# vim:sw=4:ts=4:et:
