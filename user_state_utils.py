import datetime
import pytz

import logging

ukest = pytz.timezone('Europe/London')

def get_users_states(event_list, params, statlist):
    #tasks full list of events (sorting not important) for a user.
    #Converts to a trigger list (sorted)
    #Converts to state list (handling an overlapping) including temperatures

    trigger_list = []
    for event in event_list:
        trigger_list.append({'time':event['start'],'state':event['state'],'trigger':1})
        trigger_list.append({'time':event['end'],'state':event['state'],'trigger':-1})
        if event['state'] == 'AWAKE':
            trigger_list.append({'time':event['start'],'state':'ACTIVE_SLEEP_ROOM','trigger':1})
            trigger_list.append({'time':event['start'] + params['active_time_sleep_room'],'state':'ACTIVE_SLEEP_ROOM','trigger':-1})
            trigger_list.append({'time':event['end'] - params['active_time_sleep_room'],'state':'ACTIVE_SLEEP_ROOM','trigger':1})
            trigger_list.append({'time':event['end'],'state':'ACTIVE_SLEEP_ROOM','trigger':-1})
        elif event['state'] == 'HOME':
            trigger_list.append({'time':event['start'],'state':'ACTIVE','trigger':1})
            trigger_list.append({'time':event['start'] + params['active_time'],'state':'ACTIVE','trigger':-1})
            trigger_list.append({'time':event['end'] - params['active_time'],'state':'ACTIVE','trigger':1})
            trigger_list.append({'time':event['end'],'state':'ACTIVE','trigger':-1})
        elif event['state'] == 'OUT' or event['state'] == 'AWAY':
            trigger_list.append({'time':event['start'] - params['active_time'],'state':'ACTIVE','trigger':1})
            trigger_list.append({'time':event['start'],'state':'ACTIVE','trigger':-1})
            trigger_list.append({'time':event['end'],'state':'ACTIVE','trigger':1})
            trigger_list.append({'time':event['end'] + params['active_time'],'state':'ACTIVE','trigger':-1})

    trigger_list.sort(key=lambda x:x['time'])

    temp = {}
    temp['name'] = params['name']
    temp['HOME'] = temp['AWAY'] = temp['OUT'] = temp['AWAKE'] = temp['ACTIVE'] = temp['ACTIVE_SLEEP_ROOM'] = 0
    temp['user'] = 'SLEEP'
    temp['inuse_room'] = temp['sleep_room'] = None
    #print(statlist)
    for name, _ in statlist.iteritems():
        temp[name] = None

    state_list = []
    for trigger in trigger_list:
        temp[trigger['state']] += trigger['trigger']
        temp['time'] = trigger['time']

        if temp['HOME'] > 0:
            temp_resident = 'HOME'
        elif temp['AWAY'] > 0 or temp['OUT'] > 0:
            temp_resident = 'AWAY'
        else:
            temp_resident = params['default_residency']

        if temp_resident == 'AWAY':
            temp['user'] = 'AWAY'
            temp['inuse_room'] = None
            temp['sleep_room'] = None
        elif temp['AWAKE'] == 0:
            temp['user'] = 'SLEEP'
            temp['inuse_room'] = None
            temp['sleep_room'] = params['temp_asleep']
        elif temp['ACTIVE_SLEEP_ROOM'] > 0:
            temp['user'] = 'ACTIVE_SLEEP_ROOM'
            temp['inuse_room'] = params['temp_active']
            temp['sleep_room'] = params['temp_active']
        elif temp['ACTIVE'] > 0:
            temp['user'] = 'ACTIVE'
            temp['inuse_room'] = params['temp_active']
            temp['sleep_room'] = None
        else:
            temp['user'] = 'INACTIVE'
            temp['inuse_room'] = params['temp_inactive']
            temp['sleep_room'] = None

        for room in params['awake_rooms']:
            temp[room] = temp['inuse_room']

        if params['sleep_room'] in params['awake_rooms']:
            temp[params['sleep_room']] = max(temp['sleep_room'], temp['inuse_room'])
        else:
            temp[params['sleep_room']] = temp['sleep_room']
        
        if len(state_list) == 0 or (temp['time'] != state_list[-1]['time'] and temp['user'] != state_list[-1]['user']):
            state_list.append(temp.copy())
        elif temp['user'] != state_list[-1]['user']:
            state_list[-1] = temp.copy()
         
    logging.debug("merged %s state list"%params['name'])
    for i in state_list:
        stat_temps = ' '.join(stringN(i[e]) for e, _ in statlist.iteritems())
        logging.debug( '%s %s, %s %s, %s other %i %i %i %i %i %i' % (i['time'].astimezone(ukest).strftime("%m-%d %H:%M"), i['user'].ljust(17), stringN(i['inuse_room']), stringN(i['sleep_room']), stat_temps, i['HOME'], i['AWAY'], i['OUT'], i['AWAKE'], i['ACTIVE'], i['ACTIVE_SLEEP_ROOM']) )

    return state_list

def stringN(number):
    if number is None:
        return " N"
    return str(number)

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
            #else, the time between two events to short, move the later temp forwards (note this also lets through if new temp is same as last, but does no harm
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
