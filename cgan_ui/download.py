import concurrent
import subprocess
from argparse import ArgumentParser
from datetime import datetime, timedelta
from multiprocessing import cpu_count
from os import getenv
from pathlib import Path

import cfgrib
import xarray as xr
from loguru import logger
from cgan_ui.constants import COUNTRY_NAMES
from cgan_ui.data_utils import get_region_extent

from cgan_ui.constants import OPEN_IFS_DATA_VARIABLES
from cgan_ui.data_sync import run_ecmwf_ifs_sync, run_sftp_rsync
from cgan_ui.utils import (
    get_data_store_path,
    get_data_sycn_status,
    get_dataset_file_path,
    get_forecast_data_dates,
    get_possible_forecast_dates,
    migrate_files,
    save_to_new_filesystem_structure,
    set_data_sycn_status,
    slice_dataset_by_bbox,
    standardize_dataset,
)


def read_dataset(
    file_path: str | Path, mask_area: str | None = COUNTRY_NAMES[0]
) -> xr.Dataset:
    try:
        ds = cfgrib.open_datasets(str(file_path))
    except Exception as err:
        logger.error(f"failed to read {file_path} dataset file with error {err}")
        return None
    if type(ds) is list:
        arrays = []
        for i in range(len(ds)):
            if "number" in ds[i].dims:
                arrays.append(standardize_dataset(ds[i]))
        ds = xr.combine_by_coords(arrays, compat="override")
    return slice_dataset_by_bbox(
        standardize_dataset(ds[OPEN_IFS_DATA_VARIABLES]),
        get_region_extent(shape_name=mask_area),
    )


def post_process_ecmwf_grib2_dataset(
    grib2_file_name: str,
    source: str | None = "ecmwf",
    re_try_times: int | None = 5,
    force_process: bool | None = False,
    mask_region: str | None = COUNTRY_NAMES[0],
    save_for_countries: bool | None = True,
) -> None:
    logger.info(f"executing post-processing task for {grib2_file_name}")
    data_date = datetime.strptime(grib2_file_name.split("-")[0], "%Y%m%d%H%M%S")
    downloads_path = get_data_store_path(source="jobs") / "downloads"
    grib2_file = downloads_path / grib2_file_name
    nc_file_name = grib2_file_name.replace("grib2", "nc")
    nc_file = get_dataset_file_path(
        source=source,
        mask_region=mask_region,
        file_name=nc_file_name,
        data_date=data_date,
    )

    if not nc_file.exists() or force_process:
        logger.info(
            f"post-processing ECMWF open IFS forecast data file {grib2_file_name}"
        )
        for _ in range(re_try_times):
            ds = read_dataset(str(grib2_file))
            if ds is not None:
                break
        if ds is None:
            logger.error(
                f"failed to read {grib2_file} after {re_try_times} unsuccessful trials"
            )
        else:
            try:
                ds.chunk().to_netcdf(
                    nc_file, mode="w", format="NETCDF4", engine="netcdf4"
                )
            except Exception as error:
                logger.error(
                    f"failed to save {source} open ifs dataset slice for {mask_region} with error {error}"
                )
            else:
                if save_for_countries:
                    for country_name in COUNTRY_NAMES[1:]:
                        logger.info(
                            f"processing {source} open ifs dataset slice for {country_name}"
                        )
                        sliced = slice_dataset_by_bbox(
                            ds, get_region_extent(country_name)
                        )
                        slice_file = get_dataset_file_path(
                            source=source,
                            mask_region=country_name,
                            data_date=data_date,
                            file_name=nc_file_name,
                        )
                        logger.debug(
                            f"saving {source} open ifs dataset slice for {country_name} into {slice_file}"
                        )
                        try:
                            sliced.chunk().to_netcdf(
                                path=slice_file,
                                mode="w",
                                format="NETCDF4",
                                engine="netcdf4",
                            )
                        except Exception as error:
                            logger.error(
                                f"failed to save {source} open ifs dataset slice for {mask_region} with error {error}"
                            )
                # remove grib2 file from disk
                archive_dir = get_data_store_path(source="jobs") / "grib2"
                logger.info(f"archiving {grib2_file_name} into {archive_dir}")

                if not archive_dir.exists():
                    archive_dir.mkdir(parents=True)

                try:
                    grib2_file.replace(target=archive_dir / grib2_file_name)
                except Exception as err:
                    logger.error(
                        f"failed to archive {grib2_file_name} to {archive_dir} with error {err}"
                    )
                # remove idx files from the disk
                idx_files = [
                    idxf
                    for idxf in downloads_path.iterdir()
                    if idxf.name.endswith(".idx")
                ]
                for idx_file in idx_files:
                    try:
                        idx_file.unlink()
                    except Exception as err:
                        logger.error(
                            f"failed to delete grib2 index file {idx_file.name} with error {err}"
                        )


