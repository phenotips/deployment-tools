#!/usr/bin/env python3.6

"""
Clones, builds and deploys PhenomeCentral instance out of 3 branches of Patient Network,
Remote Matching and PhenomeCentral GitHub repoes.
"""

from __future__ import with_statement

import sys
import os
import subprocess
import logging
import shutil
import time
import json
import platform
from git import Repo
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter

VM_METADATA_URL = "http://169.254.169.254/openstack/2017-02-22/meta_data.json"

PN_REPOSITORY_NAME = 'patient-network'
RM_REPOSITORY_NAME = 'remote-matching'
PC_REPOSITORY_NAME = 'phenomecentral.org'

BUILD_ORDER = [PN_REPOSITORY_NAME, RM_REPOSITORY_NAME, PC_REPOSITORY_NAME]

DEFAULT_BRANCH_NAME = 'master'
DEFAULT_BUILD_NAME = DEFAULT_BRANCH_NAME

PARENT_PHENOTIPS_GIT_URL = 'https://github.com/phenotips/'
TRIGGER_INITIALIZATION_UTL = 'http://localhost:8080'


def setup_folders(settings):
    # define custom build name
    if settings.build_name == DEFAULT_BRANCH_NAME and (settings.pn_branch_name != DEFAULT_BRANCH_NAME or settings.rm_branch_name != DEFAULT_BRANCH_NAME or settings.pc_branch_name != DEFAULT_BRANCH_NAME):
        settings.build_name = settings.pn_branch_name + '_' + settings.rm_branch_name + '_' + settings.pc_branch_name

    settings.pc_distrib_dir = os.path.join(settings.git_dir, 'phenomecentral.org', 'standalone', 'target')

    settings.this_build_deploy_dir = os.path.join(settings.deploy_dir, settings.build_name)
    logging.info('PC deployment directory: {0}'.format(settings.this_build_deploy_dir))

    # Wipe GitHub directory for a fresh checkout
    if os.path.isdir(settings.git_dir):
        logging.info('Removing existig github repos in {0}'.format(settings.git_dir))
        shutil.rmtree(settings.git_dir)
    os.mkdir(settings.git_dir)

    # Create general deployment directory for all deployments
    if not os.path.isdir(settings.deploy_dir):
        os.mkdir(settings.deploy_dir)

    # Create deployment directory for this current build inside of general deployment directory
    if os.path.isdir(settings.this_build_deploy_dir):
        shutil.rmtree(settings.this_build_deploy_dir)
    os.mkdir(settings.this_build_deploy_dir)


def build_pc(settings):
    # Checkout and build all repositories
    for repo_name in BUILD_ORDER:
        if repo_name not in settings.repositories:
            logging.error('Error: branch for repo {0} is not specified'.format(repo_name))
            sys.exit(-1)
        os.chdir(settings.git_dir)
        build_repo(repo_name, settings.repositories[repo_name])


def build_repo(repo_name, repo_branch):
    logging.info('Started building repo {0} ...'.format(repo_name))
    os.mkdir(repo_name)
    os.chdir(repo_name)

    Repo.clone_from(PARENT_PHENOTIPS_GIT_URL + repo_name + '.git', '.', branch=repo_branch)
    # make python wait for os.system build process to finish before building next repo
    retcode = subprocess.call(['mvn', 'clean', 'install', '-Pquick'], shell=True)
    if retcode != 0:
        logging.error('Error: building repo {0} failed'.format(repo_name))
        sys.exit(-2)
    logging.info('->Finished building repo {0}.'.format(repo_name))


def deploy_pc(settings):
    # extract PhenomeCentral distribution files to the target installation directory
    logging.info('Started extracting PhenomeCentral distribution files to the target installation directory {0} ...'.format(settings.this_build_deploy_dir))
    assert os.path.isdir(settings.pc_distrib_dir)
    os.chdir(settings.pc_distrib_dir)
    retcode = subprocess.call(['unzip', 'phenomecentral-standalone*.zip', '-d', settings.this_build_deploy_dir])
    if retcode != 0:
        logging.error('Error: extracting PhenomeCentral distribution files to the target installation directory {0} failed'.format(settings.this_build_deploy_dir))
        sys.exit(-3)
    logging.info('->Finished extracting PhenomeCentral distribution files.'.format(settings.this_build_deploy_dir))


def start_pc(settings):
    # Run PhenomeCentral instance
    logging.info('Starting PhenomeCentral {0} instance ...'.format(settings.build_name))
    os.chdir(os.path.join(settings.this_build_deploy_dir, os.listdir(settings.this_build_deploy_dir)[0]))

    start_filename = './start.sh'

    if platform.system() == 'Windows':
        os.system("sed -i 's/set XWIKI_DATA_DIR=.*/set XWIKI_DATA_DIR=data/' start.bat")
        os.system("sed -i 's/REM set START_OPTS/set START_OPTS/' start.bat")
        start_filename = 'start.bat'
        # os.system("sed -i 's/PAUSE//' start.bat")
        retcode = subprocess.Popen([start_filename], shell=True)
    else:
        log_file = open("webapps/phenotips/resources/serverlog.txt", "wb")
        retcode = subprocess.Popen([start_filename], stdout=log_file, stderr=log_file)

    if retcode != 0:
        logging.error('Error: starting PhenomeCentral {0} instance'.format(settings.build_name))
    else:
        logging.info('<------PhenomeCentral STARTED---->')

    # wait until web server initializes and starts listening to the incoming connections
    time.sleep(30)

    # make initial curl call to trigger PhenomeCentral start up (which is longer and on top of web server startup)
    command = ['curl', TRIGGER_INITIALIZATION_UTL]
    retcode = subprocess.call(command)


