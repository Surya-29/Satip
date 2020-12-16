# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_eumetsat.ipynb (unless otherwise specified).

__all__ = ['request_access_token', 'query_data_products', 'format_dt_str', 'identify_available_datasets',
           'dataset_id_to_link', 'json_extract', 'extract_metadata', 'metadata_maps', 'check_valid_request',
           'DownloadManager', 'get_dir_size', 'get_filesize_megabytes', 'eumetsat_filename_to_datetime',
           'compress_downloaded_files', 'upload_compressed_files']

# Cell
import numpy as np
import pandas as pd
import dataset

import FEAutils as hlp
from typing import Union, List
import xmltodict
import dotenv
import datetime
import zipfile
import copy
import os
import io
import re
import glob
import logging
import math
import shutil
import subprocess
from pathlib import Path


from requests.auth import HTTPBasicAuth
import requests

from nbdev.showdoc import *
from fastcore.test import test

from satip import utils
from .gcp_helpers import get_eumetsat_filenames, upload_blob

from ipypb import track
from IPython.display import JSON

# Cell
def request_access_token(user_key, user_secret):
    """
    Requests an access token from the EUMETSAT data API

    Parameters:
        user_key: EUMETSAT API key
        user_secret: EUMETSAT API secret

    Returns:
        access_token: API access token

    """

    token_url = 'https://api.eumetsat.int/token'

    data = {
      'grant_type': 'client_credentials'
    }

    r = requests.post(token_url, data=data, auth=(user_key, user_secret))
    access_token = r.json()['access_token']

    return access_token

# Cell
format_dt_str = lambda dt: pd.to_datetime(dt).strftime('%Y-%m-%dT%H:%M:%SZ')

def query_data_products(
    start_date:str='2020-01-01',
    end_date:str='2020-01-02',
    start_index:int=0,
    num_features:int=10_000,
    product_id:str='EO:EUM:DAT:MSG:MSG15-RSS'
) -> requests.models.Response:
    """
    Queries the EUMETSAT data API for the specified data
    product and date-range. The dates will accept any
    format that can be interpreted by `pd.to_datetime`.
    A maximum of 10,000 entries are returned by the API
    so the indexes of the returned entries can be specified.

    Parameters:
        start_date: Start of the query period
        end_date: End of the query period
        start_index: Starting index of returned entries
        num_features: Number of returned entries
        product_id: ID of the EUMETSAT product requested

    Returns:
        r: Response from the request

    """

    search_url = 'https://api.eumetsat.int/data/search-products/os'

    params = {
        'format': 'json',
        'pi': product_id,
        'si': start_index,
        'c': num_features,
        'sort': 'start,time,0',
        'dtstart': format_dt_str(start_date),
        'dtend': format_dt_str(end_date)
    }

    r = requests.get(search_url, params=params)

    assert r.ok, f'Request was unsuccesful - Error code: {r.status_code}'

    return r

# Cell
def identify_available_datasets(start_date: str, end_date: str,
                                product_id='EO:EUM:DAT:MSG:MSG15-RSS'):
    """
    Identifies available datasets from the EUMETSAT data
    API for the specified data product and date-range.
    The dates will accept any format that can be
    interpreted by `pd.to_datetime`.

    Parameters:
        start_date: Start of the query period
        end_date: End of the query period
        product_id: ID of the EUMETSAT product requested

    Returns:
        r: Response from the request

    """

    num_features = 10000
    start_index = 0

    datasets = []
    all_results_returned = False

    while all_results_returned == False:
        r_json = query_data_products(start_date, end_date,
                                     start_index=start_index,
                                     num_features=num_features,
                                     product_id='EO:EUM:DAT:MSG:MSG15-RSS').json()

        datasets += r_json['features']

        num_total_results = r_json['properties']['totalResults']
        num_returned_results = start_index + len(r_json['features'])

        if num_returned_results < num_total_results:
            start_index += num_features
        else:
            all_results_returned = True

        assert num_returned_results == len(datasets), 'Some features have not been appended'

    return datasets

# Cell
dataset_id_to_link = lambda data_id: f'https://api.eumetsat.int/data/download/products/{data_id}'

# Cell
def json_extract(json_obj:Union[dict, list], locators:list):
    extracted_obj = copy.deepcopy(json_obj)

    for locator in locators:
        extracted_obj = extracted_obj[locator]

    return extracted_obj