def post_process_downloaded_ecmwf_forecasts(source: str | None = "ecmwf") -> None:
    downloads_path = get_data_store_path(source="jobs") / "downloads"
    grib2_files = [dfile.name for dfile in downloads_path.iterdir()]
    logger.info(
        f"starting batch post-processing tasks for {'  <---->  '.join(grib2_files)}"
    )
    for grib2_file in grib2_files:
        post_process_ecmwf_grib2_dataset(
            source=source, grib2_file_name=grib2_file, force_process=True
        )


def syncronize_open_ifs_forecast_data(
    date_str: str | None = None,
    dateback: int | None = 4,
    start_step: int | None = 30,
    final_step: int | None = 54,
) -> None:
    logger.info(
        f"recived IFS open forecast data syncronization job at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    # proceed only if there is no active data syncronization job
    if not get_data_sycn_status():
        logger.info(
            f"starting IFS open forecast data syncronization at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        # generate down download parameters
        data_dates = get_possible_forecast_dates(data_date=date_str, dateback=dateback)

        # set data syncronization status
        set_data_sycn_status(source="ecmwf", status=1)
        open_ifs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=cpu_count()) as executor:
            results = [
                executor.submit(
                    run_ecmwf_ifs_sync,
                    data_date=data_date,
                    start_step=start_step,
                    final_step=final_step,
                )
                for data_date in data_dates
            ]
            for future in concurrent.futures.as_completed(results):
                if future.result() is not None:
                    open_ifs.extend(future.result())

        for grib2_file in open_ifs:
            post_process_ecmwf_grib2_dataset(
                grib2_file_name=grib2_file, force_process=True
            )

        # set data syncronization status
        set_data_sycn_status(source="ecmwf", status=0)


def generate_cgan_forecasts(mask_region: str | None = COUNTRY_NAMES[0]):
    ifs_dates = get_forecast_data_dates(mask_region=mask_region, source="gbmc")
    gan_dates = get_forecast_data_dates(mask_region=mask_region, source="cgan")
    for ifs_date in ifs_dates:
        if ifs_date not in gan_dates:
            logger.info(f"generating cGAN forecast for {ifs_date}")
            # generate forecast for date
            data_date = datetime.strptime(ifs_date, "%b %d, %Y")
            ifs_filename = f"IFS_{data_date.strftime('%Y%m%d')}_00Z.nc"
            try:
                subprocess.call(
                    shell=True,
                    cwd=f'{getenv("WORK_HOME","/opt/mycgan")}/ensemble-cgan/dsrnngan',
                    args=f"python test_forecast.py -f {ifs_filename}",
                )
            except Exception as error:
                logger.error(
                    f"failed to generate cGAN forecast for {ifs_date} with error {error}"
                )
            else:
                cgan_file_path = (
                    get_data_store_path(source="jobs")
                    / "cgan"
                    / f"GAN_{data_date.strftime('%Y%m%d')}.nc"
                )
                save_to_new_filesystem_structure(
                    file_path=cgan_file_path,
                    source="cgan",
                    part_to_replace="GAN_",
                )


def syncronize_post_processed_ifs_data(
    mask_region: str | None = COUNTRY_NAMES[0], verbose: bool | None = False
):
    logger.debug(f"received cGAN data syncronization for {mask_region}")
    if not get_data_sycn_status(source="cgan"):
        # set data syncronization status
        set_data_sycn_status(source="cgan", status=1)
        gan_dates = get_forecast_data_dates(mask_region=mask_region, source="cgan")
        gan_dates = ["Feb 01, 2024"] if not len(gan_dates) else gan_dates
        # final_data_date = datetime.strptime(gan_dates[0].lower(), "%b %d, %Y")
        final_data_date = datetime(2024, 8, 10)
        delta = datetime.now() - final_data_date
        logger.debug(
            f"syncronizing cGAN data for the period {final_data_date.date()} to {datetime.now().date()}"
        )

        ifs_host = getenv("IFS_SERVER_HOST", "domain.example")
        ifs_user = getenv("IFS_SERVER_USER", "username")
        src_ssh = f"{ifs_user}@{ifs_host}"
        assert (
            src_ssh != "username@domain.example"
        ), "you must specify IFS data source server address"
        src_dir = getenv("IFS_DIR", "/data/Operational")
        dest_dir = get_data_store_path(source="jobs") / "gbmc"

        if not dest_dir.exists():
            dest_dir.mkdir(parents=True)
        data_dates = [
            (final_data_date + timedelta(days=i)).strftime("%Y%m%d")
            for i in range(delta.days + 1)
        ]
        gbmc_files = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=cpu_count()) as executor:
            results = [
                executor.submit(
                    run_sftp_rsync,
                    data_date=data_date,
                    source_ssh=src_ssh,
                    source_dir=src_dir,
                    dest_dir=str(dest_dir),
                )
                for data_date in data_dates
            ]

            for future in concurrent.futures.as_completed(results):
                if future.result() is not None:
                    gbmc_files.append(future.result())
        for gbmc_file in gbmc_files:
            dest_file = dest_dir / gbmc_file
            save_to_new_filesystem_structure(
                file_path=dest_file,
                source="gbmc",
                part_to_replace="IFS_",
            )

        generate_cgan_forecasts()
        # set data syncronization status
        set_data_sycn_status(source="cgan", status=0)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--command",
        dest="command",
        type=str,
        default="download",
        help="Command to be executed. Either of download or process.",
    )
    parser.add_argument(
        "-d",
        "--date",
        dest="date_str",
        type=str,
        default=None,
        help="Download ECMWF forecast data for given date",
    )
    parser.add_argument(
        "-p",
        "--period",
        dest="dateback",
        type=int,
        default=4,
        help="Forecasts data time range in days since current date",
    )
    parser.add_argument(
        "-s",
        "--start",
        dest="start_step",
        type=int,
        default=30,
        help="Forecast data start time step",
    )
    parser.add_argument(
        "-f",
        "--final",
        dest="final_step",
        type=int,
        default=54,
        help="Forecast data final time step",
    )
    args = parser.parse_args()
    dict_args = {key: value for key, value in args.__dict__.items() if key != "command"}
    match args.command:
        case "download":
            logger.info(
                f"received ecmwf forecast data download task with parameters {dict_args}"
            )
            syncronize_open_ifs_forecast_data(**dict_args)
        case "process":
            logger.info(
                "received ecmwf forecast datasets post-processing task for initial download grib2 files"
            )
            post_process_downloaded_ecmwf_forecasts()
        case "cgan":
            syncronize_post_processed_ifs_data()
        case "migrate":
            for source in ["ecmwf", "gbmc", "cgan"]:
                migrate_files(source)
        case _:
            logger.error(f"handler for {args.command} not implemented!")
