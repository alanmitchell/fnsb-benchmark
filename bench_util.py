# -*- coding: utf-8 -*-
"""
Utilities for assisting with the benchmarking analysis process.
"""
import io
import os
from collections import namedtuple
import pandas as pd
import numpy as np
import requests

def calendar_to_fiscal(cal_year, cal_mo):
    """Converts a calendar year and month into a fiscal year and month.
    Returns (fiscal_year, fical_month) tuple.
    """
    if cal_mo <= 6:
        fiscal_year = cal_year
        fiscal_month = cal_mo + 6
    else:
        fiscal_year = cal_year + 1
        fiscal_month = cal_mo - 6

    return fiscal_year, fiscal_month

def fiscal_to_calendar(fiscal_year, fiscal_mo):
    """Converts a fiscal year and month into a calendar year and month for graphing purposes.
    Returns (calendar_year, calendar_month) tuple."""
    
    if fiscal_mo > 6:
        calendar_month = fiscal_mo - 6
        calendar_year = fiscal_year
    else:
        calendar_month = fiscal_mo + 6
        calendar_year = fiscal_year - 1
        
    return (calendar_year, calendar_month)

# Fiscal Month labels, both as a list and as a dictionary
mo_list = [
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun'
]

mo_dict = dict(zip(range(1,13), mo_list))

PeriodSplit = namedtuple('PeriodSplit', 'cal_year cal_mo bill_frac days_served')
def split_period(start_date, end_date):
    """Splits a range of service dates from a utility bill into pieces that
    fit within calendar months. For each piece, the number of days in that piece 
    and the fraction of the original date range are returned in a namedtuple.
    For the first and last day in the date range, it is assumed that only half
    the day is served (this is typically the meter reading day).
    """
    # make a daily series.  The value is the fraction of the day served,
    # 1.0 for days except the first and last.
    ser = pd.Series(data=1.0, index=pd.date_range(start_date, end_date))
    
    # the half days at the beginning and end
    ser.iloc[0] = 0.5
    ser.iloc[-1] = 0.5
    
    tot_days = ser.sum()    # total days served in the bill
    
    # break into monthly pieces and add up the days served
    pieces = ser.resample('M').sum()
    
    result = []
    for dt, days in pieces.items():
        result.append(
            PeriodSplit(cal_year=dt.year, cal_mo=dt.month, bill_frac=days/tot_days, days_served=days)
        )
    return result

def months_present(df, yr_col='fiscal_year', mo_col='fiscal_mo'):
    """Returns a list of the year/months present in a DataFrame.  Each item
    of the list is a two-tuple: (year, mo), and list is sorted from earliest
    to latest month.
    yr_col: the name of the column in the DataFrame containing the year.
    mo_col: the name of the column in the DataFrame containing the month.
    """
    yr_mo = set(zip(df[yr_col], df[mo_col]))
    yr_mo = list(yr_mo)
    yr_mo.sort()
    return yr_mo

def month_count(mo_present):
    """Returns a Pandas series that gives the number of months present for each
    year in the 'mo_present' list.  The 'mo_present' list is a list of two
    tuples:  (year, mo).  The returned series is indexed on year.
    """
    return pd.DataFrame(data=mo_present, columns=['year', 'month']).groupby('year').count()['month']

def add_month_count_column(df_target, df_detail, yr_col='fiscal_year', mo_col='fiscal_mo'):
    """Adds a 'month_count' column to the 'df_target' DataFrame, whose index
    must be a year value.  The value in the 'month_count' column is the number
    of months that are present in the detailed DataFrame 'df_detail' for each 
    year.  'yr_col' and 'mo_col' give the names of the columns in 'df_detail'
    that are used to determine the month counts by year.
    """
    mo_present = months_present(df_detail)
    mo_count = month_count(mo_present)
    df_target['month_count'] = mo_count

def add_month_count_column_by_site(df_target, df_detail, yr_col='fiscal_year', mo_col='fiscal_mo', site_col='site_id'):
    """Returns a DataFrame the same as df_target but with a 'month_count' column; that
    column indicates how many months of data are present in df_detail for the 
    (site ID, year) of the row. 'df_target' must have an index of (site ID, year).  
    'yr_col' is the name of the column in df_detail that contains the year of 
    the data. 'mo_col' gives the name of the column in 'df_detail' that holds the 
    month of the data. 'site_col' is the name of the column in df_detail that 
    indicates the site.
    """
    site_yr_mo = set(zip(df_detail[site_col], df_detail[yr_col], df_detail[mo_col]))
    site_yr_mo = list(site_yr_mo)
    df_mo_count = pd.DataFrame(data=site_yr_mo, columns=[site_col, yr_col, mo_col]).groupby([site_col, yr_col]).count()
    df_mo_count.rename(columns={'fiscal_mo': 'month_count'}, inplace=True)

    return df_target.merge(df_mo_count, how='left', left_index=True, right_index=True)