def extract_metadata(data_dir: str, product_id='EO:EUM:DAT:MSG:MSG15-RSS'):
    with open(f'{data_dir}/EOPMetadata.xml', 'r') as f:
        xml_str = f.read()

    raw_metadata = xmltodict.parse(xml_str)
    metadata_map = metadata_maps[product_id]

    datatypes_to_transform_func = {
        'datetime': pd.to_datetime,
        'str': str,
        'int': int,
        'float': float
    }

    cleaned_metadata = dict()

    for feature, attrs in metadata_map.items():
        location = attrs['location']
        datatype = attrs['datatype']

        value = json_extract(raw_metadata, location)
        formatted_value = datatypes_to_transform_func[datatype](value)

        cleaned_metadata[feature] = formatted_value

    return cleaned_metadata

metadata_maps = {
    'EO:EUM:DAT:MSG:MSG15-RSS': {
        'start_date': {
            'datatype': 'datetime',
            'location': ['eum:EarthObservation', 'om:phenomenonTime', 'gml:TimePeriod', 'gml:beginPosition']
        },
        'end_date': {
            'datatype': 'datetime',
            'location': ['eum:EarthObservation', 'om:phenomenonTime', 'gml:TimePeriod', 'gml:endPosition']
        },
        'result_time': {
            'datatype': 'datetime',
            'location': ['eum:EarthObservation', 'om:resultTime', 'gml:TimeInstant', 'gml:timePosition']
        },
        'platform_short_name': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:procedure', 'eop:EarthObservationEquipment', 'eop:platform', 'eop:Platform', 'eop:shortName']
        },
        'platform_orbit_type': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:procedure', 'eop:EarthObservationEquipment', 'eop:platform', 'eop:Platform', 'eop:orbitType']
        },
        'instrument_name': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:procedure', 'eop:EarthObservationEquipment', 'eop:instrument', 'eop:Instrument', 'eop:shortName']
        },
        'sensor_op_mode': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:procedure', 'eop:EarthObservationEquipment', 'eop:sensor', 'eop:Sensor', 'eop:operationalMode']
        },
        'center_srs_name': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:featureOfInterest', 'eop:Footprint', 'eop:centerOf', 'gml:Point', '@srsName']
        },
        'center_position': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:featureOfInterest', 'eop:Footprint', 'eop:centerOf', 'gml:Point', 'gml:pos']
        },
        'file_name': {
            'datatype': 'str',
            'location': ['eum:EarthObservation', 'om:result', 'eop:EarthObservationResult', 'eop:product', 'eop:ProductInformation', 'eop:fileName', 'ows:ServiceReference', '@xlink:href']
        },
        'file_size': {
            'datatype': 'int',
            'location': ['eum:EarthObservation', 'om:result', 'eop:EarthObservationResult', 'eop:product', 'eop:ProductInformation', 'eop:size', '#text']
        },
        'missing_pct': {
            'datatype': 'float',
            'location': ['eum:EarthObservation', 'eop:metaDataProperty', 'eum:EarthObservationMetaData', 'eum:missingData', '#text']
        },
    }
}

# Cell
def check_valid_request(r: requests.models.Response):
    """
    Checks that the response from the request is valid

    Parameters:
        r: Response object from the request

    """

    class InvalidCredentials(Exception):
        pass

    if r.ok == False:
        if 'Invalid Credentials' in r.text:
            raise InvalidCredentials('The access token passed in the API request is invalid')
        else:
            raise Exception(f'The API request was unsuccesful {r.text} {r.status_code}')

    return

