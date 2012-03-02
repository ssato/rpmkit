#
# misc utility routines
#
# Copyright (C) 2011, 2012 Red Hat, Inc.
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
import rpmkit.globals as G
import rpmkit.tenjinwrapper as T
import rpmkit.utils as U
import os.path


# Aliases:
typecheck = U.typecheck
is_local = U.is_local


def compile_template(tmpl, context={}, spaths=[G.RPMKIT_TEMPLATE_PATH]):
    """
    :param tmpl: Template file name or (abs or rel) path
    :param context: Context parameters to instantiate the template :: dict
    """
    return T.template_compile(os.path.join("1/myrepo", tmpl), context, spaths)


# vim:sw=4 ts=4 et:
