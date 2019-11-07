#!/usr/bin/python
#
# Ian Horsley 2018

#
# Test out processing calendars
#
"""
Gets data from multiple Google Calendars through API.
Processes these events to find user precense and states.
User states converted into list of target temperatures per room.

Requirements on calendar entries
    Entries either must be less than 1 day in length or contain a state (AWAY, HOME) to be considered.
    Entries with state IGNORE are always ignored
    Entries with a name only apply to those names
    Assume that we record actual time of the event and that reminder is set to trigger user to leave house.
        A default extension is allowed afterwards to allow for the addtional time returning home.

User residency from joint calendar
    Entries in the joint calendar that contain a name or state (AWAY, HOME, IGNORE) have an impact on the residency
"""
from __future__ import print_function

import logging
# hm imports
from heatmisercontroller import logging_setup
logging_setup.initialize_logger('logs', logging.INFO, True)
from heatmisercontroller import setup as hms

import pytz
from user_defn import ian_params, izzy_params
from google_cal_utils import gcal_processor, get_users_states, select_temperatures, filter_temperatures_for_stat

# Setup the Calendar API
gcal = gcal_processor('https://www.googleapis.com/auth/calendar.readonly', 'service.json')
service = gcal.connect_google()

# Setup time variables
gcal.set_time_zone('Europe/London') # Not local server to house so set the local time zone
timeMidnight = gcal.set_start_time_midnight_local()
#now = gcal.setuptime
gcal.set_search_time_range(5,10) # Days before and days after today. Needs the history for events that started in the past.

# Get the list of rooms/zones from the stats on heatmiser network
try:
    hmsetup = hms.HeatmiserControllerFileSetup("hmcontroller.conf")
    settings = hmsetup.settings
except hms.HeatmiserControllerSetupInitError as err:
    logging.error(err)
    raise
statlist = settings['devices']

logging.info('Getting the upcoming events')

#process to find izzy states
combined_list = gcal.get_users_events(izzy_params)
z_state_list = get_users_states(combined_list, izzy_params, statlist)

#process to find ian states
combined_list = gcal.get_users_events(ian_params)
###Need to handle impact of each users wake states on each other. If close (say within 2 hours), take the earlier bed and sleep times.
a_state_list = get_users_states(combined_list, ian_params, statlist)

#combine users states
combined_state_list = z_state_list + a_state_list
combined_state_list.sort(key=lambda x:x['time'])

#process states into list of trigger times with temps for each room

temp = {}
temp['IAN'] = temp['IZZY'] = {'inuse_room':None,'sleep_room':None,'user':'Not Set'}
for name, controllersettings in statlist.iteritems():
  if controllersettings['control_mode'] == 'manual':
    temp[name] = controllersettings['frost_temperature']
  temp['IAN'][name] = None
  temp['IZZY'][name] = None

state_list = []
for trigger in combined_state_list:
  temp[trigger['name']] = trigger
  temp['time'] = trigger['time']

  for name, controllersettings in statlist.iteritems():
    if controllersettings['control_mode'] == 'auto':
      temp[name] = max(controllersettings['frost_temperature'],temp['IAN'][name],temp['IZZY'][name])

  if len(state_list) == 0 or temp['time'] != state_list[-1]['time']:
    state_list.append(temp.copy())
  else:
    state_list[-1] = temp.copy()

ukest = pytz.timezone('Europe/London')
logging.debug("room state tracking")
for i in state_list:
  logging.debug('%s %i %i %i %i other %s %s'% (i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['Kit'], i['B1'], i['B2'], i['Cons'], i['IAN']['user'].ljust(17), i['IZZY']['user'].ljust(17))   )

#filter room temperatures
kitchen_temps = select_temperatures(state_list,'Kit')
logging.debug('kitchen')
for i in kitchen_temps:
  logging.debug('%s %i'%( i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['temp']))



import xml.etree.ElementTree as ET

def createsublement(parent, item, text=None):
  subE = ET.SubElement(parent, item)
  if text != None:
    subE.text = text
  return subE

# create the file structure
data = ET.Element('data')
other = ET.SubElement(data, 'other')
createsublement(other, 'calendarslastupdated', gcal.get_last_calendar_update_time().astimezone(pytz.utc).isoformat())
createsublement(other, 'calendarslastpolled', gcal.get_last_calendar_poll_time().isoformat())

cals = ET.SubElement(data, 'calendars') #should contain list of calendars and last update time
for itemid, values in gcal.calendarAccess.iteritems():
  stat = ET.SubElement(cals, 'calendar')
  createsublement(stat, 'name', values['name'])
  createsublement(stat, 'id', itemid)
  createsublement(stat, 'lastUpdated', values['lastUpdated'])

stats = ET.SubElement(data, 'stats') #should contain list of stats and last update time, and entries required
for stat_name, controllersettings in statlist.iteritems():
#for stat in stats_defn.StatList:
  #stat_name = stat[stats_defn.SL_SHORT_NAME]
  stat = ET.SubElement(stats, 'stat')
  createsublement(stat, 'name', stat_name)
  createsublement(stat, 'lastchanged', 'timethatthedataforthisstatelastchanged')

  items = ET.SubElement(stat, 'targets')
  for temp in select_temperatures(state_list,stat_name):
    nextitem = ET.SubElement(items, 'target')
    nextitem.set('time',temp['time'].astimezone(pytz.utc).isoformat())
    nextitem.text = str(temp['temp'])

# create a new XML file with the results
mydata = ET.tostring(data)
myfile = open(outfilexml, "w")
myfile.write(mydata)

### following code for the processing code in myversion.
kitchen_schedule = filter_temperatures_for_stat(kitchen_temps, timeMidnight)

logging.debug('kitchen short list')
for i in kitchen_schedule:
  logging.debug('%s %i'%( i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['temp']))

#b1_temps = select_temperatures(state_list,'B1')
#print('B1')
#for i in b1_temps:
#  print( i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['temp'])     