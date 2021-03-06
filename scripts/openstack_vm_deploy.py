#!/usr/bin/env python3.6

"""
Provides ability to start a VM (with provided metadata), list available VMs and kill an existing VM.
"""
from __future__ import with_statement

import sys
import os
import logging
import subprocess
import traceback
# openstack source: https://github.com/openstack/openstacksdk/tree/master/openstack/network/v2
import openstack
from novaclient import client

#####################################################
# OpenStack parameters
#####################################################
SNAPSHOT_NAME = "PC_deployment_base"
FLAVOR = "m2.medium"
KEYPAIR_NAME = 'PCMain'
NETWORK_NAME = "TestPC"
KID_NETWORK_NAME = "Kidnet External"
EXCLUDE_SERVER_PREFIX = "PC_deployment"
SECURITY_GROUPS = ["default", "ingress_cidr_local_tcp_8080","ingress_cidr_local_tcp_8090"]
OS_TENANT_NAME="HSC_CCM_PhenoTips"
#####################################################

# script parameters
SERVER_LIST_FILE_NAME = "server_list.txt"
DEFAULT_BRANCH_NAME = 'master'

# list of supported projects, and repositories needed to build each project
PROJECTS = { "PhenomeCentral": { "pn": "Patient Network",
                                 "rm": "Remote Matching",
                                 "pc": "PhenomeCentral",
                               },
             "PhenoTips":      { "pt": "PhenoTips"
                               }
           }

def script(settings):
    # Initialize and turn on debug openstack logging
    openstack.enable_logging(debug=True)
    logging.info("Initialize and turn on debug openstack logging")

    # Connection
    credentials = get_credentials()
    logging.info("Got OpenStack credentials {0}".format(credentials))
    conn = openstack.connect(**credentials)
    logging.info("Connected to OpenStack")

    if settings.action == 'list':
        list_servers(conn)
        sys.exit(0)

    if settings.action == 'deploy':
        # check if a custom build name should be set (only when deploying)
        all_default_branches = True
        settings.branch_names = {}
        for repo in PROJECTS[settings.project].keys():
            settings.branch_names[repo] = getattr(settings, repo + "_branch_name");
            if settings.branch_names[repo] != DEFAULT_BRANCH_NAME:
                all_default_branches = False

        if settings.build_name == DEFAULT_BRANCH_NAME and not all_default_branches:
            settings.build_name = "_".join(settings.branch_names.values())
            logging.info("Setting build name to {0}".format(settings.build_name))

    # find if there already exists a VM with the build name
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
    logging.info("Assigning floating IPs..........")
    fip = get_floating_ip(conn)
    retcode = subprocess.call(['openstack', 'server', 'add', 'floating', 'ip', server.name, fip.floating_ip_address])
    if retcode != 0:
        logging.error('Error: assiging floating_ip_address {0} failed'.format(fip.floating_ip_address))
        sys.exit(-4)
    else:
        logging.info("-- FLOATING IP ASSOCIATED: {0}".format(fip))

def create_server(conn, settings):
    image = conn.compute.find_image(SNAPSHOT_NAME)
    flavor = conn.compute.find_flavor(FLAVOR)
    network = conn.network.find_network(NETWORK_NAME)
    keypair = conn.compute.find_keypair(KEYPAIR_NAME)
    sgroups = []
    for group in SECURITY_GROUPS:
        sgroup = conn.network.find_security_group(group)
        if sgroup is not None:
            sgroups.append({"name": sgroup.name})
        else:
            logging.error("Security group {0} not found".format(group))
            # keep going, this is a minor error

    metadatau = {}
    metadatau['pr'] = settings.project
    metadatau['bn'] = settings.build_name
    for repo in PROJECTS[settings.project].keys():
        metadatau[repo] = settings.branch_names[repo]

    logging.info("Setting VM metadata to {0}".format(str(metadatau)))
    logging.info("Creating a new VM..........")

    try:
        server = conn.compute.create_server(
            name=settings.build_name, image_id=image.id, flavor_id=flavor.id,
            networks=[{"uuid": network.id}], security_groups=sgroups,
            key_name=keypair.name, metadata=metadatau)

        # Wait for a server to be in a status='ACTIVE'
        # interval - Number of seconds to wait before to consecutive checks. Default to 2.
        # wait - Maximum number of seconds to wait before the change. Default to 120.
        server = conn.compute.wait_for_server(server, interval=30, wait=1200)
        return server
    except:
        logging.info("-- FAILED TO START A VM (timeout?)")
        server = conn.compute.find_server(settings.build_name)
        if server:
            logging.info("-- STATUS: {0}".format(server.status))
        else:
            logging.info("-- VM with name {0} not found".format(settings.build_name))
        sys.exit(-3)

