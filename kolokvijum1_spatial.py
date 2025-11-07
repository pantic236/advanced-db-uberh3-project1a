import time
import pandas as pd
import pyproj
from h3 import latlng_to_cell
from h3 import grid_disk
from geopy.distance import geodesic
import matplotlib

from auto_simulator import AutoSimulator
from drive_simulator import DriveSimulator, get_route_coordinates, get_route_coords, load_serbian_roads, \
    show_route_distances

# globalna promenljiva koja cuva podatke o nezgodama
ACCIDENTS_DF = None

# mapiranje (h3 celija -> lista nesreca) za brzu pretragu
ACCIDENTS_H3_MAP = {}


def load_accidents_data():
    global ACCIDENTS_DF, ACCIDENTS_H3_MAP
    print("Učitavanje i indeksiranje podataka")

    df = pd.read_excel("data/nez-opendata-2024-20250125.xlsx")

    # preimenovanje kolone za laksi rad
    df = df.rename(columns={df.columns[3]: 'datetime_str'})
    df['datetime'] = pd.to_datetime(df['datetime_str'], format='%d.%m.%Y,%H:%M', errors='coerce')
    df = df.dropna(subset=['datetime'])

    df['lon'] = df.iloc[:, 4].astype(float) / 1_000_000.0
    df['lat'] = df.iloc[:, 5].astype(float) / 1_000_000.0

    # dodaje h3 index
    resolution = 9
    df['h3_cell'] = df.apply(lambda r: latlng_to_cell(r['lat'], r['lon'], resolution), axis=1)

    ACCIDENTS_DF = df
    ACCIDENTS_H3_MAP = df.groupby('h3_cell').apply(
        lambda g: g[['lat', 'lon', 'datetime']].to_dict('records'),
    ).to_dict()

    print(f"Završeno učitavanje {len(df)} nesreća u H3 index rezolucije {resolution}.")

def check_accident_zone(lat, lon, current_time=None, look_ahead_km=5.0, print_warning=True):
    if current_time is None:
        current_time = pd.Timestamp.now()

    current_cell = latlng_to_cell(lat, lon, 9)
    ring_size = int(look_ahead_km / 0.35) + 1
    nearby_cells = grid_disk(current_cell, ring_size)

    total_accidents = 0
    time_matched = 0
    seasonal_matched = 0
    accidents_details = []

    for cell in nearby_cells:
        if cell in ACCIDENTS_H3_MAP:
            for accident in ACCIDENTS_H3_MAP[cell]:
                acc_lat = accident['lat']
                acc_lon = accident['lon']
                acc_time = accident['datetime']

                distance = geodesic((lat, lon), (acc_lat, acc_lon)).kilometers

                if distance <= look_ahead_km:
                    total_accidents += 1

                time_diff = abs((current_time - acc_time).total_seconds() / 3600)
                if time_diff <= 1.0:
                    time_matched += 1

                day_diff = abs((current_time - acc_time).days % 365)
                if day_diff <= 30 or day_diff >= 335:
                    seasonal_matched += 1

                accidents_details.append({
                    'distance': distance,
                    'time_diff_hours': time_diff,
                    'day_diff': day_diff
                })

    danger_level = "BEZBEDNO"
    if total_accidents > 10 or (time_matched >= 3 and seasonal_matched >= 5):
        danger_level = "VEOMA OPASNO"
    elif total_accidents >= 5 or (time_matched >= 2 and seasonal_matched >= 3):
        danger_level = "OPASNO"
    elif total_accidents >= 2:
        danger_level = "UMERENO OPASNO"

    if print_warning and total_accidents > 0:
        print(f"\n{'=' * 60}")
        print(f"UPOZORENJE - {danger_level}")
        print(f"{'=' * 60}")
        print(f"Pozicija: ({lat:.4f}, {lon:.4f})")
        print(f"Ukupno nesreća u narednih {look_ahead_km} km: {total_accidents}")
        print(f"  • Nesreće u isto vreme dana (±1h): {time_matched}")
        print(f"  • Nesreće u isto doba godine (±30 dana): {seasonal_matched}")
        print(f"{'=' * 60}\n")

    return {
        'total': total_accidents,
        'time_matched': time_matched,
        'seasonal_matched': seasonal_matched,
        'danger_level': danger_level,
        'details': accidents_details
    }


