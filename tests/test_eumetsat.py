"""Tests for satip.eumetsat."""
import glob
import os
import tempfile
from datetime import datetime, timezone, timedelta

from satip.eumetsat import DownloadManager


def test_download_manager_setup():

    user_key = os.environ.get("EUMETSAT_USER_KEY")
    user_secret = os.environ.get("EUMETSAT_USER_SECRET")

    with tempfile.TemporaryDirectory() as tmpdirname:
        _ = DownloadManager(
            user_key=user_key,
            user_secret=user_secret,
            data_dir=tmpdirname,
            native_file_dir=tmpdirname,
        )

def test_filename_to_datetime():
    """If there were a test here, there would also be a docstring here."""
    pass


def test_data_tailor_identify_available_datasets():
    """If there were a test here, there would also be a docstring here."""

    user_key = os.environ.get("EUMETSAT_USER_KEY")
    user_secret = os.environ.get("EUMETSAT_USER_SECRET")

    start_date = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    end_date = datetime.now(tz=timezone.utc)

    with tempfile.TemporaryDirectory() as tmpdirname:
        download_manager = DownloadManager(
            user_key=user_key,
            user_secret=user_secret,
            data_dir=tmpdirname,
            native_file_dir=tmpdirname,
        )

        datasets = download_manager.identify_available_datasets(
            start_date=start_date.strftime("%Y-%m-%d-%H-%M-%S"),
            end_date=end_date.strftime("%Y-%m-%d-%H-%M-%S"),
            product_id="EO:EUM:DAT:MSG:HRSEVIRI",
        )

        assert len(datasets) > 0


def test_data_tailor():
    """If there were a test here, there would also be a docstring here."""

    user_key = os.environ.get("EUMETSAT_USER_KEY")
    user_secret = os.environ.get("EUMETSAT_USER_SECRET")

    start_date = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    end_date = datetime.now(tz=timezone.utc)

    with tempfile.TemporaryDirectory() as tmpdirname:
        download_manager = DownloadManager(
            user_key=user_key,
            user_secret=user_secret,
            data_dir=tmpdirname,
            native_file_dir=tmpdirname,
        )

        datasets = download_manager.identify_available_datasets(
            start_date=start_date.strftime("%Y-%m-%d-%H-%M-%S"),
            end_date=end_date.strftime("%Y-%m-%d-%H-%M-%S"),
            product_id="EO:EUM:DAT:MSG:HRSEVIRI",
        )

        assert len(datasets) > 0
        # only download one dataset
        datasets = datasets[0:1]

        download_manager.download_tailored_datasets(
            datasets,
            product_id="EO:EUM:DAT:MSG:HRSEVIRI",
        )

        native_files = list(glob.glob(os.path.join(tmpdirname, "*HRSEVIRI")))
        assert len(native_files) > 0

        native_files = list(glob.glob(os.path.join(tmpdirname, "*HRSEVIRI_HRV")))
        assert len(native_files) > 0
