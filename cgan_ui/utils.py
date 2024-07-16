import os
import xarray as xr
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from cgan_ui.enums import DataSourceIdentifier
from show_forecasts.data_utils import get_region_extent, get_locations_data
from show_forecasts.constants import (
    LEAD_START_HOUR,
    LEAD_END_HOUR,
    DATA_PARAMS,
    COUNTRY_NAMES,
)


def load_env_file(
    dotenv_path: Path | None = Path("./.env"), override: bool | None = False
):
    if dotenv_path.exists():
        with open(dotenv_path, "r") as fp:
            lines = fp.read().splitlines()  # make a list of lines using brak marks (\n)
        # process values from .env
        env_vars = {}
        for line in lines:
            line = line.strip()
            # skip blank lines, comments and args with no value
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            env_vars.setdefault(key, value)
        # set environment variables
        if override:
            os.environ.update(env_vars)
        else:
            for key, value in env_vars.items():
                os.environ.setdefault(key, value)


def get_locations_data_for_region(region: str | None = None):
    locations = get_locations_data()
    if region is None or region == COUNTRY_NAMES[0]:
        return locations
    return [location for location in locations if location["country"] == region]


def get_possible_forecast_dates(
    data_date: str | None = None, dateback: int | None = 4
) -> list[datetime.date]:
    if data_date is not None:
        return [datetime.strptime(data_date, "%Y-%m-%d").date()]
    now = datetime.now()
    dates = [now.date()]
    for i in range(1, dateback + 1):
        new_date = now - timedelta(days=i)
        dates.append(new_date.date())
    return dates


def get_relevant_forecast_steps(
    start: int | None = 30, final: int | None = 54, step: int | None = 3
) -> list[int]:
    return [step for step in range(start, final + 1, step)]


# data directory structure
# store -> source (ecmwf, gbmc, cgan, jobs)
# for ecmwf, gbmc, cgan; branches to region/year/month/file_name
# for jobs; subdirectories include downloads, grib2, gbmc
def get_data_store_path(source: str, mask_region: str | None = None) -> Path:
    load_env_file()
    store = Path(os.getenv("DATA_STORE_DIR", str(Path("./store")))).absolute()
    data_dir_path = (
        store / source if mask_region is None else store / source / mask_region
    )

    # create directory tree
    if not data_dir_path.exists():
        data_dir_path.mkdir(parents=True)

    return data_dir_path


def get_dataset_file_path(
    source: str, data_date: datetime, file_name: str, mask_region: str | None = None
) -> Path:
    store_path = (
        get_data_store_path(source=source, mask_region=mask_region)
        / str(data_date.year)
        / f"{str(data_date.month).rjust(2, '0')}"
    )

    # create directory tree
    if not store_path.exists():
        store_path.mkdir(parents=True)

    mask_code = "" if mask_region is None else mask_region.replace(" ", "_").lower()
    source_code = DataSourceIdentifier[source].value

    return store_path / f"{mask_code}-{source_code}-{file_name}"


# recursive function that calls itself until all directories in data_path are traversed
def get_directory_files(data_path: Path, files: list[Path] | None = []) -> list[Path]:
    for item in data_path.iterdir():
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(get_directory_files(data_path=item, files=files))
    # TODO: re-factor to remove below filter step. Could be expensive on more data
    return list(set(files))


def get_forecast_data_files(mask_region: str, source: str) -> list[str]:
    store_path = get_data_store_path(source=source, mask_region=mask_region)
    data_files = get_directory_files(data_path=store_path, files=[])
    return [str(dfile).split("/")[-1] for dfile in data_files]


def get_ecmwf_files_for_date(
    data_date: datetime, mask_region: str | None = "East Africa"
) -> list[str]:
    steps = get_relevant_forecast_steps()
    return [
        f"{mask_region.lower().replace(' ', '_')}-open_ifs-{data_date.strftime('%Y%m%d')}000000-{step}h-enfo-ef.nc"
        for step in steps
    ]


def get_forecast_data_dates(
    mask_region: str, source: str, strict: bool | None = True
) -> list[str]:
    data_files = get_forecast_data_files(source=source, mask_region=mask_region)
    data_dates = sorted(
        set(
            [
                dfile.replace(".nc", "").split("-")[2].split("_")[0]
                for dfile in data_files
            ]
        )
    )
    if not strict or source != "ecmwf":
        return list(
            reversed(
                [
                    datetime.strptime(
                        data_date.replace("000000", ""), "%Y%m%d"
                    ).strftime("%b %d, %Y")
                    for data_date in data_dates
                ]
            )
        )
    tmp_dates = []
    for date_str in data_dates:
        data_date = datetime.strptime(date_str.replace("000000", ""), "%Y%m%d")
        files_for_date = get_ecmwf_files_for_date(data_date)
        in_files = [True if dfile in data_files else False for dfile in files_for_date]
        if False not in in_files:
            tmp_dates.append(data_date)
    return [data_date.strftime("%b %d, %Y") for data_date in reversed(tmp_dates)]


def standardize_dataset(d: xr.DataArray | xr.Dataset):
    if "x" in d.dims and "y" in d.dims:
        d = d.rename({"x": "longitude", "y": "longitude"})
    if "lon" in d.dims and "lat" in d.dims:
        d = d.rename({"lon": "longitude", "lat": "latitude"})
    return d


def slice_dataset_by_bbox(ds: xr.Dataset, bbox: list[float]):
    try:
        ds = ds.sel(longitude=slice(bbox[0], bbox[1]))
    except Exception as err:
        logger.error(
            f"failed to slice dataset by bbox with error {err}. Dataset dims: {ds.dims}"
        )
        return None
    else:
        if ds.latitude.values[0] < ds.latitude.values[-1]:
            ds = ds.sel(latitude=slice(bbox[2], bbox[3]))
        else:
            ds = ds.sel(latitude=slice(bbox[3], bbox[2]))
        return ds


def save_to_new_filesystem_structure(
    file_path: Path, source: str, part_to_replace: str | None = None
) -> None:
    ds = standardize_dataset(xr.open_dataset(file_path, decode_times=False))
    fname = file_path.name.replace(part_to_replace, "")
    data_date = datetime.strptime(
        fname.replace(".nc", "").split("-")[0].split("_")[0].replace("000000", ""),
        "%Y%m%d",
    )
    target_file = get_dataset_file_path(
        source=source,
        data_date=data_date,
        file_name=fname,
        mask_region=os.getenv("DEFAULT_MASK", "East Africa"),
    )
    logger.debug(f"migrating dataset file {file_path} to {target_file}")
    errors = []
    try:
        ds.to_netcdf(target_file, mode="w", format="NETCDF4")
    except Exception as error:
        errors.append(f"failed to save {target_file} with error {error}")
    else:
        logger.debug(f"succeefully saved dataset file {file_path} to {target_file}")
        for country_name in COUNTRY_NAMES[1:]:
            # create country slices
            sliced = slice_dataset_by_bbox(
                ds=ds, bbox=get_region_extent(shape_name=country_name)
            )
            if sliced is None:
                errors.append(f"error slicing {file_path.name} for bbox {country_name}")
            else:
                slice_target = get_dataset_file_path(
                    source=source,
                    data_date=data_date,
                    file_name=fname,
                    mask_region=country_name,
                )
                logger.debug(
                    f"migrating dataset slice for {country_name} to {slice_target}"
                )
                try:
                    sliced.to_netcdf(slice_target, mode="w", format="NETCDF4")
                except Exception as error:
                    errors.append(f"failed to save {slice_target} with error {error}")
                else:
                    logger.debug(
                        f"succeefully migrated dataset slice for {country_name}"
                    )
    if not len(errors):
        if "IFS_" not in file_path.name:
            logger.debug(
                f"removing original file {file_path.name} after a successful migration"
            )
            file_path.unlink(missing_ok=True)
    else:
        logger.error(
            f"failed to migrate {target_file.name} with following {len(errors)} Errors: {' <-> '.join(errors)}"
        )


# migrate dataset files from initial filesystem structure to revised.
def migrate_files(source: str):
    store = Path(os.getenv("DATA_STORE_DIR", str(Path("./store")))).absolute()
    match source:
        case "gbmc":
            data_dir = store / "IFS"
            part_to_replace = "IFS_"
        case "cgan":
            data_dir = store / "GAN_forecasts"
            part_to_replace = "GAN_"
        case "ecmwf":
            data_dir = store / "interim" / "EA" / "ecmwf" / "enfo"
            part_to_replace = ""
    data_files = [fpath for fpath in data_dir.iterdir() if fpath.name.endswith(".nc")]
    logger.info(
        f"processing file-structure migration for {len(data_files)} {source} data files"
    )
    # copy data_files to new files path
    for dfile in data_files:
        save_to_new_filesystem_structure(
            file_path=dfile, source=source, part_to_replace=part_to_replace
        )


def set_data_sycn_status(source: str | None = "ecmwf", status: int | None = 1):
    file_name = "post-processed-ifs.log" if source == "cgan" else "ecmwf-open-ifs.log"
    status_file = Path(os.getenv("LOGS_DIR", "./")) / file_name
    # initialize with not-active status
    with open(status_file, "w") as sf:
        sf.write(str(status))


def get_data_sycn_status(source: str | None = "ecmwf") -> int:
    file_name = "post-processed-ifs.log" if source == "cgan" else "ecmwf-open-ifs.log"
    status_file = Path(os.getenv("LOGS_DIR", "./")) / file_name

    if not status_file.exists():
        # initialize with not-active status
        with open(status_file, "w") as sf:
            sf.write("0")

    # check if there is an active data syncronization job
    with open(status_file, "r") as sf:
        return int(sf.read())


# Some info to be clear with dates and times
# Arguments
#    forecast_init_date - A datetime.datetime corresponding to when the forecast was initialised.
def print_forecast_info(forecast_init_date):
    start_date = forecast_init_date + timedelta(hours=LEAD_START_HOUR)
    end_date = forecast_init_date + timedelta(hours=LEAD_END_HOUR)
    print(f"Forecast average: {start_date} - {end_date}")
    print(f"Forecast initialisation: {forecast_init_date.date()} 00:00:00")
    print()


# Lists the variables available for plotting
# Arguments
#    print_variables=True - print a list of the variables (True or False)
# Returns
#    A list of the variable names that can be used for plotting.
def get_possible_variables(print_variables=True):

    keys = list(DATA_PARAMS.keys())
    if print_variables:
        print("Available variables to plot are the following:")
        for i in range(len(keys)):
            print(
                f"{keys[i]:<5} - {DATA_PARAMS[keys[i]]['name']} ({DATA_PARAMS[keys[i]]['units']})"
            )
        print()

    return list(DATA_PARAMS.keys())
