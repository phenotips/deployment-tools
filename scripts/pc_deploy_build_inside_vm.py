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
import traceback
from git import Repo
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter

VM_METADATA_URL = "http://169.254.169.254/openstack/2017-02-22/meta_data.json"

PN_REPOSITORY_NAME = 'patient-network'
RM_REPOSITORY_NAME = 'remote-matching'
PC_REPOSITORY_NAME = 'phenomecentral.org'
PT_REPOSITORY_NAME = 'phenotips'

PROJECTS = { "PhenomeCentral": { "build_order": [PN_REPOSITORY_NAME, RM_REPOSITORY_NAME, PC_REPOSITORY_NAME],
                                 "distrib_dir": os.path.join('phenomecentral.org', 'standalone', 'target'),
                                 "distrib_file": 'phenomecentral-standalone*.zip'
                               },
             "PhenoTips":      { "build_order": [PT_REPOSITORY_NAME],
                                 "distrib_dir": os.path.join('phenotips', 'distribution', 'standalone', 'target'),
                                 "distrib_file": 'phenotips-standalone*.zip'
                               }
           }

REPO_SHORTCUTS = { PN_REPOSITORY_NAME : "pn",
                   RM_REPOSITORY_NAME : "rm",
                   PC_REPOSITORY_NAME : "pc",
                   PT_REPOSITORY_NAME : "pt" }

DEFAULT_BRANCH_NAME = 'master'
DEFAULT_BUILD_NAME = DEFAULT_BRANCH_NAME

PARENT_PHENOTIPS_GIT_URL = 'https://github.com/phenotips/'
TRIGGER_INITIALIZATION_UTL = 'http://localhost:8080'

DEPLOYMENT_TOOLS_REPOSITORY_NAME = 'deployment-tools'
DEPLOYMENT_BRANCH_NAME = 'master'
DEPLOYMENT_REST_SUBDIR = 'pc-test-deploy-rest'
DEPLOYMENT_REST_JAR_FILES = os.path.join(DEPLOYMENT_REST_SUBDIR, 'target', 'pc-test-deploy*.jar')
REST_TARGET_LOCATION = os.path.join("webapps", "phenotips", "WEB-INF", "lib")

WEB_ACCESSIBLE_LOG_FILE = os.path.join("webapps", "phenotips", "resources", "serverlog.txt")


def setup_folders(settings):
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


def build_project(settings):
    # Checkout and build all repositories
    for repo_name in PROJECTS[settings.project]["build_order"]:
        if repo_name not in settings.use_branch:
            logging.error('Error: branch for repo {0} is not specified'.format(repo_name))
            exit_on_fail(settings)
        os.chdir(settings.git_dir)
        build_repo(repo_name, settings.use_branch[repo_name], settings)

def build_reindex_rest(settings):
    os.chdir(settings.git_dir)
    # thi sis not an essential component, so set `continue_on_fail = True`
    build_repo(DEPLOYMENT_TOOLS_REPOSITORY_NAME, DEPLOYMENT_BRANCH_NAME, settings, sub_dir = DEPLOYMENT_REST_SUBDIR, continue_on_fail = True)

def build_repo(repo_name, repo_branch, settings, sub_dir = None, continue_on_fail = False):
    logging.info('Started building repo {0} ...'.format(repo_name))
    os.mkdir(repo_name)
    os.chdir(repo_name)

    try:
        Repo.clone_from(PARENT_PHENOTIPS_GIT_URL + repo_name + '.git', '.', branch=repo_branch)
    except:
        logging.error('Error: failed to check out branch {0} for repo {1}'.format(repo_branch, repo_name))
        if continue_on_fail:
            return
        else:
            exit_on_fail(settings)

    logging.info('Successfully cloned and checked out branch {0} for repo {1}'.format(repo_branch, repo_name))

    if sub_dir is not None:
        os.chdir(sub_dir)

    # make python wait for os.system build process to finish before building next repo
    retcode = subprocess.call(['mvn', 'clean', 'install', '-Pquick'], shell=True)
    if retcode != 0:
        logging.error('Error: building repo {0} failed'.format(repo_name))
        if continue_on_fail:
            return
        else:
            exit_on_fail(settings)
    logging.info('->Finished building repo {0}.'.format(repo_name))


def deploy(settings):
    # extract distribution files to the target installation directory
    logging.info('Started extracting {0} distribution files to the target installation directory {1} ...'.format(settings.project, settings.this_build_deploy_dir))
    assert os.path.isdir(settings.distrib_dir)
    os.chdir(settings.distrib_dir)
    dist_filename = PROJECTS[settings.project]['distrib_file']
    logging.info('->Trying to install from {0}...'.format(dist_filename))
    retcode = subprocess.call(['unzip', dist_filename, '-d', settings.this_build_deploy_dir])
    if retcode != 0:
        logging.error('Error: extracting {0} distribution files to the target installation directory {1} failed'.format(settings.project, settings.this_build_deploy_dir))
        exit_on_fail(settings)
    logging.info('->Finished extracting {0} distribution files.'.format(settings.project))

