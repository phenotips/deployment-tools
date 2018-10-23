#!/usr/bin/env python3.6

"""
Clones, builds and deploys PhenomeCentral instance out of 3 branches of Patient Network,
Remote Matching and PhenomeCentral GitHub repoes.

Once PC build is successfully done, script would unzip and run PC.
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

DEFAULT_BRANCH_NAME = 'master'
DEFAULT_BUILD_NAME = DEFAULT_BRANCH_NAME
PC_GIT_REPOS = {'patient-network' : '', 'remote-matching' : '', 'phenomecentral.org' : ''}
PARENT_PHENOTIPS_GIT_URL = 'https://github.com/phenotips/'
CONSENT_URL = 'http://localhost:8080/rest/patients/{0}/consents/assign'
PATIENTS_REST_URL = 'http://localhost:8080/rest/patients'
CREDENTIALS = 'Admin:admin'
REQUEST_HEADER = 'Content-Type: application/json'
START_TIME = 0
END_TIME = 0

def script(settings):
    # Checkout and build all repositories
    for repo_name in PC_GIT_REPOS.keys():
        os.chdir(settings.git_dir)
        build_repo(repo_name)

    # Unzip PhenomeCentral distribution to the target installation directory
    unzip(settings)

    if settings.start:
        # Start PhenomeCentral instance
        start_pc(settings)

def setup(settings):
    # define custom build name
    if settings.build_name == DEFAULT_BRANCH_NAME and (settings.pn_branch_name != DEFAULT_BRANCH_NAME or settings.rm_branch_name != DEFAULT_BRANCH_NAME or settings.pc_branch_name != DEFAULT_BRANCH_NAME):
        settings.build_name = settings.pn_branch_name + settings.rm_branch_name + settings.pc_branch_name

    settings.pc_distrib_dir = os.path.join(settings.git_dir, 'phenomecentral.org', 'standalone', 'target')

    settings.this_build_deploy_dir = os.path.join(settings.deploy_dir, settings.build_name)

    # Fill map between repos and their baranch names to build
    PC_GIT_REPOS['patient-network'] = settings.pn_branch_name
    PC_GIT_REPOS['remote-matching'] = settings.rm_branch_name
    PC_GIT_REPOS['phenomecentral.org'] = settings.pc_branch_name

    # Wipe GitHub directory for a fresh checkout
    if os.path.isdir(settings.git_dir):
        shutil.rmtree(settings.git_dir)
    os.mkdir(settings.git_dir)

    # Create general deployment directory for all deployments
    if not os.path.isdir(settings.deploy_dir):
        os.mkdir(settings.deploy_dir)

    # Create deployment directory for this current build inside of general deployment directory
    if os.path.isdir(settings.this_build_deploy_dir):
        shutil.rmtree(settings.this_build_deploy_dir)
    os.mkdir(settings.this_build_deploy_dir)

def build_repo(repo_name):
    logging.info('Started building repo {0} ...'.format(repo_name))
    os.mkdir(repo_name)
    os.chdir(repo_name)

    Repo.clone_from(PARENT_PHENOTIPS_GIT_URL + repo_name + '.git', '.', branch=PC_GIT_REPOS[repo_name])
    # make python wait for os.system build process to finish before building next repo
    retcode = subprocess.call(['mvn', 'clean', 'install', '-Pquick'], shell=True)
    if retcode != 0:
        logging.error('Error: building repo {0} failed'.format(repo_name))
    logging.info('->Finished building repo {0}.'.format(repo_name))

def unzip(settings):
    # extract PhenomeCentral distribution files to the target installation directory
    logging.info('Started extracting PhenomeCentral distribution files to the target installation directory {0} ...'.format(settings.this_build_deploy_dir))
    assert os.path.isdir(settings.pc_distrib_dir)
    os.chdir(settings.pc_distrib_dir)
    retcode = subprocess.call(['unzip', 'phenomecentral-standalone*.zip', '-d', settings.this_build_deploy_dir])
    if retcode != 0:
        logging.error('Error: extracting PhenomeCentral distribution files to the target installation directory {0} failed'.format(settings.this_build_deploy_dir))
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
        stdout = open("stdout.txt", "wb")
        stderr = open("stderr.txt", "wb")
        retcode = subprocess.Popen([start_filename], stdout=stdout, stderr=stderr)

    if retcode != 0:
        logging.error('Error: starting PhenomeCentral {0} instance'.format(settings.build_name))
    else:
        logging.info('<------PhenomeCentral STARTED---->')

    # wait until web server initializes and starts listening to the incoming connections
    time.sleep(30)

    # make initial curl call to trigger PhenomeCentral start up (which is longer and on top of web server startup)
    command = ['curl', 'http://localhost:8080']
    retcode = subprocess.call(command)

def read_vm_metadata():
    meta = {'pn' : DEFAULT_BRANCH_NAME, 'rm' : DEFAULT_BRANCH_NAME, 'pc' : DEFAULT_BRANCH_NAME, 'bn' : DEFAULT_BUILD_NAME}

    # Fetch server metadata and use as default values for script parameters
    response = subprocess.Popen(['curl', '-s', 'http://169.254.169.254/openstack/2017-02-22/meta_data.json'], stdout=subprocess.PIPE)
    metadata_json_string = response.stdout.readline().decode('ascii')

    if metadata_json_string:
        # Convert bytes to string type and string type to dict
        try:
            json_obj = json.loads(metadata_json_string)
            meta_json = json_obj['meta']
            if 'pn' in meta_json.keys():
                meta['pn'] = meta_json['pn']
                meta['pn_from_vm'] = True
            if 'rm' in meta_json.keys():
                meta['rm'] = meta_json['rm']
                meta['rm_from_vm'] = True
            if 'pc' in meta_json.keys():
                meta['pc'] = meta_json['pc']
                meta['pc_from_vm'] = True
            if 'bn' in meta_json.keys():
                meta['bn'] = meta_json['bn']
                meta['bn_from_vm'] = True
        except:
            pass
    return meta

def parse_args(args, vm_metadata):
    read_from_vm_meta_str = ", as specified in VM metadata";
    pn_read_from_vm = read_from_vm_meta_str if vm_metadata.get('pn_from_vm', False) else ""
    rm_read_from_vm = read_from_vm_meta_str if vm_metadata.get('rm_from_vm', False) else ""
    pc_read_from_vm = read_from_vm_meta_str if vm_metadata.get('pc_from_vm', False) else ""

    parser = ArgumentParser()
    parser.add_argument("--git-dir", dest='git_dir',
                      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GitHub'),
                      help="path to the GitHub directory to clone repositories (by default the 'GitHub' folder in the directory from where the script runs)")
    parser.add_argument("--pn", dest='pn_branch_name',
                      default=vm_metadata['pn'],
                      help="branch name for Patient Network repo ('{0}' by default ".format(vm_metadata['pn']) + pn_read_from_vm + ")")
    parser.add_argument("--rm", dest='rm_branch_name',
                      default=vm_metadata['rm'],
                      help="branch name for Remote Matching repo ('{0}' by default".format(vm_metadata['rm']) + rm_read_from_vm + ")")
    parser.add_argument("--pc", dest='pc_branch_name',
                      default=vm_metadata['pc'],
                      help="branch name for PhenomeCentral repo ('{0}' by default".format(vm_metadata['pc']) + pc_read_from_vm + ")")
    parser.add_argument("--build-name", dest='build_name',
                      default=vm_metadata['bn'],
                      help="custom build name (by default '{0}' or '[pn_branch_name]_[rm_branch_name]_[pc_branch_name]') if any of branch names provided)".format(vm_metadata['bn']))
    parser.add_argument("--deployment-dir", dest='deploy_dir',
                      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deploy'),
                      help="path to the deployment folder that will contain folder for current installation (by default the 'deploy/[build_name]' folder in the directory from where the script runs)")
    parser.add_argument("--start", dest='start',
                      action="store_true",
                      help="unzip and start PhenomeCentral instance after build")
    args = parser.parse_args()
    return args

def main(args=sys.argv[1:]):
    START_TIME = time.ctime()

    vm_metadata = read_vm_metadata()
    settings = parse_args(args, vm_metadata)

    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='pc_deploy_{0}.log'.format(settings.build_name), level=logging.INFO, format=format_string)
    logging.info('Got server metadata: {0}'.format(str(vm_metadata)))

    # Wipe out previous log file with the same deployment name if exists
    open('pc_deploy_{0}.log'.format(settings.build_name), 'w').close()

    logging.info('Started deployment with arguments: ')
    logging.info('-->>'.join(sys.argv[1:]))

    setup(settings)
    script(settings)

if __name__ == '__main__':
    sys.exit(main())

