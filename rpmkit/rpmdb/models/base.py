#
# rpmdb.modles.base - Base classes and objects for tables
#
# Copyright (C) 2012 Red Hat, Inc.
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
from sqlalchemy.ext.declarative import declarative_base, declared_attr

import sqlalchemy as S


# Use 'Declarative' extension
# (http://docs.sqlalchemy.org/en/rel_0_7/orm/extensions/declarative.html)
DeclBase = declarative_base()


class DeclMixin(object):

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = S.Column(S.Integer, primary_key=True)  # It's always needed.


# vim:sw=4:ts=4:et:
