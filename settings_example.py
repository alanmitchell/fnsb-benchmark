"""This file is an example settings.py file, which controls aspects of
how the benchmark.py script will run.

Copy this file to a file named "settings.py" in this directory, and then 
modify the settings in that file, not this example file.

The settings file is a standard Python module, so Python expressions or any
type of Python code is possible.
"""

# This is the path to the Utility Bill CSV file that will be read by the 
# benchmark script.  The path should be expressed relative to this directory
# (the directory where settings.py and benchmark.py reside). 
#(string file path, use forward slashes for directory separators)
UTILITY_BILL_FILE_PATH = 'data/20171017 AllDataExport.CSV'

# This is the path to the Other Data spreadsheet that holds additional
# information about the buildings (e.g. square feet, address) and degreee-day
# information. (string file path, use forward slashes for directory separators)
OTHER_DATA_FILE_PATH = 'data/Other_Building_Data.xlsx'

# Set the following to True if you want to use the same Utility Bill and Other 
# Data from the last run of the benchmark script.  This will substantially
# speed up the time required to run the script, since reading the CSV file and
# preprocessing the data are skipped. Useful for debugging code that doesn't 
# affect the preprocessing routine.  (True / False)
USE_DATA_FROM_LAST_RUN = False

# If the following setting is True, debug information will be written to the
# 'output/debug' directory, including the raw variable values that are passed
# to the HTML reporting template. (True / False)
WRITE_DEBUG_DATA = True

# If you are debugging or modifying the code in the benchmark script, it is
# convenient to only run some of the sites through the benchmark script to save
# time.  Set the number of sites you want to run in the setting below.  If you
# want to run all the sites, set the value to 0. The sites are processed in
# alphabetical order based on their Site ID. (integer)
MAX_NUMBER_SITES_TO_RUN = 0
