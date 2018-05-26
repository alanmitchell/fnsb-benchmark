#!/usr/local/bin/python3.6
"""Script to read ARIS utility billing data via the ARIS API and 
transform the data into a format that can be processed by the Fairbanks
North Star Borough (FNSB) benchmarking script.  The output of this script
is a CSV file containing a record for each fuel purchase for a building, 
placed in the data subdirectory with the name 'aris_records.csv'. A second
output is an Excel file with general information for each building present
in the ARIS database; this file is found at 'data/Buildings.xlsx'.  It is 
used by the main benchmarking script. Inputs for this script come from 
the settings.py file in this directory.
"""
import time
from datetime import timedelta
import pandas as pd
import numpy as np
import requests
import settings         # settings file for this application

# URLs and Passwords
base_url = settings.ARIS_API_URL
my_username = settings.ARIS_USERNAME
my_password = settings.ARIS_PASSWORD

# Get the full list of buildings
my_params = {'username': my_username,
             'password':my_password}
building_list_url = base_url + '/GetBuildingList'
results = requests.post(building_list_url, params=my_params).json()
df_bldgs = pd.DataFrame(results)

# Add a Degree-Day Site column by looking up via zip code
df_zip_to_dd = pd.read_excel('data/Zip_to_DD_Site.xlsx', skiprows=4)
df_zip_to_dd['zip_code'] = df_zip_to_dd.zip_code.astype(str)
zip_to_dd = dict(zip(df_zip_to_dd.zip_code, df_zip_to_dd.dd_site))
df_bldgs['dd_site'] = df_bldgs.BuildingZip.map(zip_to_dd)

# So need to find the zip codes that don't map to a Degree-Day site
# 'dd_site != dd_site' is a hack for finding NaN values. 
df_no_map = df_bldgs.query('(BuildingZip > "") and (dd_site != dd_site)')
print('''The following zip codes do not have an entry in the 
"data/Zip_to_DD_Site.xlsx" file, so no degree-days are available:
{}'''.format(df_no_map.BuildingZip.unique()))

# Rename columns and write out the Excel file describing the buildings.
col_map = [
    ('BuildingId', 'site_id'),
    ('BuildingName', 'site_name'),
    ('BuildingOwnerName', 'site_category'),
    ('BuildingStreet', 'address'),
    ('BuildingCity', 'city'),
    ('BuildingUsageName', 'primary_func'),
    ('YearBuilt', 'year_built'),
    ('SquareFeet', 'sq_ft'),
    ('dd_site', 'dd_site')
]
old_cols, new_cols = zip(*col_map)
df_bldgs2 = df_bldgs[list(old_cols)].copy()
df_bldgs2.columns = new_cols
df_bldgs2['onsite_gen'] = ''    # not used
df_bldgs2.to_excel('data/Buildings.xlsx', startrow=3, index=False)

# ----------- Now work on the detailed records, processing to a form
# ----------- usable by the FNSB script.

building_detail_url = base_url + '/GetBuildingEnergyDetail'
my_data = {'username': my_username,
           'password':my_password,
           'buildingId': None}
dfd = None
next_prn = time.time()
for bldg_id in df_bldgs2.site_id.unique():
    my_data['buildingId'] =  bldg_id
    detail = requests.post(building_detail_url, data=my_data).json()
    if len(detail['BuildingEnergyDetailList']):
        df_detail = pd.DataFrame(detail['BuildingEnergyDetailList'])
        # Get rid of unneeded columns
        df_detail.drop(columns=['EnergyTypeId', 'EnergyUnitId', 'UsageYear'], inplace=True)
        if dfd is not None:
            dfd = dfd.append(df_detail, ignore_index=True)
        else:
            dfd = df_detail.copy()
        if time.time() > next_prn:
            print('{:,} records fetched'.format(len(dfd)))
            next_prn += 10.0   # wait 10 seconds before printing

# Change columns to correct data types
dfd = dfd.apply(pd.to_numeric, errors='ignore')
dfd[['UsageDate', 'MeterReadDate']] = dfd[['UsageDate', 'MeterReadDate']].apply(pd.to_datetime)

# Now, need to determine the From and Thru dates for each bill.

