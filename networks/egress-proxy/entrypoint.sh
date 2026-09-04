#!/usr/bin/env bash
set -e

echo "Starting egress proxy service..."
exec squid -N -f /etc/squid/squid.conf
