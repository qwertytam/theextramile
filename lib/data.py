# -*- coding: utf-8 -*-
"""Data Gathering

This module contains functions to wrangle the data to visit the desired
locations. The functions in included here will download, clean and gather
the data from https://www.geonames.org/.

This file  contains the following functions:

    * dl_county_data - downloads the geoname data from the geonames server
    * dl_fips_codes - downloads FIPS codes for each county
    * prep_data - prepares the tour data for calculating the tour
    * write_data - writes given data to a csv file
    * cleanup_geoname_data - removes downloaded zip and txt files
    * find_tour - find the optimal using the Concorde algorithm

"""

import math
import numpy as np
import os.path
import pandas as pd

from concorde.tsp import TSPSolver
from datetime import datetime
from os import listdir, mkdir, remove
from re import search, sub
from requests import get
from zipfile import ZipFile

# Class for terminal output colours


class bcolours:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


def dl_county_data(url, path):
    '''
    Gathers the county and seat data from the given url. Adds cat_code
    (country.state.county) and some data corrections. Writes the corrected data
    to the the given path and also returns it.

    Parameters:
        url (str): A full url to a zip file e.g.
            https://www.data.org/data.zip
        path (str): A full path to a csv file e.g. ../data/data.csv. Will
            create dir and file if they do not exist

    Returns:
        data.frame : Data frame of downloaded data

    Raises:
        Exception: url does not point to a zip file
        Exception: path does not point to a csv file
    '''

    # Function local variables
    url_ext = '.zip'
    txt_ext = '.txt'
    seat_fcode = 'PPLA2'
    keep_fcodes = ['PPLA2', 'ADM2']  # PPLA2 for county, ADM2 for county seat

    # csv header names and keep columns
    header_names = ['gid', 'name', 'asciiname', 'altnames', 'lat', 'lon',
                    'f_class', 'f_code', 'country', 'alt_country', 'state',
                    'county', 'admin3', 'admin4', 'popn', 'elev', 'dem', 'tz',
                    'mod_date']
    keep_cols = ['gid', 'name', 'lat', 'lon', 'f_class', 'f_code',
                 'country', 'state', 'county']

    # Specify dtype; warning is raised for country, state and county columns if
    # their type is not specified
    dyptes = {'gid': np.int32, 'name': str, 'lat': np.float64,
              'lon': np.float64, 'f_class': str, 'f_code': str, 'country': str,
              'state': str, 'county': str}
    # dyptes = {'country': str, 'state': str, 'county': 'Int64'}

    # Check url and path are correct form
    try:
        error_msg = f'.zip not found before or at end of url: {url}'
        assert (search(r'\.zip', url).span()[1] == len(url)), error_msg
    except AttributeError:
        print(f'.zip not found in url: {url}')
        raise
    else:
        print('url is correctly formed')

    try:
        error_msg = f'.csv not found before or at end of path: {path}'
        assert (search(r'\.csv', path).span()[1] == len(path)), error_msg
    except AttributeError:
        print(f'.csv not found in path: {path}')
        raise

    # Get the zip file name to be downloaded
    zip_fnm = search(r'(([0-9a-zA-Z])+\.zip)$', url)
    zip_fnm = zip_fnm.group(0)

    # Get the text file name we expect to find in the zip file
    txt_fnm = sub(url_ext, txt_ext, zip_fnm)

    # Create dir if it does not exist
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        mkdir(dir)
        print(f'Created dir {dir}')

    zip_path = os.path.join(dir, zip_fnm)
    with open(zip_path, 'wb') as f:
        print(f'Downloading {url} to {zip_path}')
        response = get(url, stream=True)
        total_length = response.headers.get('content-length')

        if total_length is None:  # no content length header
            f.write(response.content)
        else:
            dl = 0
            total_length = int(total_length)
            for data in response.iter_content(chunk_size=4096):
                dl += len(data)
                f.write(data)
                done = int(50 * dl / total_length)
                print(f'\r[{"="*done}{" "*(50-done)}] {done*2}%', end='\r')

    # Retrieve HTTP meta-data
    print(f'\nHTTP status {response.status_code}')
    print('Content type {}'.format(response.headers['content-type']))
    print(f'Enconding {response.encoding}')

    with ZipFile(zip_path, 'r') as zip_ref:
        print(f'Unzipping {zip_path}')
        txt_path = zip_ref.extract(txt_fnm, path=dir)
        zip_ref.close()
        print('Extracted {}'.format(txt_path))

    # Write the county data to csv file
    data = pd.read_csv(txt_path, names=header_names, header=0, dtype=dyptes,
                       usecols=keep_cols, delimiter="\t", na_values=[-1])

    # Keep only the geoname feature code(s) of interest
    data.drop(data.loc[~data.isin({'f_code': keep_fcodes}).f_code].index,
              axis=0, inplace=True)

    # Name correction in data source
    data.loc[data['gid'] == 5465283, 'name'] = 'Dona Ana County'
    data.loc[data['gid'] == 5135484, 'name'] = 'Saint Lawrence County'

    # Drop county seats Orange, CA and the Washington Street Courthouse Annex,
    # as they are not county seats ref Wikipedia
    drop_gids = [11497201, 5379513]
    data.drop(data.loc[data.isin(drop_gids).gid].index, axis=0, inplace=True)

    # # Oakley, KS is actually the county seat for Logan County,
    # # i.e. for county 109 in KS
    data.at[(data.state == 'KS') & (data.name == 'Oakley')
            & (data.f_code == seat_fcode), 'county'] = 109

    # Add cat_code for reference and later use to identify county:seat
    # matchups
    data[['county']] = data[['county']].apply(pd.to_numeric)

    data['cat_code'] = data[['country', 'state', 'county']].apply(
        lambda x: (f'{x[0]}.{x[1]}.{x[2]:03d}'), axis=1)

    write_data(data, path)
    return data


