"""Utilities and initialization code related to the Jinja2 templates
used by the benchmarking script.
"""

from jinja2 import Environment, FileSystemLoader, Undefined
import numpy as np


class SilentUndefined(Undefined):
    '''
    Dont break pageloads because vars aren't there!
    '''
    def _fail_with_undefined_error(self, *args, **kwargs):
        return None

# Create the Template environment
env = Environment(
    loader=FileSystemLoader(['templates', 'templates/sites']),
    undefined=SilentUndefined
)

#------ Below are Custom Filters used for Formatting --------

def is_blank(val):
    try:
        return not np.isfinite(val)
    except:
        return True

def filter_money(val, precision = 0):
    if is_blank(val): return ''
    format_string = "$ {:,.%sf}" % precision
    return format_string.format(val)

def filter_number(val, precision = 0, commas=True):
    if is_blank(val): return ''
    if commas:
        format_string = "{:,.%sf}" % precision
    else:
        format_string = "{:.%sf}" % precision
    return format_string.format(val)

def filter_percent(val, precision = 1):
    if is_blank(val): return ''
    format_string = "{:.%s%%}" % precision
    return format_string.format(val)

def filter_only_string(val):
    'Return blank for anything but strings.'
    if type(val) is str:
        return val
    else:
        return ''

# -------------- Assign the custom filters to the Environment
    
env.filters['money'] = filter_money
env.filters['number'] = filter_number
env.filters['percent'] = filter_percent
env.filters['only_string'] = filter_only_string

# ------------- Utility Functions -----------------

def get_template(template_filename):
    """Returns a template having the name 'template_file_name'
    """
    return env.get_template(template_filename)