def deploy_rest(settings):
    # we don't know what was insode the installation .zip file that was extracted in deploy() above
    # - but we can assume ther eis only one installation there, as each branch has its own deploy dir
    deploy_dir_list = os.listdir(settings.this_build_deploy_dir)
    logging.info("Assuming project instalation directgory to be {0}".format(deploy_dir_list[0]))
    jar_file_target_dir = os.path.join(settings.this_build_deploy_dir, deploy_dir_list[0], REST_TARGET_LOCATION)
    jar_file_source = os.path.join(settings.git_dir, DEPLOYMENT_TOOLS_REPOSITORY_NAME, DEPLOYMENT_REST_JAR_FILES)
    logging.info('Copying REST jars {0} to {1} ...'.format(jar_file_source, jar_file_target_dir))
    retcode = subprocess.call('cp -t ' + jar_file_target_dir + ' ' + jar_file_source, shell=True)
    if retcode != 0:
        logging.error('Failed to copy {0} to {1}'.format(jar_file_source, jar_file_target_dir))
        #exit_on_fail(settings)
        # not critical, so no exit
        return
    logging.info('->Finished copying the RESt JAR file.')

def start_instance(settings):
    # Run instance
    logging.info('Starting {0} {1} instance ...'.format(settings.project, settings.build_name))

    work_dir = os.path.join(settings.this_build_deploy_dir, os.listdir(settings.this_build_deploy_dir)[0])
    logging.info('* working directory [{0}]'.format(work_dir))
    os.chdir(work_dir)

    start_filename = './start.sh'

    if platform.system() == 'Windows':
        os.system("sed -i 's/set XWIKI_DATA_DIR=.*/set XWIKI_DATA_DIR=data/' start.bat")
        os.system("sed -i 's/REM set START_OPTS/set START_OPTS/' start.bat")
        start_filename = 'start.bat'
        # os.system("sed -i 's/PAUSE//' start.bat")
        p = subprocess.Popen([start_filename], shell=True)
    else:
        log_file = open(WEB_ACCESSIBLE_LOG_FILE, "wb")
        p = subprocess.Popen([start_filename], stdout=log_file, stderr=log_file)

    logging.info('<------{0} STARTED------>'.format(settings.project))

    # wait until web server initializes and starts listening to the incoming connections
    time.sleep(30)

    logging.info('Sending first request to start {0} initialization process...'.format(settings.project))

    # make initial curl call to trigger instance start up (which is longer and on top of web server startup)
    command = ['curl', TRIGGER_INITIALIZATION_UTL]
    retcode = subprocess.call(command)

    # wait for the server to finish
    logging.info('All done, waiting for instance to shutdown...')
    p.wait()


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

def exit_on_fail(settings):
    mark_progress("failed", settings)
    sys.exit(-1)

def mark_progress(stage_name, settings = None):
    if not settings.inside_vm:
        return

    if settings is not None:
        os.chdir(settings.start_directory)
    open('__' + stage_name + '.indicator', 'w').close()

def setup_logfile(settings):
    if not settings.inside_vm:
        log_file = 'deploy_{0}.log'.format(settings.build_name)
    else:
        log_file = 'deploy.log'

    if os.path.isfile(log_file):
        # wipe out previous log file with the same deployment name if exists
        open(log_file, 'w').close()

    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename=log_file, level=logging.INFO, format=format_string)

    # clone output to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[SCRIPT] %(levelname)s: %(message)s'))
    logging.getLogger('').addHandler(console)