class DownloadManager:
    """
    The DownloadManager class provides a handler for downloading data
    from the EUMETSAT API, managing: retrieval, logging and metadata

    """

    def __init__(self, user_key: str, user_secret: str,
                 data_dir: str, metadata_db_fp: str, log_fp: str,
                 main_logging_level: str='DEBUG', slack_logging_level: str='CRITICAL',
                 slack_webhook_url: str=None, slack_id: str=None,
                 bucket_name=None, bucket_prefix=None, logger_name='EUMETSAT Download'):
        """
        Initialises the download manager by:
        * Setting up the logger
        * Requesting an API access token
        * Configuring the download directory
        * Connecting to the metadata database
        * Adding satip helper functions

        Parameters:
            user_key: EUMETSAT API key
            user_secret: EUMETSAT API secret
            data_dir: Path to the directory where the satellite data will be saved
            metadata_db_fp: Path to where the metadata database is stored/will be saved
            log_fp: Filepath where the logs will be stored
            main_logging_level: Logging level for file and Jupyter
            slack_logging_level: Logging level for Slack
            slack_webhook_url: Webhook for the log Slack channel
            slack_id: Option user-id to mention in Slack
            bucket_name: (Optional) Google Cloud Storage bucket name to check for existing files
            bucket_prefix: (Optional) Prefix for cloud bucket files

        Returns:
            download_manager: Instance of the DownloadManager class

        """

        # Configuring the logger
        self.logger = utils.set_up_logging(logger_name, log_fp,
                                           main_logging_level, slack_logging_level,
                                           slack_webhook_url, slack_id)

        self.logger.info(f'********** Download Manager Initialised **************')

        # Requesting the API access token
        self.user_key = user_key
        self.user_secret = user_secret

        self.request_access_token()

        # Configuring the data directory
        self.data_dir = data_dir

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # Initialising the metadata database
        self.metadata_db = dataset.connect(f'sqlite:///{metadata_db_fp}')
        self.metadata_table = self.metadata_db['metadata']

        # Adding satip helper functions
        self.identify_available_datasets = identify_available_datasets
        self.query_data_products = query_data_products

        # Google Cloud integration
        self.bucket_name = bucket_name
        self.bucket_prefix = bucket_prefix
        self.bucket_filenames = None

        if bucket_name:
            print(f'Checking files in GCP bucket {bucket_name}, this will take a few seconds')
            filenames = get_eumetsat_filenames(bucket_name, prefix=bucket_prefix)
            self.bucket_filenames = [re.match("([A-Z\d.]+-){6}", filename)[0][:-1] for filename in filenames]

        return


    def request_access_token(self, user_key=None, user_secret=None):
        """
        Requests an access token from the EUMETSAT data API.
        If no key or secret are provided then they will default
        to the values provided in the download manager initialisation

        Parameters:
            user_key: EUMETSAT API key
            user_secret: EUMETSAT API secret

        Returns:
            access_token: API access token

        """

        if user_key is None:
            user_key = self.user_key
        if user_secret is None:
            user_secret = self.user_secret

        self.access_token = request_access_token(user_key, user_secret)

        return

    def download_single_dataset(self, data_link:str):
        """
        Downloads a single dataset from the EUMETSAT API

        Parameters:
            data_link: Url link for the relevant dataset

        """

        params = {
            'access_token': self.access_token
        }

        r = requests.get(data_link, params=params)
        check_valid_request(r)

        zipped_files = zipfile.ZipFile(io.BytesIO(r.content))
        zipped_files.extractall(f'{self.data_dir}')

        return


    def check_if_downloaded(self, filenames: List[str]):
        """Checks which files should be downloaded based on
        local file contents and a cloud storage bucket, if specified.

        Parameters:
            filenames: List of filename strings

        Returns:
            List of filenames to download
        """
        in_bucket = []
        local = []
        download = []

        for filename in filenames:
            # get first part of filename for matching
            match = re.match("([A-Z\d.]+-){6}", filename)[0][:-1]

            if self.bucket_name:
                if match in self.bucket_filenames:
                    in_bucket.append(filename)
                    if f'{filename}.nat' in os.listdir(self.data_dir):
                        local.append(filename)
                    continue

            if f'{filename}.nat' in os.listdir(self.data_dir):
                local.append(filename)
                continue

            download.append(filename)

        # Download files if they are not locally downloaded or in the bucket
#         to_download = set(filenames).difference(set(local).union(set(in_bucket)))

        if self.bucket_name:
            self.logger.info(f'{len(filenames)} files queried, {len(in_bucket)} found in bucket, {len(local)} found in {self.data_dir}, {len(download)} to download.')
        else:
            self.logger.info(f'{len(filenames)} files queried, {len(local)} found in {self.data_dir}, {len(download)} to download.')

        return download


    def download_datasets(self, start_date:str, end_date:str, product_id='EO:EUM:DAT:MSG:MSG15-RSS'):
        """
        Downloads a set of dataset from the EUMETSAT API
        in the defined date range and specified product

        Parameters:
            start_date: Start of the requested data period
            end_date: End of the requested data period
            product_id: ID of the EUMETSAT product requested

        """

        # Identifying dataset ids to download
        datasets = identify_available_datasets(start_date, end_date, product_id=product_id)
        dataset_ids = sorted([dataset['id'] for dataset in datasets])

        # Check which datasets to download
        dataset_ids = self.check_if_downloaded(dataset_ids)

        # Downloading specified datasets
        if not dataset_ids:
            self.logger.info('No files will be downloaded. Set DownloadManager bucket_name argument for local download')
            return

        all_metadata = []

        for dataset_id in track(dataset_ids):
            dataset_link = dataset_id_to_link(dataset_id)

            # Download the raw data
            try:
                self.download_single_dataset(dataset_link)
            except:
                self.logger.info('The EUMETSAT access token has been refreshed')
                self.request_access_token()
                self.download_single_dataset(dataset_link)

            # Extract and save metadata
            dataset_metadata = extract_metadata(self.data_dir, product_id=product_id)
            dataset_metadata.update({'downloaded': pd.Timestamp.now()})
            all_metadata += [dataset_metadata]
            self.metadata_table.insert(dataset_metadata)

            # Delete old metadata files
            for xml_file in ['EOPMetadata.xml', 'manifest.xml']:
                xml_filepath = f'{self.data_dir}/{xml_file}'

                if os.path.isfile(xml_filepath):
                    os.remove(xml_filepath)

        df_new_metadata = pd.DataFrame(all_metadata)

        return df_new_metadata

    get_df_metadata = lambda self: pd.DataFrame(self.metadata_table.all()).set_index('id')

# Cell
def get_dir_size(directory='.'):
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)

            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return total_size

# Cell
def get_filesize_megabytes(filename):
    filesize_bytes = os.path.getsize(filename)
    return filesize_bytes / 1E6


def eumetsat_filename_to_datetime(inner_tar_name):
    p = re.compile('^MSG[23]-SEVI-MSG15-0100-NA-(\d*)\.')
    title_match = p.match(inner_tar_name)
    date_str = title_match.group(1)
    return datetime.datetime.strptime(date_str, "%Y%m%d%H%M%S")

# Cell
def compress_downloaded_files(data_dir, sorted_dir, NATIVE_FILESIZE_MB = 102.210123, log=None):
    full_native_filenames = glob.glob(os.path.join(data_dir, '*.nat'))
    print(f'Found {len(full_native_filenames)} native files.')
    if log:
        log.info('Found %d native files.', len(full_native_filenames))

    for full_native_filename in full_native_filenames:
        # Check filesize is correct
        native_filesize_mb = get_filesize_megabytes(full_native_filename)

        if not math.isclose(native_filesize_mb, NATIVE_FILESIZE_MB, abs_tol=1):
            msg = 'Filesize incorrect for {}!  Expected {} MB.  Actual = {} MB.'.format(
                full_native_filename, NATIVE_FILESIZE_MB, native_filesize_mb)
            if log:
                log.error(msg)

        if log:
            log.debug('Compressing %s', full_native_filename)

        completed_process = subprocess.run(['pbzip2', '-5', full_native_filename])
        try:
            completed_process.check_returncode()
        except:
            if log:
                log.exception('Compression failed!')
            print('Compression failed!')
            raise

        EXTENSION = '.bz2'
        full_compressed_filename = full_native_filename + EXTENSION
        compressed_filesize_mb = get_filesize_megabytes(full_compressed_filename)
        if log:
            log.debug('Filesizes: Before compression = %.1f MB. After compression = %.1f MB.  Compressed file is %.1f x the size of the uncompressed file.',
                     native_filesize_mb, compressed_filesize_mb, compressed_filesize_mb / native_filesize_mb)

        base_native_filename = os.path.basename(full_native_filename)
        dt = eumetsat_filename_to_datetime(base_native_filename)
        new_dst_path = os.path.join(sorted_dir, dt.strftime("%Y/%m/%d/%H/%M"))
        if not os.path.exists(new_dst_path):
            os.makedirs(new_dst_path)

        new_dst_full_filename = os.path.join(new_dst_path, base_native_filename + EXTENSION)
        if log:
            log.debug('Moving %s to %s', full_compressed_filename, new_dst_full_filename)

        if os.path.exists(new_dst_full_filename):
            if log:
                log.debug('%s already exists.  Deleting old file', new_dst_full_filename)
            os.remove(new_dst_full_filename)
        shutil.move(src=full_compressed_filename, dst=new_dst_path)

# Cell
def upload_compressed_files(sorted_dir, BUCKET_NAME, PREFIX, log=None):
    paths = Path(sorted_dir).rglob('*.nat.bz2')
    full_compressed_files = [x for x in paths if x.is_file()]
    if log:
        log.info('Found %d compressed files.', len(full_compressed_files))

    for file in full_compressed_files:
        rel_path = os.path.relpath(file.absolute(), sorted_dir)
        upload_blob(bucket_name=BUCKET_NAME, source_file_name=file.absolute(), destination_blob_name=rel_path, prefix=PREFIX)