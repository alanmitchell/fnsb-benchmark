#!/usr/local/bin/python3.6
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
import datetime
import warnings
import pandas as pd
import numpy as np
import bench_util as bu
import graph_util as gu
import template_util
import shutil
import settings       # the file holding settings for this script

# Filter out Matplotlib warnings, as we sometimes get warnings
# related to blank graphs.
warnings.filterwarnings("ignore", module="matplotlib")

#*****************************************************************************
#*****************************************************************************
# ----------------------Function for Preprocessing Data ----------------------

def preprocess_data():
    """Loads and processes the Utility Bill data into a smaller and more usable
    form.  Returns
        - a DataFrame with the raw billing data,
        - a DataFrame with the preprocessed data,
        - and a bench_util.Util object, which provides useful functions to
            the analysis portion of this script.
    
    This the "preprocess_data.ipynb" was used to develop this code and shows
    intermdediate results from each of the steps.
    """

    # --- Read the CSV file and convert the billing period dates into 
    #     real Pandas dates
    fn = settings.UTILITY_BILL_FILE_PATH
    msg('Starting to read Utility Bill Data File.')
    dfu = pd.read_csv(fn, 
                    parse_dates=['From', 'Thru'],
                    dtype={'Site ID': 'object', 'Account Number': 'object'}
                    )

    #--- Make a utility function object
    msg('Make an Object containing Useful Utility Functions.')
    dn = settings.OTHER_DATA_DIR_PATH
    ut = bu.Util(dfu, dn, settings.ADDITIONAL_GROUPING_COLS)

    msg('Removing Unneeded columns and Combining Charges.')

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
            # new_row['days_served'] = piece.days_served    # not really needed
            new_row['usage'] *= piece.bill_frac
            new_row['cost'] *= piece.bill_frac
            recs.append(new_row)

    dfu2 = pd.DataFrame(recs, index=range(len(recs)))

    # --- Sum Up the Pieces by Month
    dfu3 = dfu2.groupby(
        ['site_id', 'service_type', 'cal_year', 'cal_mo', 'item_desc', 'units']
    ).sum()
    dfu3 = dfu3.reset_index()

    # --- Add MMBtus Fiscal Year Info and MMBtus
    msg('Add MMBtu Information.')
    mmbtu = []
    for ix, row in dfu3.iterrows():
        row_mmbtu = ut.fuel_btus_per_unit(row.service_type, row.units) * row.usage / 1e6
        if np.isnan(row_mmbtu): row_mmbtu = 0.0
        mmbtu.append(row_mmbtu)
    dfu3['mmbtu'] = mmbtu

    # Now that original service types have been used to determine MMBtus,
    # convert all service types to standard service types.
    dfu3['service_type'] = dfu3.service_type.map(ut.service_to_category())

    # This may cause multiple rows for a fiscal month and service type.
    # Re-sum to reduce to least number of rows.
    dfu4 = dfu3.groupby(
        ['site_id', 'service_type', 'cal_year', 'cal_mo', 'item_desc', 'units']
    ).sum()
    dfu4 = dfu4.reset_index()

    # Add columns that indicate what type of grouping is being done
    dfu4['group'] = 'facility'

    df_all_groups = pd.DataFrame()
    # now create rows for the other grouping columns.
    for gp_col in settings.ADDITIONAL_GROUPING_COLS:
        dfu_gp = dfu4.copy()
        dfu_gp['group'] = gp_col
        
        # get a dictionary mapping the site_id into the group id
        map_to_group = ut.site_to_col_value_dict(gp_col)
        
        # fill out the 'site_id' column with group values
        dfu_gp['site_id'] = dfu_gp['site_id'].map(map_to_group)
        
        # Only keep rows that have a site_id
        dfu_gp = dfu_gp.loc[dfu_gp.site_id.notna()]
        
        dfu_gp2 = dfu_gp.groupby(
            ['group', 'site_id', 'service_type', 'cal_year', 'cal_mo', 'item_desc', 'units']
        ).sum()
        dfu_gp2.reset_index(inplace=True)
        df_all_groups = pd.concat([df_all_groups, dfu_gp2], sort=True, ignore_index=True)

    # add these records to the prior list of facility records
    dfu4 = pd.concat([dfu4, df_all_groups], sort=True)

    # Add the fiscal year information
    msg('Add Fiscal Year Information.')
    fyr = []
    fmo = []
    for cyr, cmo in zip(dfu4.cal_year, dfu4.cal_mo):
        fis_yr, fis_mo = bu.calendar_to_fiscal(cyr, cmo)
        fyr.append(fis_yr)
        fmo.append(fis_mo)
    dfu4['fiscal_year'] = fyr
    dfu4['fiscal_mo'] = fmo

    msg('Preprocessing complete!')

    return dfu, dfu4, ut
    
#******************************************************************************
#******************************************************************************
# --------- Functions that That Produce Reports for One Site ----------
""" Each of these functions returns, at a minimum, a dictionary containing
data for the report template.
The functions frequently have some or all of the following input parameters, which
are documented here:

    Input parameters:
        site:  The Site ID of the site to analyze.
        df:    The preprocessed Pandas DataFrame of Utility Bill information.
        ut:    The bench_util.Util object that provides additional site data
                   needed in the benchmarking process.
The functions all save the required graphs for their respective reports to the
directory determined in the graph_util.graph_filename_url() function.
"""

# --------------------- Building Information Report -----------------------

def building_info_report(site, ut, report_date_time):
    """
    'report_date_time' is a string giving the date/time this benchmarking
        script was run.
    """

    # This function returns all the needed info for the report, except
    # the date updated
    info = ut.building_info(site)
    
    return dict(
        building_info = dict(
            date_updated = report_date_time,
            bldg = info
        )
    )


# -------------------------- Energy Index Report ----------------------------

def energy_index_report(site, df, ut):
    """As well as returning template data, this function writes a spreadsheet
    that summarizes values for every building.  The spreadsheet is written to
    'output/extra_data/site_summary_FYYYYY.xlsx'.
    """

    # Start a dictionary with the main key to hold the template data
    template_data = {'energy_index_comparison': {}}

    # --------- Table 1, Yearly Table
    
    # Filter down to just this site's bills and only services that
    # are energy services.
    energy_services = bu.missing_energy_services([])
    df1 = df.query('site_id==@site and service_type==@energy_services')

    # Only do this table if there are energy services.
    if not df1.empty:

        # Sum Energy Costs and Usage
        df2 = pd.pivot_table(df1, index='fiscal_year', values=['cost', 'mmbtu'], aggfunc=np.sum)

        # Add a column showing number of months present in each fiscal year.
        bu.add_month_count_column(df2, df1)

        # Make a column with just the Heat MMBtu
        dfe = df1.query("service_type=='electricity'").groupby('fiscal_year').sum()[['mmbtu']]
        dfe.rename(columns={'mmbtu': 'elec_mmbtu'}, inplace = True)
        df2 = df2.merge(dfe, how='left', left_index=True, right_index=True)
        df2['elec_mmbtu'] = df2['elec_mmbtu'].fillna(0.0)
        df2['heat_mmbtu'] = df2.mmbtu - df2.elec_mmbtu

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
        df2 = df2.query("month_count == 12").copy()

        # Reverse the years
        df2.sort_index(ascending=False, inplace=True)

        # get the rows as a list of dictionaries and put into
        # final template data dictionary.
        template_data['energy_index_comparison']['yearly_table'] = {
            'rows': bu.df_to_dictionaries(df2)
        }

    # ---------- Table 2, Details Table

    # Use the last complete year for this site as the year for the Details
    # table.  If there was no complete year for the site, then use the
    # last complete year for the entire dataset.
    if 'df2' in locals() and len(df2):
        last_complete_year = df2.index.max()
    else:
        # Determine month count by year for Electricity in entire dataset
        # to determine the latest complete year.
        electric_only = df.query("service_type == 'electricity'")
        electric_months_present = bu.months_present(electric_only)
        electric_mo_count = bu.month_count(electric_months_present)
        last_complete_year = max(electric_mo_count[electric_mo_count==12].index)

    # Filter down to just the records of the targeted fiscal year and group
    site_grp = ut.building_info(site)['grouping']
    df1 = df.query('fiscal_year == @last_complete_year and group == @site_grp')

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

    # Add in any missing columns
    bu.add_missing_columns(df3, energy_svcs)

    # Change column names
    cols = ['{}_cost'.format(col) for col in df3.columns]
    df3.columns = cols

    # Add a total energy cost column
    df3['total_energy_cost'] = df3.sum(axis=1)

    # Add a total Heat Cost Column
    df3['total_heat_cost'] = df3.total_energy_cost.fillna(0.0) - df3.electricity_cost.fillna(0.0)

    # Add this to the final DataFrame
    df_final = pd.concat([df_final, df3], axis=1, sort=True)

    # Summarize MMBtu by Service Type
    df3 = pd.pivot_table(df2, index='site_id', columns='service_type', values='mmbtu', aggfunc=np.sum)

    # Add in any missing columns
    bu.add_missing_columns(df3, energy_svcs)

    # Change column names
    cols = ['{}_mmbtu'.format(col) for col in df3.columns]
    df3.columns = cols

    # Add a total mmbtu column
    df3['total_mmbtu'] = df3.sum(axis=1)

    # Add a total Heat mmbtu Column
    df3['total_heat_mmbtu'] = df3.total_mmbtu.fillna(0.0) - df3.electricity_mmbtu.fillna(0.0)

    # Add this to the final DataFrame
    df_final = pd.concat([df_final, df3], axis=1, sort=True)

    # Electricity kWh summed by building
    df3 = pd.pivot_table(df2.query('units == "kWh"'), index='site_id', values='usage', aggfunc=np.sum)
    df3.columns = ['electricity_kwh']

    # Include in Final DF
    df_final = pd.concat([df_final, df3], axis=1, sort=True)

    # Electricity kW, both Average and Max by building
    # First, sum up kW pieces for each month.
    df3 = df2.query('units == "kW"').groupby(['site_id', 'fiscal_year', 'fiscal_mo']).sum()
    df3 = pd.pivot_table(df3.reset_index(), index='site_id', values='usage', aggfunc=[np.mean, np.max])
    df3.columns = ['electricity_kw_average', 'electricity_kw_max']

    # Add into Final Frame
    df_final = pd.concat([df_final, df3], axis=1, sort=True)

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
    df_final = pd.concat([df_final, dd_series], axis=1, sort=True)

    # Add in a column that gives the number of months present for each site
    # in this year.  Then filter down to just the sites that have 12 months
    # of data.
    df_final.reset_index(inplace=True)
    df_final['fiscal_year'] = last_complete_year
    df_final.set_index(['site_id', 'fiscal_year'], inplace=True)
    df_final = bu.add_month_count_column_by_site(df_final, df2)
    df_final = df_final.query('month_count==12').copy()
    df_final.reset_index(inplace=True)
    df_final.set_index('site_id', inplace=True)

    # Calculate per square foot values for each building.
    df_final['eui'] = df_final.total_mmbtu * 1e3 / df_final.sq_ft
    df_final['eci'] = df_final.total_energy_cost / df_final.sq_ft
    df_final['specific_eui'] = df_final.total_heat_mmbtu * 1e6 / df_final.sq_ft / df_final.degree_days

    # Save this to a spreadsheet, if it has not already been saved
