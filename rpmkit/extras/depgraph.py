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
from logging import DEBUG, INFO
from itertools import count
from jinja2_cli.render import render

import rpmkit.memoize as RM
import rpmkit.rpmutils as RU
import rpmkit.utils as U
import rpmkit.shell2 as SH

import datetime
import logging
import networkx as NX
import networkx.readwrite.json_graph as JS
import optparse
import os
import os.path
import sys


_E_ATTRS = dict(weight=1.0, )

_RPM_ROOT = "/var/lib/rpm"
_TEMPLATE_PATHS = [os.curdir, "/usr/share/rpmkit/templates"]
_GV_ENGINE = "sfdp"   # or neato, twopi, ...
_GV_ENGINES = ("dot", "neato", "twopi", "circo", "fdp", "sfdp")


def _make_dependency_graph(root, reversed=True, rreqs=None,
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

    # Remove edges of self cyclic nodes:
    g.remove_edges_from(g.selfloop_edges())

    return g


make_dependency_graph = RM.memoize(_make_dependency_graph)

_DGNODE_CTR = count()


def _degenerate_node(nodes, reason, cntr=_DGNODE_CTR):
    """
    :param nodes: List of nodes to degenerate :: [str]
    :param reason: Reason to degenerate nodes

    :return: Degenerated node, (name :: str, attr :: dict)
    """
    assert nodes, "Empty node list was given!"

    label = "%s %d" % (reason, cntr.next())
    nodes_s = "[%s...]" % ', '.join(n for n in nodes[:5])
    logging.debug("Create degenerate node: %s %s" % (label, nodes_s))

    return (label, dict(names=nodes, reason=reason))


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


def make_dependencies_dag(root, reqs=None, rreqs=None):
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

    g = make_dependency_graph(root, rreqs=rreqs)

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
        "I'm still missing something to make the dep. graph to dag..."

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
                    logging.debug("Clone visited node %s to %s" % (s, new_s))

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


tree_size = RM.memoize(_tree_size)


def make_dependencies_trees(root, fmt=False, compute_size=False):
    """
    Make dependency trees of RPMs.

    :param root: RPM Database root dir
    :param fmt: Return data in tree format that is suitable for JSON
        serialization.
    :param compute_size: Compute size from all paths in the tree

    :return: List of networkx.DiGraph instance or its JSON representation.
    """
    g = make_dependencies_dag(root)
    root_nodes = list_root_nodes(g)

    def _get_tree(graph, root_node, fmt):
        tree = tree_from_dag(graph, root_node, False)  # tree :: nx.DiGraph
        if fmt:
            size = tree_size(tree) if compute_size else tree.size()
            tree = JS.tree_data(tree, root_node)  # tree :: ! nx.DiGraph
            tree["size"] = size

        return tree

    logging.debug("Trees: %d nodes, %d edges and %d roots" %
                  (g.number_of_nodes(), g.number_of_edges(), len(root_nodes)))

    return [_get_tree(g, rn, fmt) for rn in root_nodes]


def _renderfile(workdir, tmpl, ctx={}, tpaths=_TEMPLATE_PATHS):
    if os.path.sep in tmpl:
        subdir = os.path.dirname(tmpl)
        d = os.path.join(workdir, subdir)
        tpaths = [os.path.join(t, subdir) for t in tpaths]

        if not os.path.exists(d):
            os.makedirs(d)

    s = render(tmpl, ctx, tpaths, ask=True)
    U.copen(os.path.join(workdir, tmpl[:-3]), 'w').write(s)


def dump_gv_depgraph(root, workdir, tpaths=_TEMPLATE_PATHS,
                     engine=_GV_ENGINE, html=True):
    """
    Generate dependency graph with graphviz.

    TODO: Utilize graph, DAG and trees generated w/ ``dump_graphs``.

    :param root: Root dir where 'var/lib/rpm' exists
    :param workdir: Working dir to dump the result
    :param tpaths: Template path list
    :param engine: Graphviz rendering engine to choose, e.g. neato
    :param html: Generate HTML graph files if True
    """
    reqs = RU.make_requires_dict(root)

    # Set virtual root for root rpms:
    for p, rs in reqs.iteritems():
        if not rs:  # This is a root RPM:
            reqs[p] = ["<rpmlibs>"]  # Set virtual root for this root rpm.

    # Remove self dependency refs:
    ctx = dict(dependencies=[(r, [p for p in ps if p != r]) for r, ps in
                             reqs.iteritems()])

    depgraph_s = render("rpmdep_graph_gv.j2", ctx, tpaths, ask=True)
    src = os.path.join(workdir, "rpmdep_graph.dot")
    U.copen(src, 'w').write(depgraph_s)

    output = src + ".svg"
    SH.run("%s -Tsvg -o %s %s" % (engine, output, src), workdir=workdir)

    if html:
        logging.info("Generate HTML files for graphviz outputs")
        for t in ("js/graphviz-svg.js.j2", "js/jquery.js.j2",
                  "rpmdep_graph_gv.html.j2"):
            _renderfile(workdir, t, ctx={}, tpaths=tpaths)


def dump_graphs(root, workdir, tpaths=_TEMPLATE_PATHS, html=True):
    """
    Make and dump RPM dependency graphs.

    :param root: RPM Database root dir
    :param workdir: Working directory to dump results
    :param tpaths: Template path list
    :param html: Generate HTML graph files if True
    """
    g = make_dependency_graph(root)
    dag = make_dependencies_dag(root)
    trees = make_dependencies_trees(root, True)

    if os.path.exists(workdir):
        assert os.path.isdir(workdir)
    else:
        os.makedirs(workdir)

    # see also: http://bl.ocks.org/mbostock/4062045.
    logging.info("Make dependency graph and dump it")
    g_data = dict()
    g_data["name"] = "RPM Dependency graph: root=%s" % root
    g_data["nodes"] = [dict(name=n, group=1) for n in g]

    nodeids = dict((n["name"], i) for i, n in enumerate(g_data["nodes"]))
    g_data["links"] = [dict(source=nodeids[e[0]], target=nodeids[e[1]],
                            value=1) for e in g.edges_iter()]

    U.json_dump(g_data, os.path.join(workdir, "rpmdep_graph.json"))

    # Likewise.
    logging.info("Make dependency DAG and dump it")
    dag_data = dict()
    dag_data["name"] = "RPM Dependency DAG: root=%s" % root
    dag_data["nodes"] = [dict(name=n, group=1) for n in dag]

    nodeids = dict((n["name"], i) for i, n in enumerate(dag_data["nodes"]))
    dag_data["links"] = [dict(source=nodeids[e[0]], target=nodeids[e[1]],
                              value=1) for e in dag.edges_iter()]

    U.json_dump(dag_data, os.path.join(workdir, "rpmdep_dag.json"))

    # see also: http://bl.ocks.org/mbostock/4063550 (flare.json)
    logging.info("Make dependency trees and dump them")
    for tree in trees:
        f = os.path.join(workdir, "rpmdep_tree_%(name)s.json" % tree)
        U.copen(f, 'w').write(str(tree))

    # Render dependency graph w/ d3.js (force directed layout).
    # see also: https://github.com/mbostock/d3/wiki/Force-Layout
    if html:
        logging.info("Generate HTML graph files")
        t = "rpmdep_graph_d3_force_directed_graph.html.j2"
        _renderfile(workdir, t, dict(root=root, graph_type="graph"), tpaths)
        _renderfile(workdir, t, dict(root=root, graph_type="daga"), tpaths)


def option_parser(root=_RPM_ROOT, tpaths=_TEMPLATE_PATHS, engine=_GV_ENGINE,
                  engines=_GV_ENGINES):
    """
    Command line option parser.

    :param tpaths: Template search paths
    :param engine: Graphviz engine for rendering
    :param engines: Graphviz engine choices
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d")
    defaults = dict(root=root, workdir="rk_depgraph_output_%s" % timestamp,
                    tpaths=tpaths, engine=engine, html=True,
                    verbose=False)

    p = optparse.OptionParser("""%prog [Options...]

Examples:
 # RPM database files exist in ./target_systems/www-server-101/var/lib/rpm/.
 %prog -w ./depgraph.out -v -r ./target_systems/www-server-101""")
    p.set_defaults(**defaults)

    p.add_option("-r", "--root", help="RPM database root dir [%default]")
    p.add_option("-w", "--workdir", help="Working (output) dir")
    p.add_option("-T", "--tpaths", action="append",
                 help="Specify template search paths one by one. Default "
                      "paths are: " + ', '.join(tpaths))
    p.add_option("", "--no-html", action="store_false", dest="html",
                 help="Do not generate HTML graph files")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    gog = optparse.OptionGroup(p, "Graphviz options")
    gog.add_option("", "--engine", choices=engines,
                   help="Graphviz Layout engine to render dependency graph. "
                        "Choicec: " + ', '.join(engines) + " [%default]")
    p.add_option_group(gog)

    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)
    dump_graphs(options.root, options.workdir, options.tpaths, options.html)

    logging.info("Make dependency graph and dump it with graphviz")
    dump_gv_depgraph(options.root, options.workdir, options.tpaths,
                     options.engine, options.html)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
