#! /bin/bash

echo "Starting log server..."

cd /home/pcinstall

touch __log_server_started

#su -c "python -m SimpleHTTPServer 8090" centos
python -m SimpleHTTPServer 8090

touch __log_server_stopped