#    fn = 'output/extra_data/site_summary_FY{}.xlsx'.format(last_complete_year)
#    if not os.path.exists(fn):
#        with pd.ExcelWriter(fn) as excel_writer:
#            df_final.to_excel(excel_writer, sheet_name='Sites')

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

    # -------------- Energy Comparison Graphs ---------------

    # Filter down to only services that are energy services.
    energy_services = bu.missing_energy_services([])
    df4 = df.query('service_type==@energy_services').copy()

    # Sum Energy Costs and Usage
    df5 = pd.pivot_table(df4, index=['site_id', 'fiscal_year'], values=['cost', 'mmbtu'], aggfunc=np.sum)

    # Add a column showing number of months present in each fiscal year.
    df5 = bu.add_month_count_column_by_site(df5, df4)

    # Create an Electric MMBtu column so it can be subtracted from total to determine
    # Heat MMBtu.
    dfe = df4.query("service_type=='Electricity'").groupby(['site_id', 'fiscal_year']).sum()[['mmbtu']]
    dfe.rename(columns={'mmbtu': 'elec_mmbtu'}, inplace = True)
    df5 = df5.merge(dfe, how='left', left_index=True, right_index=True)
    df5['elec_mmbtu'] = df5['elec_mmbtu'].fillna(0.0)
    df5['heat_mmbtu'] = df5.mmbtu - df5.elec_mmbtu

    # Add in degree-days:
    # Create a DataFrame with site, year, month and degree-days, but only one row
    # for each site/year/month combo.
    dfd = df4[['site_id', 'fiscal_year', 'fiscal_mo']].copy()
    dfd.drop_duplicates(inplace=True)
    ut.add_degree_days_col(dfd)

    # Use the agg function below so that a NaN will be returned for the year
    # if any monthly values are NaN
    dfd = dfd.groupby(['site_id', 'fiscal_year']).agg({'degree_days': lambda x: np.sum(x.values)})[['degree_days']]
    df5 = df5.merge(dfd, how='left', left_index=True, right_index=True)

    # Add in some needed building info like square footage, primary function 
    # and building category.
    df_bldg = ut.building_info_df()

    # Shrink to just the needed fields and remove index.
    # Also, fill blank values with 'Unknown'.
    df_info = df_bldg[['sq_ft', 'site_category', 'primary_func']].copy().reset_index()
    df_info['site_category'] = df_info.site_category.fillna('Unknown')
    df_info['primary_func'] = df_info.primary_func.fillna('Unknown Type')

    # Also Remove the index from df5 and merge in building info
    df5.reset_index(inplace=True)
    df5 = df5.merge(df_info, how='left')

    # Now calculate per square foot energy measures
    df5['eui'] = df5.mmbtu * 1e3 / df5.sq_ft
    df5['eci'] = df5.cost / df5.sq_ft
    df5['specific_eui'] = df5.heat_mmbtu * 1e6 / df5.degree_days / df5.sq_ft

    # Restrict to full years
    df5 = df5.query("month_count == 12").copy()

    # Make all of the comparison graphs
    g1_fn, g1_url = gu.graph_filename_url(site, 'eci_func')
    gu.building_type_comparison_graph(df5, 'eci', site, g1_fn)

    g2_fn, g2_url = gu.graph_filename_url(site, 'eci_owner')
    gu.building_owner_comparison_graph(df5, 'eci', site, g2_fn)
    
    g3_fn, g3_url = gu.graph_filename_url(site, 'eui_func')
    gu.building_type_comparison_graph(df5, 'eui', site, g3_fn)

    g4_fn, g4_url = gu.graph_filename_url(site, 'eui_owner')
    gu.building_owner_comparison_graph(df5, 'eui', site, g4_fn)

    g5_fn, g5_url = gu.graph_filename_url(site, 'speui_func')
    gu.building_type_comparison_graph(df5, 'specific_eui', site, g5_fn)

    g6_fn, g6_url = gu.graph_filename_url(site, 'speui_owner')
    gu.building_owner_comparison_graph(df5, 'specific_eui', site, g6_fn)

    template_data['energy_index_comparison']['graphs'] = [
        g1_url, g2_url, g3_url, g4_url, g5_url, g6_url
    ]

    return template_data

# ------------------ Utility Cost Overview Report ----------------------

def utility_cost_report(site, df, ut):
    """As well as return the template data, this function returns a utility cost
    DataFrame that is needed in the Heating Cost Analysis Report.
    """

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
    df2['total'] = df2.sum(axis=1)

    # Add a percent change column
    df2['pct_change'] = df2.total.pct_change()

    # Add in degree days
    months_present = bu.months_present(df1)
    deg_days = ut.degree_days_yearly(months_present, site)
    df2['hdd'] = deg_days

    # Add in a column to show the numbers of months present for each year
    # This will help to identify partial years.
    bu.add_month_count_column(df2, df1)

    # trim out the partial years
    if len(df2):
        df2 = df2.query("month_count == 12").copy()

    # Reverse the DataFrame
    df2.sort_index(ascending=False, inplace=True)

    # Reset the index so the fiscal year column can be passed to the graphing utility
    reset_df2 = df2.reset_index()

    # Save a copy of this DataFrame to return for use in the
    # Heating Cost Analysis Report
    df_utility_cost = reset_df2.copy()

    # Get appropriate file names and URLs for the graph
    g1_fn, g1_url = gu.graph_filename_url(site, 'util_cost_ovw_g1')

    # make the area cost distribution graph
    utility_list = bu.all_services.copy()
    gu.area_cost_distribution(reset_df2, 'fiscal_year', utility_list, g1_fn);

    # make the stacked bar graph
    g2_fn, g2_url = gu.graph_filename_url(site, 'util_cost_ovw_g2')
    gu.create_stacked_bar(reset_df2, 'fiscal_year', utility_list, 'Utility Cost ($)', "Annual Cost by Utility Type",g2_fn)

    # Put results into the final dictionary that will be passed to the Template.
    # A function is used to convert the DataFrame into a list of dictionaries.
    template_data = dict(
        utility_cost_overview = dict(
            graphs=[g1_url, g2_url],
            table={'rows': bu.df_to_dictionaries(df2)}
        )
    )

    return template_data, df_utility_cost

