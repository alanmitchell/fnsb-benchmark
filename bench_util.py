# -*- coding: utf-8 -*-
"""
Utilities for assisting with the benchmarking analysis process.
"""
from collections import namedtuple
import pandas as pd
import numpy as np

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

# A dictionary used to map column names to more standardized variable names.
name_changes = {
    'Electricity': 'electricity',
    'Natural Gas': 'natural_gas',
    'Oil #1': 'fuel_oil',
    'Refuse': 'refuse',
    'Sewer': 'sewer',
    'Steam': 'district_heat',
    'Water': 'water',
    'Total': 'total'
}

# If a function is needed to change one name, here is one:
def change_name(old_name):
    """This returns a new name if the old name is in the "name_changes"
    ditionary.  Otherwise, it just returns the old name.
    """
    return name_changes.get(old_name, old_name)

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

# List of all possible services
# I'm leaving out Oil #2 here.
all_services = [
        'Oil #1',
        'Natural Gas',
        'Electricity',
        'Steam',
        'Water',
        'Sewer',
        'Refuse'
]

all_energy_services = [
    'Oil #1',
    'Natural Gas',
    'Electricity',
    'Steam'
]

all_heat_services = [
    'Oil #1',
    'Natural Gas',
    'Steam'
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
    """Adds columns to the DataFrame 'df' if it does not contain all of the
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
        raw_util_df: DataFrame containing the raw utility bill data
        other_data_pth: path to the Excel file containing other application data,
            building info, degree days, etc.
        """
        
        # Read in the Building Information from the Other Data file
        df_bldg = pd.read_excel(
                other_data_pth, 
                sheetname='Building', 
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

        # read in the degree-day info as well.
        df_dd = pd.read_excel(
                other_data_pth, 
                sheetname='Degree Days', 
                skiprows=3, 
                parse_dates=['Month']
                )
        sites = list(df_dd.columns)[1:]
        
        # make a dictionary keyed on fiscal_yr, fiscal_mo, site_id
        # with a value of degree days.
        self._dd = {}
        for ix, row in df_dd.iterrows():
            f_yr, f_mo = calendar_to_fiscal(row.Month.year, row.Month.month)
            for site in sites:
                self._dd[(f_yr, f_mo, site)] = row[site]
  
        # Get Fuel Btu Information and put it in a dictionary as an object
        # attribute.  Keys are fuel type, fuel unit, both in lower case.
        df_fuel = pd.read_excel(other_data_pth, sheetname='Fuel Types', skiprows=3)
        self._fuel_btus = {}
        for ix, row in df_fuel.iterrows():
            self._fuel_btus[(row.fuel.lower(), row.unit.lower())] = row.btu_per_unit

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
            deg_days = self._dd.get((row.fiscal_year, row.fiscal_mo, self._bldg_info[row.site_id]['dd_site']), np.NaN)
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
            recs.append(
                {'fiscal_year': yr, 
                 'fiscal_mo': mo, 
                 'dd': self._dd.get((yr, mo, self._bldg_info[site_id]['dd_site']), np.NaN)
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
            fuel_units: string, units of the fuel, e.g. CCF, Gallongs
        Parameters are case insenstive.  If the fuel type and units are not in
        source spreadsheet, 0.0 is returned.
        """
        return self._fuel_btus.get( (fuel_type.lower(), fuel_units.lower()), 0.0)
    