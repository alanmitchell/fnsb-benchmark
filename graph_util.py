import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import matplotlib as mpl
import matplotlib.dates as mdates
import datetime

# Set the matplotlib settings (eventually this will go at the top of the graph_util)
mpl.rcParams['axes.labelsize'] = 16
mpl.rcParams['axes.titlesize'] = 20
mpl.rcParams['legend.fontsize'] = 16
mpl.rcParams['font.size'] = 16.0
mpl.rcParams['figure.figsize'] = [15,10]
mpl.rcParams['xtick.labelsize'] = 16
mpl.rcParams['ytick.labelsize'] = 16

# Set the style for the graphs
plt.style.use('bmh')

# Additional matplotlib formatting settings
months = mdates.MonthLocator()

# This formats the months as three-letter abbreviations
months_format = mdates.DateFormatter('%b')

def area_cost_distribution(df, fiscal_year_col, utility_col_list, filename):
    # Inputs include the dataframe, the column name for the fiscal year column, and the list of column names for the 
    # different utility bills.  The dataframe should already include the summed bills for each fiscal year.

    fig, ax = plt.subplots()

    
    # Take costs for each utility type and convert to percent of total cost by fiscal year
    df['total_costs'] = df[utility_col_list].sum(axis=1)

    percent_columns = []

    for col in utility_col_list:
        percent_col = "Percent " + col
        percent_columns.append(percent_col)
        df[percent_col] = df[col] / df.total_costs

    # Create stacked area plot
    ax.stackplot(df[fiscal_year_col], df[percent_columns].T, labels=percent_columns)

    # Format the y axis to be in percent
    ax.yaxis.set_major_formatter(FuncFormatter('{0:.0%}'.format))
    
    # Format the x-axis to include all fiscal years
    plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0))

    # Add title and axis labels
    plt.title('Annual Utility Cost Distribution')
    plt.ylabel('Utility Cost Distribution')
    plt.xlabel('Fiscal Year')
    
    # Add legend
    plt.legend()
    
    # Make sure file goes in the proper directory
    folder_and_filename = 'output/images/' + filename
    
    # Save and show
    plt.savefig(folder_and_filename)
    plt.show()
	
	
def area_use_distribution(df, fiscal_year_col, utility_col_list, filename):
    # Inputs include the dataframe, the column name for the fiscal year column, and the list of column names for the 
    # different utility bills.  The dataframe should already include the summed bills for each fiscal year.
    

    fig, ax = plt.subplots()

    
    # Take usage for each utility type and convert to percent of total cost by fiscal year
    df['total_use'] = df[utility_col_list].sum(axis=1)

    percent_columns = []

    for col in utility_col_list:
        percent_col = "Percent " + col
        percent_columns.append(percent_col)
        df[percent_col] = df[col] / df.total_use

    # Create stacked area plot
    ax.stackplot(df[fiscal_year_col], df[percent_columns].T, labels=percent_columns)


    # Format the y axis to be in percent
    ax.yaxis.set_major_formatter(FuncFormatter('{0:.0%}'.format))
    
    # Format the x-axis to include all fiscal years
    plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0))

    # Add title and axis labels
    plt.title('Annual Energy Usage Distribution')
    plt.ylabel('Annual Energy Usage Distribution')
    plt.xlabel('Fiscal Year')
    
    # Add legend 
    plt.legend()
    
    # Make sure file goes in the proper directory
    folder_and_filename = 'output/images/' + filename
    
    # Save and show
    plt.savefig(folder_and_filename)
    plt.show()
	
	
def create_stacked_bar(df, fiscal_year_col, column_name_list, filename):
    
    # Parameters include the dataframe, the name of the column where the fiscal year is listed, a list of the column names
    # with the correct data for the chart, and the filename where the output should be saved.
    
    
    # Create the figure
    plt.figure()
    
    # Set the bar width
    width = 0.50
    
    
    # Create the stacked bars.  The "bottom" is the sum of all previous bars to set the starting point for the next bar.
    previous_col_name = 0
    
    for col in column_name_list:
        short_col_name = col.split(" Cost")[0]
        short_col_name = plt.bar(df[fiscal_year_col], df[col], width, label=short_col_name, bottom=previous_col_name)
        previous_col_name = previous_col_name + df[col]
      
    # label axes
    plt.ylabel('Utility Cost [$]')
    plt.xlabel('Fiscal Year')
    plt.title('Total Annual Utility Costs')
    
    # Make one bar for each fiscal year
    plt.xticks(np.arange(df[fiscal_year_col].min(), df[fiscal_year_col].max()+1, 1.0), 
               np.sort(list(df[fiscal_year_col].unique())))
    
    # Set the yticks to go up to the total cost in increments of 100,000
    df['total_cost'] = df[column_name_list].sum(axis=1)
    plt.yticks(np.arange(0, df.total_cost.max(), 100000))
    
    plt.legend()
    
    # Make sure file goes in the proper directory
    folder_and_filename = 'output/images/' + filename
    
    # Save and show
    plt.savefig(filename)
    plt.show()
	
	
def energy_use_stacked_bar(df, fiscal_year_col, column_name_list, filename):
    
    # Parameters include the dataframe, the name of the column where the fiscal year is listed, a list of the column names
    # with the correct data for the chart, and the filename where the output should be saved.
    
    # Create the figure
    plt.figure()
    
    # Set the bar width
    width = 0.50
    
    
    # Create the stacked bars.  The "bottom" is the sum of all previous bars to set the starting point for the next bar.
    previous_col_name = 0
    
    for col in column_name_list:
        short_col_name = col.split(" [MMBTU")[0]
        short_col_name = plt.bar(df[fiscal_year_col], df[col], width, label=short_col_name, bottom=previous_col_name)
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
    plt.yticks(np.arange(0, df.total_use.max(), 1000))
    
    plt.legend()
    
    # Make sure file goes in the proper directory
    folder_and_filename = 'output/images/' + filename
    
    # Save and show
    plt.savefig(folder_and_filename)
    plt.show()
	
	
def usage_pie_charts(df, use_or_cost_cols, chart_type, filename):
    
    # df: A dataframe with the fiscal_year as the index and needs to include the values for the passed in list of columns.
    # use_or_cost_cols: a list of the energy usage or energy cost column names
    # chart_type: 1 for an energy use pie chart, 2 for an energy cost pie chart

    
    # Get the three most recent complete years of data
    complete_years = df.query("month_count == 12.0")
    sorted_completes = complete_years.sort_index(ascending=False)
    most_recent_complete_years = sorted_completes[0:3]
    years = list(most_recent_complete_years.index.values)
    
    # Create percentages from usage
    most_recent_complete_years = most_recent_complete_years[use_or_cost_cols]
    most_recent_complete_years['Totals'] = most_recent_complete_years.sum(axis=1)
    for col in use_or_cost_cols:
        most_recent_complete_years[col] = most_recent_complete_years[col] / most_recent_complete_years.Totals
    
    most_recent_complete_years = most_recent_complete_years.drop('Totals', axis=1)

    
    # Create a pie chart for each of 3 most recent complete years
    for year in years:
   
        # Make current year dataframe
        year_df = most_recent_complete_years.query("fiscal_year == @year")
    
        # Drop columns that only have zero usage
        for col in use_or_cost_cols:
            if year_df[col].iloc[0] == 0:
                year_df = year_df.drop(col, axis=1)

        fig, ax = plt.subplots()

        ax.pie(list(year_df.iloc[0].values), labels=list(year_df.columns.values), autopct='%1.1f%%',
        shadow=True, startangle=90)
        
        plt.tick_params(axis='both', which='both', labelsize=16)
    
        # Create the title based on whether it is an energy use or energy cost pie chart.  
        if chart_type == 1:
            title = "FY " + str(year) + " Energy Usage [MMBTU]"
        else:
            titel = "FY " + str(year) + " Energy Cost [$]"
            
        plt.title(title, fontsize=20)

        ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

        # Make sure file goes in the proper directory
        folder_and_filename = 'output/images/' + filename + str(year)

        # Save and show
        plt.savefig(folder_and_filename)
        plt.show()
		
		
def create_monthly_profile(df, graph_column_name, yaxis_name, color_choice, filename):
    # Parameters: 
        # df: A dataframe with the fiscal_year, fiscal_mo, and appropriate graph column name ('kWh', 'kW', etc.)
        # graph_column_name: The name of the column containing the data to be graphed on the y-axis
        # yaxis_name: A string that will be displayed on the y-axis
        # color_choice: 'blue', 'red', or 'green' depending on the desired color palette.  
    
    # Additional matplotlib formatting settings
    months = mdates.MonthLocator()
    
    # This formats the months as three-letter abbreviations
    months_format = mdates.DateFormatter('%b')

    # Get five most recent years
    recent_years = (sorted(list(df.index.levels[0].values), reverse=True)[0:5])
    
    # Reset the index of the dataframe for more straightforward queries
    df_reset = df.reset_index()
    
    def get_date(row):
        # Converts the fiscal year and fiscal month columns to a datetime object for graphing
        
        # Year is set to 2016-17 so that the charts overlap; otherwise they will be spread out by year.
        # The "year trick" allows the graph to start from July so the seasonal energy changes are easier to identify
        if row['fiscal_mo'] > 6:
            year_trick = 2016
        else:
            year_trick = 2017

        return datetime.date(year=year_trick, month=row['fiscal_mo'], day=1)

    # This creates a new date column with data in the datetime format for graphing
    df_reset['date'] = df_reset[['fiscal_year', 'fiscal_mo']].apply(get_date, axis=1)
                        
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
        year_df = year_df.sort_values(by='date')

        # Plot the data
        ax.plot_date(year_df['date'], year_df[graph_column_name], fmt='-', color=color_df.iloc[i][color_choice], 
                     label=str(year_df.fiscal_year.iloc[0]))

        # Increase counter by one to use the next color
        i += 1


    # Format the dates
    ax.xaxis.set_major_locator(months)
    ax.xaxis.set_major_formatter(months_format)
    fig.autofmt_xdate()

    # Add the labels
    plt.xlabel('Month of Year')
    plt.ylabel(yaxis_name)
    plt.legend()

    # Make sure file goes in the proper directory
    folder_and_filename = 'output/images/' + filename
    
    # Save and show
    plt.savefig(folder_and_filename)
    plt.show()

		
		
