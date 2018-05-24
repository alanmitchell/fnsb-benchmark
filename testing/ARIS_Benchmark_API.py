
# coding: utf-8

# In[1]:

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests

get_ipython().magic(u'matplotlib inline')


# In[2]:

import json


# In[3]:

my_username = 'buildingenergyapp'
my_password = 'buildingenergyappTest1!'


# In[4]:

test_url = 'http://arisapi.test.ahfc.us/api/buildingenergy'


# In[5]:

building_list = '/GetBuildingList'
building_energy_detail = '/GetBuildingEnergyDetail'


# In[6]:

my_params = {'username': my_username,
             'password':my_password}


# In[7]:

building_list_url = test_url + building_list
building_energy_url = test_url + building_energy_detail


# In[8]:

req = requests.post(building_list_url, params=my_params)
results = json.loads(req.text)
results


# In[65]:

building_list_results = pd.DataFrame(results)
building_list_results.head()


# In[66]:

building_list_results.to_csv("aris_building_information.csv")


# In[9]:

building_ids = []
for i in np.arange(len(results)):
    building_ids.append(results[i]['BuildingId'])
    
print (len(building_ids))
print (building_ids)


# In[10]:

# Check to see if each of these IDs are unique
unique_building_ids = set(building_ids)
print (len(unique_building_ids))


# In[11]:

print (building_energy_url)


# In[12]:

my_headers = {'Accept':'application/json'}
my_data = {'username': my_username,
           'password':my_password,
           'buildingId':44}

detail_req = requests.post(building_energy_url, data=my_data, headers=my_headers)
detail_results = json.loads(detail_req.text)
detail_results


# In[13]:

test_df = pd.DataFrame(detail_results)


# In[50]:

test_df


# In[15]:

test_df.iloc[0]['BuildingEnergyDetailList']


# In[49]:

results_list = []

for row in test_df.itertuples():
    results_list.append(pd.DataFrame([row[3]], columns=row[3].keys()))
    
    
results_df = pd.concat(results_list, axis=0, ignore_index=True)
results_df


# In[53]:

results_list = []

# Loop through all unique building ids obtained from ARIS API and get the 
# resulting data in a dataframe
for building_id in building_ids:
    my_headers = {'Accept':'application/json'}
    my_data = {'username': my_username,
               'password':my_password,
               'buildingId':building_id}
    
    detail_req = requests.post(building_energy_url, data=my_data, headers=my_headers)
    detail_results = json.loads(detail_req.text)
    api_results_df = pd.DataFrame(detail_results)
    
    # Loop through the dataframe and extract the monthly building energy results
    # and append them to a list
    for row in api_results_df.itertuples():
        results_list.append(pd.DataFrame([row[3]], columns=row[3].keys()))
        
# Concatenate the results from each building into one big dataframe
results_df = pd.concat(results_list, axis=0, ignore_index=True)
results_df


# In[54]:

results_df.to_csv("aris_benchmark_data_from_api.csv")


