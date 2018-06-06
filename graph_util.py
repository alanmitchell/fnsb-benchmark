import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib as mpl
import matplotlib.dates as mdates
import bench_util as bu
import shutil
import os
from matplotlib import font_manager as fm

# Set the matplotlib settings (eventually this will go at the top of the graph_util)
mpl.rcParams['axes.labelsize'] = 20
mpl.rcParams['axes.titlesize'] = 24
mpl.rcParams['legend.fontsize'] = 20
mpl.rcParams['font.size'] = 20.0
mpl.rcParams['figure.figsize'] = [15,10]
mpl.rcParams['xtick.labelsize'] = 20
mpl.rcParams['ytick.labelsize'] = 20

# Set the style for the graphs
plt.style.use('bmh')

# Additional matplotlib formatting settings
months = mdates.MonthLocator()

# This formats the months as three-letter abbreviations
months_format = mdates.DateFormatter('%b')

def beautify_legend(df, col_list):
    """ This function takes a dataframe and the list of columns that 
    will ultimately be displayed and re-formats the names so that they 
    are prettier when displayed in the legend. Returns a list of column
    names"""
    
    pretty_cols = []
    
    for col in col_list:
        new_col = col.replace("_mmbtu", "")
        new_col = new_col.replace("_unit_cost", " unit cost")
        new_col = new_col.replace("_cost", "")
        new_col = new_col.replace("kwh", "electricity usage")
        new_col = new_col.replace("kw_avg", "electricity demand")
        new_col = new_col.replace("hdd", "heating degree days")
        new_col = new_col.replace("_", " ")
        new_col = new_col.title()
        df = df.rename(columns={col:new_col})
        
        pretty_cols.append(new_col)
    
    return df, pretty_cols
    
        

def color_formatter(col_name_list):
    """This function takes in a list of dataframe column names and then
    converts them to standardized colors so that the final graphs show 
    each fuel type using the same color.
    """
    color_dict = {}
    
    for col_name in col_name_list:
        if 'natural' in col_name.lower():
            color_dict[col_name] = '#1f78b4'
        elif 'fuel' in col_name.lower():
            color_dict[col_name] = '#e31a1c'
        elif 'water' in col_name.lower():
            color_dict[col_name] = '#b3df8a'
        elif 'sewer' in col_name.lower():
            color_dict[col_name] = '#fdbf6f'
        elif 'district' in col_name.lower():
            color_dict[col_name] = '#fb9a99'
        elif 'kw_' in col_name.lower() or 'demand' in col_name.lower():
            color_dict[col_name] = '#33a02c'
        elif 'electricity' in col_name.lower() or 'kwh' in col_name.lower() or 'Electricity' in col_name:
            color_dict[col_name] = '#a6cee3'
        elif 'refuse' in col_name.lower():
            color_dict[col_name] = '#ff7f00'
        elif 'propane' in col_name.lower():
            color_dict[col_name] = '#cab2d6'
        elif 'wood' in col_name.lower():
            color_dict[col_name] = '#6a3d9a'
        else:
            color_dict[col_name] = '#000000'
            
    return color_dict


