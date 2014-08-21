#! /bin/bash
# Setup and initalize rpmkit-ylc.
#
set -e

# globals:
ADD_USER=0  # or 1 (true)
INIT_DATA=0  # or 1 (true)
USER="admin"
PASSWD=""
RUNLEVEL=3
msg_setup_firewall_manually="
[Warn] lokkit in system-config-firewall-base does not look available in this
       host. Please save and update /etc/sysconfig/iptables to allow inboud
       http access to this host and restart iptables system service manually. 
"
msg_add_user_manually="
[Info] Add a user and initialize data by yourself, please:
       /usr/sbin/ylc-data-set-htpasswd [USER [PASSWORD]]
"
msg_init_data_manually="
[Info] Initialize www data by yourself, please:
       bash -ex /etc/cron.daily/yum_makelistcache.cron
"

function show_help () {
    cat << EOH
Usage: $0 [Options ...]
Options:
    -U  Add a user
    -I  Initialize the wwww data by running the cron job script
    -h  Show this help
EOH
}

# main:
while getopts "UIh" opt
do
    case $opt in
        U) ADD_USER=1 ;;
        I) INIT_DATA=1 ;;
        h) show_help; exit 0 ;;
        \?) show_help; exit 1 ;;
    esac
done
shift $(($OPTIND - 1))

echo -ne "[Info] Ensure httpd system service is enabled ... "
/sbin/chkconfig --list httpd | grep -q ${RUNLEVEL:?}:on >/dev/null 2>/dev/null || /sbin/chkconfig httpd on
echo "Done"

echo -ne "[Info] Ensure inbound http access is allowed ... "
if `/sbin/service iptables status 2>/dev/null >/dev/null`; then
    which lokkit && (lokkit --quiet -p http:tcp && echo "Done") || \
        (echo "${msg_setup_firewall_manually}"; echo "Skip")
else
    echo "Firewall is disabled and nothing to do ... Done"
fi

if test $ADD_USER -eq 1; then
    echo -ne "[Info] Add a user ... "
    read -t 5 -s -p "Password: " passwd
    /usr/sbin/ylc-data-set-htpasswd ${USER:?} ${PASSWD:?}
    echo "Done"
else
    echo "${msg_add_user_manually}"
fi

if test $INIT_DATA -eq 1; then
    echo -ne "[Info] Initialize www data ... "
    bash -ex /etc/cron.daily/yum_makelistcache.cron
    echo "Done"
else
    echo "${msg_init_data_manually}"
fi

# vim:sw=4:ts=4:et:
