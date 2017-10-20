"""This script uses sample data from a YAML to file to test the Benchmarking
template.  It creates an output HTML file at the path: output/sample.html.
"""
import yaml
import os
from jinja2 import Template
from jinja2 import Environment, FileSystemLoader, select_autoescape
import numpy as np

def is_blank(val):
    try:
        return not np.isfinite(val)
    except:
        return True

def filter_blank(val):
    if is_blank(val): return ''
    return val

def filter_money(val, precision = 0):
    if is_blank(val): return ''
    format_string = "${:,.%sf}" % precision
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

env = Environment(
    loader=FileSystemLoader(["../templates", "../templates/sites"])
)

env.filters['blank'] = filter_blank
env.filters['money'] = filter_money
env.filters['number'] = filter_number
env.filters['only_string'] = filter_only_string
env.filters['percent'] = filter_percent

sample_building = yaml.load(open("./data/sample_benchmark_data_new.yaml").read())
sites_template_folder = "sites/"
output_folder = "output/"
output_sites_folder = output_folder + sites_template_folder

"""Example
template = Template(open("../templates/example.html").read())
result = template.render(sample_building)
open("output/example.html", "w").write(result)
"""

# TODO: Give template a list of sites
sites = yaml.load(open("./data/sample_buildings_list.yaml").read())
template = env.get_template("index.html")
result = template.render(sites)
open("output/index.html", "w").write(result)

# TODO: Loop through each building and render template
building_id = "ANSBG1" # TODO: This will be determined by the loop

# template filename matches output filename just in different directory
template_filename = sites_template_folder + "index.html"

# read Jinja2 template
template = env.get_template(template_filename)

# render the Jinja2 template with the building info
result = template.render(sample_building)

# ensure the sites directory exists before we try writing file
os.makedirs(output_sites_folder, 0o777, True)

# write the contents of the rendered report to the corresponding file
open(output_sites_folder + building_id + ".html", "w").write(result)
