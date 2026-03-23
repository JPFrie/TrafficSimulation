import numpy as np
import pandas as pd
from pathlib import Path
from zipfile import ZipFile
import csv
import heapq

from airtrafficsim.utils.calculation import Cal


class Nav:
    """
    Nav class to provide navigation data from x-plane 11.

    Attributes
    ----------
    Nav.fix : pandas.dataframe
        Fixes data https://developer.x-plane.com/wp-content/uploads/2019/01/XP-FIX1101-Spec.pdf

    Nav.nav : pandas.dataframe
        Radio navigation aid data https://developer.x-plane.com/wp-content/uploads/2020/03/XP-NAV1150-Spec.pdf

    Nav.airway : pandas.dataframe
        Airway data https://developer.x-plane.com/wp-content/uploads/2019/01/XP-AWY1101-Spec.pdf

    Nav.holding : pandas.dataframe
        Holding procedures data https://developer.x-plane.com/wp-content/uploads/2018/12/XP-HOLD1140-Spec.pdf

    Nav.min_off_route_alt : pandas.dataframe
        Minimum off route grid altitudes https://developer.x-plane.com/wp-content/uploads/2020/03/XP-MORA1150-Spec.pdf

    Nav.min_sector_alt : pandas.dataframe
        Minimum sector altitudes for navaids, fixes, airports and runway threshold https://developer.x-plane.com/wp-content/uploads/2020/03/XP-MSA1150-Spec.pdf

    Nav.airports : pandas.dataframe
        Airports data (extracted to contain only runway coordinates) https://developer.x-plane.com/article/airport-data-apt-dat-file-format-specification/

    Notes
    -----
    https://developer.x-plane.com/docs/data-development-documentation/

    https://developer.x-plane.com/article/navdata-in-x-plane-11/
    """
    
    # Install navigation data
    if not Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/').is_dir():
        # Create directories
        Path(__file__).parent.parent.resolve().joinpath(
            './data/navigation/xplane/airports').mkdir(parents=True)

        # Unzip files
        print("Unzipping X-plane navigation data.")
        ZipFile(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane_default_data.zip')
                ).extractall(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/'))

        # Extract apt.dat to runways.csv and individual csv in xplane/airports/
        print("Unpacking airport data (apt.dat). This will take a while...")
        airport = []
        icao = ""
        alt = 0.0

        runways = []
        with open(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/apt.dat'), 'r') as file:
            # Skip 3 lines
            next(file)
            next(file)
            next(file)
            # Loop through all files
            for line in file:
                row = line.split()
                if row:
                    # If row code equals to airport
                    if row[0] in ("1", "16", "17", "99"):
                        # Write previous airport
                        if not icao == "":
                            print(
                                "\r"+"Extracting information from airport "+icao, end="", flush=True)
                            with open(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/airports', icao+'.csv'), 'w') as f:
                                f.writelines(airport)
                        # Reset if not the end
                        if not row[0] == "99":
                            icao = row[4]
                            alt = row[1]
                            airport = []
                    # If row code equals to land runway
                    if row[0] == "100":
                        for i in range(8, len(row), 9):
                            runways.append([icao]+row[i:i+3]+[alt])
                    # If row code equals to water runway
                    if row[0] == "101":
                        for i in range(3, len(row), 3):
                            runways.append([icao]+row[i:i+3]+[alt])
                    # If row code equals to helipad runway
                    if row[0] == "102":
                        runways.append([icao]+row[1:4]+[alt])
                    # Add data line to cache
                    airport.append(line)

        # Write saved runway data to airports.csv
        print("\nExporting airport runways data.")
        with open(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/airports.csv'), 'w') as f:
            writer = csv.writer(f)
            writer.writerows(runways)
        del airport
        del icao
        del runways

    # Static variables
    print("Reading NAV data...")
    fix = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/earth_fix.dat'), delimiter='\s+', skiprows=3, header=None)
    """Fixes data https://developer.x-plane.com/wp-content/uploads/2019/01/XP-FIX1101-Spec.pdf"""
    nav = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath('./data/navigation/xplane/earth_nav.dat'),
                      delimiter='\s+', skiprows=3, header=None, names=np.arange(0, 18), low_memory=False).apply(pd.to_numeric, errors='ignore')
    """Radio navigation data https://developer.x-plane.com/wp-content/uploads/2020/03/XP-NAV1150-Spec.pdf"""
    airway = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/earth_awy.dat'), delimiter='\s+', skiprows=3, header=None)
    """Airway data https://developer.x-plane.com/wp-content/uploads/2019/01/XP-AWY1101-Spec.pdf"""
    holding = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/earth_hold.dat'), delimiter='\s+', skiprows=3, header=None)
    """Holding data https://developer.x-plane.com/wp-content/uploads/2018/12/XP-HOLD1140-Spec.pdf"""
    min_off_route_alt = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/earth_mora.dat'), delimiter='\s+', skiprows=3, header=None)
    """Minimum off route grid altitudes https://developer.x-plane.com/wp-content/uploads/2020/03/XP-MORA1150-Spec.pdf"""
    min_sector_alt = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/earth_msa.dat'), delimiter='\s+', skiprows=3, header=None, names=np.arange(0, 26))
    """Minimum sector altitudes for navaids, fixes, airports and runway threshold https://developer.x-plane.com/wp-content/uploads/2020/03/XP-MSA1150-Spec.pdf"""
    airports = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
        './data/navigation/xplane/airports.csv'), header=None)
    """Airports data (extracted to contain only runway coordinates) https://developer.x-plane.com/article/airport-data-apt-dat-file-format-specification/"""

    taxi_nodes = None
    taxi_edges = None
    taxi_active = None

    taxi_loaded = False

    taxi_graph_cache = {}

    @staticmethod
    def get_wp_coord(name, lat, long):
        """
        Get the nearest waypoint (fix and navaid) coordinate given name.

        Parameters
        ----------
        name : String
            ICAO name of the waypoint (max 5 chars)

        lat : float
            Latitude of current position

        long : float
            Longitude of current position

        Returns
        -------
        lat, Long: float, float
            Latitude and Longitude of the waypoint
        """
        # Find lat and long of all fixes that match the name
        mask = Nav.fix[2].to_numpy() == name
        fix_lat = Nav.fix[0].to_numpy()[mask]
        fix_long = Nav.fix[1].to_numpy()[mask]
        # Find lat and long of all navaids that match the name
        mask = Nav.nav[7].to_numpy() == name
        nav_lat = Nav.nav[1].to_numpy()[mask]
        nav_long = Nav.nav[2].to_numpy()[mask]
        # Combine fix and nav
        wp_lat = np.append(fix_lat, nav_lat)
        wp_long = np.append(fix_long, nav_long)
        # Find index of minimum distance
        index = np.argmin(Cal.cal_great_circle_dist(
            lat, long, wp_lat, wp_long), axis=0)
        return wp_lat[index], wp_long[index]

    @staticmethod
    def get_wp_in_area(lat1, long1, lat2, long2):
        """
        Get all waypoints(fix, navaids) within area

        Parameters
        ----------
        lat1 : float
            Latitude 1 of area (South)
        long1 : float
            Longitude 1 of area (West)
        lat2 : float
            Latitude 2 of area (North)
        long2 : float
            Longitude 2 of area (East)

        Returns
        -------
        [lat, long, name] : [float[], float[], string[]]
            [Latitude, Longitude, Name] array of all waypoints in the area
        """
        if lat1 < lat2 and long1 < long2:
            # If normal condition
            fix = Nav.fix[(Nav.fix.iloc[:, 0].between(lat1, lat2)) & (
                Nav.fix.iloc[:, 1].between(long1, long2))].iloc[:, 0:3].to_numpy()
            nav = Nav.nav[(Nav.nav.iloc[:, 1].between(lat1, lat2)) & (
                Nav.nav.iloc[:, 2].between(long1, long2))].iloc[:, [1, 2, 7]].to_numpy()
        elif lat1 < lat2 and long1 > long2:
            # If long1 = 170 and long2 = -170
            fix = Nav.fix[(Nav.fix.iloc[:, 0].between(lat1, lat2)) & (Nav.fix.iloc[:, 1].between(
                long1, 180.0) | Nav.fix.iloc[:, 1].between(-180.0, long2))].iloc[:, 0:3].to_numpy()
            nav = Nav.nav[(Nav.nav.iloc[:, 1].between(lat1, lat2)) & (Nav.nav.iloc[:, 2].between(
                long1, 180.0) | Nav.nav.iloc[:, 2].between(-180.0, long2))].iloc[:, [1, 2, 7]].to_numpy()
        elif lat1 > lat2 and long1 < long2:
            # If lat1 = 80 and lat2 = -80
            fix = Nav.fix[(Nav.fix.iloc[:, 0].between(lat1, 90.0) | Nav.fix.iloc[:, 0].between(
                lat1, -90.0)) & (Nav.fix.iloc[:, 1].between(long1, long2))].iloc[:, 0:3].to_numpy()
            nav = Nav.nav[(Nav.nav.iloc[:, 1].between(lat1, 90.0) | Nav.nav.iloc[:, 1].between(
                lat1, -90.0)) & (Nav.nav.iloc[:, 2].between(long1, long2))].iloc[:, [1, 2, 7]].to_numpy()
        else:
            # If lat1 = 80 and lat2 = -80 and if long1 = 170 and long2 = -170
            fix = Nav.fix[(Nav.fix.iloc[:, 0].between(lat1, 90.0) | Nav.fix.iloc[:, 0].between(lat1, -90.0)) & (
                Nav.fix.iloc[:, 1].between(long1, 180.0) | Nav.fix.iloc[:, 1].between(-180.0, long2))].iloc[:, 0:3].to_numpy()
            nav = Nav.nav[(Nav.nav.iloc[:, 1].between(lat1, 90.0) | Nav.nav.iloc[:, 1].between(lat1, -90.0)) & (
                Nav.nav.iloc[:, 2].between(long1, 180.0) | Nav.nav.iloc[:, 2].between(-180.0, long2))].iloc[:, [1, 2, 7]].to_numpy()
        return np.vstack((fix, nav))

    @staticmethod
    def get_runway_coord(airport, runway):
        """
        Get runway coordinate

        Parameters
        ----------
        airport : string
            ICAO code of the airport

        runway: string
            Runway name (RW07L).

        Returns
        -------
        (lat, Long, alt): (float, float, float)
            Latitude, Longitude, and Altitude of the runway end
        """
        # TODO: Convert MSL to Geopotentail altitude
        airport = Nav.airports[(Nav.airports[0].to_numpy() == airport)]
        return tuple(airport[airport[1].str.contains(runway)].iloc[0, 2:5])

    @staticmethod
    def find_closest_airport_runway(lat, long):
        """
        Find the closest runway and airport given lat long.

        Parameters
        ----------
        lat : float
            Latitude
        long : float
            Longitude

        Returns
        -------
        Airport : string
            ICAO code of airport
        Runway : string
            Runway Name
        """
        tmp = Nav.airports[(Nav.airports.iloc[:, 2].between(
            lat-0.1, lat+0.1)) & (Nav.airports.iloc[:, 3].between(long-0.1, long+0.1))]
        dist = Cal.cal_great_circle_dist(
            tmp.iloc[:, 2].to_numpy(), tmp.iloc[:, 3].to_numpy(), lat, long)
        return tmp.iloc[np.argmin(dist)].tolist()

    @staticmethod
    def get_airport_procedures(airport, procedure_type):
        """
        Get instrument procedures of an airport.

        Parameters
        ----------
        airport : string
            ICAO code of the airport

        procedure_type : string
            Procedure type (SID/STAR/APPCH)

        Returns
        -------
        procedure_names : string []
            Names of all procedures of the airport
        """
        procedures = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
            './data/navigation/xplane/CIFP/'+airport+'.dat'), header=None)
        return procedures[procedures[0].str.contains(procedure_type)][2].unique()

    @staticmethod
    def get_procedure(airport, runway, procedure, appch="", iaf=""):
        """
        Get the details of standard instrument procedure

        Parameters
        ----------
        airport : string
            ICAO code of the airport

        runway: string
            Runway name (RW07L) for SID/STAR.

        procedure : string
            Procedure name of SID/STAR/APPCH (XXXX7A)
            For Approach: ILS = I07C, Localliser = L25L, RNAV = R25LY/Z

        appch : string
            Approach procedure type (A = initial approach, I = ILS, "" = None)

        iaf : string
            Initial approach fix (Please provide when appch = A)

        Returns
        -------
        Waypoint names : string []
            Waypoint names array

        Altitude restriction type : float []
            Altitude restriction type (+, =, -)

        Altitude restriction : float []
            Altitude restriction 1 

        Altitude restriction : float []
            Altitude restriction 2

        Speed restriction type : float []
            Speed restriction type (+, =, -)

        Speed restriction : float []
            Speed restriction

        Note
        ----
            Terminal procedures (SID/STAR/Approach/Runway) https://developer.x-plane.com/wp-content/uploads/2019/01/XP-CIFP1101-Spec.pd f
            https://wiki.flightgear.org/User:Www2/XP11_Data_Specification
        """
        procedures = pd.read_csv(Path(__file__).parent.parent.resolve().joinpath(
            './data/navigation/xplane/CIFP/'+airport+'.dat'), header=None)

        if appch == "":
            # SID/STAR
            procedure_df = procedures[(procedures[2] == procedure) & (
                procedures[3].str.contains(runway))]
            if procedure_df.empty:
                procedure_df = procedures[procedures[2] == procedure]
        elif appch == "A":
            # Initial Approach
            procedure_df = procedures[(procedures[1] == appch) & (
                procedures[2] == procedure) & (procedures[3] == iaf)]
        elif appch == "I":
            # Final Approach
            procedure_df = procedures[(procedures[1] == appch) & (
                procedures[2] == procedure)]

        # Remove missed approach waypoints
        index = procedure_df[procedure_df[8].str.contains('M')].index
        if len(index) > 0:
            procedure_df = procedure_df.loc[:index[0]-1, :]

        alt_restriction_1 = []
        alt_restriction_2 = []
        speed_restriction = []

        for val in procedure_df[23].values:
            if "FL" in val:
                alt_restriction_1.append(float(val.replace("FL", ""))*100.0)
            else:
                if val == "     ":
                    alt_restriction_1.append(-1)
                else:
                    alt_restriction_1.append(float(val))

        for val in procedure_df[24].values:
            if "FL" in val:
                alt_restriction_2.append(float(val.replace("FL", ""))*100.0)
            else:
                if val == "     ":
                    alt_restriction_2.append(-1)
                else:
                    alt_restriction_2.append(float(val))

        for val in procedure_df[27].values:
            if val == "   ":
                speed_restriction.append(-1)
            else:
                speed_restriction.append(float(val))

        # Assume a lowest alt restriction
        alt_restriction = np.where(np.array(alt_restriction_2) != -1, np.minimum(
            alt_restriction_1, alt_restriction_2), alt_restriction_1)

        return procedure_df[4].values.tolist(), procedure_df[22].values.tolist(), alt_restriction, procedure_df[26].values.tolist(), speed_restriction

    @staticmethod
    def get_holding_procedure(fix, region):
        """
        Get holding procedure.

        Parameters
        ----------
        fix : string
            Fix name
        region : string
            ICAO region

        Returns
        -------
        [inbound holding course, legtime, leg length, direction, min alt, max alt, speed] : []

        Note
        ----
        https://developer.x-plane.com/wp-content/uploads/2018/12/XP-HOLD1140-Spec.pdf
        """
        holding = Nav.holding[(Nav.holding[1] == region)
                              & (Nav.holding[0] == fix)]
        return holding.iloc[0, :].tolist()

    @staticmethod
    def load_taxi_network():

        if Nav.taxi_nodes is not None:
            return

        nodes = []
        edges = []
        restrictions = []

        apt_path = Path(__file__).parent.parent.resolve().joinpath(
            "./data/navigation/xplane/apt.dat"
        )

        with open(apt_path, "r") as file:

            next(file); next(file); next(file)

            current_airport = ""
            in_network = False
            current_edge = None
            edge_id = 0

            for line in file:

                row = line.strip().split()

                if not row:
                    continue

                code = row[0]

                if code in ("1", "16", "17"):
                    current_airport = row[4]
                    in_network = False
                    continue

                if code == "1200":
                    in_network = True
                    continue

                if not in_network:
                    continue

                # -----------------------------
                # TAXI NODE
                # -----------------------------
                if code == "1201":

                    lat = float(row[1])
                    lon = float(row[2])
                    node_type = row[3]
                    node_id = int(row[4])

                    nodes.append([
                        current_airport,
                        node_id,
                        lat,
                        lon,
                        node_type
                    ])

                # -----------------------------
                # TAXI EDGE
                # -----------------------------
                elif code == "1202":

                    start = int(row[1])
                    end = int(row[2])
                    edge_type = row[4]
                    name = row[5] if len(row) > 5 else ""

                    size = None
                    if "_" in edge_type:
                        edge_type, size = edge_type.split("_")

                    edges.append([
                        edge_id,
                        current_airport,
                        start,
                        end,
                        edge_type,
                        size,
                        name
                    ])
                    current_edge = edge_id
                    edge_id += 1

                # -----------------------------
                # ACTIVE ZONE
                # -----------------------------
                elif code == "1204":

                    if current_edge is None:
                        continue

                    restrictions.append([
                        current_edge,
                        row[1],
                        row[2:]
                    ])

        Nav.taxi_nodes = pd.DataFrame(
            nodes,
            columns=["airport", "node", "lat", "lon", "type"]
        )

        Nav.taxi_edges = pd.DataFrame(
            edges,
            columns=["edge_id", "airport", "start", "end", "type", "size", "name"]
        )

        Nav.taxi_active = pd.DataFrame(
            restrictions,
            columns=["edge_id", "restriction", "runways"]
        )

        print("Taxi network loaded")

    @staticmethod
    def _nearest_node(airport, lat, lon):

        nodes = Nav.taxi_nodes[Nav.taxi_nodes["airport"] == airport]

        coords = nodes[["lat", "lon"]].to_numpy()
        ids = nodes["node"].to_numpy()

        dlat = coords[:,0] - lat
        dlon = coords[:,1] - lon

        dist = dlat*dlat + dlon*dlon

        return ids[np.argmin(dist)]
    
    def _nearest_connected_node(airport, lat, lon):
        nodes = Nav.taxi_nodes[Nav.taxi_nodes["airport"] == airport]
        edges = Nav.taxi_edges[Nav.taxi_edges["airport"] == airport]

        connected = set(edges["start"]).union(set(edges["end"]))

        nodes = nodes[nodes["node"].isin(connected)]

        coords = nodes[["lat","lon"]].to_numpy()
        ids = nodes["node"].to_numpy()

        dist = Cal.cal_great_circle_dist(
            lat, lon,
            coords[:,0],
            coords[:,1]
        )

        return ids[np.argmin(dist)]

    @staticmethod
    def _build_graph(airport, aircraft_size=None, allow_crossing=True):

        key = (airport, aircraft_size, allow_crossing)

        if key in Nav.taxi_graph_cache:
            return Nav.taxi_graph_cache[key]

        nodes = Nav.taxi_nodes[Nav.taxi_nodes["airport"] == airport]
        edges = Nav.taxi_edges[Nav.taxi_edges["airport"] == airport]

        node_dict = {
            row["node"]: (row["lat"], row["lon"])
            for _, row in nodes.iterrows()
        }

        graph = {}

        for _, row in edges.iterrows():

            # Aircraft size restriction
            if aircraft_size and row["size"]:
                if row["size"] > aircraft_size:
                    continue
            
            # Runway crossing restriction
            if "runway" in row["type"]:
                continue

            n1 = row["start"]
            n2 = row["end"]

            if n1 not in node_dict or n2 not in node_dict:
                continue

            lat1, lon1 = node_dict[n1]
            lat2, lon2 = node_dict[n2]

            dist = Cal.cal_great_circle_dist(lat1, lon1, lat2, lon2)

            if row["type"] == "runway":
                dist *= 10000

            graph.setdefault(n1, []).append((n2, dist))
            graph.setdefault(n2, []).append((n1, dist))

        Nav.taxi_graph_cache[key] = (graph, node_dict)
        return graph, node_dict
    
    @staticmethod
    def _astar(graph, node_dict, start, goal):

        def heuristic(a, b):
            lat1, lon1 = node_dict[a]
            lat2, lon2 = node_dict[b]
            return Cal.cal_great_circle_dist(lat1, lon1, lat2, lon2)

        open_set = [(0, start)]
        g_score = {start: 0}
        parent = {}

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == goal:
                break

            for neighbor, weight in graph.get(current, []):
                tentative = g_score[current] + weight

                if neighbor not in g_score or tentative < g_score[neighbor]:
                    g_score[neighbor] = tentative
                    f = tentative + heuristic(neighbor, goal)
                    parent[neighbor] = current
                    heapq.heappush(open_set, (f, neighbor))

        path = []
        while goal in parent:
            path.append(goal)
            goal = parent[goal]

        path.append(start)
        return path[::-1]

    @staticmethod
    def detect_hold_short(airport, path):

        holds = []

        for i in range(len(path)-1):

            start = path[i]
            end = path[i+1]

            edge = Nav.taxi_edges[
                (Nav.taxi_edges["airport"] == airport) &
                (Nav.taxi_edges["start"] == start) &
                (Nav.taxi_edges["end"] == end)
            ]

            if edge.empty:
                continue

            edge_id = edge.iloc[0]["edge_id"]

            active = Nav.taxi_active[
                Nav.taxi_active["edge_id"] == edge_id
            ]

            if not active.empty:
                holds.append(start)

        return holds
    
    def _runway_entry_nodes(airport):
        edges = Nav.taxi_edges[
            (Nav.taxi_edges["airport"] == airport) &
            (Nav.taxi_edges["type"] == "runway")
        ]

        runway_nodes = set(edges["start"]).union(set(edges["end"]))

        taxi_nodes = Nav.taxi_nodes[
            Nav.taxi_nodes["airport"] == airport
        ]

        # Nodes die mit runway verbunden sind
        entry_nodes = taxi_nodes[
            taxi_nodes["node"].isin(runway_nodes)
        ]

        return entry_nodes
    
    @staticmethod
    def _nearest_runway_entry(airport, runway):

        rwy_lat, rwy_lon, _ = Nav.get_runway_coord(airport, runway)

        edges = Nav.taxi_edges[
            Nav.taxi_edges["airport"] == airport
        ]

        # alle Runway Edges
        runway_edges = edges[edges["type"] == "runway"]

        runway_nodes = set(runway_edges["start"]).union(set(runway_edges["end"]))

        # alle Taxiway Edges
        taxi_edges = edges[edges["type"] == "taxiway"]

        taxi_nodes = set(taxi_edges["start"]).union(set(taxi_edges["end"]))

        # Taxi Nodes die mit Runway verbunden sind
        entry_nodes = taxi_nodes.intersection(runway_nodes)

        nodes = Nav.taxi_nodes[
            (Nav.taxi_nodes["airport"] == airport) &
            (Nav.taxi_nodes["node"].isin(entry_nodes))
        ]

        coords = nodes[["lat","lon"]].to_numpy()
        ids = nodes["node"].to_numpy()

        dist = Cal.cal_great_circle_dist(
            rwy_lat,
            rwy_lon,
            coords[:,0],
            coords[:,1]
        )
        return ids[np.argmin(dist)]
    
    @staticmethod
    def simulate_pushback(airport, gate_lat, gate_lon):

        node = Nav._nearest_node(airport, gate_lat, gate_lon)

        row = Nav.taxi_nodes[
            (Nav.taxi_nodes["airport"] == airport) &
            (Nav.taxi_nodes["node"] == node)
        ].iloc[0]

        return [
            (gate_lat, gate_lon),
            (row["lat"], row["lon"])
        ]

    @staticmethod
    def taxi_between_points(
        airport,
        start_lat,
        start_lon,
        end_lat,
        end_lon,
        aircraft_size=None,
        allow_crossing=True
    ):

        graph, node_dict = Nav._build_graph(
            airport,
            aircraft_size,
            allow_crossing
        )

        start = Nav._nearest_connected_node(airport, start_lat, start_lon)
        end = Nav._nearest_node(airport, end_lat, end_lon)
        path = Nav._astar(graph, node_dict, start, end)

        holds = Nav.detect_hold_short(airport, path)

        coords = [node_dict[n] for n in path]

        return {
            "route": coords,
            "hold_short_nodes": holds
        }
    
    @staticmethod
    def taxi_position_to_runway(airport, lat, lon, runway):

        graph, node_dict = Nav._build_graph(airport)

        start = Nav._nearest_connected_node(airport, lat, lon)
        end = Nav._nearest_runway_entry(airport, runway)

        path = Nav._astar(graph, node_dict, start, end)

        holds = Nav.detect_hold_short(airport, path)

        coords = [node_dict[n] for n in path]

        return {
            "route": coords,
            "hold_short_nodes": holds
        }

    @staticmethod
    def taxi_position_to_gate(airport, lat, lon, gate):
        gate_lat, gate_lon = Nav.get_gate_position(airport, gate)
        return Nav.taxi_between_points(airport, lat, lon, gate_lat, gate_lon)

    @staticmethod
    def taxi_gate_to_runway(airport, gate, runway):
        gate_lat, gate_lon = Nav.get_gate_position(airport, gate)
        rwy_lat, rwy_lon, _ = Nav.get_runway_coord(airport, runway)
        return Nav.taxi_between_points(airport, gate_lat, gate_lon, rwy_lat, rwy_lon)

    @staticmethod
    def taxi_runway_to_gate(airport, runway, gate):
        rwy_lat, rwy_lon, _ = Nav.get_runway_coord(airport, runway)
        gate_lat, gate_lon = Nav.get_gate_position(airport, gate)
        return Nav.taxi_between_points(airport, rwy_lat, rwy_lon, gate_lat, gate_lon)
    
    @staticmethod
    def get_gate_position(airport, gate_name):

        with open(Path(__file__).parent.parent.resolve().joinpath(
            './data/navigation/xplane/apt.dat'), 'r') as file:

            next(file); next(file); next(file)

            current_airport = ""

            for line in file:
                row = line.split()
                if not row:
                    continue

                if row[0] in ("1", "16", "17"):
                    current_airport = row[4]

                if current_airport == airport and row[0] == "1300":

                    if gate_name in line:
                        lat = float(row[1])
                        lon = float(row[2])
                        heading = float(row[3])
                        heading = (heading + 360) % 360
                        return lat, lon, heading

        raise ValueError("Gate not found")
    
    @staticmethod
    def get_all_gates(airport):

        gates = []

        with open(Path(__file__).parent.parent.resolve().joinpath(
            './data/navigation/xplane/apt.dat'), 'r') as file:

            next(file); next(file); next(file)

            current_airport = ""

            for line in file:
                row = line.split()
                if not row:
                    continue

                if row[0] in ("1", "16", "17"):
                    current_airport = row[4]

                if current_airport == airport and row[0] == "1300":
                    gates.append(line.strip())

        return gates