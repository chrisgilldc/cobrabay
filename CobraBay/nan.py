# Simple class to pass Not-a-Number results, along with some reason text, around the system.

class NaN:
    def __init__(self, reason=None):
        self._reason = reason

    @property
    def reason(self):
        return self._reason

    def __str__(self):
        if self._reason:
            return self._reason
        else:
            return "unknown"