# List of all possible services
all_services = [
    'fuel_oil',
    'natural_gas',
    'electricity',
    'propane',
    'wood',
    'district_heat',
    'water',
    'sewer',
    'refuse'
]

all_energy_services = [
    'fuel_oil',
    'natural_gas',
    'electricity',
    'propane',
    'wood',
    'district_heat',
]

all_heat_services = [
    'fuel_oil',
    'natural_gas',
    'propane',
    'wood',
    'district_heat',
]

def missing_services(services_present):
    """Returns a list of the Service Types that are *not* present in the 
    'services_present' input list.
    """
    return list(set(all_services) - set(services_present))

def missing_energy_services(services_present):
    """Returns a list of the Energy-related Service Types that are *not* present
    in the 'services_present' input list.
    """
    return list(set(all_energy_services) - set(services_present))

def add_columns(df, col_names):
    """Adds a new column to the DataFrame df for each column name in the list
    'col_names'.  Sets all the values to 0.0 for that column.
    """
    for col in col_names:
        df[col] = 0.0

def add_missing_columns(df_in, required_columns, fill_val=0.0):
    """Adds columns to the DataFrame 'df_in' if it does not contain all of the
    columns in the list 'required_columns'.  'fill_val' is the value that is used
    to fill the new columns.
    """
    missing_cols = set(required_columns) - set(df_in.columns)
    for col in missing_cols:
        df_in[col] = fill_val

    return df_in

def df_to_dictionaries(df, change_names={}, include_index=True):
    """Returns a list of dictionaries, one dictionary for each row in the 
    DataFrame 'df'.  The keys of the dictionary match the DataFrame column names,
    except for any substitututions provided in the 'change_names' dictionary;
    {'old_name': 'new_name', etc}.  If 'include_index' is True, the index 
    values are included in the dictionary keyed on the index name (unless changed
    in the 'change_names' dictionary)
    """
    # make a list of the final names to use
    names = list(df.columns.values)
    if include_index:
        names = [df.index.name] + names
        
    # apply name substitutions
    for i in range(len(names)):
        names[i] = change_names.get(names[i], names[i])
    
    result = []
    for ix, row in df.iterrows():
        vals = list(row.values)
        if include_index:
            vals = [ix] + vals
        result.append(
            dict(zip(names, vals))
        )
    
    return result


