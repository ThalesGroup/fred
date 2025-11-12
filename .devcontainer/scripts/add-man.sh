#!/bin/bash

# To add man command back in a minimized linux environement
# from: https://github.com/blitterated/docker-dev-env/wiki/Setup-man-pages-in-a-minimized-Ubuntu-container

apt update

# comment out dpkg exclusion for manpages
sed -e '\|/usr/share/man|s|^#*|#|g' -i /etc/dpkg/dpkg.cfg.d/excludes

# install manpage packages and dependencies
apt --yes install apt-utils dialog manpages manpages-posix man-db

# remove dpkg-divert entries
rm -f /usr/bin/man
dpkg-divert --quiet --remove --rename /usr/bin/man
rm -f /usr/share/man/man1/sh.1.gz
dpkg-divert --quiet --remove --rename /usr/share/man/man1/sh.1.gz
