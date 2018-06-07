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

#cd /home/ahfc/fnsb-benchmark
#python3.6 -u read_aris.py > logs/read_aris.log 2>&1 || error_exit "Error reading ARIS data."
#python3.6 -u benchmark.py > logs/benchmark.log 2>&1 || error_exit "Error executing Benchmark script."

#rm -rf /home/ahfc/webapps/benchmark/* || error_exit "Error removing old web site files."
#cp -r /home/ahfc/fnsb-benchmark/output/* /home/ahfc/webapps/benchmark/ || error_exit "Error copying new files to site."

/usr/bin/sendmail "$recipient" <<EOF
Subject: AHFC Benchmark Script Succeeded

Awesome!!
EOF
