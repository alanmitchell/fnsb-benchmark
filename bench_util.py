# -*- coding: utf-8 -*-
"""
Utilities for assisting with the benchmarking analysis process.

@author: Alan
"""

from collections import namedtuple
import pandas as pd
import numpy as np

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
        
        # make a dictionary keyed on yr, mo, site_id
        self.dd = {}
        for ix, row in df_dd.iterrows():
            for site in sites:
                self.dd[(row.Month.year, row.Month.month, site)] = row[site]

    def add_degree_days(self, df):
        """Adds a degree-day column to the Pandas DataFrame df.  The new column
        is named "degree_days".  The code assumes that there are columns: 
        cal_year, cal_mo, and site_id already in the DataFrame.  These are 
        used to look-up the degree-days for a paricular site and month.
        """
        dd_col = []
        for ix, row in df.iterrows():
            try:
                deg_days = self.dd[(row.cal_year, row.cal_mo, self.bldg_info[row.site_id].dd_site)]
            except:
                deg_days = np.NaN
                
            dd_col.append(deg_days)
        
        df['degree_days'] = dd_col

