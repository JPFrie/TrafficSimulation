from datetime import datetime
from pathlib import Path

import time
import numpy as np

from airtrafficsim.core.environment import Environment
from airtrafficsim.core.aircraft import Aircraft
from airtrafficsim.utils.enums import Config, FlightPhase, GroundPhase
from airtrafficsim.core.navigation import Nav


class MUCTEST(Environment):

    def __init__(self):
        # Initialize environment super class
        super().__init__(file_name=Path(__file__).name.removesuffix('.py'),  # File name (do not change)
                         start_time=datetime.fromisoformat(
                             '2022-03-22T00:00:00+00:00'),
                         end_time=10**9,
                         weather_mode="",
                         performance_mode="OpenAP"
                         )

        # Add aircraft
        lat_dep, long_dep, alt_dep = Nav.get_runway_coord("EDDM", "08R")
        lat_gate, long_gate, hdg_gate = Nav.get_gate_position("EDDM", "102")
        #lat_gate2, long_gate2, hdg_gate2 = Nav.get_gate_position("EDDM", "102")
        lat_gate3, long_gate3, hdg_gate3 = Nav.get_gate_position("EDDM", "103")
        lat_gate4, long_gate4, hdg_gate4 = Nav.get_gate_position("EDDM", "104")
        lat_gate5, long_gate5, hdg_gate5 = Nav.get_gate_position("EDDM", "105")
        lat_gate6, long_gate6, hdg_gate6 = Nav.get_gate_position("EDDM", "108")
        lat_gate7, long_gate7, hdg_gate7 = Nav.get_gate_position("EDDM", "110")
        lat_gate8, long_gate8, hdg_gate8 = Nav.get_gate_position("EDDM", "111")
        lat_gate9, long_gate9, hdg_gate9 = Nav.get_gate_position("EDDM", "112")
        lat_gate10, long_gate10, hdg_gate10 = Nav.get_gate_position("EDDM", "113")
        lat_gate11, long_gate11, hdg_gate11 = Nav.get_gate_position("EDDM", "116")
        lat_gate12, long_gate12, hdg_gate12 = Nav.get_gate_position("EDDM", "118")
        lat_gate13, long_gate13, hdg_gate13 = Nav.get_gate_position("EDDM", "119")
        lat_gate14, long_gate14, hdg_gate14 = Nav.get_gate_position("EDDM", "120")
        lat_gate15, long_gate15, hdg_gate15 = Nav.get_gate_position("EDDM", "203")
        lat_gate16, long_gate16, hdg_gate16 = Nav.get_gate_position("EDDM", "206")
        lat_gate17, long_gate17, hdg_gate17 = Nav.get_gate_position("EDDM", "208")
        lat_gate18, long_gate18, hdg_gate18 = Nav.get_gate_position("EDDM", "211")
        self.aircraft_head = Aircraft(self.traffic, call_sign="DLH110", aircraft_type="A320", flight_phase=FlightPhase.CRUISE, configuration=Config.CLEAN,
                                      lat=lat_dep, long=long_dep, alt=3500.0, heading=85.0, cas=100.0, fuel_weight=1000.0, payload_weight=500.0, cruise_alt=5000)
        self.aircraft_fol = Aircraft(self.traffic, call_sign="RYR830", aircraft_type="B738", flight_phase=FlightPhase.CRUISE, configuration=Config.CLEAN,
                                     lat=lat_dep + 0.01, long=long_dep, alt=4500.0, heading=85.0, cas=100.0, fuel_weight=1000.0, payload_weight=500.0, cruise_alt=5000)
        self.aircraft_full = Aircraft(self.traffic, call_sign="DLH330", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate, long=long_gate, alt=alt_dep, heading=hdg_gate, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        #self.aircraft_gate1 = Aircraft(self.traffic, call_sign="DLH200", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
        #                              lat=lat_gate2, long=long_gate2, alt=alt_dep, heading=hdg_gate2, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate2 = Aircraft(self.traffic, call_sign="RYR201", aircraft_type="B738", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate3, long=long_gate3, alt=alt_dep, heading=hdg_gate3, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate3 = Aircraft(self.traffic, call_sign="AFR202", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate4, long=long_gate4, alt=alt_dep, heading=hdg_gate4, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate4 = Aircraft(self.traffic, call_sign="KLM203", aircraft_type="B738", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate5, long=long_gate5, alt=alt_dep, heading=hdg_gate5, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate5 = Aircraft(self.traffic, call_sign="BEL204", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate6, long=long_gate6, alt=alt_dep, heading=hdg_gate6, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate6 = Aircraft(self.traffic, call_sign="CFG205", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate7, long=long_gate7, alt=alt_dep, heading=hdg_gate7, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate7 = Aircraft(self.traffic, call_sign="DLH206", aircraft_type="A333", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate8, long=long_gate8, alt=alt_dep, heading=hdg_gate8, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate8 = Aircraft(self.traffic, call_sign="DLH207", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate9, long=long_gate9, alt=alt_dep, heading=hdg_gate9, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate9 = Aircraft(self.traffic, call_sign="KLM208", aircraft_type="B738", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate10, long=long_gate10, alt=alt_dep, heading=hdg_gate10, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate10 = Aircraft(self.traffic, call_sign="EWG209", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate11, long=long_gate11, alt=alt_dep, heading=hdg_gate11, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate11 = Aircraft(self.traffic, call_sign="DLH210", aircraft_type="A333", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate12, long=long_gate12, alt=alt_dep, heading=hdg_gate12, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate12 = Aircraft(self.traffic, call_sign="DLH211", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate13, long=long_gate13, alt=alt_dep, heading=hdg_gate13, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate13 = Aircraft(self.traffic, call_sign="DLH212", aircraft_type="A333", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate14, long=long_gate14, alt=alt_dep, heading=hdg_gate14, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate14 = Aircraft(self.traffic, call_sign="DLH213", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate15, long=long_gate15, alt=alt_dep, heading=hdg_gate15, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate15 = Aircraft(self.traffic, call_sign="RYR214", aircraft_type="B738", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate16, long=long_gate16, alt=alt_dep, heading=hdg_gate16, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate16 = Aircraft(self.traffic, call_sign="DLH215", aircraft_type="A320", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate17, long=long_gate17, alt=alt_dep, heading=hdg_gate17, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_gate17 = Aircraft(self.traffic, call_sign="DLH216", aircraft_type="A333", flight_phase=FlightPhase.AT_GATE_ORIGIN, configuration=Config.TAKEOFF,
                                      lat=lat_gate18, long=long_gate18, alt=alt_dep, heading=hdg_gate18, cas=0.0, fuel_weight=5273.0, payload_weight=12000.0, cruise_alt=37000)
        self.aircraft_head.set_speed(220.0) # To set the aircraft to follow given speed command instead of auto procedural
        self.aircraft_fol.set_speed(250.0) # To set the aircraft to follow given speed command instead of auto procedural
        self.aircraft_full.set_speed(0.0)
        #self.aircraft_gate1.set_speed(0.0)
        self.aircraft_gate2.set_speed(0.0)
        self.aircraft_gate3.set_speed(0.0)
        self.aircraft_gate4.set_speed(0.0)
        self.aircraft_gate5.set_speed(0.0)
        self.aircraft_gate6.set_speed(0.0)
        self.aircraft_gate7.set_speed(0.0)
        self.aircraft_gate8.set_speed(0.0)
        self.aircraft_gate9.set_speed(0.0)
        self.aircraft_gate10.set_speed(0.0)
        self.aircraft_gate11.set_speed(0.0)
        self.aircraft_gate12.set_speed(0.0)
        self.aircraft_gate13.set_speed(0.0)
        self.aircraft_gate14.set_speed(0.0)
        self.aircraft_gate15.set_speed(0.0)
        self.aircraft_gate16.set_speed(0.0)
        self.aircraft_gate17.set_speed(0.0)

        self.aircraft_list = [
            self.aircraft_head,
            self.aircraft_fol,
            self.aircraft_full,
            self.aircraft_gate2,
            self.aircraft_gate3,
            self.aircraft_gate4,
            self.aircraft_gate5,
            self.aircraft_gate6,
            self.aircraft_gate7,
            self.aircraft_gate8,
            self.aircraft_gate9,
            self.aircraft_gate10,
            self.aircraft_gate11,
            self.aircraft_gate12,
            self.aircraft_gate13,
            self.aircraft_gate14,
            self.aircraft_gate15,
            self.aircraft_gate16,
            self.aircraft_gate17,
        ]

    def should_end(self):
        return False

    def atc_command(self):
        print("ATC running at", self.global_time)
        print(self.aircraft_head.get_heading())
#        if not hasattr(self, "_head_turn_start_time"):
#            self._head_turn_start_time = time.time()

        # Speed/Vertikalbewegung kappen
        # self.aircraft_full.set_speed(0.0)
        #self.aircraft_gate1.set_speed(0.0)       

#        if time.time() - self._head_turn_start_time == 61:
#            self.aircraft_head.set_heading(350)

        for ac in self.aircraft_list:
            if ac.is_taxiing():
                ac.update_taxi()

        if self.global_time == 10:
            print("EDDM nodes:", Nav.taxi_nodes[Nav.taxi_nodes["airport"]=="EDDM"].shape)
            print("EDDM edges:", Nav.taxi_edges[Nav.taxi_edges["airport"]=="EDDM"].shape)
            self.aircraft_full.start_taxi_to_runway("EDDM", "08L")

        if self.global_time == 20:
            self.aircraft_gate7.start_taxi_to_runway("EDDM", "08R")

        #self.aircraft_full.update_taxi()
        #self.aircraft_gate7.update_taxi()
        # self.print_ground_debug()
        if(self.global_time > 10):
            print("Taxi index DLH330:", self.aircraft_full.taxi_index)
            print("Taxi route length DLH330:", len(self.aircraft_full.taxi_route))
            if self.aircraft_gate7.taxi_index < len(self.aircraft_gate7.taxi_route):
                print("Taxi targetDLH306:", self.aircraft_gate7.taxi_route[self.aircraft_gate7.taxi_index])
            else:
                print("Taxi finished for: DLH206")

        if(self.global_time > 20):
            print("Taxi index DLH206:", self.aircraft_gate7.taxi_index)
            print("Taxi route length DLH206:", len(self.aircraft_gate7.taxi_route))
            if self.aircraft_gate7.taxi_index < len(self.aircraft_gate7.taxi_route):
                print("Taxi targetDLH306:", self.aircraft_gate7.taxi_route[self.aircraft_gate7.taxi_index])
            else:
                print("Taxi finished for: DLH206")

        t = self.global_time % 320

        if t == 70:
            self.aircraft_head.set_heading(355)
            self.aircraft_fol.set_heading(355)

        elif t == 110:
            self.aircraft_head.set_heading(265)
            self.aircraft_fol.set_heading(265)

        elif t == 240:
            self.aircraft_head.set_heading(175)
            self.aircraft_fol.set_heading(175)

        elif t == 280:
            self.aircraft_head.set_heading(85)
            self.aircraft_fol.set_heading(85)
        #return False
        # User algorithm
        #if self.global_time == 100:
        #    # Right
        #    self.aircraft_fol.set_heading(220)
        #    # Left
        #    self.aircraft_head.set_heading(150)
        #
        #if self.global_time == 500:
        #    # Climb
        #    self.aircraft_fol.set_alt(5000)
        #    # Descend
        #    self.aircraft_head.set_alt(3000)
        #
        #if self.global_time == 900:
        #    self.traffic.del_aircraft(self.aircraft_head.index)