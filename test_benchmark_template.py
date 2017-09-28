import yaml
from jinja2 import Template

sample_data = yaml.load(open('sample_benchmark_data.yaml').read())
template = Template(open('benchmark.html').read())
result = template.render(sample_data)
open('output/sample.html', 'w').write(result)
