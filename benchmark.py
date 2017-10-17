#!/usr/bin/env python3
""" -------------------- MAIN BENCHMARKING SCRIPT -----------------------

Run this script by executing the following from a command prompt:
    
    python3 benchmark.py
    
Or, use just "python benchmark.py" if that is how you normally access Python 3.
One some operating systems (Linux, Mac OSX), you may be able to run the script
by executing "./benchmark.py" if you have changed the file mode of the file
to be executable.

This script uses settings from a "settings.py" file, which should be placed
in the same directory as this script.  Start by copying "settings_example.py"
to "settings.py" and then modify settings in that copied file.

In the settings file, you can specify the Utility Bill CSV file you want to 
read and the spreadsheet Other Data file, which contains the list of sites
to process, information (e.g. square feet) about each site, and degree day 
data.  Modify this spreadsheet according to your needs; create multiple
versions if you sometimes only want to process some of the sites.

All reports and other output from this script appear in the "output" directory.
View the resulting benchmarking report by opening the "output/index.html" file.
Other useful data is put in the "output/extra_data" directory, including a 
spreadsheet that summarizes utility information for all of the buildings.

Each time the script is run, all files in the output directory are deleted and
replaced with new files. So, if you have modified any of these files and want
to save your modifications, copy the files to a location outside the output
directory.

The main script code is found at the *bottom* of this file; prior to the script
are the functions that do that main work.  This code handles the main control
flow of the script. This script also relies on a couple
of modules:  bench_util.py, graph_util.py, and template_util.py
These are present in this directory.
"""
import time
import pickle
import glob
import os
import pprint
import pandas as pd
import numpy as np
import bench_util
import settings       # the file holding settings for this script

#*****************************************************************************
#*****************************************************************************
# ----------------------Function for Preprocessing Data ----------------------

def preprocess_data():
    """Loads and processes the Utility Bill data into a smaller and more useable
    form.  Returns a DataFrame with the preprocessed data, and a 
    bench_util.Util object, which provides useful functions to the analysis
    portion of this script.
    
    This the "preprocess_data.ipynb" was used to develop this code and shows
    intermdediate results from each of the steps.
    """
    
    # --- Read the CSV file and convert the billing period dates into 
    #     real Pandas dates
    fn = settings.UTILITY_BILL_FILE_PATH
    msg('Starting to read Utility Bill Data File.')
    dfu = pd.read_csv(fn, parse_dates=['From', 'Thru'])

    # Pickle it for fast loading later, if needed
    dfu.to_pickle('df_raw.pkl')

    msg('Removing Unneed columns and Combining Charges.')
    
    # Filter down to the needed columns and rename them
    cols = [
        ('Site ID', 'site_id'),
        ('From', 'from_dt'),
        ('Thru', 'thru_dt'),
        ('Service Name', 'service_type'),
        ('Item Description', 'item_desc'),
        ('Usage', 'usage'),
        ('Cost', 'cost'),
        ('Units', 'units'),
    ]
    
    old_cols, new_cols = zip(*cols)         # unpack into old and new column names
    dfu1 = dfu[list(old_cols)].copy()       # select just those columns from the origina dataframe
    dfu1.columns = new_cols                 # rename the columns
    
    # --- Collapse Non-Usage Changes into "Other Charge"
    
    # This cuts the processing time in half due to not having to split a whole 
    # bunch of non-consumption charges.
    dfu1.loc[np.isnan(dfu1.usage), 'item_desc'] = 'Other Charge'
    # Pandas can't do a GroupBy on NaNs, so replace with something
    dfu1.units.fillna('-', inplace=True)   
    dfu1 = dfu1.groupby(['site_id', 
                         'from_dt', 
                         'thru_dt', 
                         'service_type', 
                         'item_desc', 
                         'units']).sum()
    dfu1.reset_index(inplace=True)
    
    # --- Split Each Bill into Multiple Pieces, each within one Calendar Month

    msg('Split Bills into Calendar Month Pieces.')
    # Split all the rows into calendar month pieces and make a new DataFrame
    recs=[]
    for ix, row in dfu1.iterrows():
        # it is *much* faster to modify a dictionary than a Pandas series
        row_tmpl = row.to_dict()   
    
        # Pull out start and end of billing period; can drop the from & thru dates now
        # doing split-up of billing period across months.
        st = row_tmpl['from_dt']
        en = row_tmpl['thru_dt']
        del row_tmpl['from_dt']
        del row_tmpl['thru_dt']
        
        for piece in bench_util.split_period(st, en):
            new_row = row_tmpl.copy()
            new_row['cal_year'] = piece.cal_year
            new_row['cal_mo'] = piece.cal_mo
            new_row['days_served'] = piece.days_served
            new_row['usage'] *= piece.bill_frac
            new_row['cost'] *= piece.bill_frac
            recs.append(new_row)
    
    dfu2 = pd.DataFrame(recs, index=range(len(recs)))
    
    # --- Sum Up the Pieces by Month
    dfu3 = dfu2.groupby(
        ['site_id', 'service_type', 'cal_year', 'cal_mo', 'item_desc', 'units']
    ).sum()
    dfu3 = dfu3.reset_index()

    #--- Make a utility function object
    msg('Make an Object containing Useful Utility Functions.')
    fn = settings.OTHER_DATA_FILE_PATH
    ut = bench_util.Util(dfu, fn)
    
    # save this object to a pickle file for quick loading
    pickle.dump(ut, open('util_obj.pkl', 'wb'))

    # --- Add Fiscal Year Info and MMBtus
    msg('Add Fiscal Year and MMBtu Information.')
    fyr = []
    fmo = []
    for cyr, cmo in zip(dfu3.cal_year, dfu3.cal_mo):
        fis_yr, fis_mo = bench_util.calendar_to_fiscal(cyr, cmo)
        fyr.append(fis_yr)
        fmo.append(fis_mo)
    dfu3['fiscal_year'] = fyr
    dfu3['fiscal_mo'] = fmo

    mmbtu = []
    for ix, row in dfu3.iterrows():
        row_mmbtu = ut.fuel_btus_per_unit(row.service_type, row.units) * row.usage / 1e6
        if np.isnan(row_mmbtu): row_mmbtu = 0.0
        mmbtu.append(row_mmbtu)
    dfu3['mmbtu'] = mmbtu
    
    # --- Save this DataFrame in a pickle file for fast loading
    dfu3.to_pickle('df_processed.pkl')
    
    msg('Preprocessing complete!')
    
    return dfu3, ut
    

