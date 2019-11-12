import datetime
import pytz

import logging

from user import User
from state_list import StateList

ukest = pytz.timezone('Europe/London')

def calc_event_triggers(start, end, state):
    #creates a start and end trigger for event.
    #trigger is a dictionary of time, state and trigger count
    #1 means entry to state and -1 leaving state.
    return [{'time':start,'state':state,'trigger':1},
        {'time':end,'state':state,'trigger':-1}]

def build_trigger_list(event_list, params):
    #creates a list of trigger events for the start and end of each state type from event list.
    #returns list of triggers
    trigger_list = []
    for event in event_list:
        #create triggers for the start and end of each event
        trigger_list.extend(calc_event_triggers(event['start'],event['end'],event['state']))
        #add some additional temperatures around events
        if event['state'] == 'AWAKE':
            trigger_list.extend(calc_event_triggers(event['start'],event['start'] + params['active_time_sleep_room'],'ACTIVE_SLEEP_ROOM'))
            trigger_list.extend(calc_event_triggers(event['end'] - params['active_time_sleep_room'],event['end'],'ACTIVE_SLEEP_ROOM'))
        elif event['state'] == 'HOME':
            trigger_list.extend(calc_event_triggers(event['start'],event['start'] + params['active_time'],'ACTIVE'))
            trigger_list.extend(calc_event_triggers(event['end'] - params['active_time'],event['end'],'ACTIVE'))
        elif event['state'] == 'OUT' or event['state'] == 'AWAY':
            trigger_list.extend(calc_event_triggers(event['start'] - params['active_time'],event['start'],'ACTIVE'))
            trigger_list.extend(calc_event_triggers(event['end'],event['end'] + params['active_time'],'ACTIVE'))

    trigger_list.sort(key=lambda x:x['time'])
    
    return trigger_list

def get_users_states(event_list, params, statlist):
    #takes full list of events (sorting not important) for a user.
    #Converts to a trigger list (sorted)
    #Converts to state list (handling an overlapping) including temperatures

    trigger_list = build_trigger_list(event_list, params) #convert events to list of starts/ends

    user = User(params, statlist) #create a user with rooms temps, etc.
    
    #temp = {'username': params['name']}
    state_list = StateList(params['name'])

    for trigger in trigger_list:
        user.apply_trigger(trigger) #update the rooms temps, etc. based on state changes.

        #temp['counters'] = user.state_counters.copy() #store counters in temp
        #temp['roomtemps'] = user.roomtemps.copy() #store room temps in temp
        #temp['state'] = user.current_state
        #temp['inuse_room'] = user.inuse_room_temp
        #temp['sleep_room'] = user.sleep_room_temp
        
        state_list.add_user_state(user)

    logging.debug("merged %s state list"%params['name'])
    state_list.print_user_debug(statlist)

    return state_list

MINIMUM_TIME_AT_TEMP = 15 #in minutes

def select_temperatures(state_list,temp_name):
    #pulls out the temperature data for a room.
    #filters out where two temps the same
    #or if time difference is less than MINIMUM_TIME_AT_TEMP moves temperature forwards
    temps = []
    temp = {}
    temp['time'] = temp['temp'] = 0

    for state in state_list:
        temp['time'] = state['time']
        temp['temp'] = state[temp_name]

        if len(temps) == 0 or (temp['temp'] != temps[-1]['temp'] and temp['time'] >= temps[-1]['time'] + datetime.timedelta(minutes=MINIMUM_TIME_AT_TEMP)):
            temps.append(temp.copy())
        elif len(temps) > 1:
            #else, the time between two events to short,
            #move the later temp forwards (note this also lets through if new temp is same as last, but does no harm
            #but if only one temp don't check for doubles
            if temps[-2]['temp'] != temp['temp']:
                temps[-1]['temp'] = temp['temp']
            else: #remove entries that would have matching temps
                del temps[-1]

    return temps

def roundTime(dt=None, roundTo=60):
     """Round a datetime object to any time laps in seconds
     dt : datetime.datetime object, default now.
     roundTo : Closest number of seconds to round to, default 1 minute.
     Author: Thierry Husson 2012 - Use it as you want but don't blame me.
     """
     if dt is None : dt = datetime.datetime.now()
     seconds = (dt.replace(tzinfo=None) - dt.min).seconds
     rounding = (seconds+roundTo/2) // roundTo * roundTo
     return dt + datetime.timedelta(0, rounding-seconds,-dt.microsecond)

def roundToNearestInt(inputnumber, nearest):
    return int(round(inputnumber/nearest, 0) * nearest)

MAXIMUM_STATES_PER_STAT = 4
MAXIMUM_DAYS_PER_STAT = 7
TIME_GRANULARITY = 15 #minutes
TEMP_GRANULARITY = 1 #degrees
START_TEMP_RANGE = 1
STEP_TEMP_RANGE = 0.5
START_MINUTES_RANGE = 30
STEP_MINUTES_RANGE = 30

def filter_temperatures_for_stat(state_list,timeStart):

    state_list = reduce_temperatures_for_stat(state_list)

    endoftime = timeStart + datetime.timedelta(days=MAXIMUM_DAYS_PER_STAT)

    return [{'time':roundTime(x['time'],60*TIME_GRANULARITY),'temp':roundToNearestInt(x['temp'],TEMP_GRANULARITY)} for x in state_list if x['time'] >= timeStart and x['time'] < endoftime]

def reduce_temperatures_for_stat(state_list):

    values = set(map(lambda x:x['time'].astimezone(ukest).date(), state_list))
    grouped_state_list = [[y for y in state_list if y['time'].astimezone(ukest).date()==x] for x in values]

    temps = []

    for group in grouped_state_list:
        if len(group) <= MAXIMUM_STATES_PER_STAT:
            #print("No filter needed", group[0])
            temps = temps + group
        else:
            #print("Filtering needed", group[0])
            #for i in group:
            #    print( i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['temp'])
            filtered = None
            temp_range = START_TEMP_RANGE
            minutes_range = START_MINUTES_RANGE
            while filtered is None or len(filtered) > MAXIMUM_STATES_PER_STAT:
                filtered = filter_temperatures_by_temp(group,temp_range,minutes_range)
                temp_range += STEP_TEMP_RANGE
                minutes_range += STEP_MINUTES_RANGE
                if (temp_range > 15):
                    logging.warn("WARNING LONG FILTERING")
            #print("after")
            #for i in filtered:
            #    print( i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['temp'])
            temps = temps + filtered

    temps.sort(key=lambda x:x['time'])
    return temps


def filter_temperatures_by_temp(state_list, temp_range, minutes_range):
    #pulls out the temperature data for a room.
    #filters out where two temps the same
    #or if time difference is less than MINIMUM_TIME_AT_TEMP moves temperature forwards
    temps = []
    temp = {}
    temp['time'] = temp['temp'] = 0

    for state in state_list:
        temp['time'] = state['time']
        temp['temp'] = state['temp']

        if len(temps) != 0 and abs(temps[-1]['temp'] - temp['temp']) <= temp_range:
            temps[-1]['temp'] = max(temp['temp'],temps[-1]['temp']) #should improve on and make a weighted average or something more complex.
        elif len(temps) > 1 and abs(temps[-2]['temp'] - temp['temp']) <= temp_range and temp['time'] - temps[-2]['time']    <= datetime.timedelta(minutes=minutes_range):
            del temps[-1]
            temps[-1]['temp'] = max(temp['temp'],temps[-1]['temp'])
        else:
            temps.append(temp.copy())

    return temps
