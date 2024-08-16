# Required information about each variable we want to look at
DATA_PARAMS = {
    "tp": {
        "name": "Total precipitation",
        "units": "mm/day",
        "normalisation": 0.001,  # Convert from m to mm/day
        "offset": 0,
        "accumulated": True,
    },
    "sp": {
        "name": "Surface pressure",
        "units": "hPa",
        "normalisation": 100,  # Convert from Pa to hPa
        "offset": 0,
        "accumulated": False,
    },
    "msl": {
        "name": "Pressure at mean sea level",
        "units": "hPa",
        "normalisation": 100,  # Convert from Pa to hPa
        "offset": 0,
        "accumulated": False,
    },
    "t2m": {
        "name": "Two metre temperature",
        "units": "deg. C",
        "normalisation": 1,
        "offset": -273.15,  # Convert from Kelvin to deg. C
        "accumulated": False,
    },
    "wind": {
        "name": "Wind speed",
        "units": "m/s",
        "normalisation": 1,
        "offset": 0,
        "accumulated": False,
    },
    "ro": {
        "name": "Surface runoff water",
        "units": "m",
        "normalisation": 1,
        "offset": 0,
        "accumulated": False,
    },
}

OPEN_IFS_DATA_VARIABLES = ["tp", "sp", "msl", "t2m", "ro", "u10", "v10"]

# All forecasts are initialised at 00:00 UTC
# Lead times are 30, 33, 36, 39, 42, 45, 48, 51, 54 hours.
LEAD_START_HOUR = 30
LEAD_END_HOUR = 54

# visualization color schemes
COLOR_SCHEMES = ["ICPAC", "ICPAC_heavy", "KMD", "EMI", "EMI_heavy", "Default"]

# boundary layers
COUNTRY_NAMES = [
    "East Africa",
    "Ethiopia",
    "Kenya",
    "Burundi",
    "Djibouti",
    "Eritrea",
    "Rwanda",
    "Somalia",
    "South Sudan",
    "Sudan",
    "Tanzania",
    "Uganda",
]

ACCUMULATION_UNITS = ["mm/h", "mm/6h", "mm/day", "mm/week"]
ACCUMULATION_TIME = ["6h", "24h"]
VALID_TIME_START_HOUR = ["6", "12", "18", "0", "all"]


# Plot countour levels and their labels
GAN_THRESHOLD_PLOT_LEVELS = [
    0,
    2.5,
    25,
    50,
    75,
    100,
]  # Percentage chance of rain above this value
GAN_THRESHOLD_PLOT_LEVEL_NAMES = [
    "None",
    "Possible",
    "Low",
    "Medium",
    "High",
    "Certain",
]
