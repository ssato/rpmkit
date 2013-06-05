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

import rpmkit.rpmutils as RU
import networkx as NX


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

# vim:sw=4:ts=4:et:
