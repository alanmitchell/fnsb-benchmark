"""This script uses sample data from a YAML to file to test the Benchmarking
template.  It creates an output HTML file at the path: output/sample.html.
"""
import yaml
import os
from jinja2 import Template

sample_building = yaml.load(open("sample_benchmark_data.yaml").read())
template_folder = "../templates/"
buildings_template_folder = template_folder + "building/"
output_folder = "output/"

"""Example
template = Template(open("../templates/example.html").read())
result = template.render(sample_building)
open("output/example.html", "w").write(result)
"""

# TODO: Give template a list of buildings
buildings = yaml.load(open("sample_buildings_list.yaml").read())
template = Template(open(template_folder + "index.html").read())
result = template.render(buildings)
open("output/index.html", "w").write(result)

# TODO: Loop through each building and render template
building_id = "big-dipper" # TODO: This will be determined by the loop
building_dir = output_folder + building_id
report_pages = ['index'] # TODO: Add more pages here
for page in report_pages:
    # just easier than appending '.html' to all of the report array items above
    report_page_filename = page + ".html"

    # template filename matches output filename just in different directory
    template_filename = buildings_template_folder + report_page_filename

    # read Jinja2 template
    template = Template(open(template_filename).read())

    # render the Jinja2 template with the building info
    result = template.render(sample_building)

    # ensure directory exists before we try writing file
    os.makedirs(building_dir, 0o777, True)

    # write the contents of the rendered report to the corresponding file
    open(building_dir + "/" + report_page_filename, "w").write(result)
