#!/usr/bin/env python3.6

"""
Builds, deploys and runs goithub project according to the provided instructions.

Instructions format: JSON with "build", "deploy" and "run" sections.

Can read instructions from a file or from openstack VM metadata.
"""

import sys
import os
import subprocess
import logging
import shutil
import json
import re
import traceback
from git import Repo
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter

VM_METADATA_URL = "http://169.254.169.254/openstack/2017-02-22/meta_data.json"

DEFAULT_GITHUB_FOLDER = "github"
DEFAULT_DEPLOY_ROOT_FOLDER = "deploy"
DEFAULT_BUILD_NAME = "default_build"

def setup_folders(settings):
    # Wipe GitHub directory for a fresh checkout
    if os.path.isdir(settings.git_dir):
        if settings.no_clean:
            logging.info('Github folder already exists and is left as-is')
        else:
            logging.info('Removing existig github repos in {0}'.format(settings.git_dir))
            shutil.rmtree(settings.git_dir)

    if not os.path.isdir(settings.git_dir):
        os.mkdir(settings.git_dir)

    # Create general deployment directory for all deployments
    if not os.path.isdir(settings.deploy_dir):
        os.mkdir(settings.deploy_dir)

    # Create deployment directory for this current build inside of general deployment directory
    if os.path.isdir(settings.this_build_deploy_dir):
        shutil.rmtree(settings.this_build_deploy_dir)
    os.mkdir(settings.this_build_deploy_dir)

def check_object_has_mandatory_keys(instructions_object, key_list, object_description, settings):
    for key in key_list:
        if key not in instructions_object:
            logging.error('Error: {0} [{1}...] is misconfigured - missing mandatory key {2}'\
                          .format(object_description, str(instructions_object)[:20], key))
            exit_on_fail(settings)

def perform_build(build_instructions, settings):
    logging.info('==> Started build phase...')

    for repository in build_instructions:
        check_object_has_mandatory_keys(repository, ["repo", "branch", "command"], "repository", settings)

        repo_url           = repository["repo"]
        repo_branch        = repository["branch"]
        repo_build_command = repository["command"]

        repo_continue_on_fail = repository["continue_on_fail"] if "continue_on_fail" in repository else False
        repo_subdir = repository["sub_dir"] if "sub_dir" in repository else None

        build_repo(repo_url, repo_branch, repo_build_command, settings, repo_subdir, repo_continue_on_fail)

def build_repo(repo_url, repo_branch, repo_build_command, settings, sub_dir = None, continue_on_fail = False):
    repo_name = os.path.basename(repo_url)

    logging.info('Started building repo {0} @ [{1}] ...'.format(repo_name, repo_url))
    os.chdir(settings.git_dir)
    os.mkdir(repo_name)
    os.chdir(repo_name)

    try:
        Repo.clone_from(repo_url + '.git', '.', branch=repo_branch)
    except:
        logging.error('Error: failed to check out branch [{0}] for repo {1} @ {2}'.format(repo_branch, repo_name, repo_url))
        if continue_on_fail:
            return
        else:
            exit_on_fail(settings)

    logging.info('Successfully cloned and checked out branch [{0}] for repo {1}'.format(repo_branch, repo_name))

    if sub_dir is not None:
        os.chdir(sub_dir)

    # generate the list for subprocess.call(), first entry being the executable,
    # the rest command line parameters, e.g. ['mvn', 'clean', 'install', '-Pquick']
    exec_list = repo_build_command.split();

    # make python wait for os.system build process to finish before building next repo
    log_file = setup_stdout_redirect_file('build-' + repo_name + '.log')
    retcode = subprocess.call(exec_list, shell=True, stdout=log_file, stderr=log_file)
    if retcode != 0:
        logging.error('Error: building repo {0} failed'.format(repo_name))
        if continue_on_fail:
            return
        else:
            exit_on_fail(settings)

    logging.info('-> Finished building repo {0}.'.format(repo_name))


