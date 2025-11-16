import osmnx as ox
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import matplotlib.pyplot as plt
import contextily as ctx
import networkx as nx
import matplotlib
import platform
if platform.system() == 'Darwin':
    matplotlib.use('MacOSX')
else:
    matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
import contextily as ctx

from kolokvijum1_spatial import check_accident_zone


def load_serbian_roads():
    # Učitaj mrežu puteva Srbije

    G = ox.load_graphml('serbia_roads.graphml')
    if G is None:
        raise FileNotFoundError("Nema graphml fajla")

    return G


def get_route_coordinates(start_city, end_city):
    geolocator = Nominatim(user_agent="h3-project-advanced-db", timeout=10)

    start_loc = geolocator.geocode(start_city + ", Serbia")
    end_loc = geolocator.geocode(end_city + ", Serbia")

    if not start_loc or not end_loc:
        raise ValueError(f"Nisu pronađene koordinate za {start_city} ili {end_city}")

    orig = (start_loc.latitude, start_loc.longitude)
    dest = (end_loc.latitude, end_loc.longitude)

    print(f"{start_city}: {orig}")
    print(f"{end_city}: {dest}")

    return orig, dest


def get_route_length(route, G):
    route_length = 0
    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]
        # Proveri da li postoji ivica i da li ima atribut 'length'
        if G.has_edge(u, v):
            edge_data = G.get_edge_data(u, v)
            # Uzmi prvi ključ ako postoji više ivica (multigraf)
            if isinstance(edge_data, dict):
                if 0 in edge_data and 'length' in edge_data[0]:
                    route_length += edge_data[0]['length']
                elif 'length' in edge_data:
                    route_length += edge_data['length']

    return route_length


def show_route_distances(route_coords):
    total_distance = 0.0
    from geopy.distance import geodesic

    print("Segmenti rute:")
    for i in range(len(route_coords) - 1):
        start = route_coords[i]
        end = route_coords[i + 1]
        segment_distance = geodesic(start, end).meters
        total_distance += segment_distance
        print(f"  Segment {i + 1}: {segment_distance:.2f} m")

    print(f"Ukupna dužina rute: {total_distance / 1000:.2f} km")


def get_route_coords(G, orig, dest):
    # Nađi najbliže čvorove u grafu
    orig_node = ox.distance.nearest_nodes(G, orig[1], orig[0])
    dest_node = ox.distance.nearest_nodes(G, dest[1], dest[0])

    # Najkraća putanja između čvorova
    route = nx.shortest_path(G, orig_node, dest_node, weight='length')

    route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]

    # Izračunaj dužinu puta
    route_length = get_route_length(route, G)
    print(f"Ruta pronađena: {route_length / 1000:.2f} km, {len(route)} čvorova")

    return route_coords, route


