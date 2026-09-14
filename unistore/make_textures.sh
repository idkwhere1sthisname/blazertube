#!/bin/sh
if !command -v tex3ds > /dev/null 2>&1
then
    echo "Please install tex3ds. sudo dkp-pacman -S tex3ds"
    exit 1
fi
tex3ds -i textures.t3s -o textures.t3x
exit 0
