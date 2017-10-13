"""This script uses sample data from a YAML to file to test the Benchmarking
template.  It creates an output HTML file at the path: output/sample.html.
"""
import yaml
import os
from jinja2 import Template
from jinja2 import Environment, FileSystemLoader, select_autoescape

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

env = Environment(
    loader=FileSystemLoader(["../templates", "../templates/building"])
)

env.filters['blank'] = filter_blank
env.filters['money'] = filter_money
env.filters['money_accurate'] = filter_money_accurate
env.filters['number'] = filter_number
env.filters['percent'] = filter_percent

sample_building = yaml.load(open("./data/sample_benchmark_data.yaml").read())
buildings_template_folder = "building/"
output_folder = "output/"

"""Example
template = Template(open("../templates/example.html").read())
result = template.render(sample_building)
open("output/example.html", "w").write(result)
"""

# TODO: Give template a list of buildings
buildings = yaml.load(open("./data/sample_buildings_list.yaml").read())
template = env.get_template("index.html")
result = template.render(buildings)
open("output/index.html", "w").write(result)

# TODO: Loop through each building and render template
building_id = "big-dipper" # TODO: This will be determined by the loop
building_dir = output_folder + building_id
report_pages = [
    "electrical-cost-analysis",
    "electrical-usage-analysis",
    "energy-cost-usage",
    "energy-index-comparison",
    "energy-usage-overview",
    "heating-cost-analysis",
    "heating-usage-analysis",
    "index",
    "utility-cost-overview",
    "water-analysis"
]
for page in report_pages:
    # just easier than appending '.html' to all of the report array items above
    report_page_filename = page + ".html"

    # template filename matches output filename just in different directory
    template_filename = buildings_template_folder + report_page_filename

    # read Jinja2 template
    template = env.get_template(template_filename)

    # render the Jinja2 template with the building info
    result = template.render(sample_building)

    # ensure directory exists before we try writing file
    os.makedirs(building_dir, 0o777, True)

    # write the contents of the rendered report to the corresponding file
    open(building_dir + "/" + report_page_filename, "w").write(result)