def perform_deploy(deploy_instructions, settings):
    logging.info('==> Started deploy phase...')

    index = 0
    for artefact in deploy_instructions:
        index += 1
        logging.info('Processing deploy artefact #{0}'.format(index))

        check_object_has_mandatory_keys(artefact, ["action", "source_dir", "source_files"], "deployment", settings)

        action = artefact["action"]
        if action != "unzip" and action != "copy":
            logging.error('Error: Unsuported deploy operation: [{0}] in [{1}]'\
                          .format(action, str(artefact)))
            exit_on_fail(settings)

        source_dir = os.path.join(settings.git_dir, artefact["source_dir"])

        source_files = artefact["source_files"]
        if not isinstance(source_files, list):
            source_files = [source_files]

        target_dir_re = artefact["target_dir_re"] if "target_dir_re" in artefact else ""
        target_sub_dir = artefact["target_sub_dir"] if "target_sub_dir" in artefact else ""
        continue_on_fail = artefact["continue_on_fail"] if "continue_on_fail" in artefact else False

        os.chdir(settings.start_directory)
        deploy_artefact(action, source_dir, source_files, target_dir_re, target_sub_dir, continue_on_fail, settings)

def deploy_artefact(action, source_dir, source_files, target_dir_re, target_sub_dir, continue_on_fail, settings):
    assert os.path.isdir(source_dir)

    target_dir = find_dir_by_regexp(settings.this_build_deploy_dir, target_dir_re)

    if target_sub_dir != "":
        target_dir = os.path.join(target_dir, target_sub_dir)

    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)

    for file in source_files:
        if "unzip" == action:
            deploy_artefact_unzip(source_dir, file, target_dir, continue_on_fail, settings)
        elif "copy" == action:
            deploy_artefact_copy(source_dir, file, target_dir, continue_on_fail, settings)

# extract distribution files to the target installation directory
def deploy_artefact_unzip(source_dir, file, target_dir, continue_on_fail, settings):
    source_file_full_path = os.path.join(source_dir, file)

    logging.info('-> Deploying by unzipping files from {0} to the target directory {1} ...'\
                 .format(source_file_full_path, target_dir))

    log_file = setup_stdout_redirect_file('unzip.log')
    retcode = subprocess.call(['unzip', source_file_full_path, '-d', target_dir], stdout=log_file, stderr=log_file)
    if retcode != 0:
        logging.error('Error: extracting {0} distribution files to the target installation directory {1} failed'\
                      .format(source_file_full_path, target_dir))
        if not continue_on_fail:
            exit_on_fail(settings)
    logging.info('-> Finished extracting files from {0}'.format(source_file_full_path))

def deploy_artefact_copy(source_dir, file, target_dir, continue_on_fail, settings):
    source_file_full_path = os.path.join(source_dir, file)

    logging.info('-> Deploying by copying files from {0} to the target directory {1} ...'\
                 .format(source_file_full_path, target_dir))

    retcode = subprocess.call('cp -t ' + target_dir + ' ' + source_file_full_path, shell=True)
    if retcode != 0:
        logging.error('Error: failed to copy {0} to {1}'.format(source_file_full_path, target_dir))
        if not continue_on_fail:
            exit_on_fail(settings)

    logging.info('-> Finished copying files from {0}'.format(source_file_full_path))

