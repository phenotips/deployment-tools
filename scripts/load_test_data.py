#!/usr/bin/env python3.6

"""
Loads test patient data to the running PhenomeCentral instance.
- Loads patient data and updates patient consents from JSON via PhenoTips patient REST services.
- Loads families, groups, studies, users, and configurations like remote server config from XAR file via platform-core XWiki XAR upload and import services:
    https://github.com/xwiki/xwiki-platform/blob/6bc521593a1e41f69f9a20d03ffe8b7b979f7b59/xwiki-platform-core/xwiki-platform-web/src/main/webapp/resources/uicomponents/widgets/upload.js#L229
    https://github.com/xwiki/xwiki-platform/blob/6bc521593a1e41f69f9a20d03ffe8b7b979f7b59/xwiki-platform-core/xwiki-platform-web/src/main/webapp/resources/js/xwiki/importer/import.js#L389
- Copies sample processed VCF files "exomiser" folder to "/data" installation directory.
"""

from __future__ import with_statement

import sys
import os
import subprocess
import logging
import json
import re
import requests

from argparse import ArgumentParser
from base64 import b64encode
from requests import Session
from requests_toolbelt.utils import dump
from requests_toolbelt.multipart.encoder import MultipartEncoder

CONSENT_URL = 'http://localhost:8080/rest/patients/{0}/consents/assign'
PATIENTS_REST_URL = 'http://localhost:8080/rest/patients'
CREDENTIALS = 'Admin:admin'
XAR_UPLOAD_URL = 'http://localhost:8080/upload/XWiki/XWikiPreferences'
XAR_IMPORT_URL = 'http://localhost:8080/import/XWiki/XWikiPreferences?'
DATA_XAR_FILENAME = 'pc-data.xar'
PROCESSED_EXOMISER_FILES_SRC_PATH = "exomiser"
PROCESSED_EXOMISER_FILES_DEST_PATH = "/home/pcinstall/phenomecentral-standalone-1.2-SNAPSHOT/data/exomiser"


def script(settings):
    # authorise
    session = get_session()

    # load patient data with consents via REST service
    load_patients(session)

    # load and, if upload is successful, import XAR file to the running instance
    upload_xar(session, DATA_XAR_FILENAME)

    # Copy sample of processed VCF file to "/data" installation directory
    if copy_vcf:
        copy_processed_VCFs()


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


def get_session():
    session = Session()
    auth = b64encode(CREDENTIALS.encode()).decode()
    session.headers.update({
            'Authorization': 'Basic {0}'.format(auth),
            'Content-Type': 'text/plain',
            'Accept': '*/*'
            })
    session.head('http://localhost:8080')
    return session


def load_patients(session):
    logging.info('Loading patients to PhenomeCentral instance ...')
    # load patient data
    payload = {
        "clinicalStatus" : "affected",
        "genes" : [
            {"gene":"T", "id":"ENSG00000164458", "status":"candidate"}
            ],
        "features": [
            {"id":"HP:0001363", "label":"Craniosynostosis", "type":"phenotype", "observed":"yes"},
            {"id":"HP:0004325", "label":"Decreased body weight", "type":"phenotype", "observed":"yes"}
            ]
        }

    headers = {'Content-Type': 'application/json'}
    req = session.post(PATIENTS_REST_URL, data=json.dumps(payload), headers=headers)
    if req.status_code in [200, 201]:
        logging.info('Loaded patient data for patient')
        grant_consents(session, consents)
    else:
        logging.error('Error: Attempt to load patient failed {0}'.format(req.status_code))


def grant_consents(session, consents)
    consents = ["real", "genetic", "share_history", "share_images", "matching"]
    req = session.put(CONSENT_URL.format('P0000001'), data=json.dumps(consents), headers=headers)
    if req.status_code in [200, 201]:
        logging.info('Granted patient all consents')
    else:
        logging.error('Error: Attempt to grant patient all consents failed {0}'.format(req.status_code))

    logging.info('->Finished loading patients to PhenomeCentral instance.')


def upload_xar(session, filename):
    logging.info('Loading XAR to PhenomeCentral instance ...')

    # Parsing form token
    result = session.get(XAR_IMPORT_URL)
    form_token_match = re.search('name="form_token" content="(.*)"', result.text)
    if not form_token_match:
        logging.error("Can't upload xar, form token not parsed")
        return
    logging.info("Form token: {0}".format(form_token_match.group(1)))

    # Prepare XAR payload for upload
    filebase = os.path.basename(filename)
    m_enc = MultipartEncoder( fields={
            'filepath': (filebase, open(filebase, 'rb')),
            'xredirect': '/import/XWiki/XWikiPreferences?editor=globaladmin&section=Import',
            'form_token': form_token_match.group(1)} )

    req = session.post(XAR_UPLOAD_URL, data=m_enc, headers={'Content-Type': m_enc.content_type}, allow_redirects=False)

    #print("REQ headers: ", req.request.headers)
    #print("REQ body:", req.request.body)
    #print("REPLY STATUS: ", req.status_code)

    if req.status_code in [200, 201, 302]:
        logging.info('Uploaded xar file: {0}'.format(filename))
        import_xar_files(session, filename)
    else:
        logging.error('Unexpected response ({0}) from uploading XAR file {1}'.format(req.status_code, filename))


def import_xar_files(session, filename):
    logging.info('Importing XAR files to PhenomeCentral instance ...')

    payload = 'editor=globaladmin&section=Import&action=import&name=' + filename + '&historyStrategy=replace&importAsBackup=false&ajax=1'

    # Parse XAR file, loop through list of its files and form a payload string
    # payload shold be formed manualy because it should contain repetitive "pages="
    zip=zipfile.ZipFile(filename)
    filenames = zip.namelist()
    for file in filenames:
        if file == 'package.xml':
            continue
        name_match = re.search('XWiki/(.*).xml', file)
        if not name_match:
            continue
        name = name_match.group(1) + ':'
        payload = payload + '&language_' + name + '=&pages=' + name

    headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}

    req = session.post(XAR_IMPORT_URL + payload, headers=headers)
    d = dump.dump_all(req)
    if req.status_code in [200, 201]:
        logging.info('Imported XAR files')
    else:
        logging.error('Error: Importing XAR files failed {0}'.format(req.status_code))
    logging.info(d.decode('utf-8'))


def parse_args(args):
    parser = ArgumentParser()
    parser.add_argument("--vcf", dest='copy_vcf',
                      action="store_true",
                      help="copies processed vcf files to patients data if set, default false")
    args = parser.parse_args()
    return args

def main(args=sys.argv[1:]):
    settings = parse_args(args)
    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='load_data.log', level=logging.INFO, format=format_string)
    # clone output to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('[SCRIPT] %(levelname)s: %(message)s'))
    logging.getLogger('').addHandler(console)    
    # Wipe out previous log file
    open('load_data.log', 'w').close()
    logging.info('Started data load with arguments: ')
    logging.info('-->>'.join(sys.argv[1:]))
    script(settings)

if __name__ == '__main__':
    sys.exit(main())