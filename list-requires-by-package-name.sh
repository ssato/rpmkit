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


# search from 'files' table
sql="SELECT DISTINCT pkg.name FROM packages AS pkg, files AS f WHERE pkg.pid = f.pid AND f.path IN (SELECT DISTINCT r.name FROM requires AS r, packages AS p WHERE r.pid = p.pid AND p.name = \"$package_name\" AND SUBSTR(r.name,1,1) = '/')"
reqs=$($sqlite $sqldb "$sql")


# search from 'packages' table
sql="SELECT DISTINCT r.name FROM requires AS r, packages AS p WHERE r.pid = p.pid AND p.name = \"$package_name\" AND r.name IN (SELECT name FROM packages)"
reqs="$reqs "$($sqlite $sqldb "$sql")


# search from 'provides' table
sql="SELECT DISTINCT p.name FROM requires AS r, provides AS pro, packages AS p WHERE r.name = pro.name AND pro.pid = p.pid AND p.name <> \"$package_name\" AND r.pid = (SELECT pid FROM packages WHERE name = \"$package_name\")"
reqs="$reqs "$($sqlite $sqldb "$sql")


for r in $reqs; do echo $r; done | sort | uniq

# vim: set sw=4 ts=4 et:
