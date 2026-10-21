from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class General:
    cycle: int
    election_day: date
    kind: Literal["presidential", "midterm"]
    covid_outlier: bool = False

    def days_out(self, d: date) -> int:
        return (self.election_day - d).days


GENERALS: dict[int, General] = {
    g.cycle: g
    for g in [
        General(2008, date(2008, 11, 4), "presidential"),
        General(2010, date(2010, 11, 2), "midterm"),
        General(2012, date(2012, 11, 6), "presidential"),
        General(2014, date(2014, 11, 4), "midterm"),
        General(2016, date(2016, 11, 8), "presidential"),
        General(2018, date(2018, 11, 6), "midterm"),
        General(2020, date(2020, 11, 3), "presidential", covid_outlier=True),
        General(2022, date(2022, 11, 8), "midterm"),
        General(2024, date(2024, 11, 5), "presidential"),
        General(2026, date(2026, 11, 3), "midterm"),
    ]
}
