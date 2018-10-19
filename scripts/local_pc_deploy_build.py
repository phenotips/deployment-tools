#!/usr/bin/env python3.6

"""
Clones, builds and deploys PhenomeCentral instance out of 3 branches of Patient Network,
Remote Matching and PhenomeCentral GitHub repoes.
Once PC build is successfully done, script would unzip and run a new instance on VM
with custom build name uppended to the URL (if provided).
Script kills all running PC instances with the provided (or default) build name first.

* This script requires GitPython installed separately.
https://gitpython.readthedocs.io/en/stable/intro.html#installing-gitpython
To install GitPython:
1. securely download and run get-pip.py
  $ curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
2. run get-pip.py
  $ python get-pip.py
3. install gitpython
  $ pip install gitpython
"""

from __future__ import with_statement

import sys
import os
import subprocess
import logging
import shutil
import time

DEFAULT_BRANCH_NAME = 'master'
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

        # load running instance with test data - patient records
        load_data()

def setup(settings):
    # define custom build name
    if settings.build_name == DEFAULT_BRANCH_NAME and (settings.pn_branch_name != DEFAULT_BRANCH_NAME or settings.rm_branch_name != DEFAULT_BRANCH_NAME or settings.pc_branch_name != DEFAULT_BRANCH_NAME):
        settings.build_name = settings.pn_branch_name + '_' + settings.rm_branch_name + '_' + settings.pc_branch_name

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
    from git import Repo
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
    import platform
    if platform.system() == 'Windows':
        os.system("sed -i 's/set XWIKI_DATA_DIR=.*/set XWIKI_DATA_DIR=data/' start.bat")
        os.system("sed -i 's/REM set START_OPTS/set START_OPTS/' start.bat")
        start_filename = 'start.bat'
        retcode = subprocess.Popen([start_filename], shell=True)
    else:
        stdout = open("stdout.txt", "wb")
        stderr = open("stderr.txt", "wb")
        retcode = subprocess.Popen([start_filename], stdout=stdout, stderr=stderr)

    if retcode != 0:
        logging.error('Error: starting PhenomeCentral {0} instance'.format(settings.build_name))
    else:
        logging.info('<------PhenomeCentral STARTED---->')

    # make initial curl UI call to trigger PhenomeCentral start up
    command = ['curl', 'http://localhost:8080']
    retcode = subprocess.call(command)
    time.sleep(90)

def load_data():
    # push patient
    logging.info('Loading patients to PhenomeCentral instance ...')

    data = '{"clinicalStatus":"affected","genes":[{"gene":"T","id":"ENSG00000164458","status":"candidate"}],"features":[{"id":"HP:0001363","label":"Craniosynostosis","type":"phenotype","observed":"yes"},{"id":"HP:0004325","label":"Decreased body weight","type":"phenotype","observed":"yes"}]}'
    command = ['curl', '-u', CREDENTIALS, '-H', REQUEST_HEADER, '-X', 'POST', '-d', data, PATIENTS_REST_URL]
    retcode = subprocess.call(command)
    if retcode != 0:
        logging.error('Error: Attempt to import patient failed')

    # grant all consents
    data = '["real", "genetic", "share_history", "share_images", "matching"]'
    command = ['curl', '-u', CREDENTIALS, '-H', REQUEST_HEADER, '-X', 'PUT', '-d', data, CONSENT_URL.format('P0000001')]
    retcode = subprocess.call(command)
    if retcode != 0:
        logging.error('Error: Attempt to grant patient all consents failed')
    logging.info('->Finished loading patients to PhenomeCentral instance.')

    # TODO: load: families, groups, studies, users
    #       add configurations: remote servers

    END_TIME = time.ctime()
    total_time_sec = END_TIME - START_TIME
    logging.info('TOTAL TIME : {0}, start time {1}, end time {2}'.format(total_time_sec, START_TIME, END_TIME))

def parse_args(args):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--git-dir", dest='git_dir',
                      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GitGub'),
                      help="path to the GitHub directory to clone repositories (by default the 'GitHub' folder in the directory from where the script runs)")
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
    settings = parse_args(args)
    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='pc_deploy_{0}.log'.format(settings.build_name), level=logging.INFO, format=format_string)
    # Wipe out previous log file with the same deployment name if exists
    open('pc_deploy_{0}.log'.format(settings.build_name), 'w').close()
    logging.info('Started deployment with arguments: ')
    logging.info('-->>'.join(sys.argv[1:]))
    setup(settings)
    script(settings)

if __name__ == '__main__':
    sys.exit(main())