import time
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import csv
import threading
from pathlib import Path

from airtrafficsim.utils.unit_conversion import Unit
from airtrafficsim.utils.enums import (
    FlightPhase, Config, SpeedMode, VerticalMode,
    APSpeedMode, APThrottleMode, APLateralMode
)
from airtrafficsim.core.traffic import Traffic
from airtrafficsim.core.navigation import Nav
from airtrafficsim.core.integrations.xplane_bridge import XPlaneBridge, XPlaneBridgeConfig

class Environment:
    """
    Base class for simulation environment.

    Features:
    - Finite run (end_time=int seconds) OR endless run (end_time=None)
    - Real-time pacing: 1 sim step == time_step_s real seconds (default 1.0)
    - CZML streaming uses a sliding clock window (trail/lead seconds) for endless runs
    - SocketIO handlers registered once
    - Optional graceful stop via SocketIO event "stopSimulation"
    - X-Plane bridge integration (AI aircraft snapshot + optional player-controlled aircraft mapping)
    """

    def __init__(
        self,
        file_name: str,
        start_time: datetime,
        end_time: int | None = None,
        weather_mode: str = "ISA",
        performance_mode: str = "BADA",
        *,
        # Real-time pacing
        real_time: bool = True,
        time_step_s: float = 1.0,
        # Streaming / UI
        send_interval_s: float = 0.5,
        czml_trail_seconds: int = 60,
        czml_lead_seconds: int = 5,
        # Logging
        save_every_n_steps: int = 1,
        # X-Plane
        xplane_hz: float = 1.0,
        controlled_callsign: str = "OWNSHIP",
        exclude_controlled_from_ai: bool = True,
    ):
        # User setting
        self.start_time = start_time
        """Simulation start time [datetime]"""

        self.end_time = end_time
        """Simulation end time [s] or None for endless"""

        # Simulation core
        self.traffic = Traffic(file_name, start_time, end_time, weather_mode, performance_mode)
        self.global_time = 0  # [s], simulation time since start_time

        # Real-time pacing
        self.real_time = bool(real_time)
        self.time_step_s = float(time_step_s)
        self._wall_clock_start = None  # set in run()

        # Streaming / UI config
        self.send_interval_s = float(send_interval_s)
        self.czml_trail_seconds = int(czml_trail_seconds)
        self.czml_lead_seconds = int(czml_lead_seconds)
        self.graph_type = "None"
        self.last_sent_time = time.time()
        self.packet_id = 0
        self.buffer_data = []
        self._socketio_handlers_registered = False
        self._stop_requested = False

        # Save config
        self.save_every_n_steps = max(1, int(save_every_n_steps))

        # --- X-Plane bridge integration ---
        self._xp_lock = threading.Lock()
        self._xp_snapshot = []  # latest aircraft list for X-Plane
        self._last_player_state = None
        self._player_row = None

        self.controlled_callsign = str(controlled_callsign)
        self.exclude_controlled_from_ai = bool(exclude_controlled_from_ai)

        self._xp_bridge = XPlaneBridge(
            cfg=XPlaneBridgeConfig(hz=float(xplane_hz)),
            get_snapshot=self._get_xplane_snapshot,
            on_player_state=self._apply_player_state_from_xplane,
            log=lambda s: print(s),
        )
        self._xp_bridge.update_snapshot = self._update_xplane_snapshot_from_traffic
        # Load required NAV databases
        Nav.load_taxi_network()

        # File IO
        self.datetime = datetime.now(timezone.utc)
        self.file_name = file_name + "-" + self.datetime.isoformat(timespec="seconds")
        self.folder_path = Path(__file__).parent.parent.resolve().joinpath("data/result/" + self.file_name)
        self.folder_path.mkdir(parents=True, exist_ok=True)
        self.file_path = self.folder_path.joinpath(self.file_name + ".csv")

        self._csv_fp = open(self.file_path, "w+", newline="")
        self.writer = csv.writer(self._csv_fp)

        self.header = [
            "timestep", "timestamp", "id", "callsign", "lat", "long", "alt",
            "cas", "tas", "mach", "vs",
            "heading", "bank_angle", "path_angle",
            "mass", "fuel_consumed",
            "thrust", "drag", "esf", "accel",
            "ap_track_angle", "ap_heading", "ap_alt", "ap_cas", "ap_mach", "ap_procedural_speed",
            "ap_wp_index", "ap_next_wp", "ap_dist_to_next_fix", "ap_holding_round",
            "flight_phase", "configuration", "speed_mode", "vertical_mode",
            "ap_speed_mode", "ap_lateral_mode", "ap_throttle_mode",
        ]
        self.writer.writerow(self.header)

        # Header used by frontend (mirrors your original behavior)
        self.frontend_header = self.header.copy()
        for col in ("timestep", "timestamp", "id", "callsign"):
            if col in self.frontend_header:
                self.frontend_header.remove(col)


    def print_ground_debug(self):
        import os
        #os.system("clear")
        for i in range(self.traffic.n):

            callsign = self.traffic.call_sign[i]
            phase = int(self.traffic.flight_phase[i])
            speed = round(self.traffic.taxi_speed[i], 1)

            lat = round(self.traffic.lat[i], 5)
            lon = round(self.traffic.long[i], 5)

            print(f"{callsign:8} {phase:<12} {speed:<1} {lat:<10} {lon:<10}")

    # ---------- X-Plane bridge helpers ----------

    def _get_xplane_snapshot(self):
        with self._xp_lock:
            return list(self._xp_snapshot)

    @staticmethod
    def _knots_to_mps(knots: float) -> float:
        return float(knots) * 0.514444

    @staticmethod
    def _mps_to_knots(mps: float) -> float:
        return float(mps) / 0.514444
    
    @staticmethod
    def compute_pitch_from_vs_tas(vs_ft_min, tas_kts):
        vs_ft_min = np.asarray(vs_ft_min)
        tas_kts   = np.asarray(tas_kts)

        # --- Umrechnung ft/min -> m/s ---
        vs_m_s = vs_ft_min * 0.00508

        # --- Umrechnung kts tp m/s
        tas_m_s = tas_kts * 0.514444

        # Division absichern
        ratio = np.zeros_like(vs_m_s, dtype=float)
        valid = tas_m_s != 0
        ratio[valid] = vs_m_s[valid] / tas_m_s[valid]

        # numerische Stabilität
        ratio = np.clip(ratio, -1.0, 1.0)

        gamma_rad = np.arcsin(ratio)
        pitch_deg = np.degrees(gamma_rad)

        return pitch_deg

    def _update_xplane_snapshot_from_traffic(self):
        ids = self.traffic.call_sign
        lat = self.traffic.lat
        lon = self.traffic.long
        alt_ft = self.traffic.alt
        hdg = self.traffic.heading
        cas = self.traffic.cas
        tas_kt = self.traffic.tas
        vs = self.traffic.vs
        gs_north_mps = self.traffic.gs_north * 0.514444
        gs_east_mps = self.traffic.gs_east * 0.514444
        trk = self.traffic.track_angle
        bank = self.traffic.bank_angle
        model = self.traffic.aircraft_type
        pitch = self.compute_pitch_from_vs_tas(vs, tas_kt)

        aircraft = []
        for i in range(len(ids)):
            cs = str(ids[i])

            if self.exclude_controlled_from_ai and cs == self.controlled_callsign:
                continue

            aircraft.append({
                "id": cs,
                "lat": float(lat[i]),
                "lon": float(lon[i]),
                "alt_ft": float(alt_ft[i]),
                "hdg_deg": float(hdg[i]),
                "cas": float(cas[i]),
                "pitch": float(pitch[i]),
                "tas": float(tas_kt[i]),
                "vs": float(vs[i]),
                "gs_north_mps":float(gs_north_mps[i]),
                "gs_east_mps":float(gs_east_mps[i]),
                "trk": float(trk[i]),
                "bank": float(bank[i]),
                "model": model[i],
            })

        with self._xp_lock:
            self._xp_snapshot = aircraft

    def _apply_player_state_from_xplane(self, player: dict):
        # speichern für später (Frontend + Buffer)
        self._last_player_state = player
        print("PLAYER RECEIVED:", player)
        
    def _find_aircraft_index_by_callsign(self, callsign: str) -> int:
        matches = np.where(self.traffic.call_sign == callsign)[0]
        return int(matches[0]) if len(matches) else -1

    # ---------- Extension points ----------

    def atc_command(self):
        """Override to execute user command each timestep."""
        pass

    def should_end(self) -> bool:
        """Override to stop endless run, or stop before end_time in finite runs."""
        return False

    # ---------- SocketIO helpers ----------

    def _register_socketio_handlers(self, socketio):
        if self._socketio_handlers_registered or socketio is None:
            return

        @socketio.on("setSimulationGraphType")
        def set_simulation_graph_type(graph_type):
            self.graph_type = graph_type

        @socketio.on("stopSimulation")
        def stop_simulation(_payload=None):
            self._stop_requested = True

        self._socketio_handlers_registered = True

    # ---------- Real-time pacing ----------

    def _pace_realtime(self, socketio=None):
        """
        Enforce 1 sim step == self.time_step_s real seconds.

        Uses a target wall-clock schedule:
          target_time = wall_clock_start + global_time * time_step_s

        This prevents drift and keeps stable pacing.
        """
        if not self.real_time:
            return
        if self._wall_clock_start is None:
            # fallback: initialize if run() forgot (shouldn't happen)
            self._wall_clock_start = time.time()

        target = self._wall_clock_start + (self.global_time * self.time_step_s)
        now = time.time()
        sleep_s = target - now
        if sleep_s > 0:
            # If running under eventlet/gevent, socketio.sleep is better
            if socketio is not None:
                socketio.sleep(sleep_s)
            else:
                time.sleep(sleep_s)

    # ---------- Main loop ----------

    def step(self, socketio=None):
        print("STEP:", self.global_time, "end_time:", self.end_time)
        # Update simulation for current global_time
        self.atc_command()
        self.traffic.update(self.global_time)

        # Save to file (optionally downsample)
        if (self.global_time % self.save_every_n_steps) == 0:
            self.save()

        # Update X-Plane snapshot once per tick
        self._update_xplane_snapshot_from_traffic()

        # Streaming (CZML)
        if socketio is not None:
            self._register_socketio_handlers(socketio)

            data = np.column_stack((
                self.traffic.index,
                self.traffic.call_sign,
                np.full(
                    len(self.traffic.index),
                    (self.start_time + timedelta(seconds=self.global_time)).isoformat(timespec="seconds")
                ),
                self.traffic.long,
                self.traffic.lat,
                Unit.ft2m(self.traffic.alt),
                self.traffic.cas,
            ))
            self.buffer_data.extend(data)

            p = self._last_player_state

            if p is not None:
                timestamp = (self.start_time + timedelta(seconds=self.global_time)).isoformat(timespec="seconds")

                player_row = [
                    -999,
                    "OWNSHIP",
                    str(timestamp),
                    float(p["lon"]),
                    float(p["lat"]),
                    float(p["alt_m"]),
                    float(p["spd"])
                ]

                self.buffer_data.append(player_row)

            now = time.time()
            if (now - self.last_sent_time) >= self.send_interval_s:
                self.send_to_client(socketio)
                socketio.sleep(0)
                self.last_sent_time = now
                self.buffer_data = []

        # Advance simulation time by 1 second
        self.global_time += 1

        # Pace to real time AFTER increment: global_time now represents "next tick"
        self._pace_realtime(socketio)

    def run(self, socketio=None):
        """
        Run the simulation.

        - If end_time is None => endless until should_end() or stopSimulation event or KeyboardInterrupt
        - If end_time is int   => runs until end_time (inclusive) unless should_end() earlier
        """
        self._xp_bridge.start()

        # Initialize real-time schedule so t=0 happens immediately
        self._wall_clock_start = time.time()

        if socketio is not None:
            self._register_socketio_handlers(socketio)

            aircraft_list = [
                {
                    "id": int(self.traffic.index[i]),
                    "name": str(self.traffic.call_sign[i])
                }
                for i in range(len(self.traffic.index))
            ]

            socketio.emit("scenarioStarted", aircraft_list)
            socketio.emit("simulationEnvironment", {
                "header": self.frontend_header,
                "file": self.file_name
            })

        try:
            if self.end_time is None:
                # Endless
                while True:
                    if self._stop_requested:
                        break
                    if self.should_end():
                        break
                    self.step(socketio)
            else:
                # Finite horizon
                end_t = int(self.end_time)
                for _ in range(end_t + 1):
                    if self._stop_requested:
                        break
                    if self.should_end():
                        self.end_time = self.global_time
                        break
                    self.step(socketio)

        except KeyboardInterrupt:
            print("\nSimulation interrupted by user (Ctrl+C).")

        finally:
            # Flush remaining buffer once
            if socketio is not None and self.buffer_data:
                try:
                    self.send_to_client(socketio)
                    socketio.sleep(0)
                except Exception:
                    pass

            # Clean shutdown
            try:
                self._xp_bridge.stop()
            except Exception:
                pass

            try:
                self._csv_fp.flush()
                self._csv_fp.close()
            except Exception:
                pass

            print("\nSimulation finished")

    # ---------- Persistence ----------

    def save(self):
        """Save all state variables of one timestep to CSV."""
        data = np.column_stack((
            np.full(len(self.traffic.index), self.global_time),
            np.full(
                len(self.traffic.index),
                (self.start_time + timedelta(seconds=self.global_time)).isoformat(timespec="seconds")
            ),
            self.traffic.index,
            self.traffic.call_sign,
            self.traffic.lat,
            self.traffic.long,
            self.traffic.alt,
            self.traffic.cas,
            self.traffic.tas,
            self.traffic.mach,
            self.traffic.vs,
            self.traffic.heading,
            self.traffic.bank_angle,
            self.traffic.path_angle,
            self.traffic.mass,
            self.traffic.fuel_consumed,
            self.traffic.perf.thrust,
            self.traffic.perf.drag,
            self.traffic.perf.esf,
            self.traffic.accel,
            self.traffic.ap.track_angle,
            self.traffic.ap.heading,
            self.traffic.ap.alt,
            self.traffic.ap.cas,
            self.traffic.ap.mach,
            self.traffic.ap.procedure_speed,
            self.traffic.ap.flight_plan_index,
            [
                self.traffic.ap.flight_plan_name[i][val]
                if (val < len(self.traffic.ap.flight_plan_name[i]))
                else "NONE"
                for i, val in enumerate(self.traffic.ap.flight_plan_index)
            ],
            self.traffic.ap.dist,
            self.traffic.ap.holding_round,
            [FlightPhase(i).name for i in self.traffic.flight_phase],
            [Config(i).name for i in self.traffic.configuration],
            [SpeedMode(i).name for i in self.traffic.speed_mode],
            [VerticalMode(i).name for i in self.traffic.vertical_mode],
            [APSpeedMode(i).name for i in self.traffic.ap.speed_mode],
            [APLateralMode(i).name for i in self.traffic.ap.lateral_mode],
            [APThrottleMode(i).name for i in self.traffic.ap.auto_throttle_mode],
        ))
        self.writer.writerows(data)

    def export_to_csv(self):
        """Export the simulation result to a csv file per aircraft id."""
        df = pd.read_csv(self.file_path)
        for _id in df["id"].unique():
            df[df["id"] == _id].to_csv(self.folder_path.joinpath(str(_id) + ".csv"), index=False)

    # ---------- Streaming / CZML ----------

    def _compute_czml_clock_window(self):
        """
        Sliding time window for endless (and also fine for finite) runs:
        - start: sim_now - trail_seconds (or simulation start if early)
        - end:   sim_now + lead_seconds
        """
        sim_now = self.start_time + timedelta(seconds=self.global_time)

        if self.czml_trail_seconds <= 0:
            clock_start = self.start_time
        else:
            trail_start = sim_now - timedelta(seconds=self.czml_trail_seconds)
            clock_start = max(self.start_time, trail_start)

        clock_end = sim_now + timedelta(seconds=max(0, self.czml_lead_seconds))
        return sim_now, clock_start, clock_end

    def send_to_client(self, socketio):
        """Send the simulation data to client."""
        sim_now, clock_start, clock_end = self._compute_czml_clock_window()

        document = [{
            "id": "document",
            "name": "simulation",
            "version": "1.0",
            "clock": {
                "interval": clock_start.isoformat() + "/" + clock_end.isoformat(),
                "currentTime": sim_now.isoformat(),
            }
        }]

        df_buffer = pd.DataFrame(self.buffer_data)
        if self.buffer_data:
            for _id in df_buffer.iloc[:, 0].unique():
                content = df_buffer[df_buffer.iloc[:, 0] == _id]

                call_sign = content.iloc[0, 1]
                positions = content.iloc[:, [2, 3, 4, 5]].to_numpy().flatten().tolist()

                label = [{
                    "interval": t + "/" + clock_end.isoformat(),
                    "string": call_sign + "\n" + str(np.floor(Unit.m2ft(alt))) + "ft " + str(np.floor(cas)) + "kt"
                } for t, alt, cas in zip(
                    content.iloc[:, 2].to_numpy(),
                    content.iloc[:, 5].to_numpy(dtype=float),
                    content.iloc[:, 6].to_numpy(dtype=float),
                )]

                color = [255, 0, 0, 255] if call_sign == "OWNSHIP" else [39, 245, 106, 215]

                trajectory = {
                    "id": call_sign,
                    "position": {"cartographicDegrees": positions},
                    "point": {
                        "pixelSize": 6 if call_sign == "OWNSHIP" else 5,
                        "color": {"rgba": color}
                    },
                    "path": {
                        "leadTime": 0,
                        "trailTime": int(max(0, self.czml_trail_seconds)),
                        "distanceDisplayCondition": {"distanceDisplayCondition": [0, 1500000]},
                    },
                    "label": {
                        "text": label,
                        "font": "9px sans-serif",
                        "horizontalOrigin": "LEFT",
                        "pixelOffset": {"cartesian2": [20, 20]},
                        "distanceDisplayCondition": {"distanceDisplayCondition": [0, 1500000]},
                        "showBackground": "false",
                        "backgroundColor": {"rgba": [0, 0, 0, 50]},
                    }
                }
                document.append(trajectory)

        if self._last_player_state:
            p = self._last_player_state

            sim_now = self.start_time + timedelta(seconds=self.global_time)

            lon = float(p["lon"])
            lat = float(p["lat"])
            alt = float(p["alt_m"])
            spd = float(p["spd"])

            label_text = f"OWNSHIP\n{int(Unit.m2ft(alt))}ft  {float(spd)} kt"

            document.append({
                "id": "OWNSHIP",

                "position": {
                    "epoch": sim_now.isoformat(),
                    "cartographicDegrees": [
                        0, lon, lat, alt
                    ]
                },

                "point": {
                    "pixelSize": 6,
                    "color": {"rgba": [255, 0, 0, 255]}
                },

                "label": {
                    "text": label_text,
                    "font": "9px sans-serif",
                    "horizontalOrigin": "LEFT",
                    "pixelOffset": {"cartesian2": [20, 20]},
                    "distanceDisplayCondition": {"distanceDisplayCondition": [0, 1500000]},
                    "showBackground": True,
                    "backgroundColor": {"rgba": [0, 0, 0, 50]},
                },

                "path": {
                    "leadTime": 0,
                    "trailTime": int(max(0, self.czml_trail_seconds)),
                    "distanceDisplayCondition": {"distanceDisplayCondition": [0, 1500000]},
                }
            })

        # Graph data (optional)
        graph_data = []
        if self.graph_type != "None":
            try:
                df = pd.read_csv(self.file_path)
                for _id in df["id"].unique():
                    content = df[df["id"] == _id]
                    graph_data.append({
                        "x": content["timestep"].to_list(),
                        "y": content[self.graph_type].to_list(),
                        "name": content.iloc[0]["callsign"],
                        "type": "scattergl",
                        "mode": "lines",
                    })
            except Exception as e:
                print("Graph generation failed:", e)

        # progress:
        # - finite run => true progress
        # - endless run => "window progress" 0..1
        if self.end_time is not None and self.end_time > 0:
            progress_value = min(1.0, max(0.0, self.global_time / float(self.end_time)))
        else:
            window_len = (clock_end - clock_start).total_seconds()
            progress_value = 0.0 if window_len <= 0 else (sim_now - clock_start).total_seconds() / window_len

        socketio.emit("simulationData", {
            "czml": document,
            "progress": progress_value,
            "packet_id": self.packet_id,
            "graph": graph_data
        })
        self.packet_id += 1