class Util:
    
    def __init__(self, util_df, other_data_pth):
        """
        util_df: DataFrame containing the raw utility bill data
        other_data_pth: path to the directory containing other application data spreadsheets,
            building info, degree days, etc.
        """
        
        # Read in the Building Information from the Other Data file
        df_bldg = pd.read_excel(
                os.path.join(other_data_pth, 'Buildings.xlsx'), 
                skiprows=3, 
                index_col='site_id'
                )

        # Add a full address column, combo of address and city.
        df_bldg['full_address'] = df_bldg.address.str.strip() + ', ' + \
            df_bldg.city.str.strip()
        # now remove any leading or trailing commas.
        df_bldg.full_address = df_bldg.full_address.str.strip(',') 
        
        # Create a dictionary to hold info for each building
        # The keys of the dictionary are the columns from the spreadsheet that
        # was just read, but also a number of other fields related to 
        # service providers and account numbers.
        dict_keys = list(df_bldg.columns) + [
            'source_elec',
            'source_oil',
            'source_nat_gas',
            'source_steam',
            'source_water',
            'source_sewer',
            'source_refuse',
            'acct_elec',
            'acct_oil',
            'acct_nat_gas',
            'acct_steam',
            'acct_water',
            'acct_sewer',
            'acct_refuse',
        ]
            
        # make a dictionary with default values for all fields (use empty
        # string for defaults)
        default_info = dict(zip(dict_keys, [''] * len(dict_keys)))

        def find_src_acct(dfs, service_type):
            """Function used below to return service provider and account
            numbers for a particular service type.  'dfs' is a DataFrame that
            has only the records for one site.  'service_type' is the name of
            the service, e.g. 'Water'.  (provider name, account numbers) are
            returned.
            """
            try:
                df_svc = dfs[dfs['Service Name']==service_type]
                last_bill_date = df_svc.Thru.max()
                df_last_bill = df_svc[df_svc.Thru == last_bill_date]
                
                # could be multiple account numbers. Get them all and
                # separate with commas
                accts = df_last_bill['Account Number'].unique()
                acct_str = ', '.join(accts)
                # Assume only one provider.
                provider = df_last_bill['Vendor Name'].iloc[0]
                
                return provider, acct_str
            
            except:
                return '', ''

        # create a dictionary to map site_id to info about the building
        self._bldg_info = {}
        
        # separately, create a list that will be used to make a DataFrame
        # that also contains this info.
        rec_list = []
        
        for ix, row in df_bldg.iterrows():
            # Start the record of building information (as a dictionary)
            # and fill out the info from the spreadsheet first.
            rec = default_info.copy()
            rec.update(row.to_dict())

            # now find providers and account numbers from raw utility file.
            svcs = [
                ('Electricity', 'elec'),
                ('Oil #1', 'oil'),
                ('Natural Gas', 'nat_gas'),
                ('Steam', 'steam'),
                ('Water', 'water'),
                ('Sewer', 'sewer'),
                ('Refuse', 'refuse')
            ]
            df_site = util_df[util_df['Site ID']==ix]
            for svc, abbrev in svcs:
                source, accounts = find_src_acct(df_site, svc)
                rec['source_{}'.format(abbrev)] = source
                rec['acct_{}'.format(abbrev)] = accounts
                
            self._bldg_info[row.name] = rec
            
            # add in the site_id to the record so the DataFrame has this
            # column.
            rec['site_id'] = row.name
            rec_list.append(rec)
            
        # Make a DataFrame, indexed on site_id to hold this building info
        # as well.
        self._bldg_info_df = pd.DataFrame(rec_list)
        self._bldg_info_df.set_index('site_id', inplace=True)
        
        # make a list of site categories and their associated builddings
        df_sites = df_bldg.reset_index()[['site_id', 'site_name', 'site_category']]
        cats = df_sites.groupby('site_category')
        self._site_categories = []
        for nm, gp in cats:
            bldgs = list(zip(gp['site_name'], gp['site_id']))
            bldgs.sort()
            sites = []
            for site_name, site_id in bldgs:
                sites.append(dict(id=site_id, name=site_name))
            self._site_categories.append( {'name': nm, 'sites': sites} )

        # read in the degree-day info from AHFC's online file
        resp = requests.get('http://ahfc.webfactional.com/data/degree_days.pkl').content
        df_dd = pd.read_pickle(io.BytesIO(resp), compression='bz2')

        # make a dictionary keyed on fiscal_yr, fiscal_mo, site_id
        # with a value of degree days.
        self._dd = {}
        for ix, row in df_dd.iterrows():
            f_yr, f_mo = calendar_to_fiscal(row.month.year, row.month.month)
            self._dd[(f_yr, f_mo, ix)] = row.hdd65
  
        # Get Service Type information and create a Fuel Btu dictionary as an
        # object attribute.  Keys are fuel type, fuel unit, both in lower case.
        # Also create a dictionary mapping service types to standard service 
        # type category names.  
        df_services = pd.read_excel(os.path.join(other_data_pth, 'Services.xlsx'), sheet_name='Service Types', skiprows=3)
        self._fuel_btus = {}
        for ix, row in df_services.iterrows():
            # Only put energy services into fuel btu dictionary
            if row.btu_per_unit > 0.0:
                self._fuel_btus[(row.service.lower(), row.unit.lower())] = row.btu_per_unit

        # Make a dictionary mapping Service Type to Service Type Category
        # For duplicate service type entries, this will take the last category.
        self._service_to_category = dict(zip(df_services.service, df_services.category))

        # Make a dictionary that maps the standard Service Category for fuels
        # to the standard display units and the Btus per unit for that fuel unit.
        # The keys are the standardized service type names, but only include energy
        # producing fuels (not water, refuse, etc.).  The values are a two-tuple:
        # (unit, Btus/unit).
        df_svc_cat_info = pd.read_excel(os.path.join(other_data_pth, 'Services.xlsx'),
            sheet_name='Service Categories', skiprows=3)
        ky_val = zip(df_svc_cat_info.category, zip(df_svc_cat_info.unit, df_svc_cat_info.btu_per_unit))
        self._service_cat_info = dict(ky_val)

    def building_info(self, site_id):
        """Returns building information, a dictionary, for the facility
        identified by 'site_id'.  Throws a KeyError if the site is not present.
        """
        return self._bldg_info[site_id]
    
    def building_info_df(self):
        """Returns a DataFrame with all of the building information.  The index
        of the DataFrame is the Site ID.
        """
        return self._bldg_info_df
    
    def all_sites(self):
        """Returns a list of all Site IDs present in the Other Data spreadsheet.
        The list is sorted alphabetically.
        """
        ids = list(self._bldg_info.keys())
        ids.sort()
        return ids
    
    def site_categories_and_buildings(self):
        """Returns a list of site categories and associated buildings.
        The list is sorted alphabetically by the site category name.
        Each item in the list is a dictionary, with a key "category" giving 
        the category name, and a key "sites" giving a list of buildings for that
        category; the building is a two-tuple (building name, site ID).  Buildings
        are sorted alphabetically by building name.
        """
        return self._site_categories
    
    def add_degree_days_col(self, df):
        """Adds a degree-day column to the Pandas DataFrame df.  The new column
        is named "degree_days".  The code assumes that there are columns: 
        fiscal_year, fiscal_mo, and site_id already in the DataFrame.  These are 
        used to look-up the degree-days for a paricular site and month.
        """
        dd_col = []
        for ix, row in df.iterrows():
            try:
                deg_days = self._dd[(row.fiscal_year, row.fiscal_mo, self._bldg_info[row.site_id]['dd_site'])]
            except:
                deg_days = np.nan
            dd_col.append(deg_days)
        
        df['degree_days'] = dd_col
        
    def degree_days_monthly(self, months_to_include, site_id):
        """Returns a DataFrame that includes three colunns: fiscal_year, 
        fiscal_mo, and dd.  The 'dd' column gives degree days for the site
        identified by 'site_id'. The months included are specified in the input
        parameter, 'months_to_include', a list of (fiscal_yr, fiscal_mo)
        tuples. For months or sites without degree days, Numpy NaN is returned.
        """
        recs = []
        for yr, mo in months_to_include:
            try:
                deg_days = self._dd[(yr, mo, self._bldg_info[site_id]['dd_site'])]
            except:
                deg_days = np.NaN

            recs.append(
                {'fiscal_year': yr, 
                 'fiscal_mo': mo, 
                 'dd': deg_days
                }
            )
        dfdd = pd.DataFrame(data=recs)
        return dfdd

    def degree_days_yearly(self, months_to_include, site_id):
        """Returns a Pandas series indexed on fiscal year.  The values in the
        series are the total degree days for the fiscal year, but only include
        the months specified in the 'months_to_include' input parameter.  That
        parameter is a list of (fiscal_yr, fiscal_mo)
        tuples. If degree days are not present for some of the months in the
        year, Numpy NaN is returned for the entire year.
        """
        dfdd = self.degree_days_monthly(months_to_include, site_id)
        
        # I had to use the lambda function below in order to have a NaN returned
        # if one or more of the months in the sum was an NaN.
        return dfdd.groupby('fiscal_year').agg({'dd': lambda x: np.sum(x.values)})['dd']
        
       
    def fuel_btus_per_unit(self, fuel_type, fuel_units):
        """Returns the Btus per unit of fuel.
            fuel_type: string, type of fuel in lower case, e.g. Electricity, Natural Gas, etc.
            fuel_units: string, units of the fuel, e.g. CCF, Gallons
        Parameters are case insenstive.  If the fuel type and units are not in
        source spreadsheet, 0.0 is returned.
        """
        return self._fuel_btus.get( (fuel_type.lower(), fuel_units.lower()), 0.0)

    def service_to_category(self):
        """Returns a dictionary that maps service type to a standard service
        cateogory.
        """
        return self._service_to_category.copy()   # return copy to protect original

    def service_category_info(self, service_category):
        """For a 'service_category' that is a fuel (e.g. 'natural_gal') this method
        returns a a two-tuple containing the standard unit for that category 
        (e.g. CCF, Gallons) and the Btus/unit for that unit.
        """
        return self._service_cat_info[service_category]
