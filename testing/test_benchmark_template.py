"""This script uses sample data from a YAML to file to test the Benchmarking
template.  It creates an output HTML file at the path: output/sample.html.
"""
import yaml
from jinja2 import Template

buildings = yaml.load(open('sample_buildings_list.yaml').read())
sample_building = yaml.load(open('sample_benchmark_data.yaml').read())

"""Example
template = Template(open('../templates/example.html').read())
result = template.render(sample_building)
open('output/example.html', 'w').write(result)
"""

# TODO: Give template a list of buildings
template = Template(open('../templates/index.html').read())
result = template.render(buildings)
open('output/index.html', 'w').write(result)

"""
# TODO: Loop through each building and render template
template = Template(open('../templates/building.html').read())
result = template.render(sample_building)
open('output/big-dipper.html', 'w').write(result)
"""
