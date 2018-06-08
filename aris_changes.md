# Changes that were made during the Project to Allow ARIS Data to be Used

* Degree-Days no longer come from the `Other_Building_Data.xlsx` file.  They come from the
  [online file on the AHFC Webfaction server](http://ahfc.webfactional.com/data/degree_days.pkl).  See the [GitHub project update-degree-days](https://github.com/alanmitchell/update-degree-days) for more
  information on creation and updating of this file.
* `Other_Building_Data.xlsx` is split into two files now: `Buildings.xlsx` and `Services.xlsx`;  `Services.xlsx` contains info about all service types, including a new column that maps each   service to a standard category.  The ARIS script automatically creates the `Buildings.xlsx`
  file, as all that info is stored in ARIS.
* New graphs are included that compare each building's ECI, EUI and EUI/HDD to the
  10-90th percentile spread of other buildings of its same type and same organziation.
* Additional fuel types were added including Propane, Wood, Coal, and Hot Water District Heat.
* In order to accommodate different spelling of Services in the ARIS data, all services are
  mapped into standard service categories.  Different spellings of Units are accomodated by
  having a customizable `Services.xlsx` file that listing all Service/Unit combinations
  and their BTU contents.
