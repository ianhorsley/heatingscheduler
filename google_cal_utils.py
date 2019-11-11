
import datetime

import logging

#from heatmisercontroller import stats_defn

from google_cal_connector import GoogleConnector

class gcal_processor(object):
    # Setup the Calendar API
    residency_states = ['AWAY','HOME','IGNORE']
    users = ['IAN','IZZY','GUEST']
    timeMin = None
    timeMax = None
    service = None

    def __init__(self, scope, cred_file):
        self.connector = GoogleConnector(scope, cred_file)
        
    DEFAULT_REMINDER_TIME = 20
    MAXIMUM_REMINDER_TIME = 120
    USE_REMINDERS = True #if true extends start of events by the reminder time.
    TIME_TO_GET_HOME = 20
    
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
    
    def get_calendars_events(self, calendar_id_list, user=None):
        """Get events from multiple calendars, combining and filtering.
        Returns list of dictionaries"""
        combined_list = {}
        for calendar_id in calendar_id_list:
            events = self.get_calendar_events(calendar_id, user)
            eventsfiltered = self.filter_events(events, user)
            combined_list = self.combine_event_lists(combined_list, eventsfiltered)
        return combined_list
    
    def get_calendar_events(self, calendar_id, default_user=None):
        """Get events from a calendar, filtering, extending by reminders and processing for state.
        Returns list of dictionaries"""
        #assume that we record actual time of the event and that reminder is set to trigger user to leave house.
        #gets the events from a calendar extending by reminder time forwards and a default afterwards.
        #users default user list if no list included in name.

        events_result = self.connector.get_events_list(calendar_id)
        
        calendar_name = events_result.get('summary')
        logging.debug('Getting events from ' + calendar_name)

        default_reminder_time = self._get_shortest_reminder_time(events_result.get('defaultReminders'))

        events = events_result.get('items', [])
        event_list = []
        
        if not events:
            logging.info('%s No upcoming events found.'%calendar_id)
        for event in events:
            start = self.connector.parse_google_dateortime(event['start'].get('dateTime', event['start'].get('date')))
            end = self.connector.parse_google_dateortime(event['end'].get('dateTime', event['end'].get('date')))
            
            # process any reminders, considering defaults, etc.
            if self.USE_REMINDERS:
                if 'reminders' not in event or event['reminders']['useDefault']:
                    reminder = default_reminder_time
                elif 'overriders' in event['reminders']:
                    reminder = self._get_shortest_reminder_time(event['reminders']['overrides'])
                else:
                    reminder = self.DEFAULT_REMINDER_TIME
                    
                start -= datetime.timedelta(minutes=reminder)

            end += datetime.timedelta(minutes=self.TIME_TO_GET_HOME)

            length = end - start
            summary = event['summary'] if 'summary' in event else 'unlabelled'

            ##Residency
            
            if ( self.connector.start_time < end ): #ignore entries that finished before start of today.
                
                    matching_states = [s for s in self.residency_states if s in summary.upper()]
                    matching_users = [s for s in self.users if s in summary.upper()]

                    if len(matching_states) <= 1: #only process if less than two states, otherwise warn
                        if len(matching_users) == 0: #if doesn't have any users attach default
                            matching_users = default_user
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
        
    def get_users_events(self, params):
        """Get all the events for a user."""

        events = self.get_calendars_events(params['calendar_id_list'], params['name'])

        events_work = self.get_calendar_events(params['calendar_id_work'], params['name'])

        events_awake = self.get_awake_events(events_work, events, params, self.connector.start_time, 10)

        combined_list = self.combine_event_lists(events_awake, events, events_work)

        logging.debug("merged %s user list"%params['name'])

        for i in combined_list:
            user_lst = ', '.join(i['users'])
            logging.debug('%s %s %s %s %s, %s'%(i['start'].astimezone(self.connector.localzone).strftime("%m-%d %H:%M"),
                                            i['end'].astimezone(self.connector.localzone).strftime("%m-%d %H:%M"),
                                            i['state'].ljust(5),
                                            user_lst,i['calendar_name'].ljust(10),
                                            i['summary'] ))
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
        if len(events) < 2:
            return events
        
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

