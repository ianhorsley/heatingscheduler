"""Google Calendar Connector handles basic connection"""
import logging

from apiclient.discovery import build
from google.oauth2 import service_account

import pytz
import datetime
from pythonrfc3339 import parse_datetime, parse_date#, datetime_re, make_re, UTC_TZ, date_re_str, time_re_str, date_re
import rfc3339

def rfc339format(inputdate):
    return rfc3339.format(inputdate, utc=True, use_system_timezone=False)

class GoogleConnector(object):
    # Setup the Calendar API
    calendarAccess = {}
    localzone = None

    def __init__(self, scope, cred_file):
        self.scope = scope
        self.cred_file = cred_file
        #self.localzone = pytz.timezone('Europe/London')

    def connect_google(self):
        creds = service_account.Credentials.from_service_account_file(self.cred_file, scopes=[self.scope])
        self.service = build('calendar', 'v3', credentials=creds)
        return self.service

    def set_time_zone(self, timezonestring):
        #stores a local time zone, if the server processing this script isn't local to home being monitored^M
        self.localzone = pytz.timezone(timezonestring)

    def set_start_time_midnight_local(self):
        #set the start time for the results of interest
        #any events starting after or finishing after this time will be included in results
        if self.localzone is not None:
            now = datetime.datetime.now(self.localzone)
        else:
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

        self.timeMin = rfc339format(self.start_time + datetime.timedelta(days=-days_before) )
        self.timeMax = rfc339format(self.start_time + datetime.timedelta(days=days_after) )

    def get_events_list(self, calendar_id):
        if ( self.timeMin is not None and self.timeMax is not None and self.service is not None):
            events_result = self.service.events().list(calendarId=calendar_id, timeMin=self.timeMin,
                                                                                timeMax=self.timeMax,
                                                                                maxResults=200, singleEvents=True,
                                                                                orderBy='startTime').execute()
            self._record_calendar_access_time(calendar_id,events_result)
            return events_result
        else:
            logging.error("Times or service note connected.")

    def _record_calendar_access_time(self, calendar_id, event_list_results):
        """Records calendar access time against calendar_id
        Array contains, summary and updated entires from event list and query time as now."""
        self.calendarAccess[calendar_id] = {
                                        'name':event_list_results.get('summary'),
                                        'lastUpdated':event_list_results.get('updated'),
                                        'lastQueried':datetime.datetime.now()
                                        }
        
        logging.info("Calender %s queried at %s, and last updated %s" % (event_list_results.get('summary'),
                                                                datetime.datetime.now().strftime("%m-%d %H:%M"),
                                                                event_list_results.get('updated'))
                                                                )

    def parse_google_dateortime(self, inputdatetime):
        """Try parsing as a datetime, otherwise try parsing as a date."""
        try:
            return parse_datetime(inputdatetime)
        except ValueError:
            date = parse_date(inputdatetime)
            return self.localzone.localize(datetime.datetime(date.year, date.month, date.day))

    def get_last_calendar_update_time(self):
        dates = [self.parse_google_dateortime(x['lastUpdated']) for _, x in self.calendarAccess.iteritems()]
        return max(dates)

    def get_last_calendar_poll_time(self):
        dates = [x['lastQueried'] for _, x in self.calendarAccess.iteritems()]
        return max(dates)