def area_cost_distribution(df, fiscal_year_col, utility_col_list, filename):
    # Inputs include the dataframe, the column name for the fiscal year column, and the list of column names for the 
    # different utility bills.  The dataframe should already include the summed bills for each fiscal year.
    
    if not df.empty and np.any(df.fillna(0) > 0):
        fig, ax = plt.subplots()

        # Makes the legend prettier.
        df, utility_col_list = beautify_legend(df, utility_col_list)
        
        # Take costs for each utility type and convert to percent of total cost by fiscal year
        df['total_costs'] = df[utility_col_list].sum(axis=1)

       
        # Standardize colors using color_formatter utility
        color_dict = color_formatter(utility_col_list)
        
        
        percent_columns = []

        # Create dictionary for differently named keys
        percent_col_colors = {}
        
        for col in utility_col_list:
            percent_col = "Percent " + col
            percent_columns.append(percent_col)
            df[percent_col] = df[col] / df.total_costs
            percent_col_colors[percent_col] = color_dict[col]
            
        df = df.fillna(0)

        # Create stacked area plot
        ax.stackplot(df[fiscal_year_col], df[percent_columns].T, labels=percent_columns,
                    colors=[ percent_col_colors[i] for i in percent_columns])

        # Format the y axis to be in percent
        ax.yaxis.set_major_formatter(FuncFormatter('{0:.0%}'.format))
        
        # Format the x-axis to include all fiscal years
        plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0))

        # Add title and axis labels
        plt.title('Annual Utility Cost Distribution')
        plt.ylabel('Utility Cost Distribution')
        plt.xlabel('Fiscal Year')
        
        # Add legend
        plt.legend(loc='lower right', ncol=2, fancybox=True, shadow=True)
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))
        
        
def area_use_distribution(df, fiscal_year_col, utility_col_list, filename):
    # Inputs include the dataframe, the column name for the fiscal year column, and the list of column names for the 
    # different utility bills.  The dataframe should already include the summed bills for each fiscal year.
    
    # Test to see if the dataframe is empty or if all values equal zero
    if not df.empty and np.any(df.fillna(0) > 0):
        # Makes the legend prettier.
        df, utility_col_list = beautify_legend(df, utility_col_list)
        
        fig, ax = plt.subplots()

        # Take usage for each utility type and convert to percent of total cost by fiscal year
        df['total_use'] = df[utility_col_list].sum(axis=1)
        
        # Standardize colors using color_formatter utility
        color_dict = color_formatter(utility_col_list)
        
        percent_columns = []
        
        # Create dictionary for differently named keys
        percent_col_colors = {}

        for col in utility_col_list:
            percent_col = "Percent " + col
            percent_columns.append(percent_col)
            df[percent_col] = df[col] / df.total_use
            percent_col_colors[percent_col] = color_dict[col]
     
        # Fill the NaNs
        df = df.fillna(0)
        
        # Create stacked area plot
        ax.stackplot(df[fiscal_year_col], df[percent_columns].T, labels=percent_columns, 
                     colors=[ percent_col_colors[i] for i in percent_columns])


        # Format the y axis to be in percent
        ax.yaxis.set_major_formatter(FuncFormatter('{0:.0%}'.format))
        
        # Format the x-axis to include all fiscal years
        plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0))

        # Add title and axis labels
        plt.title('Annual Energy Usage Distribution')
        plt.ylabel('Annual Energy Usage Distribution')
        plt.xlabel('Fiscal Year')
        
        # Add legend 
        plt.legend(loc='lower right', ncol=2, fancybox=True, shadow=True)
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))
        
        
def create_stacked_bar(df, fiscal_year_col, column_name_list, ylabel, title, filename):
    
    # Parameters include the dataframe, the name of the column where the fiscal year is listed, a list of the column names
    # with the correct data for the chart, and the filename where the output should be saved.
    
    # Test to see if the dataframe is empty or if all values equal zero
    if not df.empty and np.any(df[column_name_list].fillna(0) > 0):
        # Makes the legend prettier.
        df, column_name_list = beautify_legend(df, column_name_list)

        # Create the figure
        fig, ax = plt.subplots()

        # Set the bar width
        width = 0.50

        # Standardize colors using color_formatter utility
        color_dict = color_formatter(column_name_list)

        # Create the stacked bars.  The "bottom" is the sum of all previous bars to set the starting point for the next bar.
        previous_col_name = 0

        # Fill the NaNs
        df = df.fillna(0)

        for col in column_name_list:
            col_name = plt.bar(df[fiscal_year_col], df[col], width, label=col, bottom=previous_col_name, color=color_dict[col])
            previous_col_name = previous_col_name + df[col]

        # label axes
        plt.ylabel(ylabel)
        plt.xlabel('Fiscal Year')

        # Make one bar for each fiscal year
        plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0), 
                   np.sort(list(df[fiscal_year_col].unique())))

        df['total_cost'] = df[column_name_list].sum(axis=1)
        ax.set_ylim(bottom=0, top=df.total_cost.max() + df.total_cost.max()*0.10)

        # Format the y-axis so a comma is displayed for thousands
        ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))

        plt.title(title)
        plt.legend(loc='lower right', ncol=2, fancybox=True, shadow=True)

        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))

        