def read_vm_metadata():
    # Fetch server metadata (to be used as default values for script parameters)
    response = subprocess.Popen(['curl', '-s', VM_METADATA_URL], stdout=subprocess.PIPE)
    metadata_json_string = response.stdout.readline().decode('ascii')

    vm_metadata = {}
    if metadata_json_string:
        # Convert bytes to string type and string type to dict
        try:
            json_obj = json.loads(metadata_json_string)
            if 'meta' in json_obj:
                vm_metadata = json_obj['meta']
        except:
            pass
    return vm_metadata


def setup_logfile(settings):
    # Wipe out previous log file with the same deployment name if exists
    open('pc_deploy_{0}.log'.format(settings.build_name), 'w').close()

    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='pc_deploy_{0}.log'.format(settings.build_name), level=logging.INFO, format=format_string)

    # clone output to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[SCRIPT] %(levelname)s: %(message)s'))
    logging.getLogger('').addHandler(console)


def parse_args(args, vm_metadata):
    default_parameter_values = {'pn' : DEFAULT_BRANCH_NAME, 'rm' : DEFAULT_BRANCH_NAME, 'pc' : DEFAULT_BRANCH_NAME, 'bn' : DEFAULT_BUILD_NAME}

    for param_name in default_parameter_values:
        if param_name in vm_metadata:
            default_parameter_values[param_name] = vm_metadata[param_name]

    read_from_vm_meta_str = ", as specified in VM metadata";
    pn_read_from_vm = read_from_vm_meta_str if 'pn' in vm_metadata else ""
    rm_read_from_vm = read_from_vm_meta_str if 'rm' in vm_metadata else ""
    pc_read_from_vm = read_from_vm_meta_str if 'pc' in vm_metadata else ""

    parser = ArgumentParser(description='Checks out all the code required to build a fresh PC instance, and then builds and deploys a PC instance.\n\n' +
                                        'Sample usage to build, install and run a pull request form the PN-123 branch: "' +
                                        os.path.basename(__file__) + ' -pn PN-123 --start"', formatter_class=RawTextHelpFormatter)
    parser.add_argument("--start", dest='start_after_deploy',
                      action="store_true",
                      help="unzip and start PhenomeCentral instance after build")
    parser.add_argument("--pn", dest='pn_branch_name',
                      default=default_parameter_values['pn'],
                      help="branch name for Patient Network repo ('{0}' by default".format(default_parameter_values['pn']) + pn_read_from_vm + ")")
    parser.add_argument("--rm", dest='rm_branch_name',
                      default=default_parameter_values['rm'],
                      help="branch name for Remote Matching repo ('{0}' by default".format(default_parameter_values['rm']) + rm_read_from_vm + ")")
    parser.add_argument("--pc", dest='pc_branch_name',
                      default=default_parameter_values['pc'],
                      help="branch name for PhenomeCentral repo ('{0}' by default".format(default_parameter_values['pc']) + pc_read_from_vm + ")")
    parser.add_argument("--build-name", dest='build_name',
                      default=default_parameter_values['bn'],
                      help="custom build name (by default '{0}' or '[pn_branch_name]_[rm_branch_name]_[pc_branch_name]')".format(default_parameter_values['bn']))
    parser.add_argument("--git-dir", dest='git_dir',
                      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'github'),
                      help="path to the GitHub directory to clone repositories (by default the 'github' folder in the directory from where the script runs)")
    parser.add_argument("--deployment-dir", dest='deploy_dir',
                      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deploy'),
                      help="path to the deployment folder that will contain folder for current installation (by default the 'deploy/[build_name]' folder in the directory from where the script runs)")
    args = parser.parse_args()

    # Fill map between repos and their baranch names to build
    args.repositories = {}
    args.repositories[PN_REPOSITORY_NAME] = args.pn_branch_name
    args.repositories[RM_REPOSITORY_NAME] = args.rm_branch_name
    args.repositories[PC_REPOSITORY_NAME] = args.pc_branch_name

    return args


def main(args=sys.argv[1:]):
    vm_metadata = read_vm_metadata()
    settings = parse_args(args, vm_metadata)

    setup_logfile(settings)

    logging.info('Started deployment with arguments: [' + ' '.join(sys.argv[1:]) + ']')
    if len(vm_metadata) > 0:
        logging.info('VM metadata: {0}'.format(str(vm_metadata)))
    else:
        logging.info('No VM metadata available')

    setup_folders(settings)

    build_pc(settings)
    deploy_pc(settings)

    if settings.start_after_deploy:
        start_pc(settings)

if __name__ == '__main__':
    sys.exit(main())

