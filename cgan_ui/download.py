import sysrsync, subprocess, cfgrib
import xarray as xr
from os import getenv
from pathlib import Path
from typing import Dict
from argparse import ArgumentParser
from datetime import datetime, timedelta
from ecmwf.opendata import Client
from ecmwf.opendata.client import Result
from loguru import logger
from show_forecasts.data_utils import get_region_extent
from cgan_ui.utils import (
    get_data_store_path,
    get_forecast_data_dates,
    get_possible_forecast_dates,
    get_relevant_forecast_steps,
    get_dataset_file_path,
    get_data_sycn_status,
    set_data_sycn_status,
    standardize_dataset,
    slice_dataset_by_bbox,
    migrate_files,
    save_to_new_filesystem_structure,
)
from show_forecasts.constants import COUNTRY_NAMES


def read_dataset(file_path: str | Path) -> list[xr.DataArray]:
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
        return xr.combine_by_coords(arrays, compat="override")


def try_data_download(
    client: Client,
    request: Dict[str, str],
    target_file: str,
    model: str | None = "ifs",
) -> Result | None:
    try:
        result = client.download(
            request=request,
            target=target_file,
        )
    except Exception as err:
        logger.error(
            f"failed to download {model} forecast data for {request['date']} with error {err}"
        )
        Path(target_file).unlink(missing_ok=True)
        return None
    else:
        logger.info(f"downloaded {result.urls[0]} successfully")
        return result


def post_process_ecmwf_grib2_dataset(
    grib2_file_name: str,
    source: str | None = "ecmwf",
    re_try_times: int | None = 5,
    force_process: bool | None = False,
    mask_region: str | None = COUNTRY_NAMES[0],
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
            ds_slice = slice_dataset_by_bbox(
                standardize_dataset(ds), get_region_extent(mask_region)
            )
            ds = None
            logger.debug(
                f"saving {source} open ifs dataset slice for {mask_region} into {nc_file}"
            )
            try:
                ds_slice.chunk().to_netcdf(
                    nc_file, mode="w", format="NETCDF4", engine="netcdf4"
                )
            except Exception as error:
                logger.error(
                    f"failed to save {source} open ifs dataset slice for {mask_region} with error {error}"
                )
            else:
                for country_name in COUNTRY_NAMES[1:]:
                    logger.info(
                        f"processing {source} open ifs dataset slice for {country_name}"
                    )
                    sliced = slice_dataset_by_bbox(
                        ds_slice, get_region_extent(country_name)
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
    source: str | None = "ecmwf",
    model: str | None = "ifs",
    resolution: str | None = "0p25",
    stream: str | None = "enfo",
    date_str: str | None = None,
    dateback: int | None = 4,
    start_step: int | None = 30,
    final_step: int | None = 54,
    re_try_times: int | None = 10,
    force_download: bool | None = False,
    min_grib2_size: float | None = 4.1 * 1024,
    min_nc_size: float | None = 360,
    default_mask: str | None = COUNTRY_NAMES[0],
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
        steps = get_relevant_forecast_steps(start=start_step, final=final_step)

        # construct data store path
        downloads_path = get_data_store_path(source="jobs") / "downloads"
        # create data directory if it doesn't exist
        if not downloads_path.exists():
            downloads_path.mkdir(parents=True, exist_ok=True)

        # create data download client
        client = Client(source=source, model=model, resol=resolution)
        # get latest available forecast date
        latest_fdate = client.latest()

        # set data syncronization status
        set_data_sycn_status(source="ecmwf", status=1)

        for data_date in data_dates:
            if latest_fdate.date() >= data_date:
                requests = [
                    {
                        "date": data_date,
                        "step": step,
                        "stream": stream,
                    }
                    for step in steps
                ]
                grib2_files = []
                for request in requests:
                    file_name = f"{request['date'].strftime('%Y%m%d')}000000-{request['step']}h-{stream}-ef.grib2"
                    mask_file = get_dataset_file_path(
                        source="ecmwf",
                        mask_region=default_mask,
                        data_date=data_date,
                        file_name=file_name.replace(".grib2", ".nc"),
                    )
                    target_file = downloads_path / file_name
                    target_size = (
                        0
                        if not target_file.exists()
                        else target_file.stat().st_size / (1024 * 1024)
                    )
                    mask_size = (
                        0
                        if not mask_file.exists()
                        else mask_file.stat().st_size / (1024 * 1024)
                    )
                    if (
                        not (target_file.exists() or mask_file.exists())
                        or not (
                            target_size >= min_grib2_size or mask_size >= min_nc_size
                        )
                        or force_download
                    ):
                        get_url = client._get_urls(
                            request=request, target=str(target_file), use_index=False
                        )
                        logger.info(
                            f"trying {model} data download with payload {request} on URL {get_url.urls[0]}"
                        )
                        for _ in range(re_try_times):
                            result = try_data_download(
                                client=client,
                                request=request,
                                target_file=str(target_file),
                                model=model,
                            )
                            if result is not None:
                                logger.info(
                                    f"dataset for {model} forecast, {request['step']}h step, {result.datetime} successfully downloaded"
                                )
                                break
                    else:
                        logger.warning(
                            f"data download job for {request['step']}h {data_date} not executed because the file exist. Pass force_download=True to re-download the files"
                        )
                    # be sure grib2 file exists before adding to post-processing queue
                    if target_file.exists():
                        grib2_files.append(file_name)
                for grib2_file in grib2_files:
                    post_process_ecmwf_grib2_dataset(
                        source=source, grib2_file_name=grib2_file, force_process=True
                    )
            else:
                logger.warning(
                    f"IFS forecast data for {data_date} is not available. Please try again later!"
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
        gan_dates = ["Mar 31, 2024"] if not len(gan_dates) else gan_dates
        final_data_date = datetime.strptime(gan_dates[0].lower(), "%b %d, %Y")
        delta = datetime.now() - final_data_date
        logger.debug(
            f"starting cGAN data syncronization for the time since {final_data_date} to {datetime.now()}"
        )
        for i in range(delta.days + 1):
            data_date = final_data_date + timedelta(days=i)
            logger.info(
                f"starting post processed IFS forecast data syncronization for {data_date}"
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

            ifs_filename = f"IFS_{data_date.strftime('%Y%m%d')}_00Z.nc"
            logger.info(
                f"starting syncronization of IFS forecast data file {ifs_filename}"
            )

            try:
                sysrsync.run(
                    source=f"{src_dir}/{ifs_filename}",
                    destination=f"{dest_dir}",
                    source_ssh=src_ssh,
                    private_key=getenv("IFS_PRIVATE_KEY", "/srv/ssl/private.key"),
                    options=["-a", "-v", "-P"],
                    sync_source_contents=False,
                    verbose=verbose,
                )
            except Exception as error:
                logger.error(f"failed to syncronize gbmc ifs with error {error}")
            else:
                dest_file = dest_dir / ifs_filename
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
    match (args.command):
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