def dl_fips_codes(url, path):
    '''
    Gathers the FIPS codes for each county from the given url. Performs some
    data corrections to add missing counties and align the names with the names
    in the geonmaes data set. Writes the corrected data to the the given path
    and also returns it.

    Parameters:
        url (str): A full url to a zip file e.g.
            https://www.data.org/data.csv
        path (str): A full path to a csv file e.g. ../data/data.csv. Will
            create dir and file if they do not exist

    Returns:
        data.frame : Data frame of downloaded data

    Raises:
        Exception: url does not point to a csv file
        Exception: path does not point to a csv file
    '''

    # csv header names and keep columns
    header_names = ['FIPS_Code', 'State', 'Area_name',
                    'Civilian_labor_force_2011', 'Employed_2011',
                    'Unemployed_2011', 'Unemployment_rate_2011',
                    'Median_Household_Income_2011',
                    'Med_HH_Income_Percent_of_StateTotal_2011']
    keep_names = ['FIPS_Code', 'State', 'Area_name']

    # Specify dtype
    dyptes = {'FIPS_Code': 'Int64', 'State': str, 'Area_name': str}

    # Check url and path are correct form
    try:
        error_msg = f'.csv not found before or at end of url: {url}'
        assert (search(r'\.csv', url).span()[1] == len(url)), error_msg
    except AttributeError:
        print(f'.csv not found in url: {url}')
        raise
    else:
        print('url is correctly formed')

    try:
        error_msg = f'.csv not found before or at end of path: {path}'
        assert (search(r'\.csv', path).span()[1] == len(path)), error_msg
    except AttributeError:
        print(f'.csv not found in path: {path}')
        raise

    fips = pd.read_csv(url, na_values=[' '], names=header_names,
                       usecols=keep_names, header=0, dtype=dyptes)

    # Replace strings to align with what is used in geonames data
    # St. to Saint
    pat = r'St\.'
    repl = 'Saint'
    fips['Area_name'] = fips.Area_name.str.replace(pat, repl)

    # Position of city
    # For case when name is one word before city
    pat = r'^(?P<name>\w+)(\scity)'
    def replfn(m): return ('City of ' + m.group('name'))
    fips['Area_name'] = fips.Area_name.str.replace(pat, replfn)

    # For case when name is two words before city
    pat = r'^(?P<name>\w+\s\w+)(\scity)'
    def replfn(m): return ('City of ' + m.group('name'))
    fips['Area_name'] = fips.Area_name.str.replace(pat, replfn)

    # Manual adds as not in data source
    fips.loc[len(fips.index)] = [2158, 'AK', 'Kusilvak Census Area']
    fips.loc[len(fips.index)] = [15005, 'HI', 'Kalawao County']
    fips.loc[len(fips.index)] = [46102, 'SD', 'Oglala Lakota County']

    # Manual corrections to align with geonames data
    fips.loc[fips['FIPS_Code'] == 2105, 'Area_name'] = \
        'Hoonah-Angoon Census Area'
    fips.loc[fips['FIPS_Code'] == 2198, 'Area_name'] = \
        'Prince of Wales-Hyder Census Area'
    fips.loc[fips['FIPS_Code'] == 2275, 'Area_name'] = \
        'City and Borough of Wrangell'
    fips.loc[fips['FIPS_Code'] == 6075, 'Area_name'] = \
        'City and County of San Francisco'
    fips.loc[fips['FIPS_Code'] == 11001, 'Area_name'] = 'Washington County'
    fips.loc[fips['FIPS_Code'] == 17099, 'Area_name'] = 'LaSalle County'
    fips.loc[fips['FIPS_Code'] == 28033, 'Area_name'] = 'De Soto County'
    fips.loc[fips['FIPS_Code'] == 29186, 'Area_name'] = \
        'Sainte Genevieve County'
    fips.loc[fips['FIPS_Code'] == 2195, 'Area_name'] = 'Petersburg Borough'

    # Update the column names to all lower case
    fips.columns = ['fips_code', 'state', 'name']
    write_data(fips, path)

    return fips


def prep_data(data, fips, path):
    '''
    Prepares data for finding tour with the following operations:
        * Adds column for FIPS code to match up with json data for mapping
        * Pivots data so that county and county seats are in separate columns
        * Adds a series of visit columns, where each entry is county
        information unless there is seat information in which case the seat
        information is used

    Parameters:
        data (data.frame): A data frame of geonames data that contains the
            county and county seat information
        fips (data.frame): A data frame of fips code data
        path (str): A full path to a csv file e.g. ../data/data.csv. Will
            create dir and file if they do not exist

    Returns:
        data.frame : Data frame of tour data

    Raises:
        Exception: path does not point to a csv file
    '''

    # Function local variables
    county_fcode = 'ADM2'
    seat_fcode = 'PPLA2'

    # Split the data and then remerge it, effectively pivoting it into wide
    # format
    counties = data.loc[data['f_code'] == county_fcode]
    seats = data.loc[data['f_code'] == seat_fcode]

    data = counties.merge(seats, how='left', copy=False,
                          suffixes=('_county', '_seat'), on='cat_code',
                          validate='1:1')

    # Drop unrequired and/or duplicated columns
    data.drop(['f_class_county', 'f_code_county', 'country_county',
               'county_county', 'f_class_seat', 'f_code_seat', 'country_seat',
               'state_seat', 'county_seat'], axis=1, inplace=True)

    # rename existing columns where appropiate
    data.rename(columns={'state_county': 'state'}, inplace=True)

    # Merge with the fips data
    data = data.merge(fips, how='left', copy=False,
                      suffixes=(None, '_fips'),
                      left_on=('name_county', 'state'),
                      right_on=('name', 'state'), validate='1:1')

    # Drop unrequired and/or duplicated columns
    data.drop(['name'], axis=1, inplace=True)

    # If data for county seat exists, use that data for visit; else use
    # county data
    data['name_visit'] = data[['name_county', 'name_seat']].apply(
        lambda x: x[1] if type(x[1]) is str else x[0], axis=1)

    data['lat_visit'] = data[['lat_county', 'lat_seat']].apply(
        lambda x: x[0] if math.isnan(x[1]) else x[1], axis=1)

    data['lon_visit'] = data[['lon_county', 'lon_seat']].apply(
        lambda x: x[0] if math.isnan(x[1]) else x[1], axis=1)

    # Write and return data
    write_data(data, path)
    return data


def write_data(data, path):
    '''
    Writes the given data to the given path pointing to a csv file.

    Parameters:
        data (data.frame): A data frame of data
        path (str): A full path to a csv file e.g. ../data/data.csv. Will
            create dir and file if they do not exist

    Returns:
        data.frame : Data frame of filtered data

    Raises:
        Exception: path does not point to a csv file
    '''

    # Check if path is correct form
    try:
        error_msg = f'.csv not found before or at end of path: {path}'
        assert (search(r'\.csv', path).span()[1] == len(path)), error_msg
    except AttributeError:
        print(f'.csv not found in path: {path}')
        raise

    # Create dir if it does not exist
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        mkdir(dir)
        print(f'Created dir {dir}')

    print(f'Writing data to {path}')
    data.to_csv(path, index=False)
    print(f'Created and added data to {path}')


def cleanup_geoname_data(dir):
    '''
    Removes .zip and .txt files from the given dir

    Parameters:
        dir (str): Path to identify items to remove e.g. ../data/

    '''
    # Will remove .zip and .txt files
    rm_exts = ['.zip', '.txt']

    dir_items = listdir(dir)

    for ext in rm_exts:
        for item in dir_items:
            if item.endswith(ext):
                item_pth = os.path.join(dir, item)
                remove(item_pth)
                print(f'Removed: {item_pth}')


def find_tour(data, path, time_bound=-1, random_seed=42):
    '''
    Use the Concorde algorithim to find the optimal tour. Returns the tour and
    saves it to the given path.

    Parameters:
        dir (str): Path to identify items to remove e.g. ../data/
        path (str): A full path to a csv file e.g. ../data/data.csv. Will
            create dir and file if they do not exist
        time_bound (int): Time bound in seconds (?) for Concorde algorithim
        random_seed (int): Random seed for Concorde algorithim

    Returns:
        data.frame : Data frame of the optimal tour

    Raises:
        Exception: path does not point to a csv file
    '''

    # Local function variables
    # gid for starting in Kings County, NY (i.e. Brooklyn)
    # Will use this to rotate the tour so that the starting point is this gid
    start_gid = 6941775

    # Check if path is correct form
    try:
        error_msg = f'.csv not found before or at end of path: {path}'
        assert (search(r'\.csv', path).span()[1] == len(path)), error_msg
    except AttributeError:
        print(f'.csv not found in path: {path}')
        raise

    # Instantiate solver
    solver = TSPSolver.from_data(
        data.lat_visit,
        data.lon_visit,
        norm="GEO"
    )

    # Find tour
    t = datetime.now()
    tour_data = solver.solve(time_bound=time_bound, verbose=False,
                             random_seed=random_seed)
    print(f'\n\n{"~"*80}\n')
    print(f'Tour found in {(datetime.now() - t)}')
    print(f'{bcolours.OKGREEN}Solver was successful{bcolours.ENDC}'
          if tour_data.success else
          f'{bcolours.FAIL}Solver was NOT successful{bcolours.ENDC}')

    # # Rotate tour so that starting point is first
    tour_route = tour_data.tour
    while data.gid_county.iloc[tour_route[0]] != start_gid:
        tour_route = np.append(tour_route[1:], tour_route[:1])

    # Save tour to output file
    data_out = data.iloc[tour_route]
    data_out.to_csv(path)
    return data_out
