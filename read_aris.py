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

print('\nScript started: {}'.format(time.ctime()))

# URLs and Passwords
base_url = settings.ARIS_API_URL
my_username = settings.ARIS_USERNAME
my_password = settings.ARIS_PASSWORD

# Get the full list of buildings
my_params = {'username': my_username,
             'password':my_password}
building_list_url = base_url + '/GetBuildingList'

# Errors occur here.  Try three times.
for i in range(3):
    try:
        results = requests.post(building_list_url, params=my_params).json()
        break
    except:
        if i==2:
            raise
        else:
            # wait 5 seconds before trying again
            time.sleep(5)
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

    # Errors occur here.  Try three times.
    for i in range(3):
        try:
            detail = requests.post(building_detail_url, data=my_data).json()
            break
        except:
            if i==2:
                raise
            else:
                # wait 5 seconds before trying again
                time.sleep(5)

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

# For the usage end date, 'Thru', use the MeterReadDate if available, otherwise
# use the middle of the UsageDate month.
def thru_date(row):
    if pd.isnull(row.MeterReadDate):
        return row.UsageDate.replace(day=15)
    else:
        return row.MeterReadDate
dfd['Thru'] = dfd.apply(thru_date, axis=1)

# Change 'Demand - Electric' to 'Electric'
dfd.loc[dfd.EnergyTypeName == 'Demand - Electric', 'EnergyTypeName'] = 'Electric'

# There are a number of records where the EnergyQuantity is 0 or NaN,
# which probably occurs because someone doesn't have the bill for that 
# month or there was no fuel fill-up in that month.  We will eliminate
# those records, because they distort the period over which fuel usage
# occurred for sporadically bought fuels like oil and wood.  For 
# monthly-billed fuels, we will later in the code make sure that the 
# From - Thru billing period only covers 1 month.

# Start by converting 0s to NaN to make future tests easier.
dfd.loc[dfd.EnergyQuantity == 0.0, 'EnergyQuantity'] = np.NaN
dfd.loc[dfd.DemandUse == 0.0, 'DemandUse'] = np.NaN

# Also found that there were a bunch of -1.0 values for DemandUse that
# are very likely not valid.
dfd.loc[dfd.DemandUse == -1.0, 'DemandUse'] = np.NaN

# Now filter down to just the records where we have a number for
# either EnergyQuantity or DemandUse.  
mask = ~(dfd.EnergyQuantity.isnull() & dfd.DemandUse.isnull())
dfd = dfd[mask].copy()

# Fill out the From date by using the Thru date from the prior bill 
# for the building and for the particular fuel type
df_final = None
for gp, recs in dfd.groupby(['BuildingId', 'EnergyTypeName']):
    recs = recs.sort_values(['Thru']).copy()
    # Start date comes from prior record
    recs['From'] = recs.Thru.shift(1)
    recs['Item Description'] =  'Energy'
    if df_final is None:
        df_final = recs.copy()
    else:
        df_final = df_final.append(recs, ignore_index=True)

# For the services that are normally billed on a monthly basis, fill out
# any missing From dates (e.g. the first bill for a building) with a value
# 30 days prior to Thru.  Also, restrict the Thru - From difference to 25 to 35 days.
# If it is outside that range, set to Thru - 30 days.

# Fuel types that are normally billed on a monthly basis
mo_fuels = ['Electric', 'Natural Gas', 'Steam District Ht', 'Hot Wtr District Ht']
mask_mo = df_final.EnergyTypeName.isin(mo_fuels)

# Find records of that type that have NaT for From date and 
# set to 30 days prior to Thru
df_final.loc[mask_mo & df_final.From.isnull(), 'From'] = df_final.Thru - timedelta(days=30)

# Now find any records where Thru - From is outside 25 - 35 window and fix those.
# Perhaps they are buildings where there are two separate electric bills.
bill_len = df_final.Thru - df_final.From
mask2 = mask_mo & ((bill_len < timedelta(days=25)) | (bill_len > timedelta(days=35)))
df_final.loc[mask2, 'From'] = df_final.Thru - timedelta(days=30)

# Now work on the fuel types that are not billed monthly. Some of these records
# have NaT for the From date because they were the first record for the building
# and a particular fuel type.  We will ultimately delete these.  In this step
# find sporadically billed records that have a billing length of greater than 450
# days and put a NaT in for From, so that deleting all From==NaT records will catch
# them as well. A billing period more than 450 days probably indicates that a fuel
# fill was missed making the record invalid.
mask_sporadic = ~mask_mo
mask3 = mask_sporadic & (bill_len > timedelta(days=450))
df_final.loc[mask3, 'From'] = pd.NaT

# Now eliminate all the sporadically billed records that have a From
# with a NaT
mask_elim = (mask_sporadic & df_final.From.isnull())
df_final = df_final[~mask_elim].copy()

# Now add the Electric Demand Charge records.  The From-Thru dates on these
# have already been set. The demand quantity and cost
# appear in separate, dedicated columns, but we will move them to the 'EnergyQuantity'
# and 'DollarCost' columns.
df_demand = df_final.query('DemandUse > 0 and EnergyTypeName=="Electric"').copy()
df_demand['EnergyQuantity'] = df_demand.DemandUse
df_demand['DollarCost'] =  df_demand.DemandCost
df_demand['EnergyUnitTypeName'] = 'kW'
df_demand['Item Description'] = 'Demand Charge'

# add these to the final DataFrame
df_final = df_final.append(df_demand, ignore_index=True)

# Eliminate the columns that are not needed
df_final.drop(columns=['DemandCost', 'DemandUse', 'MeterReadDate', 'UsageDate'], inplace=True)

col_map = {
    'BuildingId': 'Site ID',
    'EnergyTypeName': 'Service Name',
    'EnergyUnitTypeName': 'Units',
    'EnergyQuantity': 'Usage',
    'DollarCost': 'Cost',
}
df_final.rename(col_map, axis=1, inplace=True)

# These fields are used in the report summarizing vendors.
df_final['Account Number'] = ''
df_final['Vendor Name'] = ''

# Save the final results as a CSV file and a pickle
df_final.to_pickle('data/aris_records.pkl')
df_final.to_csv('data/aris_records.csv', index=False)

print('Script completed: {}'.format(time.ctime()))
