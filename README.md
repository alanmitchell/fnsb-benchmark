# fnsb-benchmark
Creates Utility Energy Benchmarking Reports for the Fairbanks North Star Borough
and Buildings found in the Alaska Housing Finance Corporation ARIS database.  A
sample web site created with this script is available [here](http://benchmark.ahfc.webfactional.com/).

## Prerequisites
If you are running the Anaconda distribution of Python, you should have all of the
required packages to run the script.  If not, from a command line in the root
directory of the project, run:

    pip install -r requirements.txt
    
## Configuration of the Script

### Settings File

Before running the benchmarking script, some setup is required.  A settings file
controls a few different aspects of how the script runs.  There is a sample settings
file in the root directory called `settings_example.py`.  Copy that file to a new
file called `settings.py` in the same directory.  This `settings.py` file is the actual file used to control
the script.  This file is *not* stored in the GitHub repository as it has been set to be ignored, 
so it will not affect other users.

Open the `settings.py` file in an editor and read the comments for each settings
to determine the proper value.  Important settings are the path to the Utility Bill
CSV file and the path to the directory where two other key spreadsheets are located. 
These spreadsheets are described below in the Data File section.

### Data Files

There are a number of critical data files for the script:

* An Excel workbook named `Buildings.xlsx` that contains information about each site,
such as square footage, address, and year built.  Two samples of this
spreadsheet are found in the `data` directory: `Buildings_FNSB.xlsx` and `Building_AHFC.xlsx`.
In general, the `data` directory is a good location for this file, although that location
is not required.  The `OTHER_DATA_DIR_PATH` value in the `settings.py` file just needs to point
to the directory containing the file. Note that it is important to keep the format of the `Buildings.xlsx` 
file unaltered. The row number of the start of the data on each sheet is critical to operation of the script,
so rows should not be added or deleted above that point on the Excel sheet.

* An Excel workbook named `Services.xlsx` that contains information about the utility
service types that are present in the Utility Bill records file, including their Btu content
if the services are energy-providing services.  It also contains a list of
the standard categories that these service types are mapped into.  There are two sheets in
this Excel workbook, and two samples of the workbook are provided in the `data` directory: 
`Services_sample_fnsb.xlsx` and `Services_sample_aris.xlsx`.

* A Utility Bill Records file. This is a CSV file that contains the utility
bill information for all of the buildings.  Here are the first few records of a
utility bill record file:

```
Site ID,Cost,Usage,Service Name,Units,Thru,From,Item Description,Account Number,Vendor Name
1,10472.0,129800.0,Electric,kWh,2009-01-15,2008-12-16,Energy,,
1,9768.0,117600.0,Electric,kWh,2009-02-15,2009-01-15,Energy,,
1,11883.0,116000.0,Electric,kWh,2009-03-15,2009-02-15,Energy,,
1,15421.0,158800.0,Electric,kWh,2009-04-15,2009-03-15,Energy,,
1,13802.0,137400.0,Electric,kWh,2009-05-15,2009-04-15,Energy,,
```

Further documentation of the required structure for this file is
available from the software authors.

* Degree-Day Information: This script also depends upon degree-day information provided by a file on the
Alaska Housing Finance Corporation BMON server.  That file is updated monthly
by the [update-degree-days script](https://github.com/alanmitchell/update-degree-days).
The URL to the degree-day file is:  `http://ahfc.webfactional.com/data/degree_days.pkl` and
it is a pickled Pandas DataFrame using `bz2` compression.

## Running the Script

The script is compatible with Python 3.5 or higher.  To run the script, change into the root directory of
the project on a command line.  One of the following commands should start the script:

    python benchmark.py       # if 'python' starts Python 3 on your computer
    python3 benchmark.py      # some Python installs use 'python3' to start
    ./benchmark.py            # on Linux or Max OSX, if you set 'benchmark.py' to be executable

If you have multiple anaconda environments installed, you will need to first activate the one running Python 3.5 by using the following command:

    conda list envs					# Shows the names of your possible environments
    activate [your python 3.5 env]	# Activates the correct environment
    python benchmark.py				# Runs the script in the chosen environment


The script will print messages to the console about its progress; cumulative execution time
will also be shown at each step.  This script will take approximately 11 seconds per building to run.

If you are using utility bill data from the Alaska Housing Finanance Corporation ARIS
database, you need to first run a preparation script prior to running the main benchmark 
script.  This script creates a Utility Record CSV file called `aris_records.csv` in the `data` directory.  It also creates the `Buildings.xlsx` spreadsheet in the `data`
directory.

## Script Results

The script places all of the reports and other results in the `output` directory.  The reports
for all the buildings can be viewed by double-clicking the `index.html` file in the output directory.  There also is a spreadsheet created in the `output/extra_data` directory called
`site_summary_FY2017.xlsx` that shows summary information for every site for the most recent
complete fiscal year.

**NOTE**: All files in the `output/sites`, `output/images`, `output/extra_data`, and `output/debug`
directories are deleted at the beginning of each run of the benchmark script.  If you have modified
any of these files and want to keep them (e.g. the extra_data/site_summary spreadsheet), copy them
to another location before running the script.

## For Developers

Here are some debugging and testing tips, useful when adding or modifying code in this script:

* The script reads the Utility Bill CSV file and performs a number of preprocessing steps. 
  This can take approximately 4 minutes and greatly slow down testing and debugging. 
  You can eliminate this execution time by setting the `USE_DATA_FROM_LAST_RUN` setting to 
  `True` in the settings file. The Utility data and the preprocessing from the last complete run 
  will be used by the script, instead of redoing those tasks.
* You can also limit the number sites that the script will process by setting
  `MAX_NUMBER_SITES_TO_RUN` to a small number like 3.  The first `MAX_NUMBER_SITES_TO_RUN` will be
  processed by the script (in alphabetical order by Site ID) and no more.  You can also just 
  prematurely stop the script by Ctrl-C or Ctrl-Break; no post-processing steps will be missed by
  early termination.
* If you want to run selected sites through the script, make a new `Buildings.xlsx` 
  spreadsheet with only the desired sites listed.
* For each site processed, a large Python dictionary is created containing the data needed by
  the reporting template.  If the setting `WRITE_DEBUG_DATA` is set to `True`, a file showing
  this data will be created for each site processed.  Those files are located in the `debug`
  directory and are named <Site ID>.vars.  They are plain text files that can be opened in a
  text editor.
