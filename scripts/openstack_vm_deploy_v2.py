#!/usr/bin/env python3.6

"""
Provides ability to start a VM (with provided metadata), list available VMs and kill an existing VM.
"""

import sys
import os
import logging
import subprocess
import traceback
import re
import json
# openstack source: https://github.com/openstack/openstacksdk/tree/master/openstack/network/v2
import openstack
from novaclient import client

#####################################################
# OpenStack parameters
#####################################################
SNAPSHOT_NAME = "PC_deployment_base_v2"
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

def perform_action(settings):
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
        if settings.build_name == "":
            logging.info("Can't deploy a new VM: no build name is provided")
            sys.exit(-2)

    # find if there already exists a VM with the build name
    server = conn.compute.find_server(settings.build_name)

    # if a VM with the same build name already exists - delete it
    if server:
        logging.info("Server for build %s exists, deleting server.........." % settings.build_name)
        conn.compute.delete_server(server, ignore_missing=True, force=True)
        conn.compute.wait_for_delete(server)
        logging.info("Server %s deleted" % settings.build_name)

    if settings.action == 'delete':
        return

    if settings.action == 'deploy':
        server = create_server(conn, settings)
        add_floatingip(conn, server)
        return

    logging.error('Error: unsuported action {0}'.format(settings.action))
    sys.exit(-2)

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
    metadatau['build_name'] = settings.build_name

    # openstack VM metadata can't be longer than 256 characters.
    # ...so the solution is to split instructions into chunks
    instructions_chunks = [settings.build_instructions[i:i+254] for i in range(0, len(settings.build_instructions), 254)]

    metadatau['build_instructions_num_chunks'] = str(len(instructions_chunks))
    for i, chunk in enumerate(instructions_chunks):
        metadatau['build_instructions_'+str(i)] = chunk

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
        #logging.info("Exception info: ", sys.exc_info()[1])

        server = conn.compute.find_server(settings.build_name)
        if server:
            logging.info("-- STATUS: {0}".format(server.status))
        else:
            logging.info("-- VM with name {0} not found".format(settings.build_name))
        sys.exit(-3)

def merge_build_instruction_chunks(raw_metadata):
    if "build_instructions_num_chunks" not in raw_metadata:
        return raw_metadata

    num_pieces = int(raw_metadata["build_instructions_num_chunks"])
    del raw_metadata["build_instructions_num_chunks"]

    assembled_json = ""
    for piece in range(num_pieces):
        chunk_key_name = "build_instructions_" + str(piece)
        assembled_json = assembled_json + raw_metadata[chunk_key_name]
        del raw_metadata[chunk_key_name]

    raw_metadata["build_instructions"] = assembled_json

    return raw_metadata

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

        # re-asemble build instructions which were split into multiple chunks
        metadata = merge_build_instruction_chunks(server.metadata)

        data['servers'].append({'id' : server.id, 'name' : server.name, 'ip' : ipf, 'created' : server.created_at, 'status' : server.vm_state, 'metadata' : metadata})

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
        web_accessible_log_file = os.path.join(settings.log_folder, 'latest_deploy_v2.log')

    main_log_file = 'openstack_{0}.log'.format(logname)

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

def remove_key(d, key_name):
    if not isinstance(d, (dict, list)):
        return d
    if isinstance(d, list):
        return [remove_key(v, key_name) for v in d]
    return {k: remove_key(v, key_name) for k, v in d.items()
            if k != key_name}

def read_instructions_file(file_name):
    with open(file_name) as instructions_file:
        instructions_string = instructions_file.read()
        # remove comments in the custom format "### ...."
        instructions_string = re.sub(r"\s*###.*?\n", "\n", instructions_string)
        # remove comments via conversion to dict
        instructions_dict = remove_key(json.loads(instructions_string), "comment")
        # save as string with no unnecessary spaces
        compacted_instructions_string = json.dumps(instructions_dict, separators=(',', ':'))
        return compacted_instructions_string

def parse_args(args):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--action", dest='action', required=True,
                      help="action that user intented to do: kill a running VM ('delete'), get list of currently running VMs to the 'serever_list.txt' file ('list'), or spin a new one ('deploy') (REQUIRED)")

    parser.add_argument("--build-name", dest='build_name',
                      default=None,
                      help="build name, the name given to the VM which can be used to manipulate the VM (list, get properties, delete, etc.)")

    parser.add_argument("--build-instructions-file", dest='build_instructions_file',
                      default=None,
                      help="a name of a JSON file containing deploy instrctions to be executed inside the newly created VM")

    parser.add_argument("--log-folder", dest='log_folder',
                      default="",
                      help="folder to place logs into (default: script directory)")

    args = parser.parse_args()

    if args.action == "deploy" or args.action == "delete":
        if args.build_name is None:
            parser.error("Delete and deploy actions requires build name to be provided")

    if args.action == "deploy":
        if args.build_instructions_file is None:
            parser.error("Deploy actions requires build instructions to be provided")

    if args.build_instructions_file is not None:
        args.build_instructions = read_instructions_file(args.build_instructions_file)

    return args

def main(args=sys.argv[1:]):
    settings = parse_args(args)

    setup_logfile(settings)

    logging.info('Started with arguments: [' + ' '.join(sys.argv[1:]) + ']')

    try:
        perform_action(settings)
    except Exception:
        logging.error('Exception: [{0}]'.format(traceback.format_exc()))
        sys.exit(-1)

if __name__ == '__main__':
    sys.exit(main())

