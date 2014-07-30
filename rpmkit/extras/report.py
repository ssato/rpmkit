# report.py - Generate various reports from data collected by updateinfo,
# depgraph, etc.
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
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

import rpmkit.rpmutils as RU
import rpmkit.yum_surrogate as YS
import rpmkit.extras.depgraph as RD
import rpmkit.template as RT

import codecs
import logging
import optparse
import os
import os.path

try:
    import json
except ImportError:
    import simplejson as json


_TEMPLATE_PATHS = [os.curdir, "/usr/share/rpmkit/templates"]
_GV_ENGINE = "sfdp"   # or neato, twopi, ...


def copen(path, flag='r', **kwargs):
    return codecs.open(path, flag, "utf-8")


def renderfile(tmpl, workdir, ctx={}, subdir=None, tpaths=_TEMPLATE_PATHS):
    if subdir:
        subdir = os.path.join(workdir, subdir)
        if not os.path.exists(subdir):
            os.makedirs(subdir)

        dst = os.path.join(subdir, tmpl[:-3])
    else:
        dst = os.path.join(workdir, tmpl[:-3])

    s = RT.render(tmpl, ctx, tpaths, ask=True)
    copen(dst, "w").write(s)


def gen_depgraph_gv(root, workdir, template_paths=_TEMPLATE_PATHS,
                    engine=_GV_ENGINE):
    """
    Generate dependency graph with using graphviz.

    :param root: Root dir where 'var/lib/rpm' exists
    :param workdir: Working dir to dump the result
    :param template_paths: Template path list
    :param engine: Graphviz rendering engine to choose, e.g. neato
    """
    reqs = RU.make_requires_dict(root)

    # Set virtual root for root rpms:
    for p, rs in reqs.iteritems():
        if not rs:  # This is a root RPM:
            reqs[p] = ["<rpmlibs>"]

    ctx = dict(dependencies=[(r, ps) for r, ps in reqs.iteritems()])

    renderfile("rpm_dependencies.html.j2", workdir, ctx, tpaths=template_paths)

    depgraph_s = RT.render("rpm_dependencies.graphviz.j2", ctx,
                        template_paths, ask=True)
    src = os.path.join(workdir, "rpm_dependencies.graphviz")

    copen(src, 'w').write(depgraph_s)

    output = src + ".svg"
    (outlog, errlog) = (os.path.join(workdir, "graphviz_out.log"),
                        os.path.join(workdir, "graphviz_err.log"))

    (out, err, rc) = YS.run("%s -Tsvg -o %s %s" % (engine, output, src))

    copen(outlog, 'w').write(out)
    copen(errlog, 'w').write(err)


def __name(tree):
    return tree["name"].replace('-', "_")


def gen_depgraph_d3(trees, workdir, template_paths=_TEMPLATE_PATHS,
                    with_label=True):
    """
    Generate dependency graph to be rendered with d3.js.

    :param trees: JSON-formatted RPM dependency trees
    :param workdir: Working dir to dump the result
    :param template_paths: Template path list
    """
    datadir = os.path.join(workdir, "data")
    cssdir = os.path.join(workdir, "css")

    def __make_ds(tree):
        svgid = __name(tree)
        jsonfile = os.path.join("..", "%s.json" % svgid)
        jsonpath = os.path.join(datadir, "%s.json" % svgid)
        diameter = 20 + tree.get("size", 2) // 2  # TODO: Optimize this.

        if diameter < 500:
            diameter = 500

        return (svgid, jsonfile, diameter, jsonpath)

    datasets = [(t, __make_ds(t)) for t in trees]

    if not os.path.exists(datadir):
        os.makedirs(datadir)

    if not os.path.exists(cssdir):
        os.makedirs(cssdir)

    css_tpaths = [os.path.join(t, "css") for t in template_paths]
    renderfile("d3.css.j2", workdir, {}, "css", css_tpaths)

    for tree, (svgid, jsonfile, diameter, jsonpath) in datasets:
        try:
            root_node = tree["name"]
            logging.info("Dump tree data: root=%s, path=%s" %
                         (root_node, jsonpath))
            json.dump(tree, copen(jsonpath, 'w'))

            ctx = dict(svgid=svgid, jsonfile=jsonfile, diameter=diameter,
                       with_label=("true" if with_label else "false"),
                       root=root_node)

            renderfile("rpm_dependencies.d3.html.j2", workdir, ctx,
                       "data/" + svgid, tpaths=template_paths)

        except RuntimeError, e:
            logging.warn("Could not dump JSON data: " + jsonpath)
            logging.warn("Reason: " + str(e))
            json.dump({"name": "Failed to make acyclic tree"},
                      copen(jsonpath, 'w'))
        except:
            logging.warn("Could not dump JSON data: " + jsonpath)
            logging.warn("tree=" + str(tree))
            raise