# -------------------- Energy Use and Cost Reports -----------------------

def energy_use_cost_reports(site, df, ut, df_utility_cost):
    """This does both the Energy Usage report and the Energy Cost & Usage
    Pie charts.
    'df_utility_cost' is a summary utility cost DataFrame from the prior
         function.
    As well as returnin the template data, this function returns a summary
    energy usage dataframe.
    """

    # From the main DataFrame, get only the rows for this site, and only get
    # the needed columns for this analysis
    usage_df1 = df.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo', 'mmbtu']]

    # Total mmbtu by service type and year.
    usage_df2 = pd.pivot_table(
        usage_df1,
        values='mmbtu',
        index=['fiscal_year'],
        columns=['service_type'],
        aggfunc=np.sum
    )

    # drop non-energy columns
    non_energy_servics = list(set(bu.all_services) - set(bu.all_energy_services))
    usage_df2 = usage_df2[usage_df2.columns.difference(non_energy_servics)]

    # Add in columns for the missing services
    missing_services = bu.missing_energy_services(usage_df2.columns)
    bu.add_columns(usage_df2, missing_services)

    # Add a Total column that sums the other columns
    usage_df2['total_energy'] = usage_df2.sum(axis=1)
    cols = ['{}_mmbtu'.format(col) for col in usage_df2.columns]
    usage_df2.columns = cols

    # Create a list of columns to loop through and calculate percent total energy
    usage_cols = list(usage_df2.columns.values)
    usage_cols.remove('total_energy_mmbtu')

    for col in usage_cols:
        col_name = col.split('_mmbtu')[0] + "_pct"
        usage_df2[col_name] = usage_df2[col] / usage_df2.total_energy_mmbtu

    # Add in degree days
    months_present = bu.months_present(usage_df1)
    deg_days = ut.degree_days_yearly(months_present, site)
    usage_df2['hdd'] = deg_days

    # Add in a column to show the numbers of months present for each year
    # This will help to identify partial years.
    mo_count = bu.month_count(months_present)
    usage_df2['month_count'] = mo_count

    # Calculate total heat energy and normalized heating usage
    usage_df2['total_heat_mmbtu'] = usage_df2.total_energy_mmbtu - usage_df2.electricity_mmbtu
    usage_df2['total_specific_heat'] = usage_df2.total_heat_mmbtu * 1000 / usage_df2.hdd
    usage_df2 = usage_df2.query("month_count == 12").copy()

    # Reverse the DataFrame
    usage_df2.sort_index(ascending=False, inplace=True)
    usage_df2 = usage_df2.drop('month_count', axis=1)

    # --- Create Energy Usage Overview Graphs

    # Reset the index so the fiscal year column can be passed to the graphing function
    reset_usage_df2 = usage_df2.reset_index()

    p4g2_filename, p4g2_url = gu.graph_filename_url(site, 'energy_usage_ovw_g2')

    # Create the area graph
    gu.area_use_distribution(reset_usage_df2, 'fiscal_year', usage_cols, p4g2_filename)

    # The stacked bar graph
    p4g1_filename, p4g1_url = gu.graph_filename_url(site, 'energy_usage_ovw_g1')
    gu.energy_use_stacked_bar(reset_usage_df2, 'fiscal_year', usage_cols, p4g1_filename)

    # Convert df to dictionary
    energy_use_overview_rows = bu.df_to_dictionaries(usage_df2)

    # Put data and graphs into a dictionary
    template_data = dict(
        energy_usage_overview = dict(
            graphs=[p4g1_url, p4g2_url],
            table={'rows': energy_use_overview_rows}
        )
    )

    # Make a utility list to include only energy-related columns
    utility_list = bu.all_energy_services.copy()

    pie_urls = gu.usage_pie_charts(usage_df2.fillna(0.0), usage_cols, 1, 'energy_usage_pie', site)

    # Make the other graphs and append the URLs
    df_ut_cost = df_utility_cost.set_index('fiscal_year')  # need fiscal_year index for graphs
    pie_urls += gu.usage_pie_charts(df_ut_cost.fillna(0.0),
                                    utility_list,
                                    2,
                                    'energy_cost_pie',
                                    site)

    # Add pie charts to template dictionary
    template_data['energy_cost_usage'] = dict(graphs=pie_urls)

    return template_data, usage_df2

# -------------------- Electrical Usage and Cost Reports  -------------------------