class DriveSimulator:

    def __init__(self, G, drive_time, edge_color='lightgray', edge_linewidth=0.5):
        self.fig, self.ax = ox.plot_graph(G, node_size=0, edge_color=edge_color, edge_linewidth=edge_linewidth,
                                          show=False, close=False)
        self.fig.set_size_inches(10, 7)
        self.marker = None
        self.danger_text = None
        self.accident_info_text = None
        self.drive_time = drive_time

    def prikazi_mapu(self, route_coords, route_color, auto_marker_color='ro', auto_marker_size=8):
        # 5. Crtanje rute
        x = [lon for lat, lon in route_coords]
        y = [lat for lat, lon in route_coords]

        self.ax.plot(x, y, color=route_color, linewidth=2, alpha=0.8, label='Ruta')

        self._set_map_bounds(route_coords, padding=0.2)

        # 6. Pozadinska mapa
        self._show_background_map(self.ax)

        # 7. Simulacija kretanja automobila (kao crveni marker)
        self.marker, = self.ax.plot([], [], auto_marker_color, markersize=auto_marker_size, label='Automobil')
        # marker, = ax.plot([], [], 'ro', markersize=8, label='Automobil')

        self.ax.legend()

        plt.ion()  # Interaktivni mod
        plt.show()

    def _show_background_map(self, ax):
        try:

            ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.OpenStreetMap.Mapnik)
            # ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.CartoDB.Positron)
        except Exception as e:
            print(f"Contextily nije dostupan: {e}")

    #   Podesi granice mape da pokriva samo rutu sa malo paddinga
    #   route_coords: lista (lat, lon) koordinata
    #   padding: procenat paddinga oko rute (0.05 = 5%)
    def _set_map_bounds(self, route_coords, padding=0.05):

        lats = [coord[0] for coord in route_coords]
        lons = [coord[1] for coord in route_coords]

        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Dodaj padding
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon

        min_lat -= lat_range * padding
        max_lat += lat_range * padding
        min_lon -= lon_range * padding
        max_lon += lon_range * padding

        self.ax.set_xlim(min_lon, max_lon)
        self.ax.set_ylim(min_lat, max_lat)

    def move_auto_marker(self, lat, lon, auto_progress_info, plot_pause=0.1):
        danger_result = check_accident_zone(
            lat=lat,
            lon=lon,
            current_time=self.drive_time,
            look_ahead_km=5.0,
            print_warning=False
        )
        danger_level = danger_result['danger_level']
        total_accidents = danger_result['total']
        time_matched = danger_result['time_matched']
        seasonal_matched = danger_result['seasonal_matched']

        # Ažuriraj poziciju auto markera na mapi
        self.marker.set_data([lon], [lat])

        # Informacije o napretku
        title = (
            f"Pozicija: ({lat:.4f}, {lon:.4f}) | "
            f"Vreme: {self.drive_time.strftime('%H:%M')} | "
            f"Segment: {auto_progress_info['segment']}/{auto_progress_info['total_segments']} "
            f"({auto_progress_info['segment_progress']:.1f}%) | "
            f"Ukupno: {auto_progress_info['overall_progress']:.1f}% | "
            f"Brzina: {auto_progress_info['speed_kmh']} km/h | "
            f"Opasnost: {danger_level} ({total_accidents} nesreća) | "
        )
        self.ax.set_title(title, color="white", fontsize=15)

        print(
            f"[{auto_progress_info['segment']}/{auto_progress_info['total_segments']}] "
            f"Pozicija: ({lat:.4f}, {lon:.4f}) | "   
            f"Opasnost: {danger_level} | "
            f"Ukupno: {total_accidents}, "
            f"Vremenski (+- 1h): {time_matched} | "
            f"Sezonski (+- 1m): {seasonal_matched} | "
        )

        plt.pause(plot_pause)
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()

    def finish_drive(self):
        plt.ioff()
        plt.title(f"Ruta završena!")
        plt.show()

    def animate_drive(self, route_coords, speed_kmh=50, plot_pause=0.05):
        total_segments = len(route_coords) - 1
        for i in range(total_segments):
            start = route_coords[i]
            end = route_coords[i + 1]

            segment_distance = geodesic(start, end).km

            time_for_segment = (segment_distance / speed_kmh) * 3600

            steps = max(1, int(segment_distance * 10))
            for s in range(steps):
                lat = start[0] + (end[0] - start[0]) * (s / steps)
                lon = start[1] + (end[1] - start[1]) * (s / steps)

                auto_progress_info = {
                    'segment': i + 1,
                    'total_segments': total_segments,
                    'segment_progress': (s / steps) * 100,
                    'overall_progress': ((i + s / steps) / total_segments) * 100,
                    'speed_kmh': speed_kmh
                }

                self.move_auto_marker(lat, lon, auto_progress_info, plot_pause=plot_pause)
        print("\n=== Automobil je stigao na destinaciju! ===")
        self.finish_drive()
        return

if __name__ == '__main__':
    import sys
    try:
        from kolokvijum1_spatial import load_accidents_data
        load_accidents_data()
    except Exception as e:
        print("Greška pri učitavanju podataka:", e)
        sys.exit(1)

    G = load_serbian_roads()
    print(f"Graf učitan, {len(G.nodes)} čvorova, {len(G.edges)} ivica")

    start_city = input("Unesite poćetni grad: ")
    end_city = input("Unesite krajnji grad: ")
    drive_time_str = input("Unesite vreme vožnje (YYYY-MM-DD HH:MM) ili ENTER za sada: ")

    from pandas import Timestamp
    if drive_time_str.strip():
        drive_time = Timestamp(drive_time_str)
    else:
        drive_time = Timestamp.now()

    orig, dest = get_route_coordinates(start_city, end_city)

    route_coords, route_nodes = get_route_coords(G, orig, dest)

    simulator = DriveSimulator(G, drive_time)
    simulator.prikazi_mapu(route_coords, route_color='blue')
    simulator.animate_drive(route_coords, speed_kmh=50, plot_pause=0.05)

    total_segments = len(route_coords)
    speed_kmh = 50

    for i, (lat, lon) in enumerate(route_coords):
        overall_progress = (i + 1) / total_segments * 100
        segment_progress = 100
        simulator.move_auto_marker(
            lat,
            lon,
            auto_progress_info={
                'segment': i + 1,
                'total_segments': total_segments,
                'overall_progress': overall_progress,
                'segment_progress': segment_progress,
                'speed_kmh': speed_kmh
            },
            plot_pause=0.05
        )

        if i == total_segments - 1:
            simulator.finish_drive()
            break
