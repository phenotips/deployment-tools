#!/usr/bin/env python3.6

"""
Provides ability to start a VM (with provided metadata), list available VMs and kill an existing VM.
"""
from __future__ import with_statement

import sys
import os
import logging
import openstack
import subprocess
import traceback
#from openstack.cloud import exc

#####################################################
# OpenStack parameters
#####################################################
SNAPSHOT_NAME = "PC_deployment_base"
FLAVOUR = "m2.medium"
KEYPAIR_NAME = 'PCMain'
NETWORK_NAME = "TestPC"
KID_NETWORK_NAME = "Kidnet External"
EXCLUDE_SERVER_PREFIX = "PC_deployment"
SECURITY_GROUP_NAME = "ingress_cidr_local_tcp_8080"
#####################################################

# script parameters
SERVER_LIST_FILE_NAME = "server_list.txt"
DEFAULT_ACTION = 'deploy'
DEFAULT_BRANCH_NAME = 'master'


def script(settings):
    # Initialize and turn on debug openstack logging
    openstack.enable_logging(debug=True)
    logging.info("Initialize and turn on debug openstack logging")

    # Connection
    # https://docs.openstack.org/openstacksdk/latest/user/connection.html
    credentials = get_credentials()
    logging.info("Got credentials {0}".format(credentials))
    # https://docs.openstack.org/openstacksdk/latest/user/guides/connect.html
    conn = openstack.connect(**credentials)
    logging.info("Connected to OpenStack")

    if settings.action == 'list':
        list_servers(conn)
        sys.exit(0)

    # find if there already exists a VM with the given name
    server = conn.compute.find_server(settings.build_name)

    # if a VM with the same build name already exists - delete it
    if server:
        logging.info("Server for build %s exists, deleting server.........." % settings.build_name)
        conn.compute.delete_server(server, ignore_missing=True, force=True)
        conn.compute.wait_for_delete(server)
        logging.info("Server %s deleted" % settings.build_name)

    if settings.action == 'delete':
        sys.exit(0)

    server = create_server(conn, settings)
    add_floatingip(conn, server)

def add_floatingip(conn, server):
    # openstack server add floating ip [build_name] [ip]
    logging.info("Assigning floating IPs..........")
    fip = get_floating_ip(conn)
    #server.add_floating_ip(address=fip.floating_ip_address)
    retcode = subprocess.call(['openstack', 'server', 'add', 'floating', 'ip', server.name, fip.floating_ip_address])
    if retcode != 0:
        logging.error('Error: assiging floating_ip_address {0} failed'.format(fip.floating_ip_address))
        sys.exit(-4)
    else:
        logging.info("-- FLOATING IP ASSOCIATED: {0}".format(fip))

def create_server(conn, settings):
    # Get server metadata
    # server_metadata = conn.compute.get_server_metadata(server).metadata

    image = conn.compute.find_image(SNAPSHOT_NAME)
    flavor = conn.compute.find_flavor(FLAVOUR)
    network = conn.network.find_network(NETWORK_NAME)
    keypair = conn.compute.find_keypair(KEYPAIR_NAME)
    sgroup = conn.network.find_security_group(SECURITY_GROUP_NAME)

    metadatau = {}
    metadatau['pn'] = settings.pn_branch_name
    metadatau['rm'] = settings.rm_branch_name
    metadatau['pc'] = settings.pc_branch_name
    metadatau['bn'] = settings.build_name

    logging.info("Creating a new VM..........")

    try:
        server = conn.compute.create_server(
            name=settings.build_name, image_id=image.id, flavor_id=flavor.id,
            networks=[{"uuid": network.id}], security_groups=[{"name": sgroup.name}],
            key_name=keypair.name, metadata=metadatau)

        # Wait for a server to be in a status='ACTIVE', failures=None, interval=2, wait=120
        # interval – Number of seconds to wait before to consecutive checks. Default to 2.
        # wait – Maximum number of seconds to wait before the change. Default to 120.
        server = conn.compute.wait_for_server(server, interval=30, wait=600)
        return server
    except:
        logging.info("-- FAILED TO START A VM (timeout?)")
        server = conn.compute.find_server(settings.build_name)
        if server:
            logging.info("-- STATUS: {0}".format(server.status))
            return server
        else:
            logging.info("-- VM with name {0} not found".format(settings.build_name))
        sys.exit(-3)

def list_servers(conn):
    # openstack server list
    servers_list = conn.compute.servers()
    logging.info("List: {0}".format(str(servers_list)))
    data = []
    for server in servers_list:
        ipf = ''
        if NETWORK_NAME not in server.addresses.keys():
            # exclude servers not inthe PC deployment network
            continue
        if server.name.startswith(EXCLUDE_SERVER_PREFIX):
            # exclude the frontend itself, and any other development servers
            continue
        logging.info("Listing server : {0}".format(server.name))
        for address in server.addresses[NETWORK_NAME]:
            if address['OS-EXT-IPS:type'] == 'floating':
                ipf = address['addr']
        data.append({'id' : server.id, 'name' : server.name, 'ip' : ipf, 'created' : server.created_at, 'status' : server.vm_state, 'metadata' : server.metadata})
    print(data, file=open(SERVER_LIST_FILE_NAME, "w"))

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
    logging.info("Environment variables: username: [{0}]".format(os.environ['OS_USERNAME']))
    logging.info("Environment variables: URL: [{0}]".format(os.environ['OS_AUTH_URL']))

    d = {}
    d['version'] = os.environ['OS_IDENTITY_API_VERSION']
    d['username'] = os.environ['OS_USERNAME']
    d['api_key'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['project_name'] = os.environ['OS_PROJECT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    d['password'] = os.environ['OS_PASSWORD']
    return d

def setup_logfile(settings):
    if settings.action != 'deploy':
        logname = settings.action
    else:
        logname = settings.build_name

    # Wipe out previous log file with the same deployment name if exists
    open('pc_deploy_{0}.log'.format(logname), 'w').close()

    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='pc_deploy_{0}.log'.format(logname), level=logging.INFO, format=format_string)

    # clone output to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[SCRIPT] %(levelname)s: %(message)s'))
    logging.getLogger('').addHandler(console)

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

    setup_logfile(settings)

    logging.info('Started deployment with arguments: [' + ' '.join(sys.argv[1:]) + ']')

    try:
        script(settings)
    except Exception:
        logging.error('Exception: [{0}]'.format(traceback.format_exc()))
        sys.exit(-1)

if __name__ == '__main__':
    sys.exit(main())