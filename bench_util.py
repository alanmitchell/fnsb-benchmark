# -*- coding: utf-8 -*-
"""
Utilities for assisting with the benchmarking analysis process.

@author: Alan
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


class Util:
    
    def __init__(self, utility_data_pth, other_data_pth):
        """
        utility_data_pth: path to the CSV file containing all of the utility
            billing records.
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
            try:
                deg_days = self.dd[(row.fiscal_year, row.fiscal_mo, self.bldg_info[row.site_id].dd_site)]
            except:
                deg_days = np.NaN
                
            dd_col.append(deg_days)
        
        df['degree_days'] = dd_col

    def fuel_btus_per_unit(self, fuel_type, fuel_units):
        """Returns the Btus per unit of fuel.
            fuel_type: string, type of fuel in lower case, e.g. Electricity, Natural Gas, etc.
            fuel_units: string, units of the fuel, e.g. CCF, Gallongs
        Parameters are case insenstive.  If the fuel type and units are not in
        source spreadsheet, Numpy NaN is returned.
        """
        return self.fuel_btus.get( (fuel_type.lower(), fuel_units.lower()), np.NaN)
