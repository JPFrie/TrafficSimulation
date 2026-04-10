"""
An entry point to the backend of AirTrafficSim.

Attributes:

app : Flask()
    A flask server object.
socketio : SocketIO()
    A SocketIO object for communication.

"""

from pathlib import Path
from importlib import import_module
from flask import Flask, render_template
from flask_socketio import SocketIO
# import eventlet

from airtrafficsim.server.replay import Replay
from airtrafficsim.server.data import Data

# eventlet.monkey_patch()

app = Flask(__name__, static_url_path='', static_folder=Path(__file__).parent.parent.joinpath(
    'data/client/build'), template_folder=str(Path(__file__).parent.parent.joinpath('data/client/build')))
socketio = SocketIO(app, cors_allowed_origins='*', max_http_buffer_size=1e8,
                    ping_timeout=60, async_mode='eventlet', logger=True)  # engineio_logger=True

current_env = None


@socketio.on('connect')
def test_connect():
    """
    Debug function to test whether the client is connected. 
    """
    print('Client connected')


@socketio.on('disconnect')
def test_disconnect():
    """
    Debug function to inform the client is disconnected. 
    """
    print('Client disconnected')


@socketio.on('getReplayDir')
def get_replay_dir():
    """Get the list of directories in data/replay"""
    return Replay.get_replay_dir()


@socketio.on('getReplayCZML')
def get_replay_czml(replayCategory, replayFile):
    """
    Generate a CZML file to client for replaying data.

    Parameters
    ----------
    replayCategory : string
        The category to replay (historic / simulation)
    replayFile : string
        Name of the replay file directory

    Returns
    -------
    {}
        JSON dictionary of the CZML data file
    """
    return Replay.get_replay_czml(replayCategory, replayFile)


@socketio.on('getGraphHeader')
def get_graph_header(mode, replayCategory, replayFile):
    """
    Get the list of parameters name of a file suitable for plotting graph.

    Parameters
    ----------
    mode : string
        AirTrafficSim mode (replay / simulation)
    replayCategory : string
        The category to replay (historic / simulation)
    replayFile : string
        Name of the replay file directory

    Returns
    -------
    string[]
        List of graph headers
    """
    return Replay.get_graph_header(mode, replayCategory, replayFile)


@socketio.on('getGraphData')
def get_graph_data(mode, replayCategory, replayFile, simulationFile, graph):
    """
    Get the data for the selected parameters to plot a graph.

    Parameters
    ----------
    mode : string
        AirTrafficSim mode (replay / simulation)
    replayCategory : string
        The category to replay (historic / simulation)
    replayFile : string
        Name of the replay file directory

    Returns
    -------
    {}
        JSON file for graph data for Plotly.js
    """
    return Replay.get_graph_data(mode, replayCategory, replayFile, simulationFile, graph)


@socketio.on('getSimulationFile')
def get_simulation_file():
    """
    Get the list of files in airtrafficsim/env/

    Returns
    -------
    string[]
        List of simulation environment file names
    """
    simulation_list = []
    for file in sorted(Path(__file__).parent.parent.joinpath('data/environment/').glob('*.py')):
        if file.name != '__init__.py':
            simulation_list.append(file.name.removesuffix('.py'))
    return simulation_list


@socketio.on('runSimulation')
def run_simulation(file):
    """
    Start the simulation given file name.

    Parameters
    ----------
    file : string
        Environment file name
    """
    global current_env

    print(file)
    if file == "ConvertHistoricDemo":
        socketio.emit('loadingMsg', 'Converting historic data to simulation data... <br> Please check the terminal for progress.')
    elif file == "WeatherDemo":
        socketio.emit('loadingMsg', 'Downloading weather data... <br> Please check the terminal for progress.')
    else:
        socketio.emit('loadingMsg', 'Running simulation... <br> Please check the terminal for progress.')   
    socketio.sleep(0)
    Env = getattr(import_module('airtrafficsim.data.environment.'+file, '...'), file)
    #env = Env() # OLD
    current_env = Env() # NEW
    #env.run(socketio) # OLD
    current_env.run(socketio) # NEW


@socketio.on('getNav')
def get_Nav(lat1, long1, lat2, long2):
    """
    Get the navigation waypoint data given

    Parameters
    ----------
    lat1 : float
        Latitude (South)
    long1 : float
        Longitude (West)
    lat2 : float
        Latitude (North)
    long2 : float
        Longitude (East)

    Returns
    -------
    {}
        JSON CZML file of navigation waypoint data
    """
    return Data.get_nav(lat1, long1, lat2, long2)


@socketio.on('getEra5Wind')
def get_era5_wind(lat1, long1, lat2, long2, file, time):
    """
    Get the ERA5 wind data image to client

    Parameters
    ----------
    lat1 : float
        Latitude (South)
    long1 : float
        Longitude (West)
    lat2 : float
        Latitude (North)
    long2 : float
        Longitude (East)

    Returns
    -------
    {}
        JSON CZML file of ERA5 wind data image
    """
    return Data.get_era5_wind(file, lat1, long1, lat2, long2, time)


@socketio.on('getEra5Rain')
def get_era5_rain(lat1, long1, lat2, long2, file, time):
    """
    Get the ERA5 rain data image to client

    Parameters
    ----------
    lat1 : float
        Latitude (South)
    long1 : float
        Longitude (West)
    lat2 : float
        Latitude (North)
    long2 : float
        Longitude (East)

    Returns
    -------
    {}
        JSON CZML file of ERA5 rain data image
    """
    return Data.get_era5_rain(file, lat1, long1, lat2, long2, time)


@socketio.on('getRadarImage')
def get_radar_img(lat1, long1, lat2, long2, file, time):
    """
    Get the radar data image to client

    Parameters
    ----------
    lat1 : float
        Latitude (South)
    long1 : float
        Longitude (West)
    lat2 : float
        Latitude (North)
    long2 : float
        Longitude (East)
    time : string
        Time in ISO format
    file : string
        File name of the radar image

    Returns
    -------
    {}
        JSON CZML file of radar data image
    """
    return Data.get_radar_img(file, lat1, long1, lat2, long2, time)


@app.route("/")
def serve_client():
    """Serve client folder to user"""
    return render_template("index.html")

@socketio.on('setAircraftState')
def set_aircraft_state(data):
    global current_env

    if current_env is None:
        return

    try:
        ac_id = int(data.get("ac_id"))
        heading = float(data.get("heading"))
        altitude = float(data.get("altitude"))
        cas = float(data.get("cas"))
        print(f"[!!!DEBUG] CAS SPEED of {ac_id} is: {cas}")
        #phase = data.get("phase")

        # Aircraft finden
        aircraft = None
        for ac in current_env.aircraft_list:
            if int(ac.index) == ac_id:
                aircraft = ac
                break

        if aircraft is None:
            return

        aircraft.set_heading(heading)
        aircraft.set_alt(altitude)
        aircraft.set_speed(cas)

        #if phase:
        #    from airtrafficsim.utils.enums import FlightPhase
        #    idx = aircraft.index
        #    i = list(current_env.traffic.index).index(idx)
        #    current_env.traffic.flight_phase[i] = FlightPhase[phase]

        print(f"[CONTROL] Aircraft {ac_id} updated")

    except Exception as e:
        print("Error:", e)


@socketio.on('getAircraftList')
def get_aircraft_list():
    global current_env

    if current_env is None:
        socketio.emit('aircraftList', [])
        return

    t = current_env.traffic

    from airtrafficsim.utils.enums import FlightPhase

    aircraft = []

    for i in range(len(t.index)):

        speed = t.taxi_speed[i] if t.ground_phase[i] != -1 else t.cas[i]

        aircraft.append({
            "id": int(t.index[i]),
            "name": str(t.call_sign[i]),
            "type": str(t.aircraft_type[i]),
            "phase": FlightPhase(int(t.flight_phase[i])).name,
            "heading": float(t.heading[i]),
            "altitude": float(t.alt[i]),
            "cas": float(speed),
            "lat": float(t.lat[i]),
            "lon": float(t.long[i])
        })

    socketio.emit('aircraftList', aircraft)

@socketio.on('addAircraft')
def add_aircraft(data):
    global current_env

    if current_env is None:
        return

    try:
        from airtrafficsim.core.aircraft import Aircraft
        from airtrafficsim.utils.enums import FlightPhase, Config

        callsign = data.get("callsign")
        ac_type = data.get("type")
        phase = data.get("phase")

        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        heading = float(data.get("heading"))
        alt = float(data.get("altitude"))
        speed = float(data.get("speed"))

        dep_airport = data.get("departure_airport", "")
        dep_runway = data.get("departure_runway", "")
        nsid = data.get("sid", "")

        arr_airport = data.get("arrival_airport", "")
        arr_runway = data.get("arrival_runway", "")
        nstar = data.get("star", "")
        napproach = data.get("approach", "")

        nflight_plan = data.get("flight_plan", [])
        print(nflight_plan)

        if not nflight_plan:
            ac = Aircraft(
                current_env.traffic,
                call_sign=callsign,
                aircraft_type=ac_type,
                flight_phase=FlightPhase[phase],
                configuration=Config.CLEAN,
                lat=lat,
                long=lon,
                alt=alt,
                heading=heading,
                cas=speed,
                fuel_weight=1000,
                payload_weight=500,
                cruise_alt=alt + 5000
            )
        else:
            ac = Aircraft(
            current_env.traffic,
            call_sign=callsign,
            aircraft_type=ac_type,
            flight_phase=FlightPhase[phase],
            configuration=Config.CLEAN,
            lat=lat,
            long=lon,
            alt=alt,
            heading=heading,
            cas=speed,
            fuel_weight=1000,
            payload_weight=500,
            cruise_alt=alt + 5000,
            departure_airport=dep_airport,
            departure_runway=dep_runway,
            sid=nsid,
            arrival_airport=arr_airport,
            arrival_runway=arr_runway,
            star=nstar,
            approach=napproach,
            flight_plan=nflight_plan
        )

        ac.set_speed(speed)

        current_env.aircraft_list.append(ac)

        print("Aircraft added:", callsign)

    except Exception as e:
        print("Add error:", e)

@socketio.on('deleteAircraft')
def delete_aircraft(data):
    global current_env

    if current_env is None:
        return

    ac_id = int(data.get("ac_id"))

    for ac in current_env.aircraft_list:
        if int(ac.index) == ac_id:
            current_env.traffic.del_aircraft(ac.index)
            current_env.aircraft_list.remove(ac)
            print("Deleted:", ac_id)
            break

@socketio.on('setToRunway')
def set_to_runway(data):
    global current_env

    if current_env is None:
        return

    try:
        ac_id = int(data.get("ac_id"))

        aircraft = None
        for ac in current_env.aircraft_list:
            if int(ac.index) == ac_id:
                aircraft = ac
                break

        if aircraft is None:
            return

        aircraft.start_flight()

        print(f"[CONTROL] Set to RWY Aircraft {ac_id}")

    except Exception as e:
        print("Set RWY error:", e)

@socketio.on('takeOff')
def take_off(data):
    global current_env

    if current_env is None:
        return

    try:
        ac_id = int(data.get("ac_id"))

        aircraft = None
        for ac in current_env.aircraft_list:
            if int(ac.index) == ac_id:
                aircraft = ac
                break

        if aircraft is None:
            return

        # TAKE OFF Methode aufrufen
        aircraft.take_off()

        print(f"[CONTROL] Take-off Aircraft {ac_id}")

    except Exception as e:
        print("Take-off error:", e)

def run_server(port=6111, host="127.0.0.1"):
    # Change host to 0.0.0.0 during deployment
    """Start the backend server."""
    print("Running server at http://localhost:"+str(port))
    socketio.run(app, port=port, host=host)
