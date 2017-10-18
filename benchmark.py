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

In the settings file, you can specify the path to the Utility Bill CSV file you 
want to read and the spreadsheet Other Data file, which contains the list of 
sites to process, information (e.g. square feet) about each site, and degree day 
data.  Modify this spreadsheet according to your needs; create multiple
versions if you sometimes only want to process some of the sites.  The "data"
directory is the best place to put Utility Bill and Other Data files.

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
from datetime import datetime
import pandas as pd
import numpy as np
import bench_util as bu
import graph_util as gu
import template_util
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
        
        for piece in bu.split_period(st, en):
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
    ut = bu.Util(dfu, fn)
    
    # save this object to a pickle file for quick loading
    pickle.dump(ut, open('util_obj.pkl', 'wb'))

    # --- Add Fiscal Year Info and MMBtus
    msg('Add Fiscal Year and MMBtu Information.')
    fyr = []
    fmo = []
    for cyr, cmo in zip(dfu3.cal_year, dfu3.cal_mo):
        fis_yr, fis_mo = bu.calendar_to_fiscal(cyr, cmo)
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
# --------------------------- Analyze One Site --------------------------------

def analyze_site(site, df, ut, report_date_time):
    """This function produces the benchmarking data and graphs for one site. 
    The function returns a large dictionary containing all of the data necessary
    for rendering the benchmarking report template.  This function also creates
    and saves all the necessary graphs; graphs are saved in the directory
    determined in the graph_util.graph_filename_url() function.
    
    Input parameters:
        site:  The Site ID of the site to analyze.
        df:    The preprocessed Pandas DataFrame of Utility Bill information.
        ut:    The bench_util.Util object that provides additional site data
                   needed in the benchmarking process.
        report_date_time: A date/time string indicating when this benchmarking
                   report was done.
    """
    # Start the final data dictionary that is returend.
    template_data = {}

    # --------------------- Building Information Report -----------------------
    
    # This function returns all the needed info for the report, except
    # the date updated
    info = ut.building_info(site)
    
    template_data['building_info'] = {
        'date_updated': report_date_time,
        'bldg': info
    }

    # ----------- DataFrame for "Energy Index Comparison" Report --------------
    
    # --------- Table 1, Yearly Table
    
    # Filter down to just this site's bills and only services that
    # are energy services.
    energy_services = bu.missing_energy_services([])
    df1 = df.query('site_id==@site and service_type==@energy_services')
    
    # Sum Energy Costs and Usage
    df2 = pd.pivot_table(df1, index='fiscal_year', values=['cost', 'mmbtu'], aggfunc=np.sum)
    
    # Add a column showing number of months present in each fiscal year.
    bu.add_month_count_column(df2, df1)
    
    # Make a column with just the Heat MMBtu
    df2['heat_mmbtu'] = df2.mmbtu - df1.query("service_type=='Electricity'").groupby('fiscal_year').sum()['mmbtu']
    
    # Add in degree days to DataFrame
    months_present = bu.months_present(df1)
    deg_days = ut.degree_days_yearly(months_present, site)
    df2['hdd'] = deg_days
    
    # Get building square footage and calculate EUIs and ECI.
    sq_ft = ut.building_info(site)['sq_ft']
    df2['eui'] = df2.mmbtu * 1e3 / sq_ft
    df2['eci'] = df2.cost / sq_ft
    df2['specific_eui'] = df2.heat_mmbtu * 1e6 / df2.hdd / sq_ft
    
    # Restrict to full years
    df2 = df2.query("month_count == 12")
    
    # get the rows as a list of dictionaries and put into
    # final template data dictionary.
    template_data['energy_index_comparison'] = {
        'yearly_table': {'rows': bu.df_to_dictionaries(df2)}
    }
    
    # ---------- Table 2, Details Table

    # Determine month count by year for Electricity to determine the latest
    # complete year.
    electric_only = df.query("service_type == 'Electricity'")
    electric_months_present = bu.months_present(electric_only)
    electric_mo_count = bu.month_count(electric_months_present)
    last_complete_year = max(electric_mo_count[electric_mo_count==12].index)
    
    # Filter down to just the records of the targeted fiscal year
    df1 = df.query('fiscal_year == @last_complete_year')

    # Get Total Utility cost by building. This includes non-energy utilities as well.
    df2 = df1.pivot_table(index='site_id', values=['cost'], aggfunc=np.sum)
    df2.columns = ['total_cost']
    
    # Save this into the Final DataFrame that we will build up as we go.
    df_final = df2.copy()
    
    # Get a list of the Energy Services and restrict the data to
    # just these services
    energy_svcs = bu.missing_energy_services([])
    df2 = df1.query('service_type == @energy_svcs')
    
    # Summarize Cost by Service Type
    df3 = pd.pivot_table(df2, index='site_id', columns='service_type', values='cost', aggfunc=np.sum)
    
    # Change column names
    cols = ['{}_cost'.format(bu.change_name(col)) for col in df3.columns]
    df3.columns = cols
    
    # Add a total energy cost column
    df3['total_energy_cost'] = df3.sum(axis=1)
    
    # Add a total Heat Cost Column
    df3['total_heat_cost'] = df3.total_energy_cost.fillna(0.0) - df3.electricity_cost.fillna(0.0)
    
    # Add this to the final DataFrame
    df_final = pd.concat([df_final, df3], axis=1)
    
    # Summarize MMBtu by Service Type
    df3 = pd.pivot_table(df2, index='site_id', columns='service_type', values='mmbtu', aggfunc=np.sum)
    
    # Change column names
    cols = ['{}_mmbtu'.format(bu.change_name(col)) for col in df3.columns]
    df3.columns = cols
    
    # Add a total mmbtu column
    df3['total_mmbtu'] = df3.sum(axis=1)
    
    # Add a total Heat mmbtu Column
    df3['total_heat_mmbtu'] = df3.total_mmbtu.fillna(0.0) - df3.electricity_mmbtu.fillna(0.0)
    
    # Add this to the final DataFrame
    df_final = pd.concat([df_final, df3], axis=1)
    
    # Electricity kWh summed by building
    df3 = pd.pivot_table(df2.query('units == "kWh"'), index='site_id', values='usage', aggfunc=np.sum)
    df3.columns = ['electricity_kwh']
    
    # Include in Final DF
    df_final = pd.concat([df_final, df3], axis=1)
    
    # Electricity kW, both Average and Max by building
    df3 = pd.pivot_table(df2.query('units == "kW"'), index='site_id', values='usage', aggfunc=[np.mean, np.max])
    df3.columns = ['electricity_kw_average', 'electricity_kw_max']
    
    # Add into Final Frame
    df_final = pd.concat([df_final, df3], axis=1)
    
    # Add in Square footage info
    df_bldg = ut.building_info_df()[['sq_ft']]
    
    # Add into Final Frame.  I do a merge here so as not to bring
    # in buildings from the building info spreadsheet that are not in this
    # dataset; this dataset has been restricted to one year.
    df_final = pd.merge(df_final, df_bldg, how='left', left_index=True, right_index=True)
    
    # Build a DataFrame that has monthly degree days for each site/year/month
    # combination.
    combos = set(zip(df1.site_id, df1.fiscal_year, df1.fiscal_mo))
    df_dd = pd.DataFrame(data=list(combos), columns=['site_id', 'fiscal_year', 'fiscal_mo'])
    ut.add_degree_days_col(df_dd)
    
    # Add up the degree days by site (we've already filtered down to one year or less
    # of data.)
    dd_series = df_dd.groupby('site_id').sum()['degree_days']

    # Put in final DataFrame
    df_final = pd.concat([df_final, dd_series], axis=1)
    
    # Calculate per square foot values for each building.
    df_final['eui'] = df_final.total_mmbtu * 1e3 / df_final.sq_ft
    df_final['eci'] = df_final.total_energy_cost / df_final.sq_ft
    df_final['specific_eui'] = df_final.total_heat_mmbtu * 1e6 / df_final.sq_ft / df_final.degree_days
    
    # Save this to a spreadsheet, if it has not already been saved
    fn = 'output/extra_data/site_summary_FY{}.xlsx'.format(last_complete_year)
    if not os.path.exists(fn):
        excel_writer = pd.ExcelWriter(fn)
        df_final.to_excel(excel_writer, sheet_name='Sites')
    
    # Get the totals across all buildings
    totals_all_bldgs = df_final.sum()

    # Total Degree-Days are not relevant
    totals_all_bldgs.drop(['degree_days'], inplace=True)
    
    # Only use the set of buildings that have some energy use and non-zero
    # square footage to determine EUI's and ECI's
    energy_bldgs = df_final.query("total_mmbtu > 0 and sq_ft > 0")
    
    # Get total square feet, energy use, and energy cost for these buildings
    # and calculate EUI and ECI
    sq_ft_energy_bldgs = energy_bldgs.sq_ft.sum()
    energy_in_energy_bldgs = energy_bldgs.total_mmbtu.sum()
    energy_cost_in_energy_bldgs = energy_bldgs.total_energy_cost.sum()
    totals_all_bldgs['eui'] = energy_in_energy_bldgs * 1e3 / sq_ft_energy_bldgs
    totals_all_bldgs['eci'] = energy_cost_in_energy_bldgs / sq_ft_energy_bldgs
    
    # For calculating heating specific EUI, further filter the set of
    # buildings down to those that have heating fuel use.
    # Get separate square footage total and weighted average degree-day for these.
    heat_bldgs = energy_bldgs.query("total_heat_mmbtu > 0")
    heat_bldgs_sq_ft = heat_bldgs.sq_ft.sum()
    heat_bldgs_heat_mmbtu = heat_bldgs.total_heat_mmbtu.sum()
    heat_bldgs_degree_days = (heat_bldgs.total_heat_mmbtu * heat_bldgs.degree_days).sum() / heat_bldgs.total_heat_mmbtu.sum()
    totals_all_bldgs['specific_eui'] = heat_bldgs_heat_mmbtu * 1e6 / heat_bldgs_sq_ft / heat_bldgs_degree_days
    
    # calculate a rank DataFrame
    df_rank = pd.DataFrame()
    for col in df_final.columns:
        df_rank[col] = df_final[col].rank(ascending=False)
    
    if site in df_final.index:
        # The site exists in the DataFrame
        site_info = df_final.loc[site]
        site_pct = site_info / totals_all_bldgs
        site_rank = df_rank.loc[site]
    else:
        # Site is not there, probabaly because not present in this year.
        # Make variables with NaN values for all elements.
        site_info = df_final.iloc[0].copy()   # Just grab the first row to start with
        site_info[:] = np.NaN                 # Put 
        site_pct = site_info.copy()
        site_rank = site_info.copy()
    
    # Make a final dictioary to hold all the results for this table
    tbl2_data = {
        'fiscal_year': 'FY {}'.format(last_complete_year),
        'bldg': site_info.to_dict(),
        'all': totals_all_bldgs.to_dict(),
        'pct': site_pct.to_dict(),
        'rank': site_rank.to_dict()
    }
    template_data['energy_index_comparison']['details_table'] = tbl2_data
    
    # ------------ DataFrame for "Utility Cost Overview" Report ---------------
    
    # From the main DataFrame, get only the rows for this site, and only get
    # the needed columns for this analysis
    df1 = df.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo', 'cost']]

    # Summarize cost by fiscal year and service type.    
    df2 = pd.pivot_table(
        df1, 
        values='cost', 
        index=['fiscal_year'], 
        columns=['service_type'],
        aggfunc=np.sum
    )
    
    # Add in columns for the missing services
    missing_services = bu.missing_services(df2.columns)
    bu.add_columns(df2, missing_services)
    
    # Add a Total column that sums the other columns
    df2['Total'] = df2.sum(axis=1)
    
    # Add a percent change column
    df2['pct_change'] = df2.Total.pct_change()
    
    # Add in degree days
    months_present = bu.months_present(df1)
    deg_days = ut.degree_days_yearly(months_present, site)
    df2['hdd'] = deg_days
    
    # Add in a column to show the numbers of months present for each year
    # This will help to identify partial years.
    bu.add_month_count_column(df2, df1)
    
    # trim out the partial years
    df2 = df2.query("month_count == 12").copy()
    
    # Reverse the DataFrame
    df2.sort_index(ascending=False, inplace=True)
    
    # Standardize column names
    df2.columns = [bu.change_name(col) for col in df2.columns]
    
    # Reset the index so the fiscal year column can be passed to the graphing utility
    reset_df2 = df2.reset_index()

    # Get appropriate file names and URLs for the graph
    g1_fn, g1_url = gu.graph_filename_url(site, 'util_cost_ovw_g1')
    
    # make the area cost distribution graph
    utility_list = ['electricity', 'natural_gas', 'fuel_oil', 'sewer', 'water', 'refuse', 'district_heat']
    gu.area_cost_distribution(reset_df2, 'fiscal_year', utility_list, g1_fn);
    
    # make the stacked bar graph
    g2_fn, g2_url = gu.graph_filename_url(site, 'util_cost_ovw_g2')
    gu.create_stacked_bar(reset_df2, 'fiscal_year', utility_list, 'Utility Cost ($)', g2_fn)

    # Put results into the final dictionary that will be passed to the Template.
    # A function is used to convert the DataFrame into a list of dictionaries.
    template_data['utility_cost_overview'] = dict(
        graphs=[g1_url, g2_url],
        table={'rows': bu.df_to_dictionaries(df2)},
    )

    return template_data
    

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
    
    # Get a Date/Time String for labeling this report
    report_date_time = datetime.now().strftime('%B %d, %Y %I:%M %p')
    
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

    # Create Index (Home) page
    site_cats = util_obj.site_categories_and_buildings()
    template_data = dict(
        date_updated = report_date_time,
        categories = site_cats
    )
    ix_template = template_util.get_template('index.html')
    result = ix_template.render(template_data)
    open('output/index.html', 'w').write(result)

    # ------ Loop through the sites, creating a report for each
    
    # Get the template used to create the site benchmarking report.
    site_template = template_util.get_template('sites/index.html')
    
    site_count = 0    # tracks number of site processed
    for site_id in util_obj.all_sites():

        msg("Site '{}' is being processed...".format(site_id))
        
        # Run the benchmark analysis for this site, returning the template
        # data.
        template_data = analyze_site(site_id, df, util_obj, report_date_time)

        # save template data variables to debug file if requested
        if settings.WRITE_DEBUG_DATA:
            with open('output/debug/{}.vars'.format(site_id), 'w') as fout:
                pprint.pprint(template_data, fout)

        # create report file
        try:
            result = site_template.render(template_data)
            with open('output/sites/{}.html'.format(site_id), 'w') as fout:
                fout.write(result)
        except:
            print('error')
        
        site_count += 1
        if site_count == settings.MAX_NUMBER_SITES_TO_RUN:
            break
    
    print()
    msg('Benchmarking Script Complete!')
