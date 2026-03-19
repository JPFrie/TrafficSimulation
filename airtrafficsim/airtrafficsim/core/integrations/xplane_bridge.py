import json
import os
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Callable


def _detect_windows_host_ip() -> str:
    # WSL2: Windows host is often the nameserver in /etc/resolv.conf
    try:
        with open("/etc/resolv.conf", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("nameserver "):
                    return line.split()[1].strip()
    except Exception:
        pass
    return "127.0.0.1"


class XPlaneBridgeConfig:
    def __init__(
        self,
        xplane_host: Optional[str] = "192.168.178.159",
        xplane_port: int = 5005,     # WSL -> X-Plane plugin
        player_rx_port: int = 5006,  # X-Plane plugin -> WSL
        hz: float = 20.0,
        max_udp_bytes: int = 1200,   # safe-ish for typical MTU (avoid fragmentation)
    ):
        # Prefer explicit host, then env, then WSL nameserver detection
        self.xplane_host = (
            xplane_host
            or os.environ.get("XPLANE_HOST")
            or _detect_windows_host_ip()
        )

        # If you *know* your Windows LAN IP works, you can still override it outside:
        # cfg = XPlaneBridgeConfig(xplane_host="192.168.178.159", ...)

        self.xplane_port = int(os.environ.get("XPLANE_UDP_PORT", xplane_port))
        self.player_rx_port = int(os.environ.get("PLAYER_RX_PORT", player_rx_port))
        self.hz = float(os.environ.get("BRIDGE_HZ", hz))
        self.max_udp_bytes = int(os.environ.get("BRIDGE_MAX_UDP_BYTES", max_udp_bytes))


class XPlaneBridge:
    """
    - get_snapshot(): returns latest list of aircraft dicts for X-Plane
    - on_player_state(player_dict): called when player feedback arrives

    TX format (WSL -> X-Plane plugin): newline-separated CSV rows
      CALLSIGN,MODEL,lat,lon,alt_ft,hdg,pitch,roll

    RX format (X-Plane plugin -> WSL): JSON
      {"player": {...}}
    """

    def __init__(
        self,
        cfg: XPlaneBridgeConfig,
        get_snapshot: Callable[[], List[Dict[str, Any]]],
        on_player_state: Callable[[Dict[str, Any]], None],
        log: Callable[[str], None] = print,
    ):
        self.cfg = cfg
        self.get_snapshot = get_snapshot
        self.on_player_state = on_player_state
        self.log = log

        self._tx: Optional[socket.socket] = None
        self._rx: Optional[socket.socket] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_hb = 0.0

    # -------------------------
    # socket lifecycle helpers
    # -------------------------
    def _open_sockets(self):
        # TX
        self._tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # not strictly needed for UDP TX, but harmless:
        self._tx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # RX (player feedback)
        self._rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._rx.bind(("0.0.0.0", self.cfg.player_rx_port))
        self._rx.setblocking(False)

    def _close_sockets(self):
        if self._rx:
            try:
                self._rx.close()
            except Exception as e:
                self.log(f"[XPlaneBridge] rx close failed: {e}")
            self._rx = None

        if self._tx:
            try:
                self._tx.close()
            except Exception as e:
                self.log(f"[XPlaneBridge] tx close failed: {e}")
            self._tx = None

    # -------------------------
    # public controls
    # -------------------------
    def start(self):
        if self._running:
            return

        # (Re)create sockets on each start so restart-after-stop works reliably
        self._open_sockets()

        self._running = True
        self._thread = threading.Thread(target=self._loop, name="XPlaneBridge", daemon=True)
        self._thread.start()

        self.log(
            f"[XPlaneBridge] started tx->{self.cfg.xplane_host}:{self.cfg.xplane_port}, "
            f"rx<-0.0.0.0:{self.cfg.player_rx_port}, hz={self.cfg.hz}, max_udp_bytes={self.cfg.max_udp_bytes}"
        )

    def stop(self):
        """
        Stop thread AND close sockets so the UDP port is released.
        Safe to call multiple times.
        """
        self._running = False

        if self._thread:
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
            self._thread = None

        self._close_sockets()
        self.log("[XPlaneBridge] stopped (sockets closed)")

    # -------------------------
    # RX: player feedback (JSON)
    # -------------------------
    def _poll_player(self) -> Optional[Dict[str, Any]]:
        if not self._rx:
            return None
        try:
            data, _ = self._rx.recvfrom(65535)
            return json.loads(data.decode("utf-8", errors="replace"))
        except BlockingIOError:
            return None
        except Exception as e:
            self.log(f"[XPlaneBridge] bad player packet: {e}")
            return None

    # -------------------------
    # TX: aircraft snapshot (CSV lines)
    # -------------------------
    @staticmethod
    def _pick(d: Dict[str, Any], keys: List[str], default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    def _aircraft_to_csv_line(self, a: Dict[str, Any]) -> Optional[str]:
        """
        Converts one aircraft dict into:
          CALLSIGN,MODEL,lat,lon,alt_ft,hdg,pitch,roll
        Returns None if missing required fields.
        """
        #self.log(a)
        callsign = self._pick(a, ["callsign", "call_sign", "id", "cs"])
        if not callsign:
            return None

        model = self._pick(a, ["model"], "A320")

        lat = self._pick(a, ["lat", "latitude"])
        lon = self._pick(a, ["lon", "long", "longitude"])
        alt_ft = self._pick(a, ["alt_ft", "altitude_ft", "alt", "altitude"])
        hdg = self._pick(a, ["hdg_deg","hdg", "heading", "trk", "track"], 0.0)
        
        if lat is None or lon is None or alt_ft is None:
            return None

        cas = self._pick(a, ["cas"], 0.0)
        pitch = self._pick(a, ["pitch"], 0.0)
        tas = self._pick(a, ["tas"], 0.0)
        vs = self._pick(a, ["vs"], 0.0)
        gs_north_mps = self._pick(a, ["gs_north_mps"], 0.0)
        gs_east_mps = self._pick(a, ["gs_east_mps"], 0.0)
        trk = self._pick(a, ["trk"], 0.0)
        bank = self._pick(a, ["bank"], 0.0)

        # Ensure float formatting is consistent and parseable
        return f"{callsign},{model},{float(lat):.8f},{float(lon):.8f},{float(alt_ft):.2f},{float(hdg):.2f},{float(cas):.2f},{float(pitch):.2f},{float(tas):.2f},{float(vs):.2f},{float(gs_north_mps):.2f},{float(gs_east_mps):.2f},{float(trk):.2f},{float(bank):.2f}"

    def _send_aircraft(self, aircraft: List[Dict[str, Any]]):
        """
        Sends aircraft as newline-separated CSV.
        Splits into multiple UDP packets if necessary.
        """
        TEST_PORT = 5007 
        if not self._tx:
            return

        lines: List[str] = []
        for a in aircraft:
            line = self._aircraft_to_csv_line(a)
            if line:
                lines.append(line)

        if not lines:
            self.log(f"[XPlaneBridge] NO LINES -> aircraft_in={len(aircraft)} (nothing sent)")
            if aircraft:
                # zeig 1 Beispielobjekt, damit wir sehen welche Keys wirklich drin sind
                self.log(f"[XPlaneBridge] sample aircraft keys={list(aircraft[0].keys())} data={aircraft[0]}")
            return

        # Packetize to avoid exceeding MTU / losing packets due to fragmentation
        max_bytes = max(200, self.cfg.max_udp_bytes)

        packet = ""
        for line in lines:
            candidate = packet + line + "\n"
            if len(candidate.encode("utf-8")) > max_bytes and packet:
                self._tx.sendto(packet.encode("utf-8"), (self.cfg.xplane_host, self.cfg.xplane_port))
                self._tx.sendto(packet.encode("utf-8"), (self.cfg.xplane_host, TEST_PORT))
                # self.log(f"[XPlaneBridge] sent {len(aircraft)} aircraft DATA")
                packet = line + "\n"
            else:
                packet = candidate

        if packet:
            self._tx.sendto(packet.encode("utf-8"), (self.cfg.xplane_host, self.cfg.xplane_port))
            #self._tx.sendto(packet.encode("utf-8"), (self.cfg.xplane_host, TEST_PORT)) // only for debug purposes
            #self.log(f"[XPlaneBridge] sent {len(aircraft)} aircraft DATA")
            #self.log(packet)

    # -------------------------
    # thread loop
    # -------------------------
    def _loop(self):
        dt = 1.0 / max(1.0, self.cfg.hz)

        while self._running:
            t0 = time.time()

            # 1) player feedback (JSON)
            msg = self._poll_player()
            if msg and "player" in msg:
                try:
                    self.on_player_state(msg["player"])
                except Exception as e:
                    self.log(f"[XPlaneBridge] on_player_state failed: {e}")

            # 2) send aircraft snapshot (CSV)
            if hasattr(self, "update_snapshot"):
                try:
                    self.update_snapshot()
                except Exception as e:
                    self.log(f"[XPlaneBridge] snapshot update failed: {e}")

            # 3) send aircraft snapshot
            try:
                aircraft = self.get_snapshot()
            except Exception as e:
                self.log(f"[XPlaneBridge] get_snapshot failed: {e}")
                aircraft = []

            try:
                self._send_aircraft(aircraft)
            except Exception as e:
                self.log(f"[XPlaneBridge] send failed: {e}")

            # heartbeat log
            if t0 - self._last_hb > 5.0:
                self._last_hb = t0
                self.log(f"[XPlaneBridge] sent {len(aircraft)} aircraft (heartbeat)")

            elapsed = time.time() - t0
            if elapsed < dt:
                time.sleep(dt - elapsed)