def parse_args(vm_metadata):
    default_parameter_values = {'pn' : DEFAULT_BRANCH_NAME, 'rm' : DEFAULT_BRANCH_NAME, 'pc' : DEFAULT_BRANCH_NAME, 'pt' : DEFAULT_BRANCH_NAME, 'bn' : DEFAULT_BUILD_NAME}

    for param_name in default_parameter_values:
        if param_name in vm_metadata:
            default_parameter_values[param_name] = vm_metadata[param_name]

    parser = ArgumentParser(description='Checks out all the code required to build a fresh PC or PT instance, and then builds and deploys the instance.\n\n' +
                                        'Sample usage to build, install and run a pull request form the PN-123 branch: "' +
                                        os.path.basename(__file__) + ' --project PhenomeCentral --pn PN-123 --start"', formatter_class=RawTextHelpFormatter)

    if 'pr' in vm_metadata and (vm_metadata['pr'] in PROJECTS.keys()):
        # default project to the value specified in VM metadata (if it is a supported project)
        parser.add_argument("--project", dest='project',
                      default=vm_metadata['pr'], choices=PROJECTS.keys(),
                      help="project name (by default '{0}' as specified in VM metadata)".format(vm_metadata['pr']))
    else:
        # make project a required parameter, if no valid project is specified in Vm metadata
        parser.add_argument("--project", dest='project', choices=PROJECTS.keys(), help="project name (required)", required=True)

    parser.add_argument("--start", dest='start_after_deploy',
                      action="store_true",
                      help="unzip and start PhenomeCentral instance after build")

    # options for all the repository branches that may be used
    read_from_vm_meta_str = ", as specified in VM metadata";
    for repo, repo_shortcut in REPO_SHORTCUTS.items():
        parser.add_argument("--" + repo_shortcut, dest=repo_shortcut + '_branch_name',
                      default=default_parameter_values[repo_shortcut],
                      help="branch name for [{0}] repo ('{1}' by default".format(repo, default_parameter_values[repo_shortcut]) + (read_from_vm_meta_str if repo_shortcut in vm_metadata else "") + ")")

    parser.add_argument("--build-name", dest='build_name',
                      default=default_parameter_values['bn'],
                      help="custom build name (by default '{0}' or '[pn_branch_name]_[rm_branch_name]_[pc_branch_name]')".format(default_parameter_values['bn']))
    parser.add_argument("--install-reindex-rest", dest='reindex_rest',
                      action="store_true",
                      help="install a REST endpoint to reindex data (needed for automatic uploading of XAR files)")
    parser.add_argument("--inside-vm", dest='inside_vm',
                      action="store_true",
                      help="trigers generation of extra files and extra logs used by automatic deployment framework")

    start_dir = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--git-dir", dest='git_dir',
                      default=os.path.join(start_dir, 'github'),
                      help="path to the GitHub directory to clone repositories (by default the 'github' folder in the directory from where the script runs)")
    parser.add_argument("--deployment-dir", dest='deploy_dir',
                      default=os.path.join(start_dir, 'deploy'),
                      help="path to the deployment folder that will contain folder for current installation (by default the 'deploy/[build_name]' folder in the directory from where the script runs)")
    args = parser.parse_args()
    return args


def get_settings(args):
    settings = args

    # Fill map between repos and their branch names to build (for selected project)
    all_default_branches = True
    settings.use_branch = {}
    for repo_name in PROJECTS[settings.project]["build_order"]:
        settings.use_branch[repo_name] = getattr(args, REPO_SHORTCUTS[repo_name] + "_branch_name");
        if settings.use_branch[repo_name] != DEFAULT_BRANCH_NAME:
            all_default_branches = False

    settings.start_directory = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(settings.git_dir):
        settings.git_dir = os.path.join(settings.start_directory, args.git_dir)
    if not os.path.isabs(settings.deploy_dir):
        settings.deploy_dir = os.path.join(settings.start_directory, args.deploy_dir)

    # define custom build name if any of the branches use differ from the default
    if settings.build_name == DEFAULT_BUILD_NAME and not all_default_branches:
        settings.build_name = "_".join(settings.use_branch.values())

    settings.distrib_dir = os.path.join(settings.git_dir, PROJECTS[settings.project]["distrib_dir"])

    settings.this_build_deploy_dir = os.path.join(settings.deploy_dir, settings.build_name)

    return settings


def main():
    vm_metadata = read_vm_metadata()

    args = parse_args(vm_metadata)

    settings = get_settings(args)

    mark_progress("started", settings)

    #print("Settings: ", str(settings))
    setup_logfile(settings)

    logging.info('Started deployment with arguments: [' + ' '.join(sys.argv[1:]) + ']')
    if len(vm_metadata) > 0:
        logging.info('VM metadata: {0}'.format(str(vm_metadata)))
    else:
        logging.info('No VM metadata available')

    logging.info('Build name: {0}'.format(settings.build_name))
    logging.info('Expected {0} jar file location: {1}'.format(settings.project, settings.distrib_dir))
    logging.info('Deployment directory for {0}: {1}'.format(settings.project, settings.this_build_deploy_dir))

    setup_folders(settings)

    mark_progress("building", settings)

    build_project(settings)

    deploy(settings)

    if settings.reindex_rest:
        build_reindex_rest(settings)
        deploy_rest(settings)

    if settings.start_after_deploy:
        mark_progress("starting_instance", settings)
        start_instance(settings)

    mark_progress("finished", settings)
    logging.info('DONE')

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
      logging.error('Exception: [{0}]'.format(traceback.format_exc()))