def electrical_usage_and_cost_reports(site, df):
    """This does both the Electrical Usage and Electrical
    Cost reports."""

    site_df = df.query("site_id == @site")

    electric_df = site_df.query("units == 'kWh' or units == 'kW'")
    if 'electricity' in site_df.service_type.unique() and site_df.query("service_type == 'electricity'")['usage'].sum(axis=0) > 0:
        # only look at elecricity records
        electric_pivot_monthly = pd.pivot_table(electric_df,
                                    index=['fiscal_year', 'fiscal_mo'],
                                    columns=['units'],
                                    values='usage',
                                    aggfunc=np.sum)
    else:
        # Create an empty dataframe with the correct index
        electric_pivot_monthly = site_df.groupby(['fiscal_year', 'fiscal_mo']).mean()[[]]

    # Add in missing electricity columns and fill them with zeros
    electric_pivot_monthly = bu.add_missing_columns(electric_pivot_monthly, ['kWh', 'kW'])
    electric_pivot_monthly.kW.fillna(0.0)
    electric_pivot_monthly.kWh.fillna(0.0)

    # Do a month count for the elecricity bills
    elec_months_present = bu.months_present(electric_pivot_monthly.reset_index())
    elec_mo_count = bu.month_count(elec_months_present)
    elec_mo_count_df = pd.DataFrame(elec_mo_count)
    elec_mo_count_df.index.name = 'fiscal_year'

    if 'kWh' in site_df.units.unique() or 'kW' in site_df.units.unique():
        electric_pivot_annual = pd.pivot_table(electric_df,
                                               index=['fiscal_year'],
                                               columns=['units'],
                                               values='usage',
                                               aggfunc=np.sum
                                              )
    else:
        # Create an empty dataframe with the correct index
        electric_pivot_annual = site_df.groupby(['fiscal_year']).mean()[[]]

    electric_pivot_annual = bu.add_missing_columns(electric_pivot_annual, ['kWh', 'kW'])
    electric_use_annual = electric_pivot_annual[['kWh']]
    electric_use_annual = electric_use_annual.rename(columns={'kWh':'ann_electric_usage_kWh'})

    # Get average annual demand usage
    electric_demand_avg = electric_pivot_monthly.groupby(['fiscal_year']).mean()
    electric_demand_avg = electric_demand_avg[['kW']]
    electric_demand_avg = electric_demand_avg.rename(columns={'kW': 'avg_demand_kW'})

    # Find annual maximum demand usage
    electric_demand_max = electric_pivot_monthly.groupby(['fiscal_year']).max()
    electric_demand_max = electric_demand_max[['kW']]
    electric_demand_max = electric_demand_max.rename(columns={'kW': 'max_demand_kW'})

    # Combine dataframes
    electric_demand_join = pd.merge(electric_demand_max, electric_demand_avg, how='outer', left_index=True, right_index=True)
    annual_electric_data = pd.merge(electric_demand_join, electric_use_annual, how='outer', left_index=True, right_index=True)

    # Add percent change columns
    annual_electric_data['usage_pct_change'] = annual_electric_data.ann_electric_usage_kWh.pct_change()
    annual_electric_data['avg_demand_pct_change'] = annual_electric_data.avg_demand_kW.pct_change()
    annual_electric_data['max_demand_pct_change'] = annual_electric_data.max_demand_kW.pct_change()
    annual_electric_data = annual_electric_data.rename(columns={'avg_demand_kW': 'Average kW',
                                                               'ann_electric_usage_kWh': 'Total kWh'})
    annual_electric_data = pd.merge(annual_electric_data, elec_mo_count_df, left_index=True, right_index=True, how='left')
    annual_electric_data = annual_electric_data.query("month == 12")
    annual_electric_data = annual_electric_data.sort_index(ascending=False)
    annual_electric_data = annual_electric_data.rename(columns={'max_demand_kW':'kw_max',
                                                               'Average kW':'kw_avg',
                                                               'Total kWh':'kwh',
                                                               'usage_pct_change':'kwh_pct_change',
                                                               'avg_demand_pct_change':'kw_avg_pct_change',
                                                               'max_demand_pct_change':'kw_max_pct_change'})
    annual_electric_data = annual_electric_data.drop('month', axis=1)

    # ---- Create Electrical Usage Analysis Graphs - Page 6

    # Axes labels
    ylabel1 = 'Electricity Usage [kWh]'
    ylabel2 = 'Electricity Demand [kW]'

    p6g1_filename, p6g1_url = gu.graph_filename_url(site, "electricity_usage_g1")
    gu.stacked_bar_with_line(annual_electric_data.reset_index(), 'fiscal_year', ['kwh'], 'kw_avg',
                          ylabel1, ylabel2, "Annual Electricity Usage and Demand", p6g1_filename)


    p6g2_filename, p6g2_url = gu.graph_filename_url(site, "electricity_usage_g2")
    gu.create_monthly_profile(electric_pivot_monthly, 'kWh', 'Monthly Electricity Usage Profile [kWh]', 'blue',
                             "Monthly Electricity Usage Profile by Fiscal Year",p6g2_filename)

    # Convert df to dictionary
    electric_use_rows = bu.df_to_dictionaries(annual_electric_data)

    # Put data and graphs in a dictionary
    template_data = dict(
        electrical_usage_analysis = dict(
            graphs=[p6g1_url, p6g2_url],
            table={'rows': electric_use_rows}
        )
    )

    # only look at elecricity records
    electric_cost_df = site_df.query("service_type == 'electricity'").copy()

    # Costs don't always have units, so split the data into demand charges and usage charges (which includes other charges)
    electric_cost_df['cost_categories'] = np.where(electric_cost_df.item_desc.isin(['KW Charge', 'On peak demand', 'Demand Charge']),
                                                   'demand_cost', 'usage_cost')

    if 'electricity' in site_df.service_type.unique():
        # Sum costs by demand and usage
        electric_annual_cost = pd.pivot_table(electric_cost_df,
                                               index=['fiscal_year'],
                                               columns=['cost_categories'],
                                               values='cost',
                                               aggfunc=np.sum
                                              )
    else:
        electric_annual_cost = site_df.groupby(['fiscal_year']).mean()[[]]

    electric_annual_cost = bu.add_missing_columns(electric_annual_cost, ['demand_cost', 'usage_cost'] ,0.0)

    # Create a total column
    electric_annual_cost['Total Cost'] = electric_annual_cost[['demand_cost', 'usage_cost']].sum(axis=1)

    # Add percent change columns
    electric_annual_cost['usage_cost_pct_change'] = electric_annual_cost.usage_cost.pct_change()
    electric_annual_cost['demand_cost_pct_change'] = electric_annual_cost.demand_cost.pct_change()
    electric_annual_cost['total_cost_pct_change'] = electric_annual_cost['Total Cost'].pct_change()

    # Left join the cost data to the annual electric data, which only shows complete years
    electric_use_and_cost = pd.merge(annual_electric_data, electric_annual_cost, left_index=True, right_index=True, how='left')
    electric_use_and_cost = electric_use_and_cost.sort_index(ascending=False)
    electric_use_and_cost = electric_use_and_cost.drop(['kw_max', 'kw_max_pct_change'], axis=1)
    electric_use_and_cost = electric_use_and_cost.rename(columns={'demand_cost':'kw_avg_cost',
                                                                  'usage_cost':'kwh_cost',
                                                                  'Total Cost':'total_cost',
                                                                  'usage_cost_pct_change':'kwh_cost_pct_change',
                                                                  'demand_cost_pct_change':'kw_avg_cost_pct_change'
                                                                 })
    # --- Create Electrical Cost Analysis Graphs

    p7g1_filename, p7g1_url = gu.graph_filename_url(site, "electrical_cost_g1")

    renamed_use_and_cost = electric_use_and_cost.rename(columns={'kwh_cost':'Electricity Usage Cost [$]',
                                                                'kw_avg_cost':'Electricity Demand Cost [$]'})
    gu.create_stacked_bar(renamed_use_and_cost.reset_index(), 'fiscal_year', ['Electricity Usage Cost [$]',
                                                                              'Electricity Demand Cost [$]'],
                          'Electricity Cost [$]', "Annual Electricity Usage and Demand Costs", p7g1_filename)

    # Create Monthly Profile of Electricity Demand
    p7g2_filename, p7g2_url = gu.graph_filename_url(site, "electrical_cost_g2")
    gu.create_monthly_profile(electric_pivot_monthly, 'kW', 'Monthly Electricity Demand Profile [kW]', 'blue',
                              "Monthly Electricity Demand Profile by Fiscal Year",p7g2_filename)

    # Convert df to dictionary
    electric_cost_rows = bu.df_to_dictionaries(electric_use_and_cost)

    # Add data and graphs to main dictionary
    template_data['electrical_cost_analysis'] = dict(
        graphs=[p7g1_url, p7g2_url],
        table={'rows': electric_cost_rows},
    )

    return template_data

# --------------------Heating Usage and Cost Reports ------------------------
def heating_usage_cost_reports(site, df, ut, df_utility_cost, df_usage):
    '''This produces both the Heating Usage and the Heating Cost
    reports.
    'df_utility_cost': The utility cost DataFrame produced in the
    utility_cost_report function above.
    'df_usage': A summary energy usage DataFrame produced in the prior
    energy_use_cost_reports function.
    '''

    heat_service_mmbtu_list = []
    for heat_service in bu.all_heat_services:
        heat_service_mmbtu_list.append(heat_service + '_mmbtu')

    keep_cols_list = heat_service_mmbtu_list + ['hdd', 'total_heat_mmbtu']

    heating_usage = df_usage[keep_cols_list].copy()

    # Add in percent change columns
    # First sort so the percent change column is correct and then re-sort the other direction
    heating_usage.sort_index(ascending=True, inplace=True)
    for heating_service in heat_service_mmbtu_list:
        new_col_name = heating_service.split('_mmbtu')[0] + '_pct_change'
        heating_usage[new_col_name] = heating_usage[heating_service].pct_change()
    heating_usage['total_heat_pct_change'] = heating_usage.total_heat_mmbtu.pct_change()
    # Now reset the sorting
    heating_usage.sort_index(ascending=False, inplace=True)

    # Get the number of gallons, ccf, and cords of wood by converting MMBTUs using the supplied conversions
    # This is hard-coded because I couldn't figure out how to do it more generically
    heating_usage['fuel_oil_usage'] = heating_usage.fuel_oil_mmbtu * 1000000 / ut.service_category_info('fuel_oil')[1]
    heating_usage['natural_gas_usage'] = heating_usage.natural_gas_mmbtu * 1000000 / ut.service_category_info('natural_gas')[1]
    heating_usage['propane_usage'] = heating_usage.propane_mmbtu * 1000000 / ut.service_category_info('propane')[1]
    heating_usage['wood_usage'] = heating_usage.wood_mmbtu * 1000000 / ut.service_category_info('wood')[1]
    heating_usage['coal_usage'] = heating_usage.coal_mmbtu * 1000000 / ut.service_category_info('coal')[1]

    # ----- Create Heating Usage Analysis Graphs

    p8g1_filename, p8g1_url = gu.graph_filename_url(site, "heating_usage_g1")
    gu.stacked_bar_with_line(heating_usage.reset_index(), 'fiscal_year', heat_service_mmbtu_list, 'hdd',
                            'Heating Fuel Usage [MMBTU/yr]', 'Heating Degree Days [Base 65F]',
                             "Annual Heating Energy Use and Degree Day Comparison", p8g1_filename)

    # --- Create Monthly Heating Usage dataframe for graph

    # From the main DataFrame, get only the rows for this site, and only get
    # the needed columns for this analysis
    usage_df1 = df.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo', 'mmbtu']]
    monthly_heating = pd.pivot_table(usage_df1,
                                    values='mmbtu',
                                    index=['fiscal_year', 'fiscal_mo'],
                                    columns=['service_type'],
                                    aggfunc=np.sum
                                    )

    # Add in columns for the missing energy services
    missing_services = bu.missing_energy_services(monthly_heating.columns)
    bu.add_columns(monthly_heating, missing_services)

    # Use only heat services
    monthly_heating = monthly_heating[bu.all_heat_services]

    # Create a total heating column
    monthly_heating['total_heating_energy'] = monthly_heating.sum(axis=1)

    p8g2_filename, p8g2_url = gu.graph_filename_url(site, "heating_usage_g2")
    gu.create_monthly_profile(monthly_heating, 'total_heating_energy', "Monthly Heating Energy Profile [MMBTU]", 'red',
                              "Monthly Heating Energy Usage Profile by Fiscal Year", p8g2_filename)

    # Convert df to dictionary
    heating_use_rows = bu.df_to_dictionaries(heating_usage)

    # Add data and graphs to a dictionary
    template_data = dict(
        heating_usage_analysis = dict(
            graphs=[p8g1_url, p8g2_url],
            table={'rows': heating_use_rows}
        )
    )

    # Using the Utility Cost DataFrame passed in as a parameter,
    # Put DataFrame back into ascending order, as we need to calculate
    # a percent change column.
    # Index is NOT Years
    df_utility_cost.sort_values('fiscal_year', ascending=True, inplace=True)

    # Make a total heat cost column and it's percent change
    df_utility_cost['total_heat_cost'] = df_utility_cost[bu.all_heat_services].sum(axis=1)
    df_utility_cost['total_heat_cost_pct_change'] = df_utility_cost.total_heat_cost.pct_change()

    # Now back in descending order
    df_utility_cost.sort_values('fiscal_year', ascending=False, inplace=True)

    cols_to_keep = bu.all_heat_services + ['fiscal_year', 'total_heat_cost','total_heat_cost_pct_change']

    # Use only necessary columns
    heating_cost = df_utility_cost[cols_to_keep]

    cost_cols = [col + "_cost" for col in bu.all_heat_services]
    cost_col_dict = dict(zip(bu.all_heat_services, cost_cols))

    # Change column names so they aren't the same as the heating usage dataframe
    heating_cost = heating_cost.rename(columns=cost_col_dict)

    # Combine the heating cost and heating use dataframes
    heating_cost_and_use = pd.merge(heating_cost, heating_usage, left_on='fiscal_year', right_index=True, how='right')

    # Put DataFrame in ascending order to calculate percent change
    heating_cost_and_use.sort_values('fiscal_year', ascending=True, inplace=True)

    # This will be used to shorten final dataframe
    final_cost_col_list = list(cost_cols)

    # Create percent change columns
    for col in cost_cols:
        new_col = col.split('_cost')[0] + '_pct_change'
        heating_cost_and_use[new_col] = heating_cost_and_use[col].pct_change()
        final_cost_col_list.append(new_col)

    # Back to descending order
    heating_cost_and_use.sort_values('fiscal_year', ascending=False, inplace=True)

    # Create unit cost columns
    for col in cost_cols:
        n_col = col.split('_cost')[0] + '_unit_cost'
        mmbtu_col = col.split('_cost')[0] + '_mmbtu'
        heating_cost_and_use[n_col] = heating_cost_and_use[col] / heating_cost_and_use[mmbtu_col]
        final_cost_col_list.append(n_col)

    heating_cost_and_use['building_heat_unit_cost'] = heating_cost_and_use.total_heat_cost / heating_cost_and_use.total_heat_mmbtu

    # Remove all columns not needed for the Heating Cost Analysis Table
    final_cost_col_list = final_cost_col_list + ['fiscal_year','building_heat_unit_cost',
                                                 'total_heat_cost','total_heat_cost_pct_change']

    heating_cost_and_use = heating_cost_and_use[final_cost_col_list]

    # ---- Create DataFrame with the Monthly Average Price Per MMBTU for All Sites

    # Filter out natural gas customer charges as the unit cost goes to infinity if there is a charge but no use
    df_no_gas_cust_charges = df.drop(df[(df['service_type'] == 'natural_gas') & (df['units'] != 'CCF')].index)

    # Filter out records with zero usage, which correspond to things like customer charges, etc.
    nonzero_usage = df_no_gas_cust_charges.query("usage > 0")

    nonzero_usage = nonzero_usage.query("mmbtu > 0")

    # Filter out zero cost or less records (these are related to waste oil)
    nonzero_usage = nonzero_usage.query("cost > 0")

    # Get the total fuel cost and usage for all buildings by year and month
    grouped_nonzero_usage = nonzero_usage.groupby(['service_type', 'fiscal_year', 'fiscal_mo']).sum()

    # Divide the total cost for all building by the total usage for all buildings so that the average is weighted correctly
    grouped_nonzero_usage['avg_price_per_mmbtu'] = grouped_nonzero_usage.cost / grouped_nonzero_usage.mmbtu

    # Get only the desired outcome, price per million BTU for each fuel type, and the number of calendar months it is based on
    # i.e. the number of months of bills for each fuel for all buildings for that particular month.
    grouped_nonzero_usage = grouped_nonzero_usage[['avg_price_per_mmbtu', 'cal_mo']]

    # Drop electricity from the dataframe.
    grouped_nonzero_usage = grouped_nonzero_usage.reset_index()
    grouped_nonzero_heatfuel_use = grouped_nonzero_usage.query("service_type != 'Electricity'")

    # Create a column for each service type
    grouped_nonzero_heatfuel_use = pd.pivot_table(grouped_nonzero_heatfuel_use,
                                                  values='avg_price_per_mmbtu',
                                                  index=['fiscal_year', 'fiscal_mo'],
                                                  columns='service_type'
                                                    )
    grouped_nonzero_heatfuel_use = grouped_nonzero_heatfuel_use.reset_index()

    # --- Monthly Cost Per MMBTU: Data and Graphs

    # Exclude other charges from the natural gas costs.  This is because the unit costs for natural gas go to infinity
    # when there is zero usage but a customer charge
    cost_df1 = df.drop(df[(df['service_type'] == 'natural_gas') & (df['units'] != 'CCF')].index)

    # Create cost dataframe for given site from processed data
    cost_df1 = cost_df1.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo', 'cost']]

    # Split out by service type
    monthly_heating_cost = pd.pivot_table(cost_df1,
                                    values='cost',
                                    index=['fiscal_year', 'fiscal_mo'],
                                    columns=['service_type'],
                                    aggfunc=np.sum
                                    )

    # Add in columns for the missing energy services
    missing_services = bu.missing_energy_services(monthly_heating_cost.columns)
    bu.add_columns(monthly_heating_cost, missing_services)

    monthly_heating_cost = monthly_heating_cost[bu.all_heat_services]

    # Create a total heating column
    monthly_heating_cost['total_heating_cost'] = monthly_heating_cost.sum(axis=1)

    monthly_heating_cost = monthly_heating_cost.rename(columns=cost_col_dict)

    monthly_heat_energy_and_use = pd.merge(monthly_heating_cost, monthly_heating, left_index=True, right_index=True, how='outer')

    # Create unit cost columns in $ / MMBTU for each fuel type
    for col in cost_cols:
        n_col_name = col.split('_cost')[0] + "_unit_cost"
        use_col_name = col.split('_cost')[0]
        monthly_heat_energy_and_use[n_col_name] = monthly_heat_energy_and_use[col] / monthly_heat_energy_and_use[use_col_name]

    monthly_heat_energy_and_use['building_unit_cost'] = monthly_heat_energy_and_use.total_heating_cost / monthly_heat_energy_and_use.total_heating_energy

    # Reset the index for easier processing
    monthly_heat_energy_and_use = monthly_heat_energy_and_use.reset_index()

    # Add in unit costs for fuels that are currently blank

    # Get only columns that exist in the dataframe
    available_service_list = list(grouped_nonzero_heatfuel_use.columns.values)

    heat_services_in_grouped_df = list(set(bu.all_heat_services) & set(available_service_list))

    unit_cost_cols = [col + "_unit_cost" for col in heat_services_in_grouped_df]
    service_types = [col + "_avg_unit_cost" for col in heat_services_in_grouped_df]

    unit_cost_dict = dict(zip(unit_cost_cols,service_types))


    # Add in average unit costs calculated from all sites for each month
    monthly_heat_energy_and_use = pd.merge(monthly_heat_energy_and_use, grouped_nonzero_heatfuel_use,
                                           left_on=['fiscal_year', 'fiscal_mo'], right_on=['fiscal_year', 'fiscal_mo'],
                                          how='left', suffixes=('', '_avg_unit_cost'))

    # Check each column to see if it is NaN (identified when the value does not equal itself) and if it is, fill with the average
    # price per MMBTU taken from all sites
    for col, service in unit_cost_dict.items():
        monthly_heat_energy_and_use[col] = np.where(monthly_heat_energy_and_use[col] != monthly_heat_energy_and_use[col],
                                                   monthly_heat_energy_and_use[service],
                                                   monthly_heat_energy_and_use[col])

    # Add calendar year and month columns
    cal_year = []
    cal_mo = []
    for fiscal_year, fiscal_mo in zip(monthly_heat_energy_and_use.fiscal_year, monthly_heat_energy_and_use.fiscal_mo):
        CalYear, CalMo = bu.fiscal_to_calendar(fiscal_year, fiscal_mo)
        cal_year.append(CalYear)
        cal_mo.append(CalMo)
    monthly_heat_energy_and_use['calendar_year'] = cal_year
    monthly_heat_energy_and_use['calendar_mo'] = cal_mo

    # Create a date column using the calendar year and month to pass to the graphing function

    def get_date(row):
        return datetime.date(year=row['calendar_year'], month=row['calendar_mo'], day=1)

    monthly_heat_energy_and_use['date'] = monthly_heat_energy_and_use[['calendar_year','calendar_mo']].apply(get_date, axis=1)

    p9g1_filename, p9g1_url = gu.graph_filename_url(site, "heating_cost_g1")
    gu.fuel_price_comparison_graph(monthly_heat_energy_and_use, 'date', unit_cost_cols, 'building_unit_cost', p9g1_filename)

    # --- Realized Savings from Fuel Switching: Page 9, Graph 2

    # Create an indicator for whether a given heating fuel is available for the facility.  This is done by checking the use for all
    # months- if it is zero, then that building doesn't have the option to use that type of fuel.
    for col in bu.all_heat_services:
        new_col_name = col + "_available"
        monthly_heat_energy_and_use[new_col_name] = np.where(monthly_heat_energy_and_use[col].sum() == 0, 0, 1)

    # Calculate what it would have cost if the building used only one fuel type
    available_cols = []
    unit_cost_cols_2 = []
    for col in bu.all_heat_services:
        available_cols.append(col + "_available")
        unit_cost_cols_2.append(col + "_unit_cost")
    available_dict = dict(zip(unit_cost_cols_2, available_cols))
    hypothetical_cost_cols = []

    for unit_cost, avail_col in available_dict.items():
        new_col_name = unit_cost + "_hypothetical"
        hypothetical_cost_cols.append(new_col_name)
        monthly_heat_energy_and_use[new_col_name] = monthly_heat_energy_and_use[unit_cost] * monthly_heat_energy_and_use.total_heating_energy * monthly_heat_energy_and_use[avail_col]

    # Calculate the monthly savings to the building by not using the most expensive available fuel entirely
    monthly_heat_energy_and_use['fuel_switching_savings'] = monthly_heat_energy_and_use[hypothetical_cost_cols].max(axis=1) - monthly_heat_energy_and_use.total_heating_cost

    # Sort dataframe to calculate cumulative value
    monthly_heat_energy_and_use = monthly_heat_energy_and_use.sort_values(by='date', ascending=True)

    # Calculate cumulative value
    monthly_heat_energy_and_use['cumulative_fuel_switching_savings'] = np.cumsum(monthly_heat_energy_and_use.fuel_switching_savings)

    p9g2_filename, p9g2_url = gu.graph_filename_url(site, "heating_cost_g2")
    gu.create_monthly_line_graph(monthly_heat_energy_and_use, 'date', 'cumulative_fuel_switching_savings',
                                'Cumulative Fuel Switching Savings Realized [$]', p9g2_filename)

    # Convert df to dictionary
    heating_cost_rows = bu.df_to_dictionaries(heating_cost_and_use)

    # Add data and graphs to main dictionary
    template_data['heating_cost_analysis'] = dict(
        graphs=[p9g1_url, p9g2_url],
        table={'rows': heating_cost_rows},
    )

    return template_data

# ---------------------- Water Analysis Table ---------------------------

def water_report(site, df):

    water_use = df.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo','cost', 'usage', 'units']]

    # Create month count field for all months that have water and sewer bills
    water_use_only = water_use.query("service_type == 'water'")
    water_months_present = bu.months_present(water_use_only)
    water_mo_count = bu.month_count(water_months_present)

    # Create annual water gallon usage dataframe
    water_gal_df = pd.pivot_table(water_use,
                                  values='usage',
                                  index=['fiscal_year',],
                                  columns=['service_type'],
                                  aggfunc=np.sum
    )

     # Add in columns for the missing services
    gal_missing_services = bu.missing_services(water_gal_df.columns)
    bu.add_columns(water_gal_df, gal_missing_services)

    # Use only required columns
    water_gal_df = water_gal_df[['water']]

    # Calculate percent change column
    water_gal_df['water_use_pct_change'] = water_gal_df.water.pct_change()

    # Create annual water and sewer cost dataframe
    water_cost_df = pd.pivot_table(water_use,
                                  values='cost',
                                  index=['fiscal_year',],
                                  columns=['service_type'],
                                  aggfunc=np.sum
    )


    # Add in columns for the missing services
    water_missing_services = bu.missing_services(water_cost_df.columns)
    bu.add_columns(water_cost_df, water_missing_services)

    # Calculate totals, percent change
    cols_to_remove = bu.all_energy_services + ['refuse']
    water_cost_df = water_cost_df[water_cost_df.columns.difference(cols_to_remove)]

    rename_dict = {'sewer': 'Sewer Cost',
                   'water': 'Water Cost'}

    water_cost_df = water_cost_df.rename(columns=rename_dict)

    # First check to make sure sewer data is included; if so, calculate total cost
    water_cost_df['total_water_sewer_cost'] = water_cost_df.sum(axis=1)

    water_cost_df['water_cost_pct_change'] = water_cost_df['Water Cost'].pct_change()
    water_cost_df['sewer_cost_pct_change'] = water_cost_df['Sewer Cost'].pct_change()

    water_cost_df['total_water_sewer_cost_pct_change'] = water_cost_df.total_water_sewer_cost.pct_change()

    # Merge use and cost dataframes
    water_use_and_cost = pd.merge(water_cost_df, water_gal_df, left_index=True, right_index=True, how='left')

    water_use_and_cost['water_unit_cost'] = water_use_and_cost.total_water_sewer_cost / water_use_and_cost.water
    water_use_and_cost['water_unit_cost_pct_change'] = water_use_and_cost.water_unit_cost.pct_change()

    # Use only complete years
    water_use_and_cost['month_count'] = water_mo_count
    if len(water_use_and_cost):
        water_use_and_cost = water_use_and_cost.query("month_count == 12")
    water_use_and_cost = water_use_and_cost.drop('month_count', axis=1)
    water_use_and_cost = water_use_and_cost.sort_index(ascending=False)
    water_use_and_cost = water_use_and_cost.rename(columns={'Sewer Cost':'sewer_cost',
                                                           'Water Cost':'water_cost',
                                                           'total_water_sewer_cost':'total_cost',
                                                           'total_water_sewer_cost_pct_change':'total_cost_pct_change',
                                                           'water':'total_usage',
                                                           'water_use_pct_change':'total_usage_pct_change',
                                                           'water_unit_cost':'total_unit_cost',
                                                           'water_unit_cost_pct_change':'total_unit_cost_pct_change'
                                                           })

    # ---- Create Water Cost Stacked Bar Graph - Page 10 Graph 1

    p10g1_filename, p10g1_url = gu.graph_filename_url(site, "water_analysis_g1")
    gu.create_stacked_bar(water_use_and_cost.reset_index(), 'fiscal_year', ['sewer_cost', 'water_cost'],
                          'Utility Cost [$]', "Annual Water and Sewer Costs", p10g1_filename)

    # ---- Create Monthly Water Profile Graph

    # Create monthly water gallon dataframe
    water_gal_df_monthly = pd.pivot_table(water_use,
                                  values='usage',
                                  index=['fiscal_year', 'fiscal_mo'],
                                  columns=['service_type'],
                                  aggfunc=np.sum
    )

    p10g2_filename, p10g2_url = gu.graph_filename_url(site, "water_analysis_g2")

    if 'water' in list(water_gal_df_monthly.columns.values):
        gu.create_monthly_profile(water_gal_df_monthly, 'water', 'Monthly Water Usage Profile [gallons]', 'green',
                                  "Monthly Water Usage Profile by Fiscal Year", p10g2_filename)
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(p10g2_filename))

    # Convert df to dictionary
    water_rows = bu.df_to_dictionaries(water_use_and_cost)

    # Return data and graphs in a dictionary
    return dict(
        water_analysis = dict(
            graphs=[p10g1_url, p10g2_url],
            table={'rows': water_rows}
        )
    )

# ---------------------- FY Analysis Table ---------------------------

def FY_spreadsheets(dfp, ut):
    """ Iterates through pre-processed billing dataframe and creates spreadsheet for each fiscal year. Saves .xlsx 
        spreadsheet for each fiscal year with a row of data for each sites and grouping.  Returns nothing.
    """
    
    # --- Read the CSV file and convert the billing period dates into 
    #     real Pandas dates

    ## Filter by FY, Pivot Table by Site
    fy = dfp['fiscal_year'].unique()

    for year in fy:

        df_fy = dfp.query('fiscal_year==@year')

        # Summarize FY Cost and usage by Service Type

        # Create pivot table of cost data
        df_FYcost = pd.pivot_table(df_fy, index=['site_id'], columns='service_type', values='cost', aggfunc=np.sum)
        df_FYcost = bu.add_missing_columns(df_FYcost, bu.missing_services([]))
        try: 
            df_FYcost['electricity_energy'] = pd.pivot_table(df_fy, index=['site_id'], columns='units', values='cost', aggfunc=np.sum)['kWh']
        except:
            df_FYcost['electricity_energy'] = 0.0
        try:
            df_FYcost['electricity_demand'] = pd.pivot_table(df_fy, index=['site_id'], columns='units', values='cost', aggfunc=np.sum)['kW']
        except:
            df_FYcost['electricity_demand'] = 0.0
        df_FYcost = df_FYcost.add_suffix('_cost')

        # Calculate additional cost totals
        df_FYcost['total_utility_cost'] = df_FYcost.sum(axis=1)
        df_FYcost['total_water_cost'] = df_FYcost[['water_cost', 'sewer_cost']].sum(axis=1)
        df_FYcost['total_energy_cost'] = df_FYcost.total_utility_cost - df_FYcost.total_water_cost
        df_FYcost['total_heat_cost'] = df_FYcost.total_energy_cost - df_FYcost.electricity_cost

        # Create pivot table of usage data in native units
        df_FYusage = pd.pivot_table(df_fy, index=['site_id'], columns='service_type', values='usage', aggfunc=np.sum)
        try:
            df_FYusage['electricity_energy'] = pd.pivot_table(df_fy, index=['site_id'], columns='units', values='usage', aggfunc=np.sum)['kWh']
        except:
            df_FYusage['electricity_energy'] = 0.0
        try:
            df_FYusage['electricity_demand'] = pd.pivot_table(df_fy, index=['site_id'], columns='units', values='usage', aggfunc=np.sum)['kW']
        except:
            df_FYusage['electricity_demand'] = 0.0
        df_FYusage['electricity_avg_demand'] = df_FYusage['electricity_energy'] / 365
        df_FYusage = bu.add_missing_columns(df_FYusage, bu.missing_services([]))
        
        df_FYusage = df_FYusage.add_suffix('_usage')

        # Create pivot table of usage data in mmbtu units
        df_FYBTU = pd.pivot_table(df_fy, index=['site_id'], columns='service_type', values='mmbtu', aggfunc=np.sum)
        df_FYBTU = bu.add_missing_columns(df_FYBTU, bu.missing_services([]))
        df_FYBTU = df_FYBTU.add_suffix('_mmbtu')
        df_FYBTU['total_energy_mmbtu'] = df_FYBTU.sum(axis=1)
        df_FYBTU['total_heat_mmbtu'] = df_FYBTU.total_energy_mmbtu - df_FYBTU.electricity_mmbtu
        
        #Merge Dataframes
        df_FYtotal = pd.concat([df_FYcost, df_FYusage, df_FYBTU], axis=1)

        # Add in HDD an sqft to df_FYtotal
        # iterate through sites

        sq_ft=[]
        dd=[]

        for site_id, row in df_FYtotal.iterrows():
            df_site = df_fy.query('site_id == @site_id')
            mo_present = bu.months_present(df_site, yr_col='fiscal_year', mo_col='fiscal_mo')
            dd_series = ut.degree_days_yearly(mo_present, site_id)
            dd.append(dd_series.iloc[0])
            try:
                bi = ut.building_info(site_id)
                sq = bi['sq_ft']
            except:
                print(site_id)    
                sq = np.nan
            sq_ft.append(sq)


        df_FYtotal['dd'] = dd
        df_FYtotal['sq_ft'] = sq_ft
        
        

        # Caclulate EUI, ECI

        #Use HDD and SQFT to calculate EUIs and ECI.
        df_FYtotal['eci'] = df_FYtotal.total_energy_cost / df_FYtotal.sq_ft
        df_FYtotal['uci'] = df_FYtotal.total_utility_cost / df_FYtotal.sq_ft
        df_FYtotal['eui'] = df_FYtotal.total_energy_mmbtu * 1e3 / df_FYtotal.sq_ft
        df_FYtotal['specific_eui'] = df_FYtotal.total_heat_mmbtu * 1e6 / df_FYtotal.dd / df_FYtotal.sq_ft
        df_FYtotal['heat_mmbtu_per_hdd'] = df_FYtotal['total_heat_mmbtu'] / df_FYtotal['dd']
        df_FYtotal['electricity_peak2avg_ratio'] = df_FYtotal['electricity_avg_demand_usage'] / df_FYtotal['electricity_demand_usage']
        #Select Desired Columns and export to excel  - This is the spreadsheet per site, row per month output

        df_export=df_FYtotal[['dd',
                            'sq_ft',
                            'electricity_energy_cost',
                            'electricity_demand_cost',
                            'electricity_cost', 
                            'fuel_oil_cost',
                            'natural_gas_cost',
                            'district_heat_cost',
                            'total_energy_cost',
                            'water_cost',
                            'sewer_cost',
                            'total_water_cost',
                            'total_utility_cost',
                            'eci',
                            'uci',
                            'electricity_energy_usage',
                            'electricity_avg_demand_usage',
                            'electricity_demand_usage',
                            'electricity_peak2avg_ratio',
                            'electricity_mmbtu',
                            'fuel_oil_usage',
                            'fuel_oil_mmbtu',
                            'natural_gas_usage',
                            'natural_gas_mmbtu',
                            'district_heat_usage',
                            'total_heat_mmbtu',
                            'eui',
                            'specific_eui',
                            'heat_mmbtu_per_hdd',
                            'total_energy_mmbtu',
                            'water_usage',
                            'sewer_usage']]

        df_export.to_excel(f"output/extra_data/FY{year}_Site_Summary_Data.xlsx")


 
# ---------------------- Site Analysis Table ---------------------------

def Site_spreadsheets(site, df, ut):
    """ Uses pre-processed billing dataframe and creates spreadsheet for each site. Saves .xlsx 
        spreadsheet for given site with a row of data for each month.  Returns nothing.
        """

    df1 = df.query('site_id==@site') 
    
    # Test for valid data
    if len(df1) == 0:
        return
    
    # Add in degree days to DataFrame
    months_present = bu.months_present(df1)
    deg_days = ut.degree_days_monthly(months_present, site)
    deg_days.set_index(['fiscal_year', 'fiscal_mo'], inplace=True)


    # Get building square footage and calculate EUIs and ECI.
    sq_ft = ut.building_info(site)['sq_ft']


    # Summarize Monthly Cost and usage by Service Type
    df_monthlycost = pd.pivot_table(df1, index=['fiscal_year', 'fiscal_mo'], columns='service_type', values='cost', aggfunc=np.sum)
    df_monthlycost = bu.add_missing_columns(df_monthlycost, bu.missing_services([]))

    # Seperate kWh and kW electricity costs
    df_units = pd.pivot_table(df1, index=['fiscal_year', 'fiscal_mo'], columns='units', values='cost', aggfunc=np.sum)
    bu.add_missing_columns(df_units, ['kWh', 'kW'])
    df_monthlycost['electricity_energy'] = df_units['kWh']
    df_monthlycost['electricity_demand'] = df_units['kW']

    # Add cost suffix
    df_monthlycost = df_monthlycost.add_suffix('_cost')

    df_monthlycost['total_utility_cost'] = df_monthlycost.sum(axis=1)
    df_monthlycost['total_water_cost'] = df_monthlycost[['water_cost', 'sewer_cost']].sum(axis=1)
    df_monthlycost['total_energy_cost'] = df_monthlycost.total_utility_cost - df_monthlycost.total_water_cost
    df_monthlycost['total_heat_cost'] = df_monthlycost.total_energy_cost - df_monthlycost.electricity_cost
    df_monthlycost['eci'] = df_monthlycost.total_energy_cost / sq_ft
    df_monthlycost['uci'] = df_monthlycost.total_utility_cost / sq_ft

    df_monthlycost_rolling = df_monthlycost.rolling(12, min_periods=None, center=False, win_type=None, on=None, axis=0, closed=None).sum().add_suffix('_12mo')


    df_monthlyusage = pd.pivot_table(df1, index=['fiscal_year', 'fiscal_mo'], columns='service_type', values='usage', aggfunc=np.sum)

    # Seperate kWh and kW electricity costs
    df_units = pd.pivot_table(df1, index=['fiscal_year', 'fiscal_mo'], columns='units', values='usage', aggfunc=np.sum)
    bu.add_missing_columns(df_units, ['kWh', 'kW'])
    df_monthlyusage['electricity_energy'] = df_units['kWh']
    df_monthlyusage['electricity_demand'] = df_units['kW']

    df_monthlyusage = bu.add_missing_columns(df_monthlyusage, bu.missing_services([]))

    # Add usage suffix
    df_monthlyusage = df_monthlyusage.add_suffix('_usage')

    df_monthlyusage_rolling = df_monthlyusage.rolling(12, min_periods=None, center=False, win_type=None, on=None, axis=0, closed=None).sum().add_suffix('_12mo')
    df_monthlyusage_rolling['electricity_demand_usage_12mo'] = df_monthlyusage_rolling['electricity_demand_usage_12mo'] / 12


    df_monthlyBTU = pd.pivot_table(df1, index=['fiscal_year', 'fiscal_mo'], columns='service_type', values='mmbtu', aggfunc=np.sum)
    df_monthlyBTU = bu.add_missing_columns(df_monthlyBTU, bu.missing_services([]))
    df_monthlyBTU = df_monthlyBTU.add_suffix('_mmbtu')
    df_monthlyBTU['total_energy_mmbtu'] = df_monthlyBTU.sum(axis=1)
    df_monthlyBTU['total_heat_mmbtu'] = df_monthlyBTU.total_energy_mmbtu - df_monthlyBTU.electricity_mmbtu
    df_monthlyBTU['eui'] = df_monthlyBTU.total_energy_mmbtu * 1e3 / sq_ft
    
    df_monthlyBTU = pd.merge(df_monthlyBTU, deg_days, how='left', left_index=True, right_index=True)  #right_on=['fiscal_year', 'fiscal_mo'])
    df_monthlyBTU['heat_mmbtu_per_hdd'] = df_monthlyBTU['total_heat_mmbtu'] / df_monthlyBTU['dd']
    df_monthlyBTU['specific eui'] = df_monthlyBTU.total_heat_mmbtu * 1e6 / df_monthlyBTU.dd / sq_ft

    df_monthlyBTU_rolling = df_monthlyBTU.rolling(12, min_periods=None, center=False, win_type=None, on=None, axis=0, closed=None).sum().add_suffix('_12mo')

    #Merge Dataframes

    df_total = pd.concat([df_monthlycost, df_monthlyusage, df_monthlyBTU, df_monthlycost_rolling, df_monthlyusage_rolling, df_monthlyBTU_rolling], axis=1)
    
        
    #Select Desired Columns and export to excel  - This is the spreadsheet per site, row per month output

    df_export=df_total[['dd', 
                        'electricity_energy_cost',
                        'electricity_demand_cost',
                        'electricity_cost', 
                        'fuel_oil_cost',
                        'natural_gas_cost',
                        'district_heat_cost',
                        'total_energy_cost',
                        'water_cost',
                        'sewer_cost',
                        'total_water_cost',
                        'total_utility_cost',
                        'eci',
                        'uci',
                        'electricity_energy_usage',
                        'electricity_demand_usage',
                        'electricity_mmbtu',
                        'fuel_oil_usage',
                        'fuel_oil_mmbtu',
                        'natural_gas_usage',
                        'natural_gas_mmbtu',
                        'district_heat_usage',
                        'total_heat_mmbtu',
                        'eui',
                        'specific eui',
                        'heat_mmbtu_per_hdd',
                        'total_energy_mmbtu',
                        'water_usage',
                        'sewer_usage',
                        'dd_12mo',
                        'electricity_energy_cost_12mo',
                        'electricity_demand_cost_12mo',
                        'electricity_cost_12mo',
                        'fuel_oil_cost_12mo',
                        'natural_gas_cost_12mo',
                        'district_heat_cost_12mo',
                        'total_heat_cost_12mo',
                        'total_energy_cost_12mo',
                        'water_cost_12mo',
                        'sewer_cost_12mo',
                        'total_water_cost_12mo',
                        'total_utility_cost_12mo',
                        'eci_12mo',
                        'uci_12mo',
                        'electricity_energy_usage_12mo',
                        'electricity_demand_usage_12mo',
                        'electricity_mmbtu_12mo',
                        'fuel_oil_usage_12mo',
                        'fuel_oil_mmbtu_12mo',
                        'natural_gas_usage_12mo',
                        'natural_gas_mmbtu_12mo',
                        'district_heat_usage_12mo',
                        'total_heat_mmbtu_12mo',
                        'eui_12mo',
                        'specific eui_12mo',
                        'heat_mmbtu_per_hdd_12mo',
                        'total_energy_mmbtu_12mo',
                        'water_usage_12mo',
                        'sewer_usage_12mo']]

    df_export.to_excel(f"output/extra_data/Site_{site}_Monthly_Summary_Data.xlsx")

def scorecard(site, df_site, df_fy, ut):
    # Make graphs and save into images directory; use graph_util to get
    # graph file name and graph URL.
    # Return a dictionary 'template_data' that will feed your template.
    # Make a scorecard.html template in the templates/sites directory; 
    # pattern after the index.html file there.
    template_data = {}
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
    report_date_time = datetime.datetime.now().strftime('%B %d, %Y %I:%M %p')
    
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
        df_raw, df, util_obj = preprocess_data()

        # Pickle the DataFrames and utility object for fast
        # loading later, if needed
        df_raw.to_pickle('df_raw.pkl')
        df.to_pickle('df_processed.pkl')
        pickle.dump(util_obj, open('util_obj.pkl', 'wb'))

        # We no longer need the raw DataFrame, so delete it to
        # save memory
        del df_raw

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

    # Run FY_spreadsheets to create FY summary excel files
    print('Starting FY spreadsheet creation...')
    FY_spreadsheets(df, util_obj)

    # ------ Loop through the sites, creating a report for each
    
    # Get the template used to create the site benchmarking report.
    site_template = template_util.get_template('sites/index.html')

    # Get the template used to create the scorecard.
    # score_template = template_util.get_template('sites/scorecard.html')
    


    site_count = 0    # tracks number of site processed
    for site_id in util_obj.all_sites():
        # This line shortens the calculation process to start with whatever
        # Site ID you want to start with
        # if site_id < '15711': continue

        msg("Site '{}' is being processed...".format(site_id))
        
        # Generate site specific spreadsheet
        Site_spreadsheets(site_id, df, util_obj)


        # Gather template data from each of the report sections.  The functions
        # return a dictionary with variables needed by the template.  Sometimes other
        # values are returned from the function, often for use in later reports.

        template_data = building_info_report(site_id, util_obj, report_date_time)

        report_data = energy_index_report(site_id, df, util_obj)
        template_data.update(report_data)

        report_data, df_utility_cost = utility_cost_report(site_id, df, util_obj)
        template_data.update(report_data)

        # Filter down to just this site's bills and only services that
        # are energy services in order to determine whether there are any
        # energy services. Only do energy reports if there are some energy
        # services
        energy_services = bu.missing_energy_services([])
        df1 = df.query('site_id==@site_id and service_type==@energy_services')
        if not df1.empty:

            report_data, df_usage = energy_use_cost_reports(site_id, df, util_obj, df_utility_cost)
            template_data.update(report_data)

            report_data = electrical_usage_and_cost_reports(site_id, df)
            template_data.update(report_data)

            #df_utility_cost.to_pickle('df_utility_cost.pkl')
            #df_usage.to_pickle('df_usage.pkl')
            #import sys; sys.exit()

            report_data = heating_usage_cost_reports(site_id, df, util_obj, df_utility_cost, df_usage)
            template_data.update(report_data)

        report_data = water_report(site_id, df)
        template_data.update(report_data)

        # save template data variables to debug file if requested
        if settings.WRITE_DEBUG_DATA:
            with open('output/debug/{}.vars'.format(site_id), 'w') as fout:
                pprint.pprint(template_data, fout)

        # create report file
        result = site_template.render(template_data)
        with open('output/sites/{}.html'.format(site_id), 'w') as fout:
            fout.write(result)

        # Make Scorecard and write out scorecard HTML file.
        # score_data = scorecard(site, df_xyz, df_abc, ut)
        # result = score_template.render(score_data)
        # with open(f'output/sites/{site_id}_score.html', 'w') as fout:
        #     fout.write(result)

        site_count += 1
        if site_count == settings.MAX_NUMBER_SITES_TO_RUN:
            break
    
    print()
    msg('Benchmarking Script Complete!')