# For the usage end date, 'Thru', use the MeterReadDate if available, otherwise
# use the middle of the UsageDate month.
def thru_date(row):
    if pd.isnull(row.MeterReadDate):
        return row.UsageDate.replace(day=15)
    else:
        return row.MeterReadDate
dfd['Thru'] = dfd.apply(thru_date, axis=1)

# Start a new DataFrame to accumulate the final usage records.
df_final = pd.DataFrame()

# The dictionary that renames the columns to names needed 
# by the benchmarking script
col_map = {
    'BuildingId': 'Site ID',
    'EnergyTypeName': 'Service Name',
    'EnergyUnitTypeName': 'Units',
    'EnergyQuantity': 'Usage',
    'DollarCost': 'Cost',
}
def add_to_final(df_to_add):
    """Adds df_to_add to the df_final DataFrame that is accumulating
    finished records.
    """
    global df_final
    df_add = df_to_add.copy()
    df_add.drop(columns=['DemandUse', 'DemandCost', 'UsageDate', 'MeterReadDate'], inplace=True)
    df_add.rename(columns=col_map, inplace=True)
    df_final = df_final.append(df_add, ignore_index=True)
    
# Change the 'Demand - Electric' Fuel Type to 'Electric'
dfd.loc[dfd.EnergyTypeName == 'Demand - Electric', 'EnergyTypeName'] = 'Electric'

# Do Fuel types that are normally billed on a monthly basis
mo_fuels = ['Electric', 'Natural Gas', 'Steam District Ht', 'Hot Wtr District Ht']
df_mo = dfd.query('EnergyTypeName==@mo_fuels').copy()

df_mo.to_pickle('df_mo.pkl')
# Assume start date of billing period was one month prior to end date
df_mo['From'] = df_mo['Thru'] - timedelta(days=30)   # approximate
# now replace with exactly the day that was in the Thru date
df_mo['From'] = [d_fr.replace(day=d_th.day) for d_fr, d_th in zip(df_mo.From, df_mo.Thru)]
df_mo['Item Description'] = 'Energy'   # not critical, except for electric demand

# Add to final DataFrame
add_to_final(df_mo)

# Now add the Electric Demand Charge records
df_demand = df_mo.query('DemandCost > 0 and EnergyTypeName=="Electric"').copy()
df_demand['EnergyQuantity'] = df_demand.DemandUse
df_demand['DollarCost'] =  df_demand.DemandCost
df_demand['EnergyUnitTypeName'] = 'kW'
df_demand['Item Description'] = 'Demand Charge'
# add this to the final DataFrame
add_to_final(df_demand)

# Do all the other fuel types that are sporadically delivered. 
# Assume the start of the billing period is the 15th of the month 
# containing the prior bill.
df_other = dfd.query('EnergyTypeName!=@mo_fuels').copy()

# Separate into a group of records for each Building ID / Fuel Type
# combo.  Determine the starting date of the billing period by 
# bringing forward the date from the prior bill.
for gp, recs in df_other.groupby(['BuildingId', 'EnergyTypeName']):
    recs = recs.query('(DollarCost > 0) or (EnergyQuantity > 0)').copy()
    if len(recs) == 0:
        continue
    recs.sort_values(['Thru'], inplace=True)
    # Start date comes from prior record
    recs['From'] = recs.Thru.shift(1)
    # Drop the first record, cuz no start date for that one
    recs = recs[1:]
    recs['Item Description'] =  'Energy'
    add_to_final(recs)

# Create a column showing length of billing period in days
df_final['PeriodLength'] = [d.days for d in (df_final.Thru - df_final.From)]

# Eliminate records with a large number of days in the Billing period, and 
# then drop the PeriodLength column
df_final.query('PeriodLength < 450', inplace=True)
df_final.drop(columns=['PeriodLength'], inplace=True)

# These fields are used in the report summarizing vendors.  We don't have the
# data, so just leave them blank.
df_final['Account Number'] = ''
df_final['Vendor Name'] = ''

# Save the final results as a CSV file and a pickle
df_final.to_pickle('data/aris_records.pkl')
df_final.to_csv('data/aris_records.csv')
