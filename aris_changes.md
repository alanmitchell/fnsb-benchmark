## Changes that were made during the Project to Allow ARIS Data to be Used

* Degree-Days no longer come from the `Other_Building_Data.xlsx` file.  They come from the
online file on the AHFC Webfaction server:  http://ahfc.webfactional.com/data/degree_days.pkl.  See the [GitHub project update-degree-days](https://github.com/alanmitchell/update-degree-days).
* `Other_Building_Data.xlsx` is split into two files now: `Buildings.xlsx` and `Services.xlsx`; `Services.xlsx` contains info about all service types, including a new column that maps each service to a standard category.  The ARIS script automatically creates the `Buildings.xlsx` file, as all that info is stored in ARIS.
* A new report comparing each building to the spread of the other buildings.
