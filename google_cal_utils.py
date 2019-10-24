
from apiclient.discovery import build
from httplib2 import Http
#from oauth2client import file, client, tools
from google.oauth2 import service_account
import rfc3339

from pythonrfc3339 import parse_datetime, parse_date#, datetime_re, make_re, UTC_TZ, date_re_str, time_re_str, date_re
import datetime
import pytz

import logging

#from heatmisercontroller import stats_defn

def rfc339formant(inputdate):
    return rfc3339.format(inputdate, utc=True, use_system_timezone=False)

class gcal_processor(object):
    # Setup the Calendar API
    residency_states = ['AWAY','HOME','IGNORE']
    users = ['IAN','IZZY','GUEST']
    timeMin = None
    timeMax = None
    service = None
    calendarAccess = {}

    def __init__(self, scope, cred_file):
        self.scope = scope
        self.cred_file = cred_file
        #self.client_file = client_file

        self.localzone = pytz.timezone('Europe/London')

    def connect_google(self):
        creds = service_account.Credentials.from_service_account_file(self.cred_file, scopes=[self.scope])
        self.service = build('calendar', 'v3', credentials=creds)
        return self.service

    def set_start_time_midnight_local(self):
        #set the start time for the results of interest
        #any events starting after or finishing after this time will be included in results
        now = datetime.datetime.now()
        self.setuptime = now
        midnight_without_tzinfo = datetime.datetime(year=now.year, month=now.month, day=now.day)
        midnight_with_tzinfo = self.localzone.localize(midnight_without_tzinfo)
        self.start_time = midnight_with_tzinfo.astimezone(pytz.utc) #start of today from local time, in UTC

        return self.start_time

    def set_search_time_range(self,days_before,days_after):
        #set the timeMin and timeMax when getting data from the calendar.
        #input in days
        self.days_before = days_before
        self.days_after = days_after
        
        self.timeMin = rfc339formant(self.start_time + datetime.timedelta(days=-days_before) )
        self.timeMax = rfc339formant(self.start_time + datetime.timedelta(days=days_after) )

    def _get_events_list(self, calendar_id):
        if (not self.timeMin == None and not self.timeMax == None and not self.service == None):
            return self.service.events().list(calendarId=calendar_id, timeMin=self.timeMin,
                                                                                timeMax=self.timeMax,
                                                                                maxResults=200, singleEvents=True,
                                                                                orderBy='startTime').execute()
        else:
            logging.error("Times or service note connected.")
            
    def _record_calendar_access_time(self, calendar_id, event_list_results):
        """Records calendar access time against calendar_id
        Array contains, summary and updated entires from event list and query time as now."""
        self.calendarAccess[calendar_id] = {'name':event_list_results.get('summary'),'lastUpdated':event_list_results.get('updated'),'lastQueried':datetime.datetime.now()}
        
        logging.info("Calender %s queried at %s, and last updated %s" % (event_list_results.get('summary'),datetime.datetime.now().strftime("%m-%d %H:%M"), event_list_results.get('updated')))
        
    DEFAULT_REMINDER_TIME = 20
    MAXIMUM_REMINDER_TIME = 120
    USE_REMINDERS = True #if true extends start of events by the reminder time.
    TIME_TO_GET_HOME = 20
    
    def get_last_calendar_update_time(self):
        
        dates = [self._parse_google_dateortime(x['lastUpdated']) for _, x in self.calendarAccess.iteritems()]
        return max(dates)
        
    def get_last_calendar_poll_time(self):
        
        dates = [x['lastQueried'] for _, x in self.calendarAccess.iteritems()]
        return max(dates)

    def _get_shortest_reminder_time(self, reminder_list):
        """If there are multiple reminders select the closest to the event start. Subject to a maximum reminder time.
        If there are no remindaers set use default.
        
        Use shortest reminder, assuming the last is the one that relates to leaving house."""
        if len(reminder_list) == 0:
            return self.DEFAULT_REMINDER_TIME
        else:
            reminder_time = self.MAXIMUM_REMINDER_TIME
            for rem in reminder_list:
                reminder_time = min(reminder_time, rem['minutes'])
            return reminder_time
            
    def _parse_google_dateortime(self, inputdatetime):
        """Try parsing as a datetime, otherwise try parsing as a date."""
        try:
            return parse_datetime(inputdatetime)
        except ValueError:
            date = parse_date(inputdatetime)
            return self.localzone.localize(datetime.datetime(date.year, date.month, date.day))
    
    def get_calendar_events(self, calendar_id, default_user_list=None):
        """Get events from a calendar, filtering, extending by reminders and processing for state.
        Returns list of dictionaries"""
        #assume that we record actual time of the event and that reminder is set to trigger user to leave house.
        #gets the events from a calendar extending by reminder time forwards and a default afterwards.
        #users default user list if no list included in name.

        events_result = self._get_events_list(calendar_id)
        
        calendar_name = events_result.get('summary')
        logging.debug('Getting events from ' + calendar_name)
             
        self._record_calendar_access_time(calendar_id,events_result)
        default_reminder_time = self._get_shortest_reminder_time(events_result.get('defaultReminders'))

        events = events_result.get('items', [])
        event_list = []
        
        if not events:
            logging.info('%s No upcoming events found.'%calendar_id)
        for event in events:
            start = self._parse_google_dateortime(event['start'].get('dateTime', event['start'].get('date')))
            end = self._parse_google_dateortime(event['end'].get('dateTime', event['end'].get('date')))
            
            # process any reminders, considering defaults, etc.
            if self.USE_REMINDERS:
                if event['reminders']['useDefault']:
                    reminder = default_reminder_time
                elif 'overriders' in event['reminders']:
                    reminder = self._get_shortest_reminder_time(event['reminders']['overrides'])
                else:
                    reminder = self.DEFAULT_REMINDER_TIME
                    
                start -= datetime.timedelta(minutes=reminder)

            end += datetime.timedelta(minutes=self.TIME_TO_GET_HOME)

            length = end - start
            summary = event['summary']

            ##Residency
            
            if ( self.start_time < end ): #ignore entries that finished before start of today.
                
                    matching_states = [s for s in self.residency_states if s in summary.upper()]
                    matching_users = [s for s in self.users if s in summary.upper()]

                    if len(matching_states) <= 1: #only process if less than two states, otherwise warn
                        if len(matching_users) == 0: #if doesn't have any users attach default
                            matching_users = default_user_list
                        if len(matching_states) == 1: print "ddd", len(matching_states) == 1, not matching_states[0] == 'IGNORE'
                        if len(matching_states) == 1 and not matching_states[0] == 'IGNORE': #if it has a state record this.
                            event_list.append({
                                                                'start': start,
                                                                'end': end,
                                                                'summary': summary,
                                                                'length': length,
                                                                'state': matching_states[0],
                                                                'users': matching_users,
                                                                'calendar_name': calendar_name
                                                                })
                            logging.debug("%s %s %s %s %s %s"%(start.isoformat(), end.isoformat(), summary, length, matching_states[0], matching_users))
                        elif len(matching_states) == 0 and length < datetime.timedelta(days=1) : #if no state and shorter than 24 hours then treat as OUT.
                            event_list.append({
                                                                'start': start,
                                                                'end': end,
                                                                'summary': summary,
                                                                'length': length,
                                                                'state': 'OUT',
                                                                'users': matching_users,
                                                                'calendar_name': calendar_name
                                                                })
                            logging.debug("%s %s %s %s %s %s"%(start.isoformat(), end.isoformat(), summary, length, 'OUT', matching_users))
                        else:
                            logging.debug("%s %s %s DROPPED"%(start.isoformat(), end.isoformat(), summary))
                    else:
                        logging.warn("Calendar event, issue with to many states")
                        
        event_list.sort(key=lambda x:x['start'])
        return event_list
        
    def get_users_events(self, params, events_joint):
        """Get all the events for a user."""
        events = self.get_calendar_events(params['calendar_id'], [params['name']])
        events_work = self.get_calendar_events(params['calendar_id_work'], [params['name']])
        
        combined_list = self.combine_event_lists(self.filter_events(events_joint,params['name']),events)
        
        events_awake = self.get_awake_events(events_work,combined_list,params,self.start_time, 10)
        
        combined_list = self.combine_event_lists(events_awake, combined_list, events_work)

        logging.debug("merged %s user list"%params['name'])
        for i in combined_list:
            user_lst = ', '.join(i['users'])
            logging.debug('%s %s %s %s %s, %s'%(i['start'].astimezone(ukest).strftime("%m-%d %H:%M"), i['end'].astimezone(ukest).strftime("%m-%d %H:%M"), i['state'].ljust(5), user_lst,i['calendar_name'].ljust(10), i['summary'] ))
        
        return combined_list

    def combine_event_lists(self, *args):
        """combines multiple lists of events and sorts by start time and merges overlapping events with same state."""
        flat_list = [item for sublist in args for item in sublist]
        flat_list.sort(key=lambda x:x['start'])
        return self.merge_events(flat_list)
    
    @staticmethod
    def filter_events(events, user):
        #takes a list of events and filters for a single user
        #returns only single user in result
        new_list = []
        for event in events:
            if user in event['users']:
                event['users'] = [user]
                new_list.append(event)

        return new_list
    
    @staticmethod
    def merge_events(events):
        """takes a sorted (by start time) event list and merges any overlapping or touching events with the same state."""
        new_list = [events[0]]
        for i in range(1,len(events)):
            if events[i]['state'] == new_list[-1]['state'] and events[i]['users'] == new_list[-1]['users']:
                if events[i]['start'] > new_list[-1]['end']: #if starts after end of recorded event
                    new_list.append(events[i])
                elif events[i]['end'] > new_list[-1]['end']: #if not inside recorded event
                    new_list[-1]['end'] = events[i]['end']
            else:
                new_list.append(events[i])
                    
        return new_list
    
    def get_awake_events(self, events_work, other_events, params, timeMidnight, number_of_days):
        #takes a set of events from a calendar
        #filters b length less than a day and assess each day.
        #returns list of AWAKE events.
        events_awake = []
        
        baseevent = {'state':"AWAKE",'users':[params['name']],'summary':'','calendar_name':'Process'}
                                    
        for shift_day in range(0,number_of_days):

            start_datetime = timeMidnight + datetime.timedelta(days=shift_day)
            end_datetime = timeMidnight +    datetime.timedelta(days=shift_day+1)
            #print(start_datetime, " until ", end_datetime)
            #current_date = current_datetime.date()
            #00:00 is part of the day 00:01 and not the day before
            shifts_complete = [elem for elem in events_work if elem['length'] < datetime.timedelta(days=1) and elem['start'] >= start_datetime and elem['end'] < end_datetime]
            shifts_starting = [elem for elem in events_work if elem['length'] < datetime.timedelta(days=1) and elem['start'] >= start_datetime and elem['start'] < end_datetime and elem['end'] >= end_datetime]
            shifts_ending = [elem for elem in events_work if elem['length'] < datetime.timedelta(days=1) and elem['start'] < start_datetime and elem['end'] >= start_datetime and elem['end'] < end_datetime]
            
            #find ends or starts today, and the highest and lowest
            events_today = [elem for elem in other_events if elem['length'] < datetime.timedelta(days=1) and (elem['start'] >= start_datetime and elem['start'] < end_datetime or elem['end'] >= start_datetime and elem['end'] < end_datetime)]
            if len(events_today) > 0:
                start_events_today = min([elem['start'] for elem in events_today])
                stop_events_today = max([elem['end'] for elem in events_today])
            else:
                start_events_today = end_datetime
                stop_events_today = start_datetime
                
            
            number_of_shifts = [len(shifts_complete),len(shifts_starting), len(shifts_ending)]
            #print(number_of_shifts)
            
            if number_of_shifts == [1, 0, 0]:
                #print ("day shift")
                event = baseevent.copy()
                event['start'] = min(start_datetime + params['default_wake'],
                                                                                             min(shifts_complete[0]['start'],start_events_today) - params['minimum_wake_before_event'])
                event['end'] = max(start_datetime + params['default_sleep'],
                                                                                             max(shifts_complete[0]['end'],stop_events_today) + params['minimum_wake_after_event'])
                #print(event)
                events_awake.append(event)
                
            elif number_of_shifts == [0, 1, 1]:
                #print ("night to night")
                event = baseevent.copy()
                event['start'] = start_datetime
                event['end'] = shifts_ending[0]['end'] + params['minimum_wake_after_event']
                events_awake.append(event)
                event = baseevent.copy()
                event['start'] = min(shifts_starting[0]['start'] - params['minimum_wake_before_event'],
                                                                                                shifts_ending[0]['end'] + params['minimum_wake_after_event'] + params['sleep_night_to_night'])
                event['end'] = end_datetime
                events_awake.append(event)
                
            elif number_of_shifts == [0, 1, 0]:
                #print ("night starting")
                event = baseevent.copy()
                event['start'] = min(start_datetime + params['default_wake'], start_events_today - params['minimum_wake_before_event'])
                event['end'] = shifts_starting[0]['start'] - params['minimum_wake_before_event'] - params['sleep_before_night']
                events_awake.append(event)
                event = baseevent.copy()
                event['start'] = shifts_starting[0]['start'] - params['minimum_wake_before_event']
                event['end'] = end_datetime
                events_awake.append(event)
                
            elif number_of_shifts == [0, 0, 1]:
                #print ("night ending")
                event = baseevent.copy()
                event['start'] = start_datetime
                event['end'] = shifts_ending[0]['end'] + params['minimum_wake_after_event'] +    params['sleep_after_night']
                events_awake.append(event)
                event = baseevent.copy()
                event['start'] = shifts_ending[0]['end'] + params['default_sleep']
                event['end'] = max(start_datetime + params['default_sleep'], stop_events_today + params['minimum_wake_after_event'])
                events_awake.append(event)
            else:
                if number_of_shifts != [0, 0, 0]:
                    logging.warn("confused")
                #else:
                    #print ("no shift")
                event = baseevent.copy()
                event['start'] = min(start_datetime + params['default_wake'], start_events_today - params['minimum_wake_before_event'])
                event['end'] = max(start_datetime + params['default_sleep'], stop_events_today + params['minimum_wake_after_event'])
                events_awake.append(event)
                
        return self.merge_events(events_awake)

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
    if number == None:
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
        else: #if the time between two events to short, move the later temp forwards (note this also lets through if new temp is same as last, but does no harm
            if len(temps) > 1: #if only one temp don't check for doubles
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
     if dt == None : dt = datetime.datetime.now()
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

ukest = pytz.timezone('Europe/London')

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
            while filtered == None or len(filtered) > MAXIMUM_STATES_PER_STAT:
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

    