if __name__ == "__main__":
    load_accidents_data()
    print("\n[DEBUG] First 3 accidents in dataset:")
    for i in range(min(3, len(ACCIDENTS_DF))):
        acc = ACCIDENTS_DF.iloc[i]
        print(f"  {i+1}. Lat: {acc['lat']:.4f}, Lon: {acc['lon']:.4f}, Time: {acc['datetime']}")

    # Test: check danger EXACTLY at first accident location
    if len(ACCIDENTS_DF) > 0:
        first = ACCIDENTS_DF.iloc[0]
        print(f"\n[DEBUG] Checking danger at accident #1: ({first['lat']:.4f}, {first['lon']:.4f})")
        result = check_accident_zone(
            first['lat'],
            first['lon'],
            current_time=first['datetime'],  # match exact time
            look_ahead_km=1.0,
            print_warning=True
        )
        print(f"[DEBUG] Result → Danger: {result['danger_level']}, Total found: {result['total']}\n")

    start_city = "Prijepolje"
    end_city = "Užice"

    # 1. Učitaj mrežu puteva Srbije
    G = load_serbian_roads()

    print(f"Ucitana mreža puteva Srbije! {len(G.nodes)} čvorova, {len(G.edges)} ivica.")

    # 2. Odredjivanje koordinata pocetka i kraja rute
    orig, dest = get_route_coordinates(start_city, end_city)

    # 3. Odredjivanje rute
    route_coords, route = get_route_coords(G, orig, dest)

    # show_route_distances(route_coords)

    # 4. Inicijalizacija grafičke mape za voznju rutom
    drive_simulator = DriveSimulator(G, edge_color='lightgray', edge_linewidth=0.5)

    # 5. Prikaz mape sa rutom
    drive_simulator.prikazi_mapu(route_coords, route_color='blue', auto_marker_color='ro', auto_marker_size=8)

    # 6. Inicijalizuj simulator kretanja automobila sa brzinom 250 km/h i intervalom od 1 sekunde
    automobil = AutoSimulator(route_coords, speed_kmh=250, interval=1.0)
    automobil.running = True

    print("\n=== Simulacija pokrenuta ===")
    print("Kontrole: Auto se pomera automatski svakih", automobil.interval, "sekundi")
    print("Za zaustavljanje pritisnite Ctrl+C\n")

    interval_simulacije = 1.0  # sekunde
    # 7. Glavna petlja simulacije
    DEST_LAT, DEST_LON = dest
    FINISH_RADIUS_KM = 1



    try:
        step_count = 0
        while automobil.running:
            # Pomeri automobil
            auto_current_pos = automobil.move()
            lat, lon = auto_current_pos

            dist_to_dest = geodesic((lat, lon), (DEST_LAT, DEST_LON)).kilometers

            danger_info = check_accident_zone(lat, lon, look_ahead_km=2)
            current_danger = danger_info["danger_level"]

            print(f"[Step {step_count}] Moving...")
            print(f"Trenutna pozicija: {lat:.6f}, {lon:.6f}")
            print(f"Nivo opasnosti: {current_danger}")
            print(f"Preostalo kilometara: {dist_to_dest:.2f} km")

            progress_info = automobil.get_progress_info()
            marker_label = f"{progress_info} | {current_danger}"
            drive_simulator.move_auto_marker(lat, lon, automobil.get_progress_info(), plot_pause=0.01)

            # Pozovi check_neighbourhood samo na svakih 5 koraka (da ne zatrpava konzolu)
            step_count += 1
            if step_count % 5 == 0:
                check_accident_zone(lat, lon)

            # Proveri da li je stigao na kraj
            if dist_to_dest <= FINISH_RADIUS_KM:
                print("\n=== Automobil je stigao na destinaciju! ===")
                break

            # Čekaj interval pre sledećeg pomeraja
            time.sleep(interval_simulacije)

    except KeyboardInterrupt:
        print("\n\n=== Simulacija prekinuta ===")

    drive_simulator.finish_drive()




