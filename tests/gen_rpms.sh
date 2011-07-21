#! /bin/sh

out=$1
if test -z "${out}"; then
    out=/dev/stdout
fi

rpm -qa --qf "%{n},%{v},%{r},%{arch},%{epoch}\n" | sort > $out
