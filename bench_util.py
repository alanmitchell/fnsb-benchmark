# -*- coding: utf-8 -*-
"""
Utilities for assisting with the benchmarking analysis process.

@author: Alan Mitchell
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

def missing_services(services_present):
    """Returns a list of the Service Types that are *not* present in the 
    'services_present' input list.
    """
    # I'm leaving out Oil #2 here.
    all_services = set([
        'Oil #1',
        'Natural Gas',
        'Electricity',
        'Steam',
        'Water',
        'Sewer',
        'Refuse'
    ])
    
    return list(all_services - set(services_present))

def missing_energy_services(services_present):
    """Returns a list of the Energy-related Service Types that are *not* present
    in the 'services_present' input list.
    """
    energy_services= set([
        'Oil #1',
        'Natural Gas',
        'Electricity',
        'Steam'
    ])

    return list(energy_services - set(services_present))

def add_columns(df, col_names):
    """Adds a new column to the DataFrame df for each column name in the list
    'col_names'.  Sets all the values to 0.0 for that column.
    """
    for col in col_names:
        df[col] = 0.0

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
    
    def __init__(self, raw_util_df, other_data_pth):
        """
        raw_util_df: DataFrame containing the raw utility data
        other_data_pth: path to the Excel file containing other application data,
            building info, degree days, etc.
        """
        
        # Read in the Building Information from the Other Data file
        df_bldg = pd.read_excel(
                other_data_pth, 
                sheetname='Building', 
                skiprows=3, 
                index_col='site_ID'
                )
        # Create a named tuple to hold info for each building
        BldgInfo = namedtuple('BldgInfo', list(df_bldg.columns))

        # create a dictionary to map site_id to info about the building
        self.bldg_info = {}
        for ix, row in df_bldg.iterrows():
            self.bldg_info[row.name] = BldgInfo(**row.to_dict())
        
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
        self.dd = {}
        for ix, row in df_dd.iterrows():
            f_yr, f_mo = calendar_to_fiscal(row.Month.year, row.Month.month)
            for site in sites:
                self.dd[(f_yr, f_mo, site)] = row[site]
  
        # Get Fuel Btu Information and put it in a dictionary as an object
        # attribute.  Keys are fuel type, fuel unit, both in lower case.
        df_fuel = pd.read_excel(other_data_pth, sheetname='Fuel Types', skiprows=3)
        self.fuel_btus = {}
        for ix, row in df_fuel.iterrows():
            self.fuel_btus[(row.fuel.lower(), row.unit.lower())] = row.btu_per_unit

    
    def add_degree_days_col(self, df):
        """Adds a degree-day column to the Pandas DataFrame df.  The new column
        is named "degree_days".  The code assumes that there are columns: 
        fiscal_year, fiscal_mo, and site_id already in the DataFrame.  These are 
        used to look-up the degree-days for a paricular site and month.
        """
        dd_col = []
        for ix, row in df.iterrows():
            deg_days = self.dd.get((row.fiscal_year, row.fiscal_mo, self.bldg_info[row.site_id].dd_site), np.NaN)
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
                 'dd': self.dd.get((yr, mo, self.bldg_info[site_id].dd_site), np.NaN)
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
        source spreadsheet, Numpy NaN is returned.
        """
        return self.fuel_btus.get( (fuel_type.lower(), fuel_units.lower()), np.NaN)