#******************************************************************************
#******************************************************************************
# ----------------------------- Misc Functions --------------------------------

# Time when the script started running. Used to determine cumulative time
start_time = None
def msg(the_message):
    """Prints a message to the console, along cumulative elapsed time
    since the script started.
    """
    print('{} ({:.1f} s)'.format(the_message, time.time() - start_time))


#*****************************************************************************
#*****************************************************************************
# ----------------------------- Main Script -----------------------------------
    
if __name__=="__main__":
    # Save the time when the script started, so cumulative times can be 
    # shown in messages printed to the console.
    start_time = time.time()
    msg('Benchmarking Script starting!')
    
    # Read and Preprocess the data in the Utility Bill file, acquiring
    # a DataFrame of preprocessed data and a utility function object that is
    # needed by the analysis routines.
    if settings.USE_DATA_FROM_LAST_RUN:
        # Read the data from the pickle files that were created during the
        # last run of the script.
        df = pickle.load(open('df_processed.pkl', 'rb'))
        util_obj = pickle.load(open('util_obj.pkl', 'rb'))
        msg('Data from Last Run has been loaded.')

    else:
        # Run the full reading and processing routine
        df, util_obj = preprocess_data()

    # Clean out the output directories to prepare for the new report files
    out_dirs = [
        'output/debug',
        'output/extra_data',
        'output/images',
        'output/sites'
    ]
    for out_dir in out_dirs:
        for fn in glob.glob(os.path.join(out_dir, '*')):
            if not 'placeholder' in fn:    # don't delete placeholder file
                os.remove(fn)

    # Create Index page

    # Loop through the sites, creating a report for each
    site_count = 0    # tracks number of site processed
    for site_id in util_obj.all_sites():
        msg("Site '{}' is being processed...".format(site_id))
        
        # process site here

        # save vars to debug file

        # create report file        
        
        
        site_count += 1
        if site_count == settings.MAX_NUMBER_SITES_TO_RUN:
            break
    
    print()
    msg('Benchmarking Script Complete!')
