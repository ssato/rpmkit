#!/bin/bash
#
# Migrate RPM Database files and fix 'version_mismatch' problem.
#
# Copyright (C) 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato redhat.com>
# License: MIT
#
# Requirements: mock and initialized root for each migration from/to
# distributions.
#
set -e

USAGE="Usage: $0 [Options...] /path/to/your/rpmdb/root"

FROM_DIST=
TO_DIST=rhel-5-x86_64
OUTDIR=$(mktemp -d -u)

RPMDB_DUMP="/usr/lib/rpm/rpmdb_dump"
RPMDB_LOAD="/usr/lib/rpm/rpmdb_load"

function show_help () {
    cat <<EOH
${USAGE}
Options:
    -F FROM_DIST  Specify the 'FROM' distribution RPM DB was generated.
                  Disribution must be available in mock, that is, 
                  /etc/mock/<dist>.cfg must exist, its root dir must be
                  initialized
                  ([/var/lib/mock/<dist>]/root/usr/lib/rpm/rpmdb_load
                  and [/var/lib/mock/<dist>/root]/usr/lib/rpm/rpmdb_dump
                  should exist). Current running dist will be used if not set.

    -T TO_DIST    Specify the 'TO' distribution in which RPM DB to be used.
                  If you want to set to the current running dist, specify
                  special keyword "CUR". [$TO_DIST]

    -O OUTDIR     Specify the output dir [$OUTDIR]
EOH
}

function detect_dbtype () {
    local dbpath=$1
    # echo "$(file ${dbpath} | sed -r 's@^(.+/[A-Z][^:]+):.*\(([^,]+),.*@test "x${dbpath}" = "x\1" \&\& dbtype=$(echo \2 | tr A-z a-z) || :@g')"
    file ${dbpath} | sed -r 's/.* DB \(([^,]+).*/\1/' | tr A-Z a-z
}

function err_root_not_exist () {
    local sys_root=$1
    local dist=$2

    cat << EOM
[Error] Root dir '${sys_root:?}' does not exist for the dist '${dist:?}'.
        Try 'mock -r ${dist} init' to initialize dist.
EOM
}

function err_bin_not_exist () {
    local bin=$1
    local dist=$2

    cat << EOM
[Error] Program ${dump_bin} does not eixst.
        Try 'mock -r ${dist} init' to initialize dist.
EOM
}

function ld_library_path_for_root () {
    local root=$1
    local ldpath=""
    for d in $(ls -d ${root}/usr/lib*); do
        test "x${d##*/}" = "xlibexec" && continue || :
        test "x$ldpath" = "x" && ldpath="$d" || ldpath="$ldpath:$d"
    done
    echo "$ldpath"
}

while getopts "F:T:O:h" opt
do
  case $opt in
    F) FROM_DIST="$OPTARG" ;;
    T) TO_DIST="$OPTARG" ;;
    O) OUTDIR="$OPTARG" ;;
    h) show_help; exit 0 ;;
    \?) show_help; exit 1 ;;
  esac
done
shift $(($OPTIND - 1))

FROM_RPMDB_ROOT=$1

if test "x$FROM_RPMDB_ROOT" = "x"; then
    show_help
    exit 1
fi

# 1. Dump text
#
# ex. LD_LIBRARY_PATH=/var/lib/mock/rhel-6-x86_64/root/usr/lib64 \
#       /var/lib/mock/rhel-6-x86_64/root/usr/lib/rpm/rpmdb_dump \
#       -f Packages.txt Packages

if test "x$FROM_DIST" = "x"; then
    FROM_SYS_ROOT=/
else
    FROM_SYS_ROOT=/var/lib/mock/${FROM_DIST}/root/
    dump_bin=${FROM_SYS_ROOT}/usr/lib/rpm/rpmdb_dump

    if test ! -d ${FROM_SYS_ROOT}; then
        err_root_not_exist ${FROM_SYS_ROOT} ${FROM_DIST}
        exit 1
    fi
    if test ! -x ${dump_bin}; then
        err_bin_not_exist ${dump_bin} ${FROM_DIST}
        exit 1
    fi

    ldpath=$(ld_library_path_for_root ${FROM_SYS_ROOT})
    RPMDB_DUMP="LD_LIBRARY_PATH=${ldpath} ${dump_bin}"
fi

if test "x$TO_DIST" = "xCUR"; then
    TO_SYS_ROOT=/
else
    TO_SYS_ROOT=/var/lib/mock/${TO_DIST}/root/
    load_bin=${FROM_SYS_ROOT}/usr/lib/rpm/rpmdb_load

    if test ! -d ${TO_SYS_ROOT}; then
        err_root_not_exist ${TO_SYS_ROOT} ${TO_DIST}
        exit 1
    fi
    ldpath=$(ld_library_path_for_root ${TO_SYS_ROOT})
    RPMDB_LOAD="LD_LIBRARY_PATH=${ldpath} ${load_bin}"
fi

if test -d ${OUTDIR}; then
    echo "[Info] Use existing ${OUTDIR} ..."
else
    echo "[Info] Creating ${OUTDIR} ..."
    mkdir -p ${OUTDIR}
fi

for dbpath in ${FROM_RPMDB_ROOT}/var/lib/rpm/[A-Z]*; do
    dbname=${dbpath##*/}
    dbtype=$(detect_dbtype ${TO_SYS_ROOT}/var/lib/rpm/${dbname})
    dumpfile=${OUTDIR}/${dbname}.txt
    outfile=${OUTDIR}/${dbname}

    #${RPMDB_DUMP} -f ${dumpfile} ${dbpath} && \
    #${RPMDB_LOAD} -t ${dbtype} -f ${dumpfile} ${outfile}
    ${RPMDB_DUMP} ${dbpath} | ${RPMDB_LOAD} -t ${dbtype} ${outfile}
done

# vim:sw=4:ts=4:et:
