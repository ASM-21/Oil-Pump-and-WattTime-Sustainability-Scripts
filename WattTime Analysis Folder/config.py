"""
WattTime Analysis - Configuration

Central configuration for credentials, signal metadata, region definitions,
and path management for the library/runs architecture.
"""
import os

import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import json

# =============================================================================
# CREDENTIALS
# =============================================================================
WATTTIME_USERNAME = os.getenv("WATTTIME_USERNAME", "")
WATTTIME_PASSWORD = os.getenv("WATTTIME_PASSWORD", "")

# =============================================================================
# API SETTINGS
# =============================================================================
WATTTIME_BASE_URL = "https://api.watttime.org"
API_MAX_DAYS_PER_REQUEST = 32
API_RATE_LIMIT = 3000  # requests per 5 minutes
TOKEN_EXPIRY_MINUTES = 30

# =============================================================================
# SIGNAL METADATA
# =============================================================================
# Each signal has: unit, unit_label (for figures), description, typical_range
SIGNALS = {
    "co2_moer": {
        "name": "Marginal Operating Emissions Rate",
        "unit": "lbs_co2_per_mwh",
        "unit_label": "lbs CO2/MWh",
        "description": "CO2 emissions from the marginal generator",
        "typical_range": (400, 1800),
        "lower_is_better": True,
    },
    "co2_aoer": {
        "name": "Average Operating Emissions Rate",
        "unit": "lbs_co2_per_mwh",
        "unit_label": "lbs CO2/MWh",
        "description": "Average CO2 emissions across all generators",
        "typical_range": (400, 1500),
        "lower_is_better": True,
    },
    "health_damage": {
        "name": "Health Damage Rate",
        "unit": "usd_per_mwh",
        "unit_label": "$/MWh",
        "description": "Monetized health impact from criteria pollutants",
        "typical_range": (0, 100),
        "lower_is_better": True,
    },
}


# =============================================================================
# REGION DEFINITIONS
# =============================================================================
# Signal availability key:
#   MOER = co2_moer (marginal emissions)
#   AOER = co2_aoer (average emissions)
#   HD   = health_damage
#
# Full region metadata
REGIONS = {
    # -------------------------------------------------------------------------
    # MISO Subregions (Midcontinent ISO)
    # -------------------------------------------------------------------------
    "MISO_INDIANAPOLIS": {  # Signals: MOER
        "name": "MISO Indianapolis",
        "timezone": "America/Indiana/Indianapolis",
        "description": "MISO subregion covering Indianapolis area",
        "coordinates": (39.7684, -86.1581),  # Indianapolis, IN
    },
    "MISO_DETROIT": {  # Signals: MOER
        "name": "MISO Detroit",
        "timezone": "America/Detroit",
        "description": "MISO subregion covering Detroit area",
        "coordinates": (42.3314, -83.0458),  # Detroit, MI
    },
    "MISO_GRAND_RAPIDS": {  # Signals: MOER
        "name": "MISO Grand Rapids",
        "timezone": "America/Detroit",
        "description": "MISO subregion covering Grand Rapids area",
        "coordinates": (42.9634, -85.6681),  # Grand Rapids, MI
    },
    "MISO_MINNEAPOLIS": {  # Signals: MOER
        "name": "MISO Minneapolis",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Minneapolis area",
        "coordinates": (44.9778, -93.2650),  # Minneapolis, MN
    },
    "MISO_MADISON": {  # Signals: MOER
        "name": "MISO Madison",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Madison area",
        "coordinates": (43.0731, -89.4012),  # Madison, WI
    },
    "MISO_EAU_CLAIRE": {  # Signals: MOER
        "name": "MISO Eau Claire",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Eau Claire area",
        "coordinates": (44.8113, -91.4985),  # Eau Claire, WI
    },
    "MISO_SAINT_LOUIS": {  # Signals: MOER
        "name": "MISO Saint Louis",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Saint Louis area",
        "coordinates": (38.6270, -90.1994),  # Saint Louis, MO
    },
    "MISO_SPRINGFIELD": {  # Signals: MOER
        "name": "MISO Springfield",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Springfield IL area",
        "coordinates": (39.7817, -89.6501),  # Springfield, IL
    },
    "MISO_LAFAYETTE": {  # Signals: MOER
        "name": "MISO Lafayette",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Lafayette LA area",
        "coordinates": (30.2241, -92.0198),  # Lafayette, LA
    },
    "MISO_NEW_ORLEANS": {  # Signals: MOER
        "name": "MISO New Orleans",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering New Orleans area",
        "coordinates": (29.9511, -90.0715),  # New Orleans, LA
    },
    "MISO_LOWER_MS_RIVER": {  # Signals: MOER
        "name": "MISO Lower MS River",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Lower Mississippi River area",
        "coordinates": (32.2988, -90.1848),  # Jackson, MS
    },
    "MISO_BEAUMONT": {  # Signals: MOER
        "name": "MISO Beaumont",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Beaumont TX area",
        "coordinates": (30.0802, -94.1266),  # Beaumont, TX
    },
    "MISO_N_DAKOTA": {  # Signals: MOER
        "name": "MISO North Dakota",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering North Dakota",
        "coordinates": (46.8772, -96.7898),  # Fargo, ND
    },
    "MISO_MASON_CITY": {  # Signals: MOER
        "name": "MISO Mason City",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Mason City IA area",
        "coordinates": (43.1536, -93.2010),  # Mason City, IA
    },
    "MISO_WORTHINGTON": {  # Signals: MOER
        "name": "MISO Worthington",
        "timezone": "America/Chicago",
        "description": "MISO subregion covering Worthington MN area",
        "coordinates": (43.6200, -95.5964),  # Worthington, MN
    },
    "MISO_UPPER_PENINSULA": {  # Signals: MOER
        "name": "MISO Upper Peninsula",
        "timezone": "America/Detroit",
        "description": "MISO subregion covering Michigan Upper Peninsula",
        "coordinates": (46.5436, -87.3954),  # Marquette, MI
    },

    # -------------------------------------------------------------------------
    # PJM Subregions
    # -------------------------------------------------------------------------
    "PJM_NJ": {  # Signals: MOER
        "name": "PJM New Jersey",
        "timezone": "America/New_York",
        "description": "PJM subregion covering New Jersey",
        "coordinates": (40.0583, -74.4057),  # Trenton, NJ
    },
    "PJM_DC": {  # Signals: MOER
        "name": "PJM DC",
        "timezone": "America/New_York",
        "description": "PJM subregion covering Washington DC area",
        "coordinates": (38.9072, -77.0369),  # Washington, DC
    },
    "PJM_CHICAGO": {  # Signals: MOER
        "name": "PJM Chicago",
        "timezone": "America/Chicago",
        "description": "PJM subregion covering Chicago area",
        "coordinates": (41.8781, -87.6298),  # Chicago, IL
    },
    "PJM_EASTERN_OH": {  # Signals: MOER
        "name": "PJM Eastern Ohio",
        "timezone": "America/New_York",
        "description": "PJM subregion covering Eastern Ohio",
        "coordinates": (41.0997, -80.6495),  # Youngstown, OH
    },
    "PJM_SOUTHWEST_OH": {  # Signals: MOER
        "name": "PJM Southwest Ohio",
        "timezone": "America/New_York",
        "description": "PJM subregion covering Southwest Ohio",
        "coordinates": (39.1031, -84.5120),  # Cincinnati, OH
    },
    "PJM_EASTERN_KY": {  # Signals: MOER
        "name": "PJM Eastern Kentucky",
        "timezone": "America/New_York",
        "description": "PJM subregion covering Eastern Kentucky",
        "coordinates": (38.0406, -84.5037),  # Lexington, KY
    },
    "PJM_WESTERN_KY": {  # Signals: MOER
        "name": "PJM Western Kentucky",
        "timezone": "America/Chicago",
        "description": "PJM subregion covering Western Kentucky",
        "coordinates": (37.7749, -87.1134),  # Owensboro, KY
    },
    "PJM_ROANOKE": {  # Signals: MOER
        "name": "PJM Roanoke",
        "timezone": "America/New_York",
        "description": "PJM subregion covering Roanoke VA area",
        "coordinates": (37.2710, -79.9414),  # Roanoke, VA
    },

    # -------------------------------------------------------------------------
    # CAISO Subregions (California ISO)
    # -------------------------------------------------------------------------
    "CAISO_NORTH": {  # Signals: MOER, HD <<<< ONLY REGION WITH HEALTH DAMAGE
        "name": "California ISO Northern",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering Northern California",
        "coordinates": (37.7749, -122.4194),  # San Francisco, CA
    },
    "CAISO_LONGBEACH": {  # Signals: MOER
        "name": "California ISO Long Beach",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering Long Beach area",
        "coordinates": (33.7701, -118.1937),  # Long Beach, CA
    },
    "CAISO_SANDIEGO": {  # Signals: MOER
        "name": "California ISO San Diego",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering San Diego area",
        "coordinates": (32.7157, -117.1611),  # San Diego, CA
    },
    "CAISO_ESCONDIDO": {  # Signals: MOER
        "name": "California ISO Escondido",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering Escondido area",
        "coordinates": (33.1192, -117.0864),  # Escondido, CA
    },
    "CAISO_PALMSPRINGS": {  # Signals: MOER
        "name": "California ISO Palm Springs",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering Palm Springs area",
        "coordinates": (33.8303, -116.5453),  # Palm Springs, CA
    },
    "CAISO_SANBERNARDINO": {  # Signals: MOER
        "name": "California ISO San Bernardino",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering San Bernardino area",
        "coordinates": (34.1083, -117.2898),  # San Bernardino, CA
    },
    "CAISO_REDDING": {  # Signals: MOER
        "name": "California ISO Redding",
        "timezone": "America/Los_Angeles",
        "description": "CAISO subregion covering Redding area",
        "coordinates": (40.5865, -122.3917),  # Redding, CA
    },

    # -------------------------------------------------------------------------
    # ERCOT Subregions (Texas)
    # -------------------------------------------------------------------------
    "ERCOT_EASTTX": {  # Signals: MOER
        "name": "ERCOT East Texas",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering East Texas",
        "coordinates": (29.7604, -95.3698),  # Houston, TX
    },
    "ERCOT_AUSTIN": {  # Signals: MOER
        "name": "ERCOT Austin",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering Austin area",
        "coordinates": (30.2672, -97.7431),  # Austin, TX
    },
    "ERCOT_SANANTONIO": {  # Signals: MOER
        "name": "ERCOT San Antonio",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering San Antonio area",
        "coordinates": (29.4241, -98.4936),  # San Antonio, TX
    },
    "ERCOT_NORTHCENTRAL": {  # Signals: MOER
        "name": "ERCOT North Central",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering Dallas/Fort Worth area",
        "coordinates": (32.7767, -96.7970),  # Dallas, TX
    },
    "ERCOT_COAST": {  # Signals: MOER
        "name": "ERCOT Coast",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering Texas Gulf Coast",
        "coordinates": (27.8006, -97.3964),  # Corpus Christi, TX
    },
    "ERCOT_SECOAST": {  # Signals: MOER
        "name": "ERCOT South Eastern Coast",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering SE Texas coast",
        "coordinates": (29.3013, -94.7977),  # Galveston, TX
    },
    "ERCOT_SOUTHTX": {  # Signals: MOER
        "name": "ERCOT South Texas",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering South Texas",
        "coordinates": (27.5064, -99.5075),  # Laredo, TX
    },
    "ERCOT_HIDALGO": {  # Signals: MOER
        "name": "ERCOT Hidalgo County",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering Hidalgo County",
        "coordinates": (26.2034, -98.2300),  # McAllen, TX
    },
    "ERCOT_WESTTX": {  # Signals: MOER
        "name": "ERCOT West Texas",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering West Texas",
        "coordinates": (31.7619, -106.4850),  # El Paso, TX
    },
    "ERCOT_PANHANDLE": {  # Signals: MOER
        "name": "ERCOT Northern Panhandle",
        "timezone": "America/Chicago",
        "description": "ERCOT subregion covering Texas Panhandle",
        "coordinates": (35.2220, -101.8313),  # Amarillo, TX
    },

    # -------------------------------------------------------------------------
    # ISONE Subregions (New England)
    # -------------------------------------------------------------------------
    "ISONE_NEMA": {  # Signals: MOER
        "name": "ISONE Northeast Massachusetts",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering NE Massachusetts",
        "coordinates": (42.3601, -71.0589),  # Boston, MA
    },
    "ISONE_SEMA": {  # Signals: MOER
        "name": "ISONE Southeast Massachusetts",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering SE Massachusetts",
        "coordinates": (41.6362, -70.9342),  # New Bedford, MA
    },
    "ISONE_WCMA": {  # Signals: MOER
        "name": "ISONE Western/Central Massachusetts",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering W/C Massachusetts",
        "coordinates": (42.2626, -71.8023),  # Worcester, MA
    },
    "ISONE_CT": {  # Signals: MOER
        "name": "ISONE Connecticut",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering Connecticut",
        "coordinates": (41.7658, -72.6734),  # Hartford, CT
    },
    "ISONE_RI": {  # Signals: MOER
        "name": "ISONE Rhode Island",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering Rhode Island",
        "coordinates": (41.8240, -71.4128),  # Providence, RI
    },
    "ISONE_ME": {  # Signals: MOER
        "name": "ISONE Maine",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering Maine",
        "coordinates": (43.6591, -70.2568),  # Portland, ME
    },
    "ISONE_NH": {  # Signals: MOER
        "name": "ISONE New Hampshire",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering New Hampshire",
        "coordinates": (43.0059, -71.0132),  # Manchester, NH
    },
    "ISONE_VT": {  # Signals: MOER
        "name": "ISONE Vermont",
        "timezone": "America/New_York",
        "description": "ISONE subregion covering Vermont",
        "coordinates": (44.4759, -73.2121),  # Burlington, VT
    },

    # -------------------------------------------------------------------------
    # NYISO Subregions (New York)
    # -------------------------------------------------------------------------
    "NYISO_NYC": {  # Signals: MOER
        "name": "NYISO New York City",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering New York City",
        "coordinates": (40.7128, -74.0060),  # New York City, NY
    },
    "NYISO_LONG": {  # Signals: MOER
        "name": "NYISO Long Island",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Long Island",
        "coordinates": (40.7891, -73.1350),  # Long Island, NY
    },
    "NYISO_HUDSON": {  # Signals: MOER
        "name": "NYISO Hudson Valley",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Hudson Valley",
        "coordinates": (41.7004, -73.9210),  # Poughkeepsie, NY
    },
    "NYISO_CAPITAL": {  # Signals: MOER
        "name": "NYISO Capital",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Albany/Capital region",
        "coordinates": (42.6526, -73.7562),  # Albany, NY
    },
    "NYISO_CENTRAL": {  # Signals: MOER
        "name": "NYISO Central",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Central New York",
        "coordinates": (43.0481, -76.1474),  # Syracuse, NY
    },
    "NYISO_MOHAWK": {  # Signals: MOER
        "name": "NYISO Mohawk Valley",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Mohawk Valley",
        "coordinates": (43.1009, -75.2327),  # Utica, NY
    },
    "NYISO_NORTH": {  # Signals: MOER
        "name": "NYISO North",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Northern New York",
        "coordinates": (44.6995, -73.4529),  # Plattsburgh, NY
    },
    "NYISO_WEST": {  # Signals: MOER
        "name": "NYISO West",
        "timezone": "America/New_York",
        "description": "NYISO subregion covering Western New York",
        "coordinates": (42.8864, -78.8784),  # Buffalo, NY
    },

    # -------------------------------------------------------------------------
    # SPP Subregions (Southwest Power Pool)
    # -------------------------------------------------------------------------
    "SPP_KANSAS": {  # Signals: MOER
        "name": "SPP Kansas",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Kansas",
        "coordinates": (37.6872, -97.3301),  # Wichita, KS
    },
    "SPP_KC": {  # Signals: MOER
        "name": "SPP Kansas City",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Kansas City area",
        "coordinates": (39.0997, -94.5786),  # Kansas City, MO
    },
    "SPP_OKCTY": {  # Signals: MOER
        "name": "SPP Oklahoma City",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Oklahoma City area",
        "coordinates": (35.4676, -97.5164),  # Oklahoma City, OK
    },
    "SPP_SWOK": {  # Signals: MOER
        "name": "SPP Southwest Oklahoma",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering SW Oklahoma",
        "coordinates": (34.6036, -98.3959),  # Lawton, OK
    },
    "SPP_TX": {  # Signals: MOER
        "name": "SPP North Texas",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering North Texas",
        "coordinates": (33.9137, -98.4934),  # Wichita Falls, TX
    },
    "SPP_MEMPHIS": {  # Signals: MOER
        "name": "SPP Memphis",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Memphis area",
        "coordinates": (35.1495, -90.0490),  # Memphis, TN
    },
    "SPP_SPRINGFIELD": {  # Signals: MOER
        "name": "SPP Springfield",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Springfield MO area",
        "coordinates": (37.2090, -93.2923),  # Springfield, MO
    },
    "SPP_SIOUX": {  # Signals: MOER
        "name": "SPP Sioux Falls",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering Sioux Falls area",
        "coordinates": (43.5460, -96.7313),  # Sioux Falls, SD
    },
    "SPP_ND": {  # Signals: MOER
        "name": "SPP North Dakota",
        "timezone": "America/Chicago",
        "description": "SPP subregion covering North Dakota",
        "coordinates": (46.8083, -100.7837),  # Bismarck, ND
    },
    "SPP_WESTNE": {  # Signals: MOER
        "name": "SPP Western Nebraska",
        "timezone": "America/Denver",
        "description": "SPP subregion covering Western Nebraska",
        "coordinates": (41.1403, -100.7601),  # North Platte, NE
    },
    "SPP_FORTPECK": {  # Signals: MOER
        "name": "SPP Fort Peck Reservation",
        "timezone": "America/Denver",
        "description": "SPP subregion covering Fort Peck area",
        "coordinates": (48.0086, -106.4210),  # Wolf Point, MT
    },

    # -------------------------------------------------------------------------
    # Major Standalone Utilities (all have MOER + AOER)
    # -------------------------------------------------------------------------
    "TVA": {  # Signals: MOER, AOER
        "name": "Tennessee Valley Authority",
        "timezone": "America/Chicago",
        "description": "Tennessee Valley Authority service area",
        "coordinates": (36.1627, -86.7816),  # Nashville, TN
    },
    "SOCO": {  # Signals: MOER, AOER
        "name": "Southern Company",
        "timezone": "America/New_York",
        "description": "Southern Company service area (GA, AL)",
        "coordinates": (33.7490, -84.3880),  # Atlanta, GA
    },
    "DUK": {  # Signals: MOER, AOER
        "name": "Duke Energy Carolinas",
        "timezone": "America/New_York",
        "description": "Duke Energy Carolinas service area",
        "coordinates": (35.2271, -80.8431),  # Charlotte, NC
    },
    "CPLE": {  # Signals: MOER, AOER
        "name": "Duke Energy Progress East",
        "timezone": "America/New_York",
        "description": "Duke Energy Progress East service area",
        "coordinates": (35.7796, -78.6382),  # Raleigh, NC
    },
    "CPLW": {  # Signals: MOER, AOER
        "name": "Duke Energy Progress West",
        "timezone": "America/New_York",
        "description": "Duke Energy Progress West service area",
        "coordinates": (35.0527, -78.8784),  # Fayetteville, NC
    },
    "FPL": {  # Signals: MOER, AOER
        "name": "Florida Power & Light",
        "timezone": "America/New_York",
        "description": "Florida Power & Light service area",
        "coordinates": (25.7617, -80.1918),  # Miami, FL
    },
    "FPC": {  # Signals: MOER, AOER
        "name": "Duke Energy Florida",
        "timezone": "America/New_York",
        "description": "Duke Energy Florida service area",
        "coordinates": (28.5383, -81.3792),  # Orlando, FL
    },
    "TEC": {  # Signals: MOER, AOER
        "name": "Tampa Electric Co",
        "timezone": "America/New_York",
        "description": "Tampa Electric service area",
        "coordinates": (27.9506, -82.4572),  # Tampa, FL
    },
    "JEA": {  # Signals: MOER, AOER
        "name": "JEA Jacksonville",
        "timezone": "America/New_York",
        "description": "JEA Jacksonville FL service area",
        "coordinates": (30.3322, -81.6557),  # Jacksonville, FL
    },
    "FMPP": {  # Signals: MOER, AOER
        "name": "Florida Municipal Power Pool",
        "timezone": "America/New_York",
        "description": "Florida Municipal Power Pool",
        "coordinates": (28.0395, -81.9498),  # Lakeland, FL
    },
    "SEC": {  # Signals: MOER, AOER
        "name": "Seminole Electric Cooperative",
        "timezone": "America/New_York",
        "description": "Seminole Electric Cooperative",
        "coordinates": (28.5383, -81.3792),  # Orlando, FL
    },
    "TAL": {  # Signals: MOER, AOER
        "name": "Tallahassee",
        "timezone": "America/New_York",
        "description": "City of Tallahassee FL",
        "coordinates": (30.4383, -84.2807),  # Tallahassee, FL
    },
    "GVL": {  # Signals: MOER, AOER
        "name": "Gainesville Regional Utilities",
        "timezone": "America/New_York",
        "description": "Gainesville Regional Utilities FL",
        "coordinates": (29.6516, -82.3248),  # Gainesville, FL
    },
    "HST": {  # Signals: MOER, AOER
        "name": "Homestead",
        "timezone": "America/New_York",
        "description": "City of Homestead FL",
        "coordinates": (25.4687, -80.4776),  # Homestead, FL
    },
    "SC": {  # Signals: MOER, AOER
        "name": "South Carolina Public Service",
        "timezone": "America/New_York",
        "description": "South Carolina Public Service Authority",
        "coordinates": (33.8361, -79.0400),  # Moncks Corner, SC
    },
    "SCEG": {  # Signals: MOER, AOER
        "name": "Dominion Energy South Carolina",
        "timezone": "America/New_York",
        "description": "Dominion Energy South Carolina",
        "coordinates": (34.0007, -81.0348),  # Columbia, SC
    },
    "PSCO": {  # Signals: MOER, AOER
        "name": "Public Service Co of Colorado",
        "timezone": "America/Denver",
        "description": "Xcel Energy Colorado service area",
        "coordinates": (39.7392, -104.9903),  # Denver, CO
    },
    "PNM": {  # Signals: MOER, AOER
        "name": "Public Service Co of New Mexico",
        "timezone": "America/Denver",
        "description": "PNM service area",
        "coordinates": (35.0844, -106.6504),  # Albuquerque, NM
    },
    "ELE": {  # Signals: MOER, AOER
        "name": "El Paso Electric",
        "timezone": "America/Denver",
        "description": "El Paso Electric service area",
        "coordinates": (31.7619, -106.4850),  # El Paso, TX
    },
    "SRP": {  # Signals: MOER, AOER
        "name": "Salt River Project",
        "timezone": "America/Phoenix",
        "description": "Salt River Project service area",
        "coordinates": (33.4484, -112.0740),  # Phoenix, AZ
    },
    "AZPS": {  # Signals: MOER, AOER
        "name": "Arizona Public Service",
        "timezone": "America/Phoenix",
        "description": "Arizona Public Service service area",
        "coordinates": (33.4484, -112.0740),  # Phoenix, AZ
    },
    "TEPC": {  # Signals: MOER, AOER
        "name": "Tucson Electric Power",
        "timezone": "America/Phoenix",
        "description": "Tucson Electric Power service area",
        "coordinates": (32.2226, -110.9747),  # Tucson, AZ
    },
    "NEVP": {  # Signals: MOER, AOER
        "name": "Nevada Power",
        "timezone": "America/Los_Angeles",
        "description": "NV Energy Southern Nevada",
        "coordinates": (36.1699, -115.1398),  # Las Vegas, NV
    },
    "LDWP": {  # Signals: MOER, AOER
        "name": "Los Angeles DWP",
        "timezone": "America/Los_Angeles",
        "description": "Los Angeles Dept of Water & Power",
        "coordinates": (34.0522, -118.2437),  # Los Angeles, CA
    },
    "IID": {  # Signals: MOER, AOER
        "name": "Imperial Irrigation District",
        "timezone": "America/Los_Angeles",
        "description": "Imperial Irrigation District",
        "coordinates": (32.7920, -115.5631),  # El Centro, CA
    },
    "TID": {  # Signals: MOER, AOER
        "name": "Turlock Irrigation District",
        "timezone": "America/Los_Angeles",
        "description": "Turlock Irrigation District",
        "coordinates": (37.4947, -120.8466),  # Turlock, CA
    },
    "BANC": {  # Signals: MOER, AOER
        "name": "Balancing Authority of Northern California",
        "timezone": "America/Los_Angeles",
        "description": "BANC - Sacramento area",
        "coordinates": (38.5816, -121.4944),  # Sacramento, CA
    },
    "PGE": {  # Signals: MOER, AOER
        "name": "Portland General Electric",
        "timezone": "America/Los_Angeles",
        "description": "Portland General Electric service area",
        "coordinates": (45.5152, -122.6784),  # Portland, OR
    },
    "PACW": {  # Signals: MOER, AOER
        "name": "PacifiCorp West",
        "timezone": "America/Los_Angeles",
        "description": "PacifiCorp West (OR, WA, CA)",
        "coordinates": (45.5152, -122.6784),  # Portland, OR
    },
    "PACE": {  # Signals: MOER, AOER
        "name": "PacifiCorp East",
        "timezone": "America/Denver",
        "description": "PacifiCorp East (UT, WY, ID)",
        "coordinates": (40.7608, -111.8910),  # Salt Lake City, UT
    },
    "IPCO": {  # Signals: MOER, AOER
        "name": "Idaho Power",
        "timezone": "America/Boise",
        "description": "Idaho Power service area",
        "coordinates": (43.6150, -116.2023),  # Boise, ID
    },
    "PSEI": {  # Signals: MOER, AOER
        "name": "Puget Sound Energy",
        "timezone": "America/Los_Angeles",
        "description": "Puget Sound Energy service area",
        "coordinates": (47.6062, -122.3321),  # Seattle, WA
    },
    "SCL": {  # Signals: MOER, AOER
        "name": "Seattle City Light",
        "timezone": "America/Los_Angeles",
        "description": "Seattle City Light service area",
        "coordinates": (47.6062, -122.3321),  # Seattle, WA
    },
    "TPWR": {  # Signals: MOER, AOER
        "name": "Tacoma Power",
        "timezone": "America/Los_Angeles",
        "description": "Tacoma Power service area",
        "coordinates": (47.2529, -122.4443),  # Tacoma, WA
    },
    "AVA": {  # Signals: MOER, AOER
        "name": "Avista Corp",
        "timezone": "America/Los_Angeles",
        "description": "Avista service area (WA, ID)",
        "coordinates": (47.6588, -117.4260),  # Spokane, WA
    },
    "BPA": {  # Signals: MOER, AOER
        "name": "Bonneville Power Administration",
        "timezone": "America/Los_Angeles",
        "description": "BPA Pacific Northwest service area",
        "coordinates": (45.5152, -122.6784),  # Portland, OR
    },
    "CHPD": {  # Signals: MOER, AOER
        "name": "PUD No 1 of Chelan County",
        "timezone": "America/Los_Angeles",
        "description": "Chelan County PUD",
        "coordinates": (47.4235, -120.3103),  # Wenatchee, WA
    },
    "DOPD": {  # Signals: MOER, AOER
        "name": "PUD No 1 of Douglas County",
        "timezone": "America/Los_Angeles",
        "description": "Douglas County PUD",
        "coordinates": (47.4982, -120.1965),  # East Wenatchee, WA
    },
    "GCPD": {  # Signals: MOER, AOER
        "name": "PUD No 2 of Grant County",
        "timezone": "America/Los_Angeles",
        "description": "Grant County PUD",
        "coordinates": (47.1301, -119.2769),  # Moses Lake, WA
    },
    "AECI": {  # Signals: MOER, AOER
        "name": "Associated Electric Coop",
        "timezone": "America/Chicago",
        "description": "Associated Electric Coop service area",
        "coordinates": (37.2090, -93.2923),  # Springfield, MO
    },
    "SPA": {  # Signals: MOER, AOER
        "name": "Southwestern Power Administration",
        "timezone": "America/Chicago",
        "description": "SPA service area",
        "coordinates": (36.1540, -95.9928),  # Tulsa, OK
    },
    "LGEE": {  # Signals: MOER, AOER
        "name": "Louisville Gas & Electric",
        "timezone": "America/Kentucky/Louisville",
        "description": "LG&E service area",
        "coordinates": (38.2527, -85.7585),  # Louisville, KY
    },
    "WACM": {  # Signals: MOER, AOER
        "name": "WAPA Rocky Mountain Region",
        "timezone": "America/Denver",
        "description": "Western Area Power Administration - Rocky Mountain",
        "coordinates": (39.7392, -104.9903),  # Denver, CO
    },
    "WALC": {  # Signals: MOER, AOER
        "name": "WAPA Desert Southwest Region",
        "timezone": "America/Phoenix",
        "description": "Western Area Power Administration - Desert SW",
        "coordinates": (33.4484, -112.0740),  # Phoenix, AZ
    },
    "WAUW": {  # Signals: MOER, AOER
        "name": "WAPA Upper Great Plains West",
        "timezone": "America/Denver",
        "description": "Western Area Power Administration - Upper Great Plains",
        "coordinates": (46.8083, -100.7837),  # Bismarck, ND
    },
    "MPCO": {  # Signals: MOER, AOER
        "name": "Northwestern Energy",
        "timezone": "America/Denver",
        "description": "NorthWestern Energy (MT)",
        "coordinates": (45.7833, -108.5007),  # Billings, MT
    },
    "MISO": {  # Signals: AOER
        "name": "Midcontinent ISO",
        "timezone": "America/Chicago",
        "description": "Midcontinent Independent System Operator",
        "coordinates": (39.7684, -86.1581),  # Indianapolis, IN
    },
    "BPA": {  # Signals: AOER
        "name": "Bonneville Power Administration",
        "timezone": "America/Los_Angeles",
        "description": "Bonneville Power Administration (Pacific NW)",
        "coordinates": (45.6387, -122.6615),  # Portland, OR
    },
    "CAISO": {  # Signals: AOER
        "name": "California ISO",
     "timezone": "America/Los_Angeles",
     "description": "California Independent System Operator",
     "coordinates": (38.5816, -121.4944),  # Sacramento, CA
    },
    "SPP": {  # Signals: AOER
        "name": "Southwest Power Pool",
        "timezone": "America/Chicago",
        "description": "Southwest Power Pool (Central US)",
        "coordinates": (38.9717, -95.2353),  # Lawrence, KS
    },
    "ERCOT": {  # Signals: AOER
        "name": "Electric Reliability Council of Texas",
        "timezone": "America/Chicago",
        "description": "ERCOT (Texas Interconnection)",
        "coordinates": (30.2672, -97.7431),  # Austin, TX
    },
    "ISONE": {  # Signals: AOER
        "name": "ISO New England",
        "timezone": "America/New_York",
        "description": "ISO New England (New England states)",
        "coordinates": (41.7658, -72.6734),  # Hartford, CT
    },
    # -------------------------------------------------------------------------
    # Canada (all have MOER + AOER except IESO subregions)
    # -------------------------------------------------------------------------
    "AESO": {  # Signals: MOER, AOER
        "name": "Alberta Electric System Operator",
        "timezone": "America/Edmonton",
        "description": "Alberta Canada grid operator",
        "coordinates": (53.5461, -113.4938),  # Edmonton, AB
    },
    "BCHYDRO": {  # Signals: MOER, AOER
        "name": "BC Hydro",
        "timezone": "America/Vancouver",
        "description": "British Columbia Hydro",
        "coordinates": (49.2827, -123.1207),  # Vancouver, BC
    },
    "HQ": {  # Signals: MOER, AOER
        "name": "Hydro Quebec",
        "timezone": "America/Montreal",
        "description": "Hydro Quebec service area",
        "coordinates": (45.5017, -73.5673),  # Montreal, QC
    },
    "IESO_SOUTH": {  # Signals: MOER
        "name": "IESO Ontario South",
        "timezone": "America/Toronto",
        "description": "Ontario ISO Southern region",
        "coordinates": (43.6532, -79.3832),  # Toronto, ON
    },
    "IESO_NORTH": {  # Signals: MOER
        "name": "IESO Ontario North",
        "timezone": "America/Toronto",
        "description": "Ontario ISO Northern region",
        "coordinates": (46.4917, -80.9930),  # Sudbury, ON
    },
    "IESO_WEST": {  # Signals: MOER
        "name": "IESO Ontario West",
        "timezone": "America/Toronto",
        "description": "Ontario ISO Western region",
        "coordinates": (42.9849, -81.2453),  # London, ON
    },
}

# =============================================================================
# REGION GROUPS (for easy config switching)
# =============================================================================
REGION_GROUPS = {
    # Original 5-region set (all MOER only)
    "US_5REG": [
        "MISO_INDIANAPOLIS",
        "PJM_NJ",
        "CAISO_NORTH",
        "ERCOT_EASTTX",
        "ISONE_NEMA",
    ],
    #subsection of regions:
    "GridMixStudy": [
        "CAISO_NORTH",
        "SPP_KANSAS",
        "BPA",
        "MISO_INDIANAPOLIS",
        "ISONE_CT",
        "ERCOT_NORTHCENTRAL",
    ],

    # By ISO (all MOER only for subregions)
    "MISO_ALL": [
        "MISO_INDIANAPOLIS", "MISO_DETROIT", "MISO_GRAND_RAPIDS",
        "MISO_MINNEAPOLIS", "MISO_MADISON", "MISO_EAU_CLAIRE",
        "MISO_SAINT_LOUIS", "MISO_SPRINGFIELD", "MISO_LAFAYETTE",
        "MISO_NEW_ORLEANS", "MISO_LOWER_MS_RIVER", "MISO_BEAUMONT",
        "MISO_N_DAKOTA", "MISO_MASON_CITY", "MISO_WORTHINGTON",
        "MISO_UPPER_PENINSULA",
    ],
    "PJM_ALL": [
        "PJM_NJ", "PJM_DC", "PJM_CHICAGO", "PJM_EASTERN_OH",
        "PJM_SOUTHWEST_OH", "PJM_EASTERN_KY", "PJM_WESTERN_KY", "PJM_ROANOKE",
    ],
    "CAISO_ALL": [
        "CAISO_NORTH", "CAISO_LONGBEACH", "CAISO_SANDIEGO",
        "CAISO_ESCONDIDO", "CAISO_PALMSPRINGS", "CAISO_SANBERNARDINO",
        "CAISO_REDDING",
    ],
    "ERCOT_ALL": [
        "ERCOT_EASTTX", "ERCOT_AUSTIN", "ERCOT_SANANTONIO",
        "ERCOT_NORTHCENTRAL", "ERCOT_COAST", "ERCOT_SECOAST",
        "ERCOT_SOUTHTX", "ERCOT_HIDALGO", "ERCOT_WESTTX", "ERCOT_PANHANDLE",
    ],
    "ISONE_ALL": [
        "ISONE_NEMA", "ISONE_SEMA", "ISONE_WCMA", "ISONE_CT",
        "ISONE_RI", "ISONE_ME", "ISONE_NH", "ISONE_VT",
    ],
    "NYISO_ALL": [
        "NYISO_NYC", "NYISO_LONG", "NYISO_HUDSON", "NYISO_CAPITAL",
        "NYISO_CENTRAL", "NYISO_MOHAWK", "NYISO_NORTH", "NYISO_WEST",
    ],
    "SPP_ALL": [
        "SPP_KANSAS", "SPP_KC", "SPP_OKCTY", "SPP_SWOK", "SPP_TX",
        "SPP_MEMPHIS", "SPP_SPRINGFIELD", "SPP_SIOUX", "SPP_ND",
        "SPP_WESTNE", "SPP_FORTPECK",
    ],
    "Restof_ALL": [
        "NYISO_NYC", "NYISO_LONG", "NYISO_HUDSON", "NYISO_CAPITAL",
        "CAISO_NORTH", "CAISO_LONGBEACH", "CAISO_SANDIEGO",
        "MISO_INDIANAPOLIS", "MISO_DETROIT", "MISO_GRAND_RAPIDS",
        "MISO_MINNEAPOLIS", "MISO_MADISON", "MISO_EAU_CLAIRE",
        "MISO_SAINT_LOUIS", "MISO_SPRINGFIELD", "MISO_LAFAYETTE",
        "MISO_NEW_ORLEANS", "MISO_LOWER_MS_RIVER", "MISO_BEAUMONT",
        "MISO_N_DAKOTA", "MISO_MASON_CITY", "MISO_WORTHINGTON",
        "MISO_UPPER_PENINSULA",
        "CAISO_ESCONDIDO", "CAISO_PALMSPRINGS", "CAISO_SANBERNARDINO",
        "CAISO_REDDING","PJM_NJ", "PJM_DC", "PJM_CHICAGO", "PJM_EASTERN_OH",
        "PJM_SOUTHWEST_OH", "PJM_EASTERN_KY", "PJM_WESTERN_KY", "PJM_ROANOKE",
        "ERCOT_EASTTX", "ERCOT_AUSTIN", "ERCOT_SANANTONIO",
        "ERCOT_NORTHCENTRAL", "ERCOT_COAST", "ERCOT_SECOAST",
        "ERCOT_SOUTHTX", "ERCOT_HIDALGO", "ERCOT_WESTTX", "ERCOT_PANHANDLE",
        "ISONE_NEMA", "ISONE_SEMA", "ISONE_WCMA", "ISONE_CT",
        "ISONE_RI", "ISONE_ME", "ISONE_NH", "ISONE_VT",
        "NYISO_CENTRAL", "NYISO_MOHAWK", "NYISO_NORTH", "NYISO_WEST",
        "SPP_KANSAS", "SPP_KC", "SPP_OKCTY", "SPP_SWOK", "SPP_TX",
        "SPP_MEMPHIS", "SPP_SPRINGFIELD", "SPP_SIOUX", "SPP_ND",
        "SPP_WESTNE", "SPP_FORTPECK",
    ],

    "ALL": [
        "NYISO_NYC", "NYISO_LONG", "NYISO_HUDSON", "NYISO_CAPITAL",
        "CAISO_NORTH", "CAISO_LONGBEACH", "CAISO_SANDIEGO",
        "MISO_INDIANAPOLIS", "MISO_DETROIT", "MISO_GRAND_RAPIDS",
        "MISO_MINNEAPOLIS", "MISO_MADISON", "MISO_EAU_CLAIRE",
        "MISO_SAINT_LOUIS", "MISO_SPRINGFIELD", "MISO_LAFAYETTE",
        "MISO_NEW_ORLEANS", "MISO_LOWER_MS_RIVER", "MISO_BEAUMONT",
        "MISO_N_DAKOTA", "MISO_MASON_CITY", "MISO_WORTHINGTON",
        "MISO_UPPER_PENINSULA",
        "CAISO_ESCONDIDO", "CAISO_PALMSPRINGS", "CAISO_SANBERNARDINO",
        "CAISO_REDDING","PJM_NJ", "PJM_DC", "PJM_CHICAGO", "PJM_EASTERN_OH",
        "PJM_SOUTHWEST_OH", "PJM_EASTERN_KY", "PJM_WESTERN_KY", "PJM_ROANOKE",
        "ERCOT_EASTTX", "ERCOT_AUSTIN", "ERCOT_SANANTONIO",
        "ERCOT_NORTHCENTRAL", "ERCOT_COAST", "ERCOT_SECOAST",
        "ERCOT_SOUTHTX", "ERCOT_HIDALGO", "ERCOT_WESTTX", "ERCOT_PANHANDLE",
        "ISONE_NEMA", "ISONE_SEMA", "ISONE_WCMA", "ISONE_CT",
        "ISONE_RI", "ISONE_ME", "ISONE_NH", "ISONE_VT",
        "NYISO_CENTRAL", "NYISO_MOHAWK", "NYISO_NORTH", "NYISO_WEST",
        "SPP_KANSAS", "SPP_KC", "SPP_OKCTY", "SPP_SWOK", "SPP_TX",
        "SPP_MEMPHIS", "SPP_SPRINGFIELD", "SPP_SIOUX", "SPP_ND",
        "SPP_WESTNE", "SPP_FORTPECK",
    ],
    "AOER_6RegionSummary": [
        "MISO","BPA", "CAISO","SPP","ERCOT","ISONE",
    ],

    # Regions with AOER data (for MOER vs AOER comparison)
    "AOER_REGIONS": [
        "TVA", "SOCO", "DUK", "CPLE", "CPLW", "FPL", "FPC", "TEC",
        "PSCO", "PNM", "SRP", "AZPS", "NEVP", "LDWP", "PGE", "PSEI",
        "BPA", "AECI", "LGEE", "AESO", "BCHYDRO", "HQ",
    ],

    # Only region with health_damage data
    "HEALTH_REGIONS": ["CAISO_NORTH"],

    # Convenience groups
    "INDY_ONLY": ["MISO_INDIANAPOLIS"],
    "EAST_COAST": ["PJM_NJ", "ISONE_NEMA", "NYISO_NYC"],
    "MIDWEST": ["MISO_INDIANAPOLIS", "MISO_DETROIT", "PJM_CHICAGO", "SPP_KC"],
    "TEXAS": ["ERCOT_EASTTX", "ERCOT_AUSTIN", "ERCOT_NORTHCENTRAL", "ERCOT_SANANTONIO"],
    "CALIFORNIA": ["CAISO_NORTH", "CAISO_SANDIEGO", "LDWP"],
    "PACIFIC_NW": ["BPA", "PGE", "PSEI", "SCL"],
    "SOUTHEAST": ["TVA", "SOCO", "DUK", "FPL"],
    "FLORIDA": ["FPL", "FPC", "TEC", "JEA", "TAL"],
    "CANADA": ["AESO", "BCHYDRO", "HQ", "IESO_SOUTH", "IESO_NORTH", "IESO_WEST"],
}

# =============================================================================
# PATHS - Library (permanent data) and Runs (disposable analysis)
# =============================================================================
PROJECT_ROOT = Path(__file__).parent
LIBRARY_DIR = PROJECT_ROOT / "library"
RUNS_DIR = PROJECT_ROOT / "runs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
UTILS_DIR = PROJECT_ROOT / "utils"

# Library subdirectories (created on first use)
def get_library_signal_dir(signal: str) -> Path:
    """Get library directory for a specific signal."""
    path = LIBRARY_DIR / signal
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_catalog_path() -> Path:
    """Get path to library catalog."""
    return LIBRARY_DIR / "catalog.json"

# =============================================================================
# DATE RANGES
# =============================================================================
DEFAULT_HISTORICAL_START = datetime(2022, 1, 1)
DEFAULT_HISTORICAL_END = datetime(2024, 12, 31)

# Forecast sample months (for forecast accuracy analysis)
FORECAST_SAMPLE_MONTHS = [
    ("2024-01", datetime(2024, 1, 1), datetime(2024, 1, 31)),   # Winter
    ("2024-04", datetime(2024, 4, 1), datetime(2024, 4, 30)),   # Spring
    ("2024-07", datetime(2024, 7, 1), datetime(2024, 7, 31)),   # Summer
    ("2024-10", datetime(2024, 10, 1), datetime(2024, 10, 31)), # Fall
]

# =============================================================================
# ANALYSIS PARAMETERS
# =============================================================================
# Shift definitions (local time hours)
SHIFTS = {
    "day": {"start": 6, "end": 14, "name": "Day (6am-2pm)"},
    "swing": {"start": 14, "end": 22, "name": "Swing (2pm-10pm)"},
    "night": {"start": 22, "end": 6, "name": "Night (10pm-6am)"},
}

# Job durations to test (hours)
JOB_DURATIONS = [0.5, 1.0, 2.0, 4.0]

# Season definitions (meteorological)
SEASONS = {
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "fall": [9, 10, 11],
}

# Reference job energy for example calculations (kWh)
REFERENCE_JOB_KWH = 2.0

# =============================================================================
# FIGURE SETTINGS
# =============================================================================
FIGURE_DPI = 150
FIGURE_SIZE = (10, 6)
FIGURE_FORMAT = "png"

_GRID_MIX_REGIONS = [
    "CAISO_NORTH",
    "SPP_KANSAS",
    "BPA",
    "MISO_INDIANAPOLIS",
    "ISONE_CT",
    "ERCOT_NORTHCENTRAL",
]
REGION_COLORS = {r: plt.cm.tab10(i) for i, r in enumerate(_GRID_MIX_REGIONS)}
# Color palette for seasons
SEASON_COLORS = {
    "winter": "#1f77b4",  # blue
    "spring": "#2ca02c",  # green
    "summer": "#ff7f0e",  # orange
    "fall": "#d62728",    # red
}

# Color palette for signals
SIGNAL_COLORS = {
    "co2_moer": "#1f77b4",     # blue
    "co2_aoer": "#ff7f0e",     # orange
    "health_damage": "#d62728", # red
}

# =============================================================================
# DATA QUALITY
# =============================================================================
MAX_MISSING_PCT_PER_DAY = 10  # Flag days with more than this % missing

# =============================================================================
# ANALYSIS THRESHOLDS
# =============================================================================
CONSISTENCY_THRESHOLD = 0.80  # Window must achieve 80% of max savings
FLEXIBILITY_WINDOWS_HOURS = [2, 4, 6, 8]  # Test flexibility windows

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_signal_metadata(signal: str) -> dict:
    """Get metadata for a signal, with fallback for unknown signals."""
    if signal in SIGNALS:
        return SIGNALS[signal]
    return {
        "name": signal,
        "unit": "unknown",
        "unit_label": "value",
        "description": f"Unknown signal: {signal}",
        "typical_range": (0, 1000),
        "lower_is_better": True,
    }

def get_region_metadata(region: str) -> dict:
    """Get metadata for a region, with fallback for unknown regions."""
    if region in REGIONS:
        return REGIONS[region]
    return {
        "name": region,
        "timezone": "UTC",
        "description": f"Unknown region: {region}",
        "coordinates": (0, 0),
    }

def expand_region_group(regions_or_group: Union[List[str], str]) -> List[str]:
    """
    Expand a region group name to list of regions.
    If already a list, return as-is. If a group name, expand it.
    """
    if isinstance(regions_or_group, str):
        if regions_or_group in REGION_GROUPS:
            return REGION_GROUPS[regions_or_group]
        else:
            return [regions_or_group]  # Single region
    return list(regions_or_group)

def get_unit_label(signal: str) -> str:
    """Get the unit label for axis labels, etc."""
    return get_signal_metadata(signal)["unit_label"]

def format_value_with_unit(value: float, signal: str) -> str:
    """Format a value with its unit for display."""
    unit = get_signal_metadata(signal)["unit_label"]
    return f"{value:.1f} {unit}"
