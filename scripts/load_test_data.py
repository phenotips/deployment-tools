#!/usr/bin/env python3.6

"""
Loads test patient data to the running PhenomeCentral instance
"""

from __future__ import with_statement

import sys
import os
import subprocess
import logging
import json

CONSENT_URL = 'http://localhost:8080/rest/patients/{0}/consents/assign'
PATIENTS_REST_URL = 'http://localhost:8080/rest/patients'
CREDENTIALS = 'Admin:admin'
PATIENT_UPLOAD_REQUEST_HEADER = 'Content-Type: application/json'
XAR_UPLOAD_REQUEST_HEADER = 'Content-Type: text/html;charset=ISO-8859-1'
XAR_UPLOAD_URL = 'http://localhost:8080/upload/XWiki/XWikiPreferences'

def script(settings):
    # push patient
    load_patients()

    # load users
    file = 'users.xar'
    load_xar(file)

    # TODO: load: families, groups, studies, users
    #       add configurations: remote server

def load_xar(file):
    # push patient
    logging.info('Loading XAR to PhenomeCentral instance ...')

    data = open(file)
    command = ['curl', '-u', CREDENTIALS, '-H', XAR_UPLOAD_REQUEST_HEADER, '-X', 'POST', '-d', data, XAR_UPLOAD_URL]

def load_patients():
    # push patient
    logging.info('Loading patients to PhenomeCentral instance ...')

    data = '{"clinicalStatus":"affected","genes":[{"gene":"T","id":"ENSG00000164458","status":"candidate"}],"features":[{"id":"HP:0001363","label":"Craniosynostosis","type":"phenotype","observed":"yes"},{"id":"HP:0004325","label":"Decreased body weight","type":"phenotype","observed":"yes"}]}'
    command = ['curl', '-u', CREDENTIALS, '-H', PATIENT_UPLOAD_REQUEST_HEADER, '-X', 'POST', '-d', data, PATIENTS_REST_URL]
    retcode = subprocess.call(command)
    if retcode != 0:
        logging.error('Error: Attempt to import patient failed')

    # grant all consents
    data = '["real", "genetic", "share_history", "share_images", "matching"]'
    command = ['curl', '-u', CREDENTIALS, '-H', PATIENT_UPLOAD_REQUEST_HEADER, '-X', 'PUT', '-d', data, CONSENT_URL.format('P0000001')]
    retcode = subprocess.call(command)
    if retcode != 0:
        logging.error('Error: Attempt to grant patient all consents failed')
    logging.info('->Finished loading patients to PhenomeCentral instance.')

    # TODO: load: families, groups, studies, users
    #       add configurations: remote servers

def parse_args(args):
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--vcf", dest='load_vcf',
                      action="store_true",
                      help="loads processed vcf files to patients if set, default false")

    args = parser.parse_args()
    return args

def main(args=sys.argv[1:]):
    settings = parse_args(args)
    format_string = '%(levelname)s: %(asctime)s: %(message)s'
    logging.basicConfig(filename='load_data.log', level=logging.INFO, format=format_string)
    # Wipe out previous log file
    open('load_data.log', 'w').close()
    logging.info('Started data load with arguments: ')
    logging.info('-->>'.join(sys.argv[1:]))
    script(settings)

if __name__ == '__main__':
    sys.exit(main())