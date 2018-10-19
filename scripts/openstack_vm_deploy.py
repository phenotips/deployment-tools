#!/usr/bin/env python3.6

"""
OpenStackClient script for starting a VM for a new test PhenomeCentral build for 3 branches
"""
from __future__ import with_statement

import sys
import os
import logging
import openstack
import subprocess

DEFAULT_ACTION = 'depoly'
DEFAULT_BRANCH_NAME = 'master'
KEYPAIR_NAME = 'PCMain'
SNAPSHOT_NAME = "test6-snapshot"
IMAGE_NAME = "Ubuntu 16.04 LTS"
FLAVOUR = "m2.medium"
NETWORK_NAME = "TestPC"
KID_NETWORK_NAME = "Kidnet External"
SERVER_LIST_FILE_NAME = "server_list.txt"

def script(settings):
    # Initialize and turn on debug openstack logging
    openstack.enable_logging(debug=True)

    # Connection
    # https://docs.openstack.org/openstacksdk/latest/user/connection.html
    credentials = get_credentials()
    # https://docs.openstack.org/openstacksdk/latest/user/guides/connect.html
    conn = openstack.connect(**credentials)

    # If the servier with the same build name already exists - delete it
    server = conn.compute.find_server(settings.build_name)

    # Get server metadata
    # server_metadata = conn.compute.get_server_metadata(server).metadata
    if settings.action == 'list':
        # openstack server list
        servers_list = conn.compute.servers()
        data = []
        for server in servers_list:
            ipf = ''
            array_addresses = server.addresses
            if NETWORK_NAME not in array_addresses.keys():
                continue
            for address in array_addresses[NETWORK_NAME]:
                if address['OS-EXT-IPS:type'] == 'floating':
                    ipf = address['addr']
            data.append({'name' : server.name, 'ip' : ipf, 'created' : server.created_at, 'status' : server.vm_state})
        print(data, file=open(SERVER_LIST_FILE_NAME, "w"))
        exit()

    if server:
        logging.info("Server for build %s exists" % settings.build_name)
        logging.info(server)
        logging.info("deleting server..........")
        conn.compute.delete_server(server, ignore_missing=True, force=True)
        conn.compute.wait_for_delete(server)
        logging.info("server %s deleted" % settings.build_name)

    if settings.action == 'delete':
        exit()

    image = conn.compute.find_image(SNAPSHOT_NAME)
    flavor = conn.compute.find_flavor(FLAVOUR)
    network = conn.network.find_network(NETWORK_NAME)
    keypair = conn.compute.find_keypair(KEYPAIR_NAME)

    metadatau = {}
    metadatau['pn'] = settings.pn_branch_name
    metadatau['rm'] = settings.rm_branch_name
    metadatau['pc'] = settings.pc_branch_name
    metadatau['bn'] = settings.build_name

    from openstack.cloud import exc
    try:
        server = conn.compute.create_server(
            name=settings.build_name, image_id=image.id, flavor_id=flavor.id,
            networks=[{"uuid": network.id}], key_name=keypair.name, metadata=metadatau)

        # Wait for a server to be in a status='ACTIVE', failures=None, interval=2, wait=120
        # interval – Number of seconds to wait before to consecutive checks. Default to 2.
        # wait – Maximum number of seconds to wait before the change. Default to 120.
        server = conn.compute.wait_for_server(server, interval=30, wait=240)
    except (exc.OpenStackCloudTimeout, TimeoutException):
        server = conn.compute.find_server(settings.build_name)
        logging.info("--STATUS---> {0}".format(server.status))

    #print("ssh -i {key} root@{ip}".format(key=PRIVATE_KEYPAIR_FILE, ip=server.access_ipv4))

    # openstack server add floating ip [build_name] [ip]
    logging.info("--ASSOCIATE FLOATING IP-->")
    fip = get_floating_ip(conn)
    #server.add_floating_ip(address=fip.floating_ip_address)
    retcode = subprocess.call(['openstack', 'server', 'add', 'floating', 'ip', settings.build_name, fip.floating_ip_address])
    if retcode != 0:
        logging.error('Error: assiging floating_ip_address {0} failed'.format(fip.floating_ip_address))
    else:
        logging.info("-- FLOATING IP ASSOCIATED --> {0}".format(fip))

# Retrieves an un-associated floating ip if available (once that dont have Fixed IP Address), or allocates 1 from pool
def get_floating_ip(conn):
    kid_network = conn.network.find_network(KID_NETWORK_NAME)
    fip = conn.network.find_available_ip()
    if fip:
        logging.info('FLOATING IP: {0}'.format(fip))
    else:
        # Create Floating IP.
        fip = conn.network.create_ip(floating_network_id=kid_network.id)
        logging.info("->CREATED FLOATING IP: {0}".format(fip))
    return fip

# get credentials from Environment Variables set by running HSC_CCM_PhenoTips-openrc.sh
def get_credentials():
    d = {}
    d['version'] = os.environ['OS_IDENTITY_API_VERSION']
    d['username'] = os.environ['OS_USERNAME']
    d['api_key'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['project_name'] = os.environ['OS_PROJECT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    d['password'] = os.environ['OS_PASSWORD']
    return d

def parse_args(args):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--pn", dest='pn_branch_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="branch name for Patient Network repo ('{0}' by default)".format(DEFAULT_BRANCH_NAME))
    parser.add_argument("--rm", dest='rm_branch_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="branch name for Remote Matching repo ('{0}' by default)".format(DEFAULT_BRANCH_NAME))
    parser.add_argument("--pc", dest='pc_branch_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="branch name for PhenomeCentral repo ('{0}' by default)".format(DEFAULT_BRANCH_NAME))
    parser.add_argument("--build-name", dest='build_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="custom build name (by default '{0}' or '[pn_branch_name]_[rm_branch_name]_[pc_branch_name]') if any of branch names provided)".format(DEFAULT_BRANCH_NAME))
    parser.add_argument("--action", dest='action',
                      default=DEFAULT_ACTION,
                      help="action that user intented to do, kill running VM server ('delete'), save list of currently running instances to the 'serever_list.txt' file ('list') in the directory where script is running, or spin a new one (by default '{0}')".format(DEFAULT_ACTION))

    args = parser.parse_args()
    return args
 
def main(args=sys.argv[1:]):
    settings = parse_args(args)
    # Setup logging
    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='pc_deploy_{0}.log'.format(settings.build_name), level=logging.INFO, format=format_string)
    # Wipe out previous log file with the same deployment name if exists
    open('pc_deploy_{0}.log'.format(settings.build_name), 'w').close()
    logging.info('Started deployment with arguments: ')
    logging.info('-->>'.join(sys.argv[1:]))

    script(settings)

if __name__ == '__main__':
    sys.exit(main())