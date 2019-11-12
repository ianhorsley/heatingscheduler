
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
            combined_list = self.combine_event_lists(combined_list, events)
        return combined_list
    
    def get_calendar_events(self, calendar_id, user=None):
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
                            matching_users = user
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
        
        if user is None:
            return event_list
        else:
            return self.filter_events(event_list, user)

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
                    new_list[-1]['summary'] += "/" + events[i]['summary']
                    new_list[-1]['calendar_name'] += "/" + events[i]['calendar_name']
            else:
                new_list.append(events[i])
                    
        return new_list

    @staticmethod
    def _in_range(value, bottom, top):
        return value >= bottom and value < top
    
    @staticmethod
    def _create_event(usernames, start, end):
        baseevent = {'state':"AWAKE",'summary':'','calendar_name':'Process'}
        baseevent['users'] = usernames
        baseevent['start'] = start
        baseevent['end'] = end
        return baseevent
        
    def _day_shift_events(self, shifts, times, params):
        #create awake event for a day shift
        event_start = min(times['start'] + params['default_wake'],
                                        min(shifts['complete'][0]['start'],times['start_events_today']) - params['minimum_wake_before_event'])
        event_end = max(times['start'] + params['default_sleep'],
                                        max(shifts['complete'][0]['end'],times['stop_events_today']) + params['minimum_wake_after_event'])
        return [self._create_event([params['name']], event_start, event_end)]

    def _night_to_night_events(self, shifts, times, params):
        #create awake events day with end of night shift and start of another
        event_end = shifts['ending'][0]['end'] + params['minimum_wake_after_event']
        event1 = self._create_event([params['name']], times['start'], event_end)

        event_start = min(shifts['starting'][0]['start'] - params['minimum_wake_before_event'],
                                shifts['ending'][0]['end'] + params['minimum_wake_after_event'] + params['sleep_night_to_night'])
        event2 = self._create_event([params['name']], event_start, times['end'])
        return [event1, event2]

    def _night_starting_events(self, shifts, times, params):
        #create awake event day with start of night shift
        event_start = min(times['start'] + params['default_wake'], times['start_events_today'] - params['minimum_wake_before_event'])
        event_end = shifts['starting'][0]['start'] - params['minimum_wake_before_event'] - params['sleep_before_night']
        event1 = self._create_event([params['name']], event_start, event_end)
        event_start = shifts['starting'][0]['start'] - params['minimum_wake_before_event']
        event2 = self._create_event([params['name']], event_start, times['end'])
        return [event1, event2]

    def _night_ending_events(self, shifts, times, params):
        #create awake event day with end of night shift
        event_end = shifts['ending'][0]['end'] + params['minimum_wake_after_event'] +    params['sleep_after_night']
        event1 = self._create_event([params['name']], times['start'], event_end)
        event_start = shifts['ending'][0]['end'] + params['default_sleep']
        event_end = max(times['start'] + params['default_sleep'], times['stop_events_today'] + params['minimum_wake_after_event'])
        event2 = self._create_event([params['name']], event_start, event_end)
        return [event1, event2]

    def _no_shift_events(self, shifts, times, params):
        #create awake event for a day shift
        if (len(shifts['complete']),len(shifts['starting']), len(shifts['ending'])) != (0, 0, 0):
            logging.warn("confused")
        event_start = min(times['start'] + params['default_wake'], times['start_events_today'] - params['minimum_wake_before_event'])
        event_end = max(times['start'] + params['default_sleep'], times['stop_events_today'] + params['minimum_wake_after_event'])
        return [self._create_event([params['name']], event_start, event_end)]

    def get_awake_events(self, events_work, events_other, params, timeMidnight, number_of_days):
        #takes a set of events from a calendar
        #filters b length less than a day and assess each day.
        #returns list of AWAKE events.
        events_awake = []
        shifts = {}
        times = {}
        shift_types = {
            (1, 0, 0): self._day_shift_events,
            (0, 1, 1): self._night_to_night_events,
            (0, 1, 0): self._night_starting_events,
            (0, 0, 1): self._night_ending_events
            }

        events_work_short = [elem for elem in events_work if elem['length'] < datetime.timedelta(days=1)] #filter length less 1 day
        events_other_short = [elem for elem in events_other if elem['length'] < datetime.timedelta(days=1)]
        
        for shift_day in range(0,number_of_days):

            start_time = times['start'] = timeMidnight + datetime.timedelta(days=shift_day)
            end_time = times['end'] = timeMidnight + datetime.timedelta(days=shift_day+1)
            #print(times['start'], " until ", times['end'])

            #find ends or starts today, and the highest and lowest
            events_today = [elem for elem in events_other_short if self._in_range(elem['start'], start_time, end_time) or self._in_range(elem['end'], start_time, end_time)]
            if len(events_today) > 0:
                times['start_events_today'] = min([elem['start'] for elem in events_today])
                times['stop_events_today'] = max([elem['end'] for elem in events_today])
            else:
                times['start_events_today'] = end_time
                times['stop_events_today'] = start_time

            #00:00 is part of the day 00:01 and not the day before
            shifts['complete'] = [elem for elem in events_work_short if elem['start'] >= start_time and elem['end'] < end_time]
            shifts['starting'] = [elem for elem in events_work_short if self._in_range(elem['start'], start_time, end_time) and elem['end'] >= end_time]
            shifts['ending'] = [elem for elem in events_work_short if elem['start'] < start_time and self._in_range(elem['end'], start_time, end_time)]
            number_of_shifts = (len(shifts['complete']),len(shifts['starting']), len(shifts['ending']))

            # Get the function from shift type dictionary
            shift_events = shift_types.get(number_of_shifts, self._no_shift_events)
            events_awake.extend(shift_events(shifts, times, params))

        return self.merge_events(events_awake)
