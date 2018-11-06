#!/usr/bin/env python3.6

"""
Loads test patient data to a running PhenomeCentral instance:
- assumes a "dataset" is represented by a folder in the "datasets" directory, folder name == dataset name
- when uploading data, the directory is examined for the following files:
  1) dataset.xar - assumed to contain only the necessary files, all of the files in the dataset will be uploaded
                  Note that due to the way filenames are passed to the XWiki if there are too many files (hundreds?) the upload will be broken
  2) P*****.json - each file is assumed to be a patient JSON. Those are uploaded via REST as new patients, and then granted all the hardcoded consents
  3) (NOT WORKING YET) F*****.json - each file is assumed to be a family JSON. Those are uploaded via REST as new families
                                     (and all member patients are granted all the hardcoded consents)
  4) (NOT WORKING YET) P00xxxx*.tsv - each file is assumed to be a processed VCF, those are uploaded for the patient matching the P00xxxx

Prepequisite: script requires requests_toolbelt, zipfile and traceback Python libraries
              (pip install requests_toolbelt; pip install zipfile; pip install requests_toolbelt)
"""

from __future__ import with_statement

import sys
import os
import subprocess
import logging
import json
import re
import requests
import zipfile
import traceback

from argparse import ArgumentParser
from base64 import b64encode
from requests import Session
from requests_toolbelt.utils import dump
from requests_toolbelt.multipart.encoder import MultipartEncoder


#######################################################
# Dataset settings & interface to running instance
#######################################################
DATASETS_ROOT_FOLDERNAME = 'datasets'
DATA_XAR_FILENAME = 'dataset.xar'
DATASETS_LIST_FILENAME = 'datasets_list.txt'
#######################################################


#######################################################
# PC settings
#######################################################
DEFAULT_SERVER_PORT = "8080"
CREDENTIALS = 'Admin:admin'
CONSENT_URL = '/rest/patients/{0}/consents/assign'
GRANT_CONSENT_NAMES = ["real", "genetic", "share_history", "share_images", "matching"]
PATIENTS_REST_URL = '/rest/patients'
PATIENTS_REINDEX_REST_URL = '/rest/patients/reindex'
XAR_UPLOAD_URL = '/upload/XWiki/XWikiPreferences'
XAR_IMPORT_URL = '/import/XWiki/XWikiPreferences?'
PROCESSED_EXOMISER_FILES_SRC_PATH = "exomiser"
PROCESSED_EXOMISER_FILES_DEST_PATH = "/home/pcinstall/deploy/phenomecentral-standalone-1.2-SNAPSHOT/data/exomiser"
#######################################################


def list_datasets():
    logging.info('Listing available datasets...')
    datasets_list = []
    dataset_list = os.listdir(DATASETS_ROOT_FOLDERNAME)
    print(dataset_list, file=open(DATASETS_LIST_FILENAME, "w"))
    sys.exit(0)

def compose_url(settings, resource_url):
    prefix = 'https://' if settings.use_https else 'http://'
    return prefix + settings.server_ip + resource_url;

def upload_data(settings):
    logging.info('Starting uploading data {0} to server {1}'.format(settings.dataset_name, settings.server_ip))

    dataset_folder = os.path.join(DATASETS_ROOT_FOLDERNAME, settings.dataset_name)
    if not os.path.isdir(dataset_folder):
        logging.error('Error: dataset folder {0} does not exist'.format(dataset_folder))
        sys.exit(-2)
    else:
        settings.dataset_folder = dataset_folder

    # authorise
    session = get_session(settings)

    # load and, if upload is successful, import XAR file to the running instance
    upload_xar(settings, session, DATA_XAR_FILENAME)

    # load patient data with consents via REST service: after uploading XARs, since XARs assume fixed
    # patient ids, while REST can create new patients with new IDs on top of those imported by XAR
    upload_json_patients(settings, session)

    # Copy sample of processed VCF file to "/data" installation directory
    #copy_processed_VCFs()

    # Call patient reindexing because Solr does not reindex when XAR is imported
    reindex_patients(session, settings)

    logging.info('Finished uploading data {0} to server {1}'.format(settings.dataset_name, settings.server_ip))

def reindex_patients(session, settings):
    logging.info('Reindexing patients...')
    reindex_rest_url = compose_url(settings, PATIENTS_REINDEX_REST_URL)
    req = session.get(reindex_rest_url)
    if req.status_code in [200, 201]:
        logging.info('Reindexed patients successfully')
    else:
        logging.error('Error during reindexing patients {0}'.format(req.status_code))


def copy_processed_VCFs():
    src = os.path.abspath(PROCESSED_EXOMISER_FILES_SRC_PATH)
    dest = os.path.abspath(PROCESSED_EXOMISER_FILES_DEST_PAT)
    logging.info('Copyting exomiser processed VCF files to {0} :'.format(dest))
    if os.path.exists(dest):
        logging.error('exomiser directory alredy exists, deleting it.')
        shutil.rmtree(dest)
    import errno
    import shutil
    try:
        shutil.copytree(src, dest)
    except OSError as e:
        # If the error was caused because the source wasn't a directory, copy as a file
        if e.errno == errno.ENOTDIR:
            shutil.copy(src, dest)
        else:
            print('Exomiser directory not copied. Error: %s' % e)


def get_session(settings):
    session = Session()
    auth = b64encode(CREDENTIALS.encode()).decode()
    session.headers.update({
            'Authorization': 'Basic {0}'.format(auth),
            'Content-Type': 'text/plain',
            'Accept': '*/*'
            })
    base_url = compose_url(settings, '')
    logging.info('Using base server URL {0}'.format(base_url))
    session.head(base_url)
    return session


def upload_json_patients(settings, session):
    logging.info('Searching for JSON files to be uploaded...')

    files_found = False
    for file_name in os.listdir(settings.dataset_folder):
        if file_name.endswith(".json"):
            if file_name.startswith("P"):
                full_file_name = os.path.join(settings.dataset_folder, file_name)
                logging.info('Found Patient JSON file {0}'.format(full_file_name))
                files_found = True
                internal_upload_patient_json(settings, session, full_file_name)

    if not files_found:
        logging.info('* no JSON files found')

def internal_upload_patient_json(settings, session, json_file_name):
    f = open(json_file_name, "r") 
    payload = f.read()

    try:
        payload = json.loads(payload)
    except:
        logging.info('* [ERROR] file does not contain valid JSON data')
        return

    # sample data
    #payload = {
    #    "clinicalStatus" : "affected",
    #    "genes" : [
    #        {"gene":"T", "id":"ENSG00000164458", "status":"candidate"}
    #        ],
    #    "features": [
    #        {"id":"HP:0001363", "label":"Craniosynostosis", "type":"phenotype", "observed":"yes"},
    #        {"id":"HP:0004325", "label":"Decreased body weight", "type":"phenotype", "observed":"yes"}
    #        ]
    #    }

    headers = {'Content-Type': 'application/json'}
    patient_rest_url = compose_url(settings, PATIENTS_REST_URL)
    req = session.post(patient_rest_url, data=json.dumps(payload), headers=headers)
    if req.status_code in [200, 201]:
        logging.info('* created new patient')
        new_patient_id = req.headers['Location'].rsplit("/",1)[1]
        logging.info('* new patient id: {0}'.format(new_patient_id))
        # grant predefined set of consents
        grant_consents(settings, session, new_patient_id, GRANT_CONSENT_NAMES)
    else:
        logging.error('Error: Attempt to load patient failed {0}'.format(req.status_code))
        #d = dump.dump_all(req)
        #logging.error(d.decode('utf-8'))
        sys.exit(-3)


def grant_consents(settings, session, patient_id, consents):
    consents_rest_url = compose_url(settings, CONSENT_URL.format(patient_id))
    logging.info('* updating patient consents using URL {0}'.format(consents_rest_url))

    headers = {'Content-Type': 'application/json'}
    req = session.put(consents_rest_url, data=json.dumps(consents), headers=headers)
    if req.status_code in [200,201]:
        logging.info('* granted consents {0}'.format(str(consents)))
    else:
        logging.error('Error: Attempt to grant patient all consents failed with HTTP code {0}'.format(req.status_code))
        sys.exit(-4)

    logging.info('->Finished loading patients to PhenomeCentral instance.')


# see also:
#   https://github.com/xwiki/xwiki-platform/blob/6bc521593a1e41f69f9a20d03ffe8b7b979f7b59/xwiki-platform-core/xwiki-platform-web/src/main/webapp/resources/uicomponents/widgets/upload.js#L229
#   https://github.com/xwiki/xwiki-platform/blob/6bc521593a1e41f69f9a20d03ffe8b7b979f7b59/xwiki-platform-core/xwiki-platform-web/src/main/webapp/resources/js/xwiki/importer/import.js#L389
def upload_xar(settings, session, xar_file_name):
    full_file_name = os.path.join(settings.dataset_folder, xar_file_name)
    if not os.path.isfile(full_file_name):
        logging.info('Skipping XAR upload: file {0} is not included in the dataset'.format(xar_file_name))
        return

    logging.info('Uploading XAR {0} to the server...'.format(full_file_name))

    # Parsing form token
    xar_import_url = compose_url(settings, XAR_IMPORT_URL)
    result = session.get(xar_import_url)
    if result.status_code != 200:
        logging.error("Can't access XAR upload page {0}, status code {1}".format(xar_import_url, result.status_code))
        sys.exit(-5)

    form_token_match = re.search('name="form_token" content="(.*)"', result.text)
    if not form_token_match:
        logging.error("Can't upload xar, form token not parsed")
        sys.exit(-6)
    else:
        logging.info("* form token: {0}".format(form_token_match.group(1)))

    # Prepare XAR payload for upload
    m_enc = MultipartEncoder( fields={
            'filepath': (xar_file_name, open(full_file_name, 'rb')),
            'xredirect': '/import/XWiki/XWikiPreferences?editor=globaladmin&section=Import',
            'form_token': form_token_match.group(1)} )

    xar_upload_url = compose_url(settings, XAR_UPLOAD_URL)
    req = session.post(xar_upload_url, data=m_enc, headers={'Content-Type': m_enc.content_type}, allow_redirects=False)

    #print("REQ headers: ", req.request.headers)
    #print("REQ body:", req.request.body)
    #print("REPLY STATUS: ", req.status_code)

    if req.status_code in [200, 201, 302]:
        logging.info('* uploaded xar file: {0}'.format(full_file_name))
        import_xar_files(settings, session, full_file_name, xar_file_name)
    else:
        logging.error('Unexpected response ({0}) from uploading XAR file {1}'.format(req.status_code, filename))
        sys.exit(-7)

def import_xar_files(settings, session, full_file_name, xar_file_name):
    logging.info('Importing documents from an uploaded XAR file...')

    payload = 'editor=globaladmin&section=Import&action=import&name=' + xar_file_name + '&historyStrategy=replace&importAsBackup=false&ajax=1'

    # Parse XAR file, loop through list of its files and compose the payload
    zip=zipfile.ZipFile(full_file_name)
    filename_list = zip.namelist()
    for file in filename_list:
        filename = os.path.splitext(os.path.basename(file))[0]
        file_space = os.path.dirname(file)
        if filename in ['package','']:
            continue
        upload_file_name = file_space + "." + filename
        logging.info('- adding file {0} as {1} to the list of imported files'.format(file, upload_file_name))
        name = upload_file_name  + ':'
        payload = payload + '&language_' + name + '=&pages=' + name

    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    xar_import_url = compose_url(settings, XAR_IMPORT_URL)

    #print("Payload: " + str(payload))
    #print("Headers: " + str(headers))

    req = session.post(xar_import_url + payload, headers=headers)
    if req.status_code in [200, 201]:
        logging.info('Imported XWiki documents from XAR file')
    else:
        logging.error('Error: Importing XAR files failed {0}'.format(req.status_code))
        sys.exit(-8)
        # d = dump.dump_all(req)
        # logging.error(d.decode('utf-8'))


def setup_logfile(settings):
    if settings.action == 'list-datasets':
        log_name = "dataset_list.log"
        web_accessible_log_file = None
    else:
        log_name = "upload_data.log";
        web_accessible_log_file = 'webapps/phenotips/resources/latest_data_upload.log'

    # Wipe out previous log file with the same deployment name if exists
    open(log_name, 'w').close()

    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename=log_name, level=logging.INFO, format=format_string)

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
    parser = ArgumentParser()
    parser.add_argument("--action", dest='action', required=True,
                      help="either `list-datasets` or `upload-dataset`");
    parser.add_argument("--ip", dest='server_ip',
                      help="when uploading datasets, the base address of the server that should get the dataset (e.g. `localhost:8080`)");
    parser.add_argument("--dataset-name", dest='dataset_name',
                      help="when uploading datasets, the name of the dataset to be uploaded");
    parser.add_argument("--use-https", dest='use_https',
                      action="store_true",
                      help="use HTTPS instead of HTTp to connect to the server")
    args = parser.parse_args()

    if args.action == 'upload-dataset' and (args.server_ip is None or args.dataset_name is None):
        parser.error("Action 'upload-dataset' requires --ip and --dataset-name")

    if args.server_ip is not None and ":" not in args.server_ip:
        args.server_ip += ":" + DEFAULT_SERVER_PORT

    return args

def main(args=sys.argv[1:]):
    settings = parse_args(args)
    setup_logfile(settings)

    try:
        if settings.action == 'list-datasets':
            list_datasets()
        else:
            upload_data(settings)
    except Exception:
        logging.error('Exception: [{0}]'.format(traceback.format_exc()))
        sys.exit(-1)

if __name__ == '__main__':
    sys.exit(main())