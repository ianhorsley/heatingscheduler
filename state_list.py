"""State list object to hold states"""
import copy
import logging
import pytz

from user import User

ukest = pytz.timezone('Europe/London')

class StateList(object):
    #Holds user statelist and generates room statelist
    user_state_list = []
    room_state_list = []

    def __init__(self, usernames):
        self.usernames = usernames
    
    def __add__(self, other):
        #combine and sort statelists
        usernamesself = self.usernames if isinstance(self.usernames, list) else [self.usernames]
        usernamesother = other.usernames if isinstance(other.usernames, list) else [other.usernames]
        
        ret_user_state_list = StateList(usernamesself + usernamesother)
        ret_user_state_list.user_state_list = self.user_state_list + other.user_state_list
        ret_user_state_list.user_state_list.sort(key=lambda x:x.last_updated)
        return ret_user_state_list
    
    #Handle user state list
    
    def add_user_state(self, new_state):
        #add a new state if different from last in list.
        
        if len(self.user_state_list) == 0 or (new_state.last_updated != self.user_state_list[-1].last_updated and new_state.current_state != self.user_state_list[-1].current_state):
            self.user_state_list.append(copy.deepcopy(new_state))
        elif new_state.current_state != self.user_state_list[-1].current_state:
            self.user_state_list[-1] = copy.deepcopy(new_state)
            
    def print_user_debug(self, statlist):
        #print debug log of state list
        for i in self.user_state_list:
            stat_temps = ' '.join(self._stringN(i.roomtemps[statnane]) for statnane, _ in statlist.iteritems())
            logging.debug( '%s %s, %s %s, %s other %i %i %i %i %i %i' % (i.last_updated.astimezone(ukest).strftime("%m-%d %H:%M"),
                                                        i.current_state.ljust(17),
                                                        self._stringN(i.inuse_room_temp),
                                                        self._stringN(i.sleep_room_temp),
                                                        stat_temps,
                                                        i.state_counters['HOME'], i.state_counters['AWAY'], i.state_counters['OUT'],
                                                        i.state_counters['AWAKE'], i.state_counters['ACTIVE'], i.state_counters['ACTIVE_SLEEP_ROOM']) )
    @staticmethod
    def _stringN(number):
        #string from number handling None case
        if number is None:
            return " N"
        return str(number)
        
    #Create room state list
    
    def create_room_state_list(self, statlist):
    
        #create temp dictionary to hold state as processing triggers.
        temp = {}
        #set the room array up for each user to hold users state and temperature demands and
        for name in self.usernames:
            temp[name] = User({}, statlist)

        for trigger in self.user_state_list:
            temp[trigger.name] = trigger
            temp['time'] = trigger.last_updated

            for name, controllersettings in statlist.iteritems():
                temp[name] = self.current_room_temp(temp, name, controllersettings)

            self._add_room_state(temp)
    
    def _add_room_state(self, temp):
        #add new room state or update existing depending on whether the time is the same.
        if len(self.room_state_list) == 0 or temp['time'] != self.room_state_list[-1]['time']:
            self.room_state_list.append(temp.copy())
        else: #if two triggers for the same time, update the previous state with the additional users information updated
            self.room_state_list[-1] = temp.copy()
    
    def current_room_temp(self, current_room_state, name, controllersettings):
        #compute current room temp based on user states and controllersettings
        
        if controllersettings['control_mode'] == 'manual':
            return controllersettings['frost_temperature']
        else:
            maxtemp = controllersettings['frost_temperature']
            for user in self.usernames:
                maxtemp = max(maxtemp, current_room_state[user].roomtemps[name])
            return maxtemp
            
    def print_room_debug(self):
        logging.debug("room state tracking")
        logging.debug('Time (m-d H:m) Kit B1 B2 Cons other IanState IzzyState')
        for i in self.room_state_list:
            logging.debug('%s %i %i %i %i other %s %s'% (i['time'].astimezone(ukest).strftime("%m-%d %H:%M"),
                                                    i['Kit'], i['B1'], i['B2'], i['Cons'],
                                                    i['IAN'].current_state.ljust(17), i['IZZY'].current_state.ljust(17)))
