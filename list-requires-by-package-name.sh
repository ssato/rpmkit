#! /bin/bash
set -e
#set -x

sqlite="/usr/bin/sqlite3"
usage="Usage: $0 sqldb filename or $0 sqldb file_basename"

if test ! -x $sqlite; then
    echo "$sqlite is not found in your system. Install it first"
    exit 1
fi

sqldb=$1
package_name=$2
if test -z "$package_name"; then
    echo $usage
    exit 1
fi

sql="SELECT DISTINCT p.name from requires as r, provides as pro, packages as p where r.name = pro.name and pro.pid = p.pid and p.name <> \"$package_name\" and r.pid = (select pid from packages where name = \"$package_name\")"

$sqlite $sqldb "$sql"

# vim: set sw=4 ts=4 et:
