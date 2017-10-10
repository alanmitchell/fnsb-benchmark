# fnsb-benchmark
Creates Utility Energy Benchmarking Reports for Fairbanks North Star Borough

## Viewing Test Report
0. Ensure you have the correct packages installed `pip3 install jinja2 pyyaml`
1. Move into testing directory `cd testing`
2. Create report `python3 test_benchmark_template.py`
3. Move into output directory `cd output`
4. Start server `python3 -m http.server`
5. Open browser to `http://localhost:8000`