def list_servers(conn):
    # openstack server list
    servers_list = conn.compute.servers()
    logging.info("List: {0}".format(str(servers_list)))
    data = {'servers' : [], 'usage' : {}}
    for server in servers_list:
        #logging.info(server.to_dict())
        ipf = ''
        if server.status != 'BUILD' and NETWORK_NAME not in server.addresses.keys():
            # exclude servers not in the PC deployment network
            continue
        if server.name.startswith(EXCLUDE_SERVER_PREFIX):
            # exclude the frontend itself, and any other development servers
            continue
        logging.info("Listing server : {0}".format(server.name))

        if NETWORK_NAME in server.addresses.keys():
            for address in server.addresses[NETWORK_NAME]:
                if address['OS-EXT-IPS:type'] == 'floating':
                    ipf = address['addr']
        else:
            ipf = "not assigned"
        data['servers'].append({'id' : server.id, 'name' : server.name, 'ip' : ipf, 'created' : server.created_at, 'status' : server.vm_state, 'metadata' : server.metadata})

    # Get CPU and memory usage stats via nova
    credentials = get_credentials()
    credentials['version'] = 2
    nova = client.Client(**credentials)
    logging.info("Authorised with nova")
    usage = nova.limits.get("HSC_CCM_PhenoTips").to_dict()
    logging.info("Got usage info")
    logging.info(usage)
    data['usage'] = usage['absolute']
    data['usage']['totalRAMUsed'] = round(data['usage']['totalRAMUsed'] / 1024)
    data['usage']['maxTotalRAMSize'] = round(data['usage']['maxTotalRAMSize'] / 1024)

    # Add flavor required VCPUs number and RAM to spin one more server
    flavor = conn.compute.find_flavor(FLAVOR)
    flavor = nova.flavors.get(flavor.id)
    data['usage']['requiredRAM'] = round(flavor.ram / 1024)
    data['usage']['requiredCores'] = flavor.vcpus
    data['usage']['requiredDisc'] = flavor.disk

    print(data, file=open(SERVER_LIST_FILE_NAME, "w"))

# Retrieves an un-associated floating ip if available (once that dont have Fixed IP Address), or allocates 1 from pool
def get_floating_ip(conn):
    kid_network = conn.network.find_network(KID_NETWORK_NAME)
    fip = conn.network.find_available_ip()
    if fip:
        logging.info('FLOATING IP: {0}'.format(fip))
    else:
        # Create Floating IP
        fip = conn.network.create_ip(floating_network_id=kid_network.id)
        logging.info("->CREATED FLOATING IP: {0}".format(fip))
    return fip

# get credentials from Environment Variables set by running HSC_CCM_PhenoTips-openrc.sh
def get_credentials():
    logging.info("Environment variables: OpenStack username: [{0}]".format(os.environ['OS_USERNAME']))
    logging.info("Environment variables: OpenStack URL: [{0}]".format(os.environ['OS_AUTH_URL']))

    d = {}
    d['version'] = os.environ['OS_IDENTITY_API_VERSION']
    d['username'] = os.environ['OS_USERNAME']
    d['api_key'] = os.environ['OS_PASSWORD']
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['project_name'] = os.environ['OS_PROJECT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    d['password'] = os.environ['OS_PASSWORD']
    d['user_domain_name'] = os.environ['OS_USER_DOMAIN_NAME']
    d['project_domain_name'] = os.environ['OS_PROJECT_DOMAIN_NAME']
    return d

def setup_logfile(settings):
    if settings.action != 'deploy':
        logname = settings.action
        web_accessible_log_file = None
    else:
        logname = settings.build_name
        web_accessible_log_file = 'webapps/phenotips/resources/latest_deploy.log'

    main_log_file = 'pc_openstack_{0}.log'.format(logname)

    format_string = '%(levelname)s: %(asctime)s: %(message)s'

    # wipe out existing log files with the same name if exists
    open(main_log_file, 'w').close()
    # setup logging
    logging.basicConfig(filename=main_log_file, level=logging.INFO, format=format_string)

    # clone output to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[SCRIPT] %(levelname)s: %(message)s'))
    logging.getLogger('').addHandler(console)

    if web_accessible_log_file is not None:
        open(web_accessible_log_file, 'w').close()
        # clone output to "latest log" file
        web_accessible_log = logging.FileHandler(web_accessible_log_file)
        web_accessible_log.setFormatter(logging.Formatter(format_string))
        logging.getLogger('').addHandler(web_accessible_log)

def parse_args(args):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--action", dest='action', required=True,
                      help="action that user intented to do: kill a running VM ('delete'), get list of currently running VMs to the 'serever_list.txt' file ('list'), or spin a new one ('deploy')")

    parser.add_argument("--project", dest='project',
                      default=None,
                      choices=PROJECTS.keys(), help="when deploying, the name of the project to be deployed into a VM (required)")
    for project, branches in PROJECTS.items():
        for repo, repo_name in branches.items():
            parser.add_argument("--" + repo, dest=repo+'_branch_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="branch name for " + repo_name + " repo ('{0}' by default)".format(DEFAULT_BRANCH_NAME))
    parser.add_argument("--build-name", dest='build_name',
                      default=DEFAULT_BRANCH_NAME,
                      help="custom build name (by default '{0}' or '[pn_branch_name]_[rm_branch_name]_[pc_branch_name]') if any of branch names provided)".format(DEFAULT_BRANCH_NAME))

    args = parser.parse_args()

    if args.action == "deploy" and args.project is None:
        parser.error("Deploy actions requires a project to be selected")

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