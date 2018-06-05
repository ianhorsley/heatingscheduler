
import datetime

izzy_params = {
              'name': 'IZZY',
              'calendar_id': 'INSERT',
              'calendar_id_work': 'INSERT',
              'default_wake' : datetime.timedelta(hours=7,minutes=0),
              'default_sleep' : datetime.timedelta(hours=21,minutes=0),
              'minimum_wake_before_event': datetime.timedelta(minutes=45),
              'minimum_wake_after_event': datetime.timedelta(minutes=40),
              'sleep_before_night': datetime.timedelta(hours=2),
              'sleep_night_to_night': datetime.timedelta(hours=8),
              'sleep_after_night': datetime.timedelta(hours=5),
              'active_time': datetime.timedelta(minutes=30), #time before and after events that user is active
              'active_time_sleep_room': datetime.timedelta(minutes=60), #time before and after bed that user is active
              'default_residency': 'HOME',
              'awake_rooms': ['Kit'],
              'sleep_room': 'B1',
              'temp_active': 18,
              'temp_inactive': 19,
              'temp_asleep': 16}

ian_params = {
              'name': 'IAN',
              'calendar_id': 'INSERT',
              'calendar_id_work': 'INSERT',
              'default_wake' : datetime.timedelta(hours=7,minutes=0),
              'default_sleep' : datetime.timedelta(hours=22,minutes=0),
              'minimum_wake_before_event': datetime.timedelta(minutes=60),
              'minimum_wake_after_event': datetime.timedelta(minutes=45),
              'sleep_before_night': datetime.timedelta(hours=2),
              'sleep_night_to_night': datetime.timedelta(hours=8),
              'sleep_after_night': datetime.timedelta(hours=5),
              'active_time': datetime.timedelta(minutes=30), #time before and after events that user is active
              'active_time_sleep_room': datetime.timedelta(minutes=45), #time before and after bed that user is active
              'default_residency': 'HOME',
              'awake_rooms': ['Kit','B2'],
              'sleep_room': 'Kit',
              'temp_active': 18,
              'temp_inactive': 19,
              'temp_asleep': 16}