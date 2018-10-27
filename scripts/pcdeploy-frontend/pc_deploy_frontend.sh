#! /bin/bash

echo "Starting PC deploy frontend..."

cd /home/pcinstall/phenomecentral-standalone-1.2-SNAPSHOT
./start.sh &> webapps/phenotips/resources/serverlog.txt