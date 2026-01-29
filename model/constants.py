from enum import Enum

class AgentStatus(Enum):
    IN_CLASS = "IN_CLASS"
    BREAK = "BREAK"
    GYM = "GYM"
    HOME = "HOME"

class LocationType(Enum):
    AUDITORIUM = "AUDITORIUM"
    GYM = "GYM"
    HOME = "HOME"

class SportType(Enum):
    BASKETBALL = "Basketball"
    VOLLEYBALL = "Volleyball"
    TENNIS = "Tennis"

class TimeSlotType(Enum):
    PAIR_1 = "Pair 1"
    BREAK_1 = "Break 1"
    PAIR_2 = "Pair 2"
    BREAK_2 = "Break 2"
    PAIR_3 = "Pair 3"
    BREAK_3 = "Break 3"
    PAIR_4 = "Pair 4"
    GYM = "Gym / Section"
    CLEANUP = "End of Day"