def energy_use_stacked_bar(df, fiscal_year_col, column_name_list, filename):
    
    # Parameters include the dataframe, the name of the column where the fiscal year is listed, a list of the column names
    # with the correct data for the chart, and the filename where the output should be saved.
    
    # Test to see if the dataframe is empty or if all values equal zero
    if not df.empty and np.any(df[column_name_list].fillna(0) > 0):
        # Makes the legend prettier.
        df, column_name_list = beautify_legend(df, column_name_list)
        
        # Create the figure
        fig, ax = plt.subplots()
        
        # Set the bar width
        width = 0.50
        
        # Standardize colors using color_formatter utility
        color_dict = color_formatter(column_name_list)
        
        # Fill the NaNs
        df = df.fillna(0)
        
        # Create the stacked bars.  The "bottom" is the sum of all previous bars to set the starting point for the next bar.
        previous_col_name = 0
        
        for col in column_name_list:
          
            col_name = ax.bar(df[fiscal_year_col].values, df[col].values, width, label=col, bottom=previous_col_name, 
                              color=color_dict[col])
            previous_col_name = previous_col_name + df[col]
          
        # label axes
        plt.ylabel('Annual Energy Usage [MMBTU]')
        plt.xlabel('Fiscal Year')
        plt.title('Total Annual Energy Usage')
        
        
        # Make one bar for each fiscal year
        plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0), 
                   np.sort(list(df[fiscal_year_col].unique())))
        
        # Set the yticks to go up to the total usage in increments of 1,000
        df['total_use'] = df[column_name_list].sum(axis=1)
        plt.yticks(np.arange(0, df.total_use.max()+df.total_use.max()*0.10, 1000))
        
        # Format the y-axis so a comma is displayed for thousands
        ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
        
        plt.legend(loc='lower right', ncol=2, fancybox=True, shadow=True)
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))

        
def usage_pie_charts(df, use_or_cost_cols, chart_type, base_filename, site_id):
    
    # df: A dataframe with the fiscal_year as the index and needs to include the values for the passed in list of columns.
    # use_or_cost_cols: a list of the energy usage or energy cost column names
    # chart_type: 1 for an energy use pie chart, 2 for an energy cost pie chart
    # base_filename: Base filename for that graph. A final filename will be 
    #    created that includes the Site ID, the correct output directory, and 
    #    the pertinent year.
    # site_id:  The Site ID to be used to create the filename.
    # 
    # This function returns a list of the URLs that can be used to access the
    # three graphs from the report page.

    # Makes the legend prettier.
    df, use_or_cost_cols = beautify_legend(df, use_or_cost_cols)
    
    # Standardize colors using color_formatter utility
    color_dict = color_formatter(use_or_cost_cols)
    
    # Get the three most recent complete years of data
    sorted_completes = df.sort_index(ascending=False)
    most_recent_complete_years = sorted_completes[0:3]
    years = list(most_recent_complete_years.index.values)
    
    # Create percentages from usage
    most_recent_complete_years = most_recent_complete_years[use_or_cost_cols]
    most_recent_complete_years['Totals'] = most_recent_complete_years.sum(axis=1)
    for col in use_or_cost_cols:
        most_recent_complete_years[col] = most_recent_complete_years[col] / most_recent_complete_years.Totals
    
    most_recent_complete_years = most_recent_complete_years.drop('Totals', axis=1)

    
    # List holding the Matplotlib figures created.
    figs = []
    
    # List holding the URLs that will access the saved graph image files.
    urls = []
    
    # Create a pie chart for each of 3 most recent complete years
    for year in years:
   
        # Make current year dataframe
        year_df = most_recent_complete_years.query("fiscal_year == @year")
    
        updated_use_or_cost_cols = []
        
        # Drop columns that only have zero usage
        for col in use_or_cost_cols:
            if year_df[col].iloc[0] == 0:
                year_df = year_df.drop(col, axis=1)
            else:
                updated_use_or_cost_cols.append(col)

        fig, ax = plt.subplots()

        if year_df.sum(axis=1).values[0] > 0:
            patches, texts, autotexts = ax.pie(list(year_df.iloc[0].values), labels=list(year_df.columns.values), autopct='%1.1f%%',
                                                    shadow=True, startangle=90, colors=[ color_dict[i] for i in updated_use_or_cost_cols])
            
            plt.tick_params(axis='both', which='both', labelsize=32)
        
            # Create the title based on whether it is an energy use or energy cost pie chart.  
            if chart_type == 1:
                title = "FY " + str(year) + " Energy Usage [MMBTU]"
            else:
                title = "FY " + str(year) + " Energy Cost [$]"
                
            plt.title(title)
            
            # Make the graph take up a larger portion of the figure 
            plt.axis([0.75, 0.75, 0.75, 0.75])
            ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
            
            # Increase the font size of the labels
            props = fm.FontProperties()
            props.set_size(32)
            plt.setp(autotexts, fontproperties=props)
            plt.setp(texts, fontproperties=props)
            
            # Include the year in the file
            fn_with_yr = '{}_{}'.format(base_filename, year)
            final_fn, url = graph_filename_url(site_id, fn_with_yr)
            urls.append(url)
            
            # Save and show
            plt.savefig(final_fn)
            figs.append(fig)
        else:
            # Include the year in the file
            fn_with_yr = '{}_{}'.format(base_filename, year)
            final_fn, url = graph_filename_url(site_id, fn_with_yr)
            urls.append(url)
            shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(final_fn))
            
        
    plt.close('all')
    
    return urls


def create_monthly_profile(df, graph_column_name, yaxis_name, color_choice, title, filename):
    # Parameters: 
        # df: A dataframe with the fiscal_year, fiscal_mo, and appropriate graph column name ('kWh', 'kW', etc.)
        # graph_column_name: The name of the column containing the data to be graphed on the y-axis
        # yaxis_name: A string that will be displayed on the y-axis
        # color_choice: 'blue', 'red', or 'green' depending on the desired color palette.  

    # Test to see if the dataframe is empty or if all values equal zero
    if not df.empty and np.any(df.fillna(0) > 0):
        # Get five most recent years
        recent_years = (sorted(list(df.index.levels[0].values), reverse=True)[0:5])
        
        # Reset the index of the dataframe for more straightforward queries
        df_reset = df.reset_index()

        # Create a color dictionary of progressively lighter colors of three different shades and convert to dataframe
        color_dict = {'blue': ['#08519c', '#3182bd', '#6baed6', '#bdd7e7', '#eff3ff'],
                      'red': ['#a50f15', '#de2d26', '#fb6a4a', '#fcae91', '#fee5d9'],
                      'green': ['#006d2c', '#31a354', '#74c476', '#bae4b3', '#edf8e9']
                     }

        color_df = pd.DataFrame.from_dict(color_dict)

        
        # i is the counter for the different colors
        i=0

        # Create the plots
        fig, ax = plt.subplots()

        for year in recent_years:

            # Create df for one year only so it's plotted as a single line
            year_df = df_reset.query("fiscal_year == @year")

            # Plot the data
            ax.plot_date(year_df['fiscal_mo'], year_df[graph_column_name], fmt='-', color=color_df.iloc[i][color_choice], 
                         label=str(year_df.fiscal_year.iloc[0]))

            # Increase counter by one to use the next color
            i += 1

        
        # Format the y-axis so a comma is displayed for thousands
        ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
        
        # Set x-axis labels to be fiscal months, starting in July
        ax.set_xticks(year_df.fiscal_mo.values)
        ax.set_xticklabels(bu.mo_list)

        # Add the labels
        plt.xlabel('Month of Year')
        plt.ylabel(yaxis_name)
        plt.legend()
        plt.title(title)

        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))
        
        
