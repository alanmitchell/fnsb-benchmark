"""Functions to read CSV files exported by DDC systems.  These functions
return Pandas DataFrames containing the data.
"""

import csv
import string
import datetime
import pandas as pd

# ---------------- Utility Functions ---------------------

# A function useful for cleaning up point names (IDs)
def clean_string(s):
    """Function that "cleans" a string by first stripping leading and trailing
    whitespace and then substituting an underscore for all other whitepace
    and punctuation. After that substitution is made, any consecutive occurrences
    of the underscore character are reduced to one occurrence.
    Finally, the string is converted to lower case.
    Returns the cleaned string.

    Input Parameters:
    -----------------
    s:  The string to clean.
    """
    to_sub = string.whitespace + string.punctuation
    trans_table = str.maketrans(to_sub, len(to_sub) * '_')
    fixed = str.translate(s.strip(), trans_table)

    while True:
        new_fixed = fixed.replace('_' * 2, '_')
        if new_fixed == fixed:
            break
        fixed = new_fixed

    return fixed.lower()

# ----------------------- The Actual Reader Functions -------------------------

def siemens_reader(file_name, include_location_in_point_name=False):
    """Reads a CSV trend file exported from a Siemens DDC system, having the
    format of the sample file, data/siemens_sample.csv.
    file_name: the full path file name of the Siemens CSV file.
    include_location_in_point_name:  if True, the location field will be
        included in the Point ID

    returns:  a Pandas DataFrame, indexed on the date/times of the readings.
        Each column of the DataFrame contains the values from a single point;
        the column titles are the point IDs.  All timestamps found in the file
        are included; if a particular point does not have a reading at that
        timestamp, a NaN value is present.
    """

    reader = csv.reader(open(file_name))

    # While reading the data from the file, load it into a dictionary,
    # keyed by the name/ID of the point.  The keys are the Point ID,
    # and each value is a two-tuple: (list of date/times, list of values).
    # The date/times are Python datetime objects.
    data_dict = {}
    for row in reader:

        # trap errors and print a message, but continue reading
        try:
            f1 = row[0]  # shorthand variable for the first field

            if '/' in f1:  # Look for the '/' in a Date
                # this is a row with a data point in it.
                # create a date/time string and parse into a Python datetime
                ts = '{} {}'.format(row[0], row[1])
                ts = datetime.datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')

                # get the value, which is usually a number, but sometimes a string.
                # first try to convert to a number, and if it errors, just return it as a string
                try:
                    val = float(row[2])
                except:
                    val = row[2]

                # get the timestamps and values that have already been read
                # for this point.  If there are none, start new lists.
                tstamps, vals = data_dict.get(pt_id, ([], []))
                # append this point
                tstamps.append(ts)
                vals.append(val)
                # save the lists back into the dictionary
                data_dict[pt_id] = (tstamps, vals)

            elif f1.startswith('Point'):
                # This row has a Point ID in it
                pt_id = clean_string(row[1])

            elif f1.startswith('Trend L'):
                # This row has a Location code in it.  If requested, add it
                # to the point name.
                if include_location_in_point_name:
                    pt_id = '{}_{}'.format(clean_string(row[1]), pt_id)

        except:
            print('Could not parse row: {}'.format(row))

    # Create the Final DataFrame by concatenating together the DataFrames for each Point
    df_final = pd.DataFrame()
    for pt_id in data_dict.keys():
        # for this point, retrieve the timestamps and values frome the dictionary
        tstamps, vals = data_dict[pt_id]

        # make a DataFrame, indexed on the timestamps, with the point ID as the column
        # name.
        df = pd.DataFrame(vals, index=tstamps, columns=[pt_id])

        # Sometimes there are duplicate timestamps due to Alarms, I think.
        # Only take the value from the last timestamp of each duplicate time
        # stamp.
        df = df.groupby(level=0).last()

        # Add this DataFrame to the final DataFrame.  Indexes are matched up
        # or added if they don't already exist in the final frame.
        df_final = pd.concat([df_final, df], axis=1)

    return df_final
