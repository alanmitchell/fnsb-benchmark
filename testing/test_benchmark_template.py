"""This script uses sample data from a YAML to file to test the Benchmarking
template.  It creates an output HTML file at the path: output/sample.html.
"""
import yaml
from jinja2 import Template

sample_data = yaml.load(open('sample_benchmark_data.yaml').read())

template = Template(open('../templates/example.html').read())
result = template.render(sample_data)
open('output/example.html', 'w').write(result)
