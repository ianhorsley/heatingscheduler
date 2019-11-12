"""User object to hold user data and states"""


class User(object):
    #Holds user data and functions

    def __init__(self, params, statlist):
        #setup variable to store state
        self.current_state = 'Not Set'
        self.inuse_room_temp = None
        self.sleep_room_temp = None
        self.current_residency = None
        self.last_updated = None
        #counter for each state to handle multiple overlapping states.
        self.state_counters = {'HOME':0, 'AWAY':0, 'OUT':0, 'AWAKE':0, 'ACTIVE':0, 'ACTIVE_SLEEP_ROOM':0}
        self.roomtemps = {}

        for key, value in params.items():
            setattr(self, key, value)

        for name, _ in statlist.iteritems():
            self.roomtemps[name] = None

    def apply_trigger(self, trigger):
        #apply trigger to states, temps, etc.
        self.state_counters[trigger['state']] += trigger['trigger']
        self.last_updated = trigger['time']
        self.calc_residency() #is user in?

        self.calc_state() #users state and room needs

        self.update_room_temps()

    def calc_residency(self):
        #determine from state counts where the user is
        #counts reflect the number of active events that idicate a particular state.
        #Presidency, Home, Away, otherwise default.
        if self.state_counters['HOME'] > 0:
            self.current_residency = 'HOME'
        elif self.state_counters['AWAY'] > 0 or self.state_counters['OUT'] > 0:
            self.current_residency =  'AWAY'
        else:
            self.current_residency =  self.default_residency

    def calc_state(self):
        #determine user state and temps from residency and state counters and users parameters
        #return state, inuse temp, sleep temp
        if self.current_residency == 'AWAY':
            state = ('AWAY', None, None)
        elif self.state_counters['AWAKE'] == 0:
            state = ('SLEEP', None, self.temp_asleep)
        elif self.state_counters['ACTIVE_SLEEP_ROOM'] > 0:
            state = ('ACTIVE_SLEEP_ROOM', self.temp_active, self.temp_active)
        elif self.state_counters['ACTIVE'] > 0:
            state = ('ACTIVE', self.temp_active, None)
        else:
            state = ('INACTIVE', self.temp_inactive, None)
        self.current_state, self.inuse_room_temp, self.sleep_room_temp = state

    def update_room_temps(self):
        #update room temps based on residency, states and counters
        for room in self.awake_rooms:
            self.roomtemps[room] = self.inuse_room_temp

        if self.sleep_room in self.awake_rooms:
            self.roomtemps[self.sleep_room] = max(self.sleep_room_temp, self.inuse_room_temp)
        else:
            self.roomtemps[self.sleep_room] = self.sleep_room_temp