def stacked_bar_with_line(df, fiscal_year_col, bar_col_list, line_col, ylabel1, ylabel2, title, filename):
    
    # Parameters:
    # fiscal_year_col: the name of the column where the fiscal year is listed (use reset_index() if it is currently the index
    # bar_col_list: a list of the column names for the bar chart portion of the graph
    # line_col: The column with the data to plot the line
    # ylabel1 and ylabel2: Strings to name the y-axes
    # filename: A string with the filename where the output should be saved.
    
    # Test to see if the dataframe is empty or if all values equal zero
    all_cols = []
    all_cols.extend(bar_col_list)
    all_cols.append(line_col)
    if not df.empty and np.any(df[all_cols].fillna(0) > 0):
        # Makes the legend prettier.
        df, bar_col_list = beautify_legend(df, bar_col_list)
        
         # Makes the legend prettier.
        df_line, line_col = beautify_legend(df, [line_col])
        
        # Create the figure
        fig, ax = plt.subplots()
        
        # Set the bar width
        width = 0.50
        
        # Standardize colors using color_formatter utility
        color_dict = color_formatter(bar_col_list)
        
        # Create the stacked bars.  The "bottom" is the sum of all previous bars to set the starting point for the next bar.
        previous_col_name = 0
        
        # Fill the NaNs
        df = df.fillna(0)
        df_line = df_line.fillna(0)
        
        for col in bar_col_list:
            col_name = ax.bar(df[fiscal_year_col], df[col], width, label=col, bottom=previous_col_name, color=color_dict[col])
            previous_col_name = previous_col_name + df[col]
          
        # label axes
        ax.set_ylabel(ylabel1)
        ax.set_xlabel('Fiscal Year')
        
        # Make one bar for each fiscal year
        plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0), 
                   np.sort(list(df[fiscal_year_col].unique())))
        
        ax.set_ylim(bottom=0, top=previous_col_name.max() + previous_col_name.max()*0.10)
        
        # Create the line on the same graph but on a separate axis.
        ax2 = ax.twinx()
        ax2.plot(df_line[fiscal_year_col], df_line[line_col[0]], label=line_col[0], color='k',linewidth=5, marker='D', markersize=10)
        ax2.set_ylabel(ylabel2)
        
        # Ensure that the axis starts at 0.
        ax2.set_ylim(bottom=0, top=df_line[line_col[0]].max() + df_line[line_col[0]].max()*0.10)
        
        # Format the y-axis so a comma is displayed for thousands
        ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
        ax2.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
        
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1+h2, l1+l2, loc='lower left')
        plt.title(title)
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))
    
    
def fuel_price_comparison_graph(unit_cost_df, date_col, unit_cost_cols, bldg_unit_cost_col, filename):
    
        # Test to see if the dataframe is empty or if all values equal zero
    if not unit_cost_df.empty and np.any(unit_cost_df.fillna(0) > 0):
        # Makes the legend prettier.
        unit_cost_df, unit_cost_cols = beautify_legend(unit_cost_df, unit_cost_cols)
        
        # Makes the legend prettier.
        unit_cost_df, bldg_unit_cost_col = beautify_legend(unit_cost_df, [bldg_unit_cost_col])
        
        # Standardize colors using color_formatter utility
        color_dict = color_formatter(unit_cost_cols)

        fig, ax = plt.subplots()

        # Plot the fuel unit costs for each fuel type
        for col in unit_cost_cols:
            plt.plot(unit_cost_df[date_col], unit_cost_df[col], label=col, linestyle='--', color=color_dict[col])

        # Plot the building unit cost for fuels used
        plt.plot(unit_cost_df[date_col], unit_cost_df[bldg_unit_cost_col[0]], label=bldg_unit_cost_col[0], linestyle='-', color='k')

        plt.ylabel('Energy Cost [$/MMBTU]')
        plt.xlabel('Date')
        plt.title("Heating Fuel Unit Price Comparison [$/MMBTU]")

        plt.legend()
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else: 
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))        

def create_monthly_line_graph(df, date_col, graph_col, ylabel, filename):
    
    # Test to see if the dataframe is empty or if all values equal zero
    if not df.empty and np.any(df.fillna(0) > 0):    
        fig, ax = plt.subplots()
        
        # Create the plot
        plt.plot(df[date_col], df[graph_col], color='k')
        
        # Set the ylabel
        plt.ylabel(ylabel)
        
        if df[graph_col].max() > 1000:
            # Format the y-axis so a comma is displayed for thousands
            ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))
        
        plt.title("Realized Cumulative Energy Savings from Fuel Switching")
        
        # Save and show
        plt.savefig(filename)
        plt.close('all')
    else: 
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))            
    
def graph_filename_url(site_id, base_graph_name):
    """This function returns a two-tuple: graph file name, graph URL.
    The graph file name is used to save the graph to the file system; the
    graph URL is used in an HTML site report to load the graph into an
    image tag.
    Parameters:
    'site_id': the Site ID of the site this graph is related to.
    'base_graph_name': a graph file name, not including the Site ID and not
        including the 'png' extension.  For example: 'eco_g1', which will
        produce a graph file name of 'ANSBG1_eco_g1.png' assuming
        the Site ID is ANSBG1.
    """
    fn = 'output/images/{}_{}.png'.format(site_id, base_graph_name)
    url = 'images/{}_{}.png'.format(site_id, base_graph_name)
    return fn, url

def building_type_comparison_graph(df, graph_column, site, filename):
    ''' This function creates a graph that compares the eui, eci, or specific_eui to 
    buildings of a chosen usage type in the dataset. The inputs are the df in a format similar to 
    the df5.pkl, the column name to graph, the building site name, 
    and the filename for saving the output.'''
    
    # Create df with chosen building site to create line plot
    site_df = df.query("site_id == @site")

    # There may be no energy data for this building.  Show "No Data" graph and exit.
    if len(site_df)==0:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))            
        return
    
    # Get the usage type of the site.  Note that the usage type should be the same
    # for all records for a given site, but if not this code will only take the first.
    usage_type = site_df.primary_func.iloc[0]
    
    # Limit dataframe to only buildings of the chosen usage type
    usage_type_df = df.query("primary_func == @usage_type")

    # Replace infinity values with NaN's so that they are ignored during percentile calculations
    usage_type_df = usage_type_df.replace([np.inf, -np.inf], np.nan)

    # Get the 10th percentile for this given usage type
    usage_type_10 = usage_type_df.groupby(['fiscal_year']).quantile(0.1)
    # Reset the index for easier merging
    usage_type_10 = usage_type_10.reset_index()

    # Get the 90th percentile for this given usage type
    usage_type_90 = usage_type_df.groupby(['fiscal_year']).quantile(0.9)
    # Reset the index for easier merging
    usage_type_90 = usage_type_90.reset_index()

    # Merge dataframes
    usage_df_10_90 = pd.merge(usage_type_90, usage_type_10, how='outer',
                             left_on='fiscal_year', right_on='fiscal_year',
                             suffixes=['_90', '_10'])

    # Create the figure
    fig, ax = plt.subplots()

    plt.xticks(rotation=45)

    # Create the labels for the legend
    plot_label = graph_column.upper() + " for building site " + site
    area_label = usage_type + " 10th-90th percentile " + graph_column.upper()

    # Define the column names for the 10th and 90th percentiles
    graph_column_10 = graph_column + '_10'
    graph_column_90 = graph_column + '_90'

    # Plot the line for the chosen building site
    ax.plot(site_df.fiscal_year, site_df[graph_column], linewidth='3.0',
           label=plot_label)

    # Format the y-axis so a comma is displayed for thousands
    ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))

    # Create an area graph showing the 10th to 90th percentile
    ax.fill_between(usage_df_10_90.fiscal_year, usage_df_10_90[graph_column_10], 
                    usage_df_10_90[graph_column_90], 
                    alpha=0.5, color='#92c5de', label=area_label)

    # Define the axis labels and titles
    pretty_names_dict = {'eui': 'Energy Use Intensity',
                'eci': 'Energy Cost Index',
                'specific_eui': 'Thermal EUI per HDD'}
    plot_title = pretty_names_dict[graph_column] + " Comparison for\n" + usage_type + " Buildings"
    units_dict = {'eui': 'kBTUs / sqft / year',
                 'eci': '$ / sqft / year',
                 'specific_eui': 'BTUs / sqft / HDD / year'}
    yaxis_label = graph_column.upper() + " (" + units_dict[graph_column] + ")"


    plt.ylabel(yaxis_label)
    plt.xlabel('Fiscal Year')
    plt.title(plot_title)

    plt.legend(fontsize=16)

    plt.savefig(filename)
    plt.close('all')
   
def building_owner_comparison_graph(df, graph_column, site, filename):
    ''' This function creates a graph that compares the eui, eci, or specific_eui to 
    buildings of a chosen usage type in the dataset. The inputs are the df in a format similar to 
    the df5.pkl, the column name to graph, the building site name, 
    and the filename for saving the output.'''
    
    # Create df with chosen building site to create line plot
    site_df = df.query("site_id == @site")

    # There may be no energy data for this building.  Show "No Data" graph and exit.
    if len(site_df)==0:
        shutil.copyfile(os.path.abspath('no_data_available.png'), os.path.abspath(filename))            
        return
    
    # Get the usage type of the site.  Note that the usage type should be the same
    # for all records for a given site, but if not this code will only take the first.
    building_owner = site_df.site_category.iloc[0]
    
    # Limit dataframe to only buildings of the chosen usage type
    owner_df = df.query("site_category == @building_owner")

    # Replace infinity values with NaN's so that they are ignored during percentile calculations
    owner_df = owner_df.replace([np.inf, -np.inf], np.nan)

    # Get the 10th percentile for this given usage type
    owner_10 = owner_df.groupby(['fiscal_year']).quantile(0.1)
    # Reset the index for easier merging
    owner_10 = owner_10.reset_index()

    # Get the 90th percentile for this given usage type
    owner_90 = owner_df.groupby(['fiscal_year']).quantile(0.9)
    # Reset the index for easier merging
    owner_90 = owner_90.reset_index()

    # Merge dataframes
    owner_df_10_90 = pd.merge(owner_90, owner_10, how='outer',
                             left_on='fiscal_year', right_on='fiscal_year',
                             suffixes=['_90', '_10'])

    # Create the figure
    fig, ax = plt.subplots()

    plt.xticks(rotation=45)

    # Create the labels for the legend
    plot_label = graph_column.upper() + " for building site " + site
    area_label = building_owner + " 10th-90th percentile " + graph_column.upper()

    # Define the column names for the 10th and 90th percentiles
    graph_column_10 = graph_column + '_10'
    graph_column_90 = graph_column + '_90'

    # Plot the line for the chosen building site
    ax.plot(site_df.fiscal_year, site_df[graph_column], linewidth='3.0',
           label=plot_label)

    # Format the y-axis so a comma is displayed for thousands
    ax.get_yaxis().set_major_formatter(FuncFormatter(lambda x, p: format(int(x), ',')))

    # Create an area graph showing the 10th to 90th percentile
    ax.fill_between(owner_df_10_90.fiscal_year, owner_df_10_90[graph_column_10], 
                    owner_df_10_90[graph_column_90], 
                    alpha=0.5, color='#92c5de', label=area_label)

    # Define the axis labels and titles
    pretty_names_dict = {'eui': 'Energy Use Intensity',
                        'eci': 'Energy Cost Index',
                        'specific_eui': 'Thermal EUI per HDD'}
    plot_title = pretty_names_dict[graph_column] + " Comparison for\n" + "Buildings Owned by " + building_owner
    units_dict = {'eui': 'kBTUs / sqft / year',
                 'eci': '$ / sqft / year',
                 'specific_eui': 'BTUs / sqft / HDD / year'}
    yaxis_label = graph_column.upper() + " (" + units_dict[graph_column] + ")"


    plt.ylabel(yaxis_label)
    plt.xlabel('Fiscal Year')
    plt.title(plot_title)

    plt.legend(fontsize=16)

    plt.savefig(filename)
    plt.close('all')
            
        
            
    
