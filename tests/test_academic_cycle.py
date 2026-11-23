import datetime
import unittest

from model.university_collective import UniversityCollective


class AcademicCycleTest(unittest.TestCase):
    """Границы семестров не должны зависеть от дня недели.

    В исходной версии `_check_academic_cycle` вызывался только после
    обычного перехода дня. Если 1 февраля приходилось на понедельник,
    воскресный переход (31 января) пропускал проверку, и весенний
    семестр терялся. Из-за этого восемь семестров занимали 1366 дней
    вместо 1213.
    """

    def _fake_collective(self, current_date):
        collective = UniversityCollective.__new__(UniversityCollective)
        collective.current_date = current_date
        collective.current_academic_year = current_date.year
        collective.current_step = 0
        collective.current_slot_idx = 0
        collective.semesters_passed = 0
        collective.agents = {}
        collective.cpp_engine = None
        collective._sync_to_cpp = lambda *args, **kwargs: None
        collective._sync_from_cpp = lambda *args, **kwargs: None
        collective._handle_graduation_and_enrollment = lambda: None
        collective._reinitialize_emotions = lambda: None
        return collective

    def test_sunday_transition_into_february_counts_semester(self):
        # 31 января 2027 — воскресенье; 1 февраля — понедельник.
        collective = self._fake_collective(datetime.date(2027, 1, 31))
        collective.semesters_passed = 6

        collective._handle_sunday()

        self.assertEqual(collective.current_date, datetime.date(2027, 2, 1))
        self.assertEqual(collective.semesters_passed, 7)

    def test_eight_semesters_take_1213_simulated_days(self):
        collective = self._fake_collective(datetime.date(2024, 9, 1))
        days = 0

        while collective.semesters_passed < 8:
            days += 1
            if collective.current_date.weekday() == 6:
                collective._handle_sunday()
            else:
                collective.current_date += datetime.timedelta(days=1)
                collective._check_academic_cycle()

        self.assertEqual(days, 1213)
        self.assertEqual(collective.semesters_passed, 8)
        # После летнего перехода дата — 1 сентября 2028 года.
        self.assertEqual(collective.current_date, datetime.date(2028, 9, 1))


if __name__ == "__main__":
    unittest.main()