def perform_start_instance(run_instructions, settings):
    # Run instance
    logging.info('==> Starting an instance of the {0} project...'.format(settings.build_name))

    running_processes = []

    index = 0
    for executable in run_instructions:
        index += 1
        logging.info('Executing step #{0}'.format(index))
        check_object_has_mandatory_keys(executable, ["command"], "execution instructions", settings)

        command = executable["command"]

        dont_wait = executable["run_and_proceed"] if "run_and_proceed" in executable else False

        stdout_redirect_file = executable["stdout_redirect_file"] if "stdout_redirect_file" in executable else None

        # find out the location of the executable
        if "directory" in executable:
            exec_dir = os.path.join(settings.this_build_deploy_dir, executable["directory"])
        elif "directory_re" in executable:
            exec_dir = find_dir_by_regexp(settings.this_build_deploy_dir, executable["directory_re"])
        else:
            exec_dir = settings.this_build_deploy_dir

        if not os.path.isdir(exec_dir):
            logging.error('Error: the target directory {0} for command {1} does not exist'\
                          .format(exec_dir, command))
            exit_on_fail(settings)

        logging.info('Working directory [{0}]'.format(exec_dir))
        os.chdir(exec_dir)

        log_file = setup_stdout_redirect_file(stdout_redirect_file)

        if dont_wait:
            logging.info('-> Starting [{0}]'.format(command))

            p = subprocess.Popen(command, stdout=log_file, stderr=log_file, shell=True)
            running_processes.append(p)

            logging.info('-> <------ STARTED, PID = [{0}] ------>'.format(p.pid))
        else:
            logging.info('-> Running [{0}]'.format(command))

            retcode = subprocess.call(command, stdout=log_file, stderr=log_file, shell=True)

            logging.info('-> Finished (retcode: {0})'.format(retcode))

    if len(running_processes) > 0:
        # wait for the runnign processes to finish
        logging.info('-> Waiting for {0} processes to finish...'.format(len(running_processes)))
        exit_codes = [p.wait() for p in running_processes]
        logging.info('-> Done. Retcodes: [{0}]'.format(str(exit_codes)))

    logging.info('All done ===============================')

def merge_build_instruction_chunks(raw_metadata):
    if "build_instructions_num_chunks" not in raw_metadata:
        return raw_metadata

    num_pieces = int(raw_metadata["build_instructions_num_chunks"])
    del raw_metadata["build_instructions_num_chunks"]

    logging.info("...assembling `build_instructions` VM metadata from {0} pieces".format(num_pieces))

    assembled_json = ""
    for piece in range(num_pieces):
        chunk_key_name = "build_instructions_" + str(piece)
        assembled_json = assembled_json + raw_metadata[chunk_key_name]
        del raw_metadata[chunk_key_name]

    raw_metadata["build_instructions"] = assembled_json

    return raw_metadata

def read_vm_metadata():
    logging.info("Reading VM metadata...")

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
            logging.info("Error parsing metadata JSON")

    return merge_build_instruction_chunks(vm_metadata)

def exit_on_fail(settings):
    mark_progress("failed", settings)
    sys.exit(-1)

def mark_progress(stage_name, settings = None):
    if settings is not None:
        os.chdir(settings.start_directory)
    open('__' + stage_name + '.indicator', 'w').close()

def find_dir_by_regexp(containing_dir, dir_regexp):
    if dir_regexp is None or dir_regexp == "":
        return containing_dir

    for file in os.listdir(containing_dir):
        if re.match(dir_regexp, file):
            return os.path.join(containing_dir, file)

    logging.error('Directory [{0}] not found in [{1}]'.format(dir_regexp, containing_dir))
    return containing_dir

def setup_stdout_redirect_file(file_name):
    if file_name is not None:
        redirect_file = open(file_name, "wb")
    else:
        redirect_file = None
    return redirect_file

def setup_logfile():
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


def read_instructions_file(file_name):
    with open(file_name) as instructions_file:
        instructions_string = instructions_file.read()
        # remove comments in the custom format "### ...."
        instructions_string = re.sub(r"\s*###.*?\n", "\n", instructions_string)
        return instructions_string


def parse_args(vm_metadata):
    logging.info("Parsing command line arguments...")

    if "build_name" in vm_metadata:
        use_build_name = vm_metadata["build_name"]
        use_build_name_description = use_build_name + "(from VM metadata)"
    else:
        use_build_name = DEFAULT_BUILD_NAME
        use_build_name_description = use_build_name

    if "build_instructions" in vm_metadata:
        build_instructions = vm_metadata["build_instructions"]
    else:
        build_instructions = None

    if '__file__' in vars():
        script_name = os.path.basename(__file__)
        script_dir = os.path.abspath(__file__)
    else:
        script_name = "script.py"
        script_dir = os.path.abspath('')

    parser = ArgumentParser(description='Processes the "build instructions" JSON given to the script, executing the three distinct stages: "build", "post_build" and "run".\n\n' +
                                        'Can either read the instructions JSON from VM metadata parameter "build_instructions" or form the provided file: "' +
                                        script_name + ' --build-instructions-file build_instructions.json --build-name "test build" --no-run', formatter_class=RawTextHelpFormatter)

    parser.add_argument("--build-instructions-file", dest='build_instructions_file',
                      default=None,
                      help="file containing JSON build instructions (see sample_build_instructions.json for an example).\n" +
                           "Overwrites VM metadata parameter 'build_instructions'.")

    parser.add_argument("--no-run", dest='no_run',
                      action="store_true",
                      help="do not execute the run part of the instructions")

    parser.add_argument("--no-clean", dest='no_clean',
                      action="store_true",
                      help="do not remove existing files from local coppies of git repositories (e.g. to perform only deploy after a build)")

    parser.add_argument("--build-name", dest='build_name',
                      default=use_build_name,
                      help=("custom build name which defines the folder the project will be deployed to (by default '{0}').\n" +
                           "Ovetrwrites VM metadata parameter 'build_name'.").format(use_build_name_description))

    parser.add_argument("--git-dir", dest='git_dir',
                      default=os.path.join(script_dir, DEFAULT_GITHUB_FOLDER),
                      help="path to the GitHub directory to clone repositories (by default the 'github' folder in the directory from where the script runs)")

    parser.add_argument("--deployment-dir", dest='deploy_dir',
                      default=os.path.join(script_dir, DEFAULT_DEPLOY_ROOT_FOLDER),
                      help="path to the deployment folder that will contain folder for current installation (by default the 'deploy' folder in the directory from where the script runs)")

    args = parser.parse_args()

    logging.info("Parsed command line args successfully")

    if args.build_instructions_file is None:
        if build_instructions is None:
            logging.error("The build/deploy instructions were not provided.\n" +\
                          "Please either set `build_instructions` VM metadata parameter, or use --build-instructions-file command line parameter\n")
            parser.error("The build/deploy instructions were not provided.")
        else:
            args.build_instructions = build_instructions
    else:
        args.build_instructions = read_instructions_file(args.build_instructions_file)

    logging.info("Using build instructions: >>>" + args.build_instructions + "<<<")

    # parse instructions string as JSON
    args.build_instructions = json.loads(args.build_instructions)

    args.start_directory = script_dir

    if not os.path.isabs(args.git_dir):
        args.git_dir = os.path.join(args.start_directory, args.git_dir)
    if not os.path.isabs(args.deploy_dir):
        args.deploy_dir = os.path.join(args.start_directory, args.deploy_dir)
    args.this_build_deploy_dir = os.path.join(args.deploy_dir, args.build_name)

    return args


def main():
    setup_logfile()

    logging.info('==> Started deployment with arguments: [' + ' '.join(sys.argv[1:]) + ']')

    vm_metadata = read_vm_metadata()

    if len(vm_metadata) > 0:
        logging.info('VM metadata: {0}'.format(str(vm_metadata)))
    else:
        logging.info('No VM metadata available')

    settings = parse_args(vm_metadata)

    mark_progress("started", settings)

    #print("Settings: ", str(settings))

    logging.info('Build name: {0}'.format(settings.build_name))
    logging.info('Deployment directory: {0}'.format(settings.this_build_deploy_dir))

    setup_folders(settings)

    mark_progress("building", settings)

    if 'build' in settings.build_instructions:
        perform_build(settings.build_instructions["build"], settings)

    if 'deploy' in settings.build_instructions:
        perform_deploy(settings.build_instructions["deploy"], settings)

    if ('run' in settings.build_instructions) and (not settings.no_run):
        mark_progress("starting_instance", settings)
        perform_start_instance(settings.build_instructions["run"], settings)

    mark_progress("finished", settings)
    logging.info('DONE')

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
      logging.error('Exception: [{0}]'.format(traceback.format_exc()))