def modmain(ppath, workdir=None, template_paths=_TEMPLATE_PATHS,
            engine=_GV_ENGINE):
    """
    :param ppath: The path to 'Packages' RPM DB file
    :param workdir: Working dir to dump the result
    :param template_paths: Template path list
    :param engine: Graphviz rendering engine to choose, e.g. neato
    """
    if not ppath:
        ppath = raw_input("Path to the RPM DB 'Packages' > ")

    ppath = os.path.normpath(ppath)
    root = YS.setup_root(ppath, force=True)

    if not workdir:
        workdir = root

    logging.info("Dump depgraph and generating HTML reports...")
    jsdir = os.path.join(workdir, "js")
    if not os.path.exists(jsdir):
        os.makedirs(jsdir)

    js_tpaths = [os.path.join(t, "js") for t in template_paths]
    for f in ("jquery.js.j2", "d3.v3.min.js.j2", "d3-svg.js.j2",
              "graphviz-svg.js.j2"):
        renderfile(f, workdir, {}, "js", js_tpaths)

    trees = RD.make_dependencies_trees(root, True)

    renderfile("updateinfo.html.j2", workdir,
               dict(d3_charts=[(__name(t), t["name"]) for t in trees], ),
               tpaths=template_paths)

    gen_depgraph_gv(root, workdir, template_paths, engine)
    gen_depgraph_d3(trees, workdir, template_paths)


def mk_template_paths(tpaths_s, default=_TEMPLATE_PATHS, sep=':'):
    """
    :param tpaths_s: ':' separated template path list

    >>> default = _TEMPLATE_PATHS
    >>> default == mk_template_paths("")
    True
    >>> ["/a/b"] + default == mk_template_paths("/a/b")
    True
    >>> ["/a/b", "/c"] + default == mk_template_paths("/a/b:/c")
    True
    """
    tpaths = tpaths_s.split(sep) if tpaths_s else None

    if tpaths:
        return tpaths + default
    else:
        return default  # Ignore given paths string.


def option_parser(template_paths=_TEMPLATE_PATHS, engine=_GV_ENGINE):
    """
    Option parser.
    """
    defaults = dict(workdir=None, template_paths="", engine=engine,
                    verbose=False)

    gv_es = ("dot", "neato", "twopi", "circo", "fdp", "sfdp")

    p = optparse.OptionParser("""%prog [Options...] RPMDB_PATH

    where RPMDB_PATH = the path to 'Packages' RPM DB file taken from
                       '/var/lib/rpm' on the target host""")
    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("-T", "--tpaths",
                 help="':' separated additional template search path "
                      "list [%s]" % ':'.join(template_paths))
    p.add_option("", "--engine", choices=gv_es,
                 help="Graphviz Layout engine to render dependency graph. "
                      "Choicec: " + ', '.join(gv_es) + " [%default]")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if args:
        ppath = args[0]
    else:
        ppath = raw_input("Path to the 'Packages' RPM DB file > ")

    assert os.path.exists(ppath), "RPM DB file looks not exist"

    tpaths = mk_template_paths(options.tpaths)

    modmain(ppath, options.workdir, tpaths, options.engine)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
