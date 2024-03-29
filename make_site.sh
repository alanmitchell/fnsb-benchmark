#!/usr/bin/bash

# Sample Script to read ARIS energy use data, run the benchmarking script,
# and copy the resulting website to the production site.  Change base paths
# and email addresses as needed.

recipient="tabb99@gmail.com"

error_exit() {

	/usr/bin/sendmail "$recipient" <<EOF
Subject: AHFC Benchmark Script Failed

Error was: ${1:-"Unknown Error"}. 
Please check log file on site for more details.
EOF

	exit 1
}

cd ~/fnsb-benchmark
source env/bin/activate
python -u read_aris.py > logs/read_aris.log 2>&1  # || error_exit "Error reading ARIS data."
python -u benchmark.py > logs/benchmark.log 2>&1  # || error_exit "Error executing Benchmark script."
deactivate

rm -rf /var/www/html/benchmark/*     # || error_exit "Error removing old web site files."
cp -r ~/fnsb-benchmark/output/* /var/www/html/benchmark/   # || error_exit "Error copying new files to site."

#/usr/bin/sendmail "$recipient" <<EOF
#Subject: AHFC Benchmark Script Succeeded

#Awesome!!
#EOF
