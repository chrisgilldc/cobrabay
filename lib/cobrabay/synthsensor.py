####
# Cobra Bay - Synthetic Sensors
# 
# Feeds fake data for debugging without sensors attached
####

from time import monotonic

class SynthSensor():
    def __init__(self,config):
        self._init_timestamp = monotonic()
        
        # Store the start value and role, we'll need those later.
        self._role = config['role']
        self._start_value = config['start_value']
        # Set the reported distance to whatever the default start is.
        self._distance = config['start_value']
        # If role is approach, fake an approaching vehicle
        if config['role'] == 'approach':

            # Convert from cm/s to cm/ns
            self._approach_rate = config['delta-d']
        elif config['role'] == 'side':
            self._variance = config['variance']
            self._side_vector = 1

        
    @property
    def distance(self):
        return self._dist_calculate()
        
    def _dist_calculate(self):
        if self._role == 'approach':
            # Decrement the distance based on approach speed and elapsed time.
            self._distance = self._start_value - (self._approach_rate * (monotonic() - self._init_timestamp))
            # if distance has wound up below 0, reset to the start.
            if self._distance <= 0:
                
                self._init_timestamp = monotonic()
                self._distance = self._start_value
            return self._distance
        elif self._role == 'side':
            self._distance = self._distance + self._side_vector
            if self._distance >= self._start_value + self._variance or self._distance <= self._start_value - self._variance:
                self._side_vector = self._side_vector * -1
                self._distance = self._distance + self._side_vector
            return self._distance
        else:
            raise ValueError('Requested a synthetic sensor mode that does not exist!')