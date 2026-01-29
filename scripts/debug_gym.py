import sys
import os
sys.path.append(os.getcwd())

from model.university_collective import UniversityCollective
from model.constants import TimeSlotType, AgentStatus
import datetime

def test_gym_attendance_jan_1():
    print("--- STARTING GYM TEST: JAN 1, 2025 ---")
    collective = UniversityCollective()
    
    # Сбрасываем дату на 1 января (хотя она и так по дефолту такая, но для надежности)
    collective.current_date = datetime.date(2025, 1, 1)
    collective.current_step = 0
    collective.current_slot_idx = 0

    print(f"Testing Day: {collective.current_date.strftime('%A, %d %b')}")
    
    # Проходим по всем слотам первого дня
    slots_count = len(collective.day_schedule_slots)
    for i in range(slots_count):
        slot = collective.day_schedule_slots[i]
        interactions = collective.perform_next_step()
        
        in_campus = sum(1 for a in collective.agents.values() if a.status != AgentStatus.HOME)
        in_gym = len(collective.current_rooms.get("GYM", []))
        
        slot_name = slot.value if hasattr(slot, 'value') else slot
        print(f"Slot {i}: {slot_name:15} | In Campus: {in_campus:5} | In Gym: {in_gym:5}")
        
        if in_gym > 0:
            print(f"  --> FOUND {in_gym} STUDENTS IN GYM AT {slot_name}!")

    print("\n--- TEST COMPLETED ---")

if __name__ == "__main__":
    test_gym_attendance_jan_1()
