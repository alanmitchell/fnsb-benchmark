"""Utilities and initialization code related to the Jinja2 templates
used by the benchmarking script.
"""

from jinja2 import Environment, FileSystemLoader

# Create the Template environment
env = Environment(
    loader=FileSystemLoader(['templates', 'templates/sites'])
)

#------ Below are Custom Filters used for Formatting --------

def is_blank(val):
    return (val is None) or (val == "nan")

def filter_blank(val):
    if is_blank(val):
        return ''
    else:
        return val

def filter_money(val):
    try:
        return "${:,}".format(val)
    except TypeError:
        return ''
    except ValueError:
        return val

def filter_money_accurate(val):
    try:
        return "${:,.3f}".format(val)
    except TypeError:
        return ''
    except ValueError:
        return val

def filter_number(val):
    try:
        return '{:,}'.format(val)
    except TypeError:
        return ''
    except ValueError:
        return val

def filter_percent(val):
    try:
        return "{:.0%}".format(val)
    except TypeError:
        return ''
    except ValueError:
        return val

# Assign the custom filters to the Environment
env.filters['blank'] = filter_blank
env.filters['money'] = filter_money
env.filters['money_accurate'] = filter_money_accurate
env.filters['number'] = filter_number
env.filters['percent'] = filter_percent

def get_template(template_filename):
    """Returns a template having the name 'template_file_name'
    """
    return env.get_template(template_filename)
