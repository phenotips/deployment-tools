#! /bin/bash

echo "Starting FakeSMTP server..."

cd /home/pcinstall/FakeSMTP

touch __fakesmtp_server_started

java -jar fakeSMTP-2.0.jar -s -b -p 2525 -a 127.0.0.1

touch __fakesmtp_server_stopped