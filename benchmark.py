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
import datetime
import pandas as pd
import numpy as np
import bench_util as bu
import graph_util as gu
import template_util
import shutil
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
    
    if df1.empty:
        return None
    
    else:
    
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

        # Save this DataFrame for use in the Heating Cost Analysis Report
        df_utility_cost = reset_df2.copy()

        # Get appropriate file names and URLs for the graph
        g1_fn, g1_url = gu.graph_filename_url(site, 'util_cost_ovw_g1')

        # make the area cost distribution graph
        utility_list = ['electricity', 'natural_gas', 'fuel_oil', 'sewer', 'water', 'refuse', 'district_heat']
        gu.area_cost_distribution(reset_df2, 'fiscal_year', utility_list, g1_fn);

        # make the stacked bar graph
        g2_fn, g2_url = gu.graph_filename_url(site, 'util_cost_ovw_g2')
        gu.create_stacked_bar(reset_df2, 'fiscal_year', utility_list, 'Utility Cost ($)', "Annual Cost by Utility Type",g2_fn)

        # Put results into the final dictionary that will be passed to the Template.
        # A function is used to convert the DataFrame into a list of dictionaries.
        template_data['utility_cost_overview'] = dict(
            graphs=[g1_url, g2_url],
            table={'rows': bu.df_to_dictionaries(df2)},
        )

        # -------------------- Energy Use Overview Report -----------------------

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
        usage_df2 = usage_df2[usage_df2.columns.difference(['Sewer', 'Water', 'Refuse'])]

        # Add in columns for the missing services
        missing_services = bu.missing_energy_services(usage_df2.columns)
        bu.add_columns(usage_df2, missing_services)

        # Add a Total column that sums the other columns
        usage_df2['total_energy'] = usage_df2.sum(axis=1)
        cols = ['{}_mmbtu'.format(bu.change_name(col)) for col in usage_df2.columns]
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

        # Add data and graphs to main dictionary
        template_data['energy_usage_overview'] = dict(
            graphs=[p4g1_url, p4g2_url],
            table={'rows': energy_use_overview_rows},
        )

        # ---------------- Energy Usage and Cost Pie Charts -----------------------

        # Shorten the utility list to include only energy-related columns
        utility_list = list(set(utility_list) - set(['sewer', 'water', 'refuse']))

        pie_urls = gu.usage_pie_charts(usage_df2.fillna(0.0), usage_cols, 1, 'energy_usage_pie', site)

        # Make the other graphs and append the URLs
        pie_urls += gu.usage_pie_charts(df2.fillna(0.0), utility_list, 2, 'energy_cost_pie', site)

        # Add pie charts to template dictionary
        template_data['energy_cost_usage'] = dict(graphs=pie_urls)

        # -------------------- Electrical Usage Analysis -------------------------

        site_df = df.query("site_id == @site")

        if 'Electricity' in site_df.service_type.unique() and site_df.query("service_type == 'Electricity'")['usage'].sum(axis=0) > 0:
            # only look at elecricity records
            electric_df = site_df.query("service_type == 'Electricity'")
            electric_df = electric_df.query("units == 'kWh' or units == 'kW'")
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

        # Add data and graphs to main dictionary
        template_data['electrical_usage_analysis'] = dict(
            graphs=[p6g1_url, p6g2_url],
            table={'rows': electric_use_rows},
        )


        # -------------------- Electrical Cost Analysis Table ---------------------

        # only look at elecricity records
        electric_cost_df = site_df.query("service_type == 'Electricity'").copy()

        # Costs don't always have units, so split the data into demand charges and usage charges (which includes other charges)
        electric_cost_df['cost_categories'] = np.where(electric_cost_df.item_desc.isin(['KW Charge', 'On peak demand', 'Demand Charge']),
                                                       'demand_cost', 'usage_cost')

        if 'Electricity' in site_df.service_type.unique():
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

        # --------------------Heating Usage Analysis Table ------------------------

        # Take only needed columns from earlier usage df
        heating_usage = usage_df2[['natural_gas_mmbtu', 'fuel_oil_mmbtu', 'district_heat_mmbtu', 'hdd', 'total_heat_mmbtu']].copy()

        # Add in percent change columns
        # First sort so the percent change column is correct and then re-sort the other direction
        heating_usage.sort_index(ascending=True, inplace=True)
        heating_usage['fuel_oil_pct_change'] = heating_usage.fuel_oil_mmbtu.pct_change()
        heating_usage['natural_gas_pct_change'] = heating_usage.natural_gas_mmbtu.pct_change()
        heating_usage['district_heat_pct_change'] = heating_usage.district_heat_mmbtu.pct_change()
        heating_usage['total_heat_pct_change'] = heating_usage.total_heat_mmbtu.pct_change()
        
        # Now reset the sorting
        heating_usage.sort_index(ascending=False, inplace=True)

        # Get the number of gallons, ccf, and 1,000 pounds of district heat by converting MMBTUs using the supplied conversions
        heating_usage['fuel_oil_usage'] = heating_usage.fuel_oil_mmbtu * 1000000 / ut.fuel_btus_per_unit('Oil #1', 'gallons')
        heating_usage['natural_gas_usage'] = heating_usage.natural_gas_mmbtu * 1000000 / ut.fuel_btus_per_unit('Natural Gas', 'ccf')

        # ----- Create Heating Usage Analysis Graphs

        p8g1_filename, p8g1_url = gu.graph_filename_url(site, "heating_usage_g1")
        gu.stacked_bar_with_line(heating_usage.reset_index(), 'fiscal_year', ['natural_gas_mmbtu', 'fuel_oil_mmbtu',
                                                                                        'district_heat_mmbtu'], 'hdd',
                                'Heating Fuel Usage [MMBTU/yr]', 'Heating Degree Days [Base 65F]', 
                                 "Annual Heating Energy Use and Degree Day Comparison", p8g1_filename)


        # --- Create Monthly Heating Usage dataframe for graph

        monthly_heating = pd.pivot_table(usage_df1,
                                        values='mmbtu',
                                        index=['fiscal_year', 'fiscal_mo'],
                                        columns=['service_type'],
                                        aggfunc=np.sum
                                        )

        # Add in columns for the missing energy services
        missing_services = bu.missing_energy_services(monthly_heating.columns)
        bu.add_columns(monthly_heating, missing_services)

        # Drop the non-heating services
        monthly_heating = monthly_heating[monthly_heating.columns.difference(['Sewer', 'Water', 'Refuse', 'Electricity'])]

        # Create a total heating column
        monthly_heating['total_heating_energy'] = monthly_heating.sum(axis=1)

        p8g2_filename, p8g2_url = gu.graph_filename_url(site, "heating_usage_g2")
        gu.create_monthly_profile(monthly_heating, 'total_heating_energy', "Monthly Heating Energy Profile [MMBTU]", 'red',
                                  "Monthly Heating Energy Usage Profile by Fiscal Year", p8g2_filename)

        # Convert df to dictionary
        heating_use_rows = bu.df_to_dictionaries(heating_usage)

        # Add data and graphs to main dictionary
        template_data['heating_usage_analysis'] = dict(
            graphs=[p8g1_url, p8g2_url],
            table={'rows': heating_use_rows},
        )

        # ------------------- Heating Cost Analysis Table -----------------------

        # Use the df_utility_cost DataFrame from the Energy Cost Analysis report,
        # 3rd report created above.

        # Put DataFrame back into ascending order, as we need to calculate a percent
        # change column.
        # Index is NOT Years
        df_utility_cost.sort_values('fiscal_year', ascending=True, inplace=True)

        # Make a total heat cost column and it's percent change
        df_utility_cost['total_heat_cost'] = df_utility_cost[['natural_gas', 'fuel_oil', 'district_heat']].sum(axis=1)
        df_utility_cost['total_heat_cost_pct_change'] = df_utility_cost.total_heat_cost.pct_change()

        # Now back in descending order
        df_utility_cost.sort_values('fiscal_year', ascending=False, inplace=True)

        # Use only necessary columns
        heating_cost = df_utility_cost[['fiscal_year', 'natural_gas',
                                        'fuel_oil', 'district_heat', 'total_heat_cost',
                                        'total_heat_cost_pct_change']]

        # Change column names so they aren't the same as the heating usage dataframe
        heating_cost = heating_cost.rename(columns={'natural_gas':'natural_gas_cost',
                                                   'fuel_oil': 'fuel_oil_cost',
                                                   'district_heat': 'district_heat_cost'})

        # Combine the heating cost and heating use dataframes
        heating_cost_and_use = pd.merge(heating_cost, heating_usage, left_on='fiscal_year', right_index=True, how='right')

        # Put DataFrame in ascending order to calculate percent change
        heating_cost_and_use.sort_values('fiscal_year', ascending=True, inplace=True)
        
        # Create percent change columns
        heating_cost_and_use['fuel_oil_pct_change'] = heating_cost_and_use.fuel_oil_cost.pct_change()
        heating_cost_and_use['natural_gas_pct_change'] = heating_cost_and_use.natural_gas_cost.pct_change()
        heating_cost_and_use['district_heat_pct_change'] = heating_cost_and_use.district_heat_cost.pct_change()

        # Back to descending order
        heating_cost_and_use.sort_values('fiscal_year', ascending=False, inplace=True)
        
        # Create unit cost columns
        heating_cost_and_use['fuel_oil_unit_cost'] = heating_cost_and_use.fuel_oil_cost / heating_cost_and_use.fuel_oil_mmbtu
        heating_cost_and_use['natural_gas_unit_cost'] = heating_cost_and_use.natural_gas_cost / heating_cost_and_use.natural_gas_mmbtu
        heating_cost_and_use['district_heat_unit_cost'] = heating_cost_and_use.district_heat_cost / heating_cost_and_use.district_heat_mmbtu
        heating_cost_and_use['building_heat_unit_cost'] = heating_cost_and_use.total_heat_cost / heating_cost_and_use.total_heat_mmbtu

        # Remove all columns not needed for the Heating Cost Analysis Table
        heating_cost_and_use = heating_cost_and_use[['fiscal_year',
                                                      'fuel_oil_cost',
                                                      'fuel_oil_pct_change',
                                                      'natural_gas_cost',
                                                      'natural_gas_pct_change',
                                                      'district_heat_cost',
                                                      'district_heat_pct_change',
                                                      'fuel_oil_unit_cost',
                                                      'natural_gas_unit_cost',
                                                      'district_heat_unit_cost',
                                                      'building_heat_unit_cost',
                                                      'total_heat_cost',
                                                      'total_heat_cost_pct_change']]

        # ---- Create DataFrame with the Monthly Average Price Per MMBTU for All Sites

        # Filter out natural gas customer charges as the unit cost goes to infinity if there is a charge but no use
        df_no_gas_cust_charges = df.drop(df[(df['service_type'] == 'Natural Gas') & (df['units'] != 'CCF')].index)

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
        cost_df1 = df.drop(df[(df['service_type'] == 'Natural Gas') & (df['units'] != 'CCF')].index)

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

        # Drop the non-heating services
        monthly_heating_cost = monthly_heating_cost[monthly_heating_cost.columns.difference(['Electricity', 'Sewer', 'Water', 'Refuse'])]

        # Create a total heating column
        monthly_heating_cost['total_heating_cost'] = monthly_heating_cost.sum(axis=1)

        monthly_heating_cost = monthly_heating_cost.rename(columns={'Natural Gas':'Natural Gas Cost',
                                                                   'Oil #1':'Oil #1 Cost',
                                                                   'Steam': 'Steam Cost'})

        monthly_heat_energy_and_use = pd.merge(monthly_heating_cost, monthly_heating, left_index=True, right_index=True, how='outer')

        # Create unit cost columns in $ / MMBTU for each fuel type
        monthly_heat_energy_and_use['fuel_oil_unit_cost'] = monthly_heat_energy_and_use['Oil #1 Cost'] / monthly_heat_energy_and_use['Oil #1']
        monthly_heat_energy_and_use['natural_gas_unit_cost'] = monthly_heat_energy_and_use['Natural Gas Cost'] / monthly_heat_energy_and_use['Natural Gas']
        monthly_heat_energy_and_use['district_heat_unit_cost'] = monthly_heat_energy_and_use['Steam Cost'] / monthly_heat_energy_and_use['Steam']
        monthly_heat_energy_and_use['building_unit_cost'] = monthly_heat_energy_and_use.total_heating_cost / monthly_heat_energy_and_use.total_heating_energy

        # Reset the index for easier processing
        monthly_heat_energy_and_use = monthly_heat_energy_and_use.reset_index()

        # Add in unit costs for fuels that are currently blank

        unit_cost_cols = ['fuel_oil_unit_cost', 'natural_gas_unit_cost', 'district_heat_unit_cost']
        service_types = ['Oil #1_avg_unit_cost', 'Natural Gas_avg_unit_cost', 'Steam_avg_unit_cost']

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

        old_usage_cols = ['Natural Gas', 'Oil #1', 'Steam']


        # Create an indicator for whether a given heating fuel is available for the facility.  This is done by checking the use for all
        # months- if it is zero, then that building doesn't have the option to use that type of fuel.
        for col in old_usage_cols:
            new_col_name = col + "_available"
            monthly_heat_energy_and_use[new_col_name] = np.where(monthly_heat_energy_and_use[col].sum() == 0, 0, 1)

        # Calculate what it would have cost if the building used only one fuel type
        available_cols = ['Oil #1_available','Natural Gas_available','Steam_available']
        available_dict = dict(zip(unit_cost_cols, available_cols))
        hypothetical_cost_cols = []

        for unit_cost, avail_col in available_dict.items():
            new_col_name = unit_cost + "_hypothetical"
            hypothetical_cost_cols.append(new_col_name)
            monthly_heat_energy_and_use[new_col_name] = monthly_heat_energy_and_use[unit_cost] *     monthly_heat_energy_and_use.total_heating_energy * monthly_heat_energy_and_use[avail_col]

        # Calculate the monthly savings to the building by not using the most expensive available fuel entirely
        monthly_heat_energy_and_use['fuel_switching_savings'] = monthly_heat_energy_and_use[hypothetical_cost_cols].max(axis=1)                                                         - monthly_heat_energy_and_use.total_heating_cost

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

        # ---------------------- Water Analysis Table ---------------------------

        water_use = df.query('site_id == @site')[['service_type', 'fiscal_year', 'fiscal_mo','cost', 'usage', 'units']]

        # Create month count field for all months that have water and sewer bills
        water_use_only = water_use.query("service_type == 'Water'")
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
        water_gal_df = water_gal_df[['Water']]

        # Calculate percent change column
        water_gal_df['water_use_pct_change'] = water_gal_df.Water.pct_change()

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
        water_cost_df = water_cost_df[water_cost_df.columns.difference(['Electricity', 'Natural Gas', 'Oil #1', 'Steam', 'Refuse'])]

        rename_dict = {'Sewer': 'Sewer Cost',
                       'Water': 'Water Cost'}

        water_cost_df = water_cost_df.rename(columns=rename_dict)

        # First check to make sure sewer data is included; if so, calculate total cost
        water_cost_df['total_water_sewer_cost'] = water_cost_df.sum(axis=1)

        water_cost_df['water_cost_pct_change'] = water_cost_df['Water Cost'].pct_change()
        water_cost_df['sewer_cost_pct_change'] = water_cost_df['Sewer Cost'].pct_change()

        water_cost_df['total_water_sewer_cost_pct_change'] = water_cost_df.total_water_sewer_cost.pct_change()

        # Merge use and cost dataframes
        water_use_and_cost = pd.merge(water_cost_df, water_gal_df, left_index=True, right_index=True, how='left')

        water_use_and_cost['water_unit_cost'] = water_use_and_cost.total_water_sewer_cost / water_use_and_cost.Water
        water_use_and_cost['water_unit_cost_pct_change'] = water_use_and_cost.water_unit_cost.pct_change()

        # Use only complete years 
        water_use_and_cost['month_count'] = water_mo_count
        water_use_and_cost = water_use_and_cost.query("month_count == 12")
        water_use_and_cost = water_use_and_cost.drop('month_count', axis=1)
        water_use_and_cost = water_use_and_cost.sort_index(ascending=False)
        water_use_and_cost = water_use_and_cost.rename(columns={'Sewer Cost':'sewer_cost',
                                                               'Water Cost':'water_cost',
                                                               'total_water_sewer_cost':'total_cost',
                                                               'total_water_sewer_cost_pct_change':'total_cost_pct_change',
                                                               'Water':'total_usage',
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

        if 'Water' in list(water_gal_df_monthly.columns.values):
            gu.create_monthly_profile(water_gal_df_monthly, 'Water', 'Monthly Water Usage Profile [gallons]', 'green', 
                                      "Monthly Water Usage Profile by Fiscal Year", p10g2_filename)
        else:
            shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(p10g2_filename))

        # Convert df to dictionary
        water_rows = bu.df_to_dictionaries(water_use_and_cost)

        # Add data and graphs to main dictionary
        template_data['water_analysis'] = dict(
            graphs=[p10g1_url, p10g2_url],
            table={'rows': water_rows},
        )

        # ------------------ Return the final Data Dictionary ---------------------

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
        #if site_id < 'MSP001': continue        # new line of code, pick whatever Site ID you want to start with

        msg("Site '{}' is being processed...".format(site_id))
        
        # Run the benchmark analysis for this site, returning the template
        # data.
        template_data = analyze_site(site_id, df, util_obj, report_date_time)

        # save template data variables to debug file if requested
        if settings.WRITE_DEBUG_DATA:
            with open('output/debug/{}.vars'.format(site_id), 'w') as fout:
                pprint.pprint(template_data, fout)

        # create report file if there is template_data
        if template_data is None:
            continue
        else:
            result = site_template.render(template_data)
            with open('output/sites/{}.html'.format(site_id), 'w') as fout:
                fout.write(result)
        
        site_count += 1
        if site_count == settings.MAX_NUMBER_SITES_TO_RUN:
            break
    
    print()
    msg('Benchmarking Script Complete!')
