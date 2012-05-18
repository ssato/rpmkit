#
# tenjin (imported.tenjin) wrapper module
#
# Copyright (C) 2011 Satoru SATOH <ssato at redhat.com>
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
import rpmkit.imported.tenjin as tenjin
import logging
import os.path
import os


# dirty hack for highly customized and looks a bit overkill (IMHO) module
# system in pyTenjin:
cache_as = tenjin.helpers.cache_as
capture_as = tenjin.helpers.capture_as
captured_as = tenjin.helpers.captured_as
echo = tenjin.helpers.echo
echo_cached = tenjin.helpers.echo_cached
escape = tenjin.helpers.escape
fragment_cache = tenjin.helpers.fragment_cache
generate_tostrfunc = tenjin.helpers.generate_tostrfunc
html = tenjin.helpers.html
new_cycle = tenjin.helpers.new_cycle
not_cached = tenjin.helpers.not_cached
start_capture = tenjin.helpers.start_capture
stop_capture = tenjin.helpers.stop_capture
to_str = tenjin.helpers.to_str
unquote = tenjin.helpers.unquote


# http://www.kuwata-lab.com/tenjin/pytenjin-users-guide.html#templace-cache
_ENGINE = tenjin.Engine(cache=tenjin.MemoryCacheStorage())


def template_compile_0(template_path, context={}, engine=_ENGINE):
    """
    :param template_path: Relative or absolute path of template file
    :param context: Context information to instanciate template
    :param engine: Template engine
    """
    return engine.render(template_path, context)


def find_template(path_or_name, search_paths=[], env_var="RPMKIT_TEMPLATE_PATH"):
    """
    :param path_or_name: Template path or name
    :param search_paths: Template search path lista
    :param env_var: Environment variable name to set template search path
    """
    if not search_paths:
        search_paths = [os.curdir]

    p = os.environ.get(env_var, False)
    if p:
        search_paths = [p] + search_paths

    # Try $path_or_name at first:
    if os.path.exists(path_or_name):
        return path_or_name

    # Try to find template in search paths:
    for p in search_paths:
        t = os.path.join(p, path_or_name)
        if os.path.exists(t):
            return t

    raise RuntimeError(
        "Template '%s' was not found. Search path: %s" % \
            (path_or_name, str(search_paths))
    )


def template_compile(path_or_name, context={}, search_paths=[]):
    """
    :param path_or_name: Template path or filename
    """
    tmpl = find_template(path_or_name, search_paths)
    return template_compile_0(tmpl, context)


# vim:sw=4:ts=4:et:
