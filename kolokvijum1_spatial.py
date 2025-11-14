import math
import time
from collections import defaultdict
import bisect
import pandas as pd
from h3 import latlng_to_cell, grid_disk
from geopy.distance import geodesic

RESOLUTION = 9
CELL_KM = 0.35
SECONDS_IN_DAY = 86400

ACCIDENTS_DF = None
ACCIDENTS_RECORDS = {}
ACCIDENTS_H3_MAP = defaultdict(set)

time_of_day_keys = []
time_of_day_ids = []

season_keys = []
season_ids = []

# pomoćne funkcije

def _seconds_since_midnight(ts: pd.Timestamp) -> int:
    return ts.hour * 3600 + ts.minute * 60 + ts.second

def _season_seconds(ts: pd.Timestamp) -> int:
    day_index = int(ts.dayofyear) - 1
    seconds = day_index * SECONDS_IN_DAY + _seconds_since_midnight(ts)
    return seconds

def _cells_for_km(look_ahead_km: float) -> int:
    return max(1, int(math.ceil(look_ahead_km / CELL_KM)))

def _insert_sorted_pair(keys_list, ids_list, key, rec_id):
    i = bisect.bisect_right(keys_list, rec_id)
    keys_list.insert(i, key)
    ids_list.insert(i, rec_id)

def _build_indexes_from_df(df: pd.DataFrame, resolution: int = RESOLUTION):
    global ACCIDENTS_RECORDS, ACCIDENTS_H3_MAP, time_of_day_keys, time_of_day_ids, season_keys, season_ids

    ACCIDENTS_RECORDS = {}
    ACCIDENTS_H3_MAP = defaultdict(set)
    time_of_day_keys = []
    time_of_day_ids = []
    season_keys = []
    season_ids = []

    for idx, row in df.iterrows():
        dt = row['datetime']
        if pd.isna(dt):
            continue
        lat = float(row['lat'])
        lon = float(row['lon'])
        rec_id = int(idx)

        rec = {'id': rec_id, 'lat': lat, 'lon': lon, 'datetime': dt}
        ACCIDENTS_RECORDS[rec_id] = rec

        cell = latlng_to_cell(lat, lon, resolution)

        tod = _seconds_since_midnight(dt)
        _insert_sorted_pair(time_of_day_keys, time_of_day_ids, tod, rec_id)

        skey = _season_seconds(dt)
        _insert_sorted_pair(season_keys, season_ids, skey, rec_id)

        ACCIDENTS_H3_MAP[cell].add(rec_id)


def load_accidents_data(path="data/nez-opendata-2024-20250125.xlsx", resolution: int = RESOLUTION):
    global ACCIDENTS_DF
    print("Učitavanje podataka o nesrećama iz", path)
    df = pd.read_excel(path)

    df = df.rename(columns={df.columns[3]: 'datetime_str'})
    df['datetime'] = pd.to_datetime(df['datetime_str'], format='%d.%m.%Y,%H:%M', errors='coerce')
    df = df.dropna(subset=['datetime'])

    df['lon'] = df.iloc[:, 4].astype(float) / 1_000_000.0
    df['lat'] = df.iloc[:, 5].astype(float) / 1_000_000.0

    ACCIDENTS_DF = df

    _build_indexes_from_df(df, resolution=resolution)
    print(f"Indeksiranje završeno: {len(ACCIDENTS_RECORDS)} zapisa, H3 rez {resolution}")

# vremenske funkcije

def _query_time_of_day_ids(current_ts: pd.Timestamp, window_seconds=3600):
    if not time_of_day_keys:
        return set()

    target = _seconds_since_midnight(current_ts)
    low = target - window_seconds
    high = target + window_seconds
    matched_ids = set()

    if low >= 0 and high < SECONDS_IN_DAY:
        l = bisect.bisect_left(time_of_day_keys, low)
        r = bisect.bisect_right(time_of_day_keys, high)
        matched_ids.update(time_of_day_ids[l:r])
    else:
        low_a = max(0, low)
        high_a = SECONDS_IN_DAY - 1
        if low_a <= high_a:
            la = bisect.bisect_left(time_of_day_keys, low_a)
            ra = bisect.bisect_right(time_of_day_keys, high_a)
            matched_ids.update(time_of_day_ids[la:ra])

        low_b = 0
        high_b = min(SECONDS_IN_DAY - 1, high % SECONDS_IN_DAY)
        if low_b <= high_b:
            lb = bisect.bisect_left(time_of_day_keys, low_b)
            rb = bisect.bisect_right(time_of_day_keys, high_b)
            matched_ids.update(time_of_day_ids[lb:rb])

    return matched_ids

def _query_season_ids(current_ts: pd.Timestamp, window_days=30):
    if not ACCIDENTS_RECORDS:
        return set()

    matched_ids = set()
    current_day = current_ts.dayofyear
    year_len_days = 366 if current_ts.is_leap_year else 365

    for rid, rec in ACCIDENTS_RECORDS.items():
        acc_day = rec['datetime'].dayofyear

        diff = abs(current_day - acc_day)
        day_diff = min(diff, year_len_days - diff)
        if day_diff <= window_days:
            matched_ids.add(rid)
    return matched_ids

# prostorne funkcije

def _collect_spatial_candidate_ids_center(lat, lon, look_ahead_km, resolution=RESOLUTION):
    if not ACCIDENTS_H3_MAP:
        return set()

    ring = _cells_for_km(look_ahead_km)
    center_cell = latlng_to_cell(lat, lon, resolution)
    cells = grid_disk(center_cell, ring)

    candidate_ids = set()
    for c in cells:
        if c in ACCIDENTS_H3_MAP:
            candidate_ids.update(ACCIDENTS_H3_MAP[c])

    filtered = set()
    for rid in candidate_ids:
        rec = ACCIDENTS_RECORDS.get(rid)
        if rec is None:
            continue
        d = geodesic((lat, lon), (rec['lat'], rec['lon'])).kilometers
        if d <= look_ahead_km:
            filtered.add(rid)
    return filtered

def _collect_spatial_candidate_ids_along_route(route_coords, look_ahead_km, resolution=RESOLUTION, buffer_ring=1):
    if not ACCIDENTS_H3_MAP:
        return set()

    ring = buffer_ring
    route_cells = set()
    for rlat, rlon in route_coords:
        c = latlng_to_cell(rlat, rlon, resolution)
        route_cells.update(grid_disk(c, ring))

    candidate_ids = set()
    for cell in route_cells:
        if cell in ACCIDENTS_H3_MAP:
            candidate_ids.update(ACCIDENTS_H3_MAP[cell])

    filtered = set()
    for rid in candidate_ids:
        rec = ACCIDENTS_RECORDS.get(rid)
        if rec is None:
            continue
        for rlat, rlon in route_coords:
            d = geodesic((rec['lat'], rec['lon']), (rlat, rlon)).kilometers
            if d <= look_ahead_km:
                filtered.add(rid)
                break
    return filtered

# glavna check funkcija

def check_accident_zone(lat, lon, current_time=None, future_route_coords=None, look_ahead_km=5.0, print_warning=True):
    if current_time is None:
        current_time = pd.Timestamp.now()

    if future_route_coords and len(future_route_coords) > 0:
        spatial_ids = _collect_spatial_candidate_ids_along_route(future_route_coords, look_ahead_km)
    else:
        spatial_ids = _collect_spatial_candidate_ids_center(lat, lon, look_ahead_km)

    total_accidents = len(spatial_ids)

    tod_ids = _query_time_of_day_ids(current_time, window_seconds=3600)
    season_ids_set = _query_season_ids(current_time, window_days=30)

    tod_spatial = spatial_ids.intersection(tod_ids)
    season_spatial = spatial_ids.intersection(season_ids_set)

    time_matched = len(tod_spatial)
    season_matched = len(season_spatial)

    accident_details = []

    current_day = int(current_time.dayofyear)
    year_len_days = 366 if current_time.is_leap_year else 365

    for rid in spatial_ids:
        rec = ACCIDENTS_RECORDS.get(rid)
        if rec is None:
            continue
        acc_time = rec['datetime']
        distance = geodesic((lat, lon), (rec['lat'], rec['lon'])).kilometers
        time_diff_hours = abs((current_time - acc_time).total_seconds()) / 3600.0

        acc_day = int(acc_time.dayofyear)
        raw_diff = abs(current_day - acc_day)
        day_diff = min(raw_diff, year_len_days - raw_diff)

        accident_details.append({
            'id': rid,
            'distance': distance,
            'time_diff_hours': time_diff_hours,
            'day_diff_days': day_diff,
            'acc_time': acc_time
        })

    danger_level = "BEZBEDNO"
    if total_accidents > 10 or (time_matched >= 3 and season_matched >= 5):
        danger_level = "VEOMA OPASNO"
    elif total_accidents >= 5 or (time_matched >= 2 and season_matched >= 3):
        danger_level = "OPASNO"
    elif total_accidents >= 2:
        danger_level = "UMERENO OPASNO"

    if print_warning and total_accidents > 0:
        print("\n" + "=" * 60)
        print(f"UPOZORENJE - {danger_level}")
        print("=" * 60)
        print(f"Pozicija: ({lat:.4f}, {lon:.4f})")
        print(f"Ukupno nesreća u narednih {look_ahead_km} km: {total_accidents}")
        print(f"  • Nesreće u isto vreme dana (±1h): {time_matched}")
        print(f"  • Nesreće u isto doba godine (±30 dana): {season_matched}")
        print("=" * 60 + "\n")

    return {
        'total': total_accidents,
        'time_matched': time_matched,
        'seasonal_matched': season_matched,
        'danger_level': danger_level,
        'details': accident_details
    }

# main

if __name__ == "__main__":
    import sys
    try:
        load_accidents_data()
    except Exception as e:
        print("Greška pri učitavanju podataka:", e)
        sys.exit(1)

    print("[DEBUG] sample records:")
    for i, (rid, rec) in enumerate(ACCIDENTS_RECORDS.items()):
        if i >= 3:
            break
        print(f"  {rid}: {rec['lat']:.5f}, {rec['lon']:.5f} at {rec['datetime']}")

    if ACCIDENTS_RECORDS:
        first_id = next(iter(ACCIDENTS_RECORDS))
        rec = ACCIDENTS_RECORDS[first_id]
        print("\n[DEBUG] running check_accident_zone on first record location/time:")
        res = check_accident_zone(rec['lat'], rec['lon'], current_time=rec['datetime'], look_ahead_km=5.0)
        print("[DEBUG] result:", res['danger_level'], "total:", res['total'])
    else:
        print("No records loaded.")


