#!/bin/sh
# Entrypoint: ensure bind-mounted paths are writable by the converter user,
# then drop privileges and exec the real command via tini.
#
# Bind mounts created by the Docker daemon at compose-up time are owned by
# root if they didn't pre-exist on the host. This script normalises that so
# self-hosters never have to chown dirs manually.
set -eu

UID_TARGET="${APP_UID:-1000}"
GID_TARGET="${APP_GID:-1000}"

for d in /app/tmp /app/tmp_failed /app/feedback /app/user_profiles /app/rules /app/bambu_profiles; do
    [ -d "$d" ] && chown -R "${UID_TARGET}:${GID_TARGET}" "$d" 2>/dev/null || true
done

exec /usr/bin/tini -- gosu "${UID_TARGET}:${GID_TARGET}" "$@"
