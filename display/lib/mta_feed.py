# SPDX-License-Identifier: MIT
# Created by Kevin Wang - https://github.com/kwwangkw/
# mta_feed.py - Fetch MTA subway realtime arrival data
#
# The MTA GTFS-RT feeds use Protocol Buffers. CircuitPython doesn't have a
# protobuf library, so we do minimal manual parsing of the binary format to
# extract trip_update → stop_time_update entries for our target stop.

import gc
import time
import os

# CircuitPython's time.time() returns seconds since Jan 1, 2000 (Y2K epoch).
# MTA feeds use Unix timestamps (seconds since Jan 1, 1970).
# Offset = 946684800 seconds (30 years).
# We add this to time.time() to get a Unix-compatible timestamp.
try:
    # On CPython, time.time() already returns Unix epoch - no offset needed
    if time.time() > 1_000_000_000:
        EPOCH_OFFSET = 0
    else:
        EPOCH_OFFSET = 946684800
except Exception:
    EPOCH_OFFSET = 946684800


def _now_unix():
    """Return current time as a Unix timestamp (seconds since 1970)."""
    return time.time() + EPOCH_OFFSET

# GTFS-RT feed URLs by line group (no API key required)
FEED_URLS = {
    # 1,2,3,4,5,6,7,S
    "1234567S": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs",
    # A,C,E,H (Rockaway shuttle)
    "ACEH": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace",
    # B,D,F,M,Franklin shuttle
    "BDFM": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-bdfm",
    # G
    "G": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
    # J,Z
    "JZ": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-jz",
    # N,Q,R,W
    "NQRW": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-nqrw",
    # L
    "L": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
    # SIR
    "SI": "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-si",
}

# Map each line to its feed group
LINE_TO_FEED = {}
for group, url in FEED_URLS.items():
    for ch in group:
        LINE_TO_FEED[ch] = group

# Multi-char route IDs for shuttles
LINE_TO_FEED["GS"] = "1234567S"   # 42nd St Shuttle - in the main feed
LINE_TO_FEED["FS"] = "BDFM"       # Franklin Ave Shuttle - in the BDFM feed
LINE_TO_FEED["H"] = "ACEH"        # Rockaway Park Shuttle - in the ACE feed


# ---------------------------------------------------------------
# Minimal GTFS-RT (protobuf) parser
# ---------------------------------------------------------------
# Protobuf wire types
VARINT = 0
FIXED64 = 1
LENGTH_DELIMITED = 2
FIXED32 = 5


def _read_varint(data, pos):
    """Read a varint from data at pos. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _read_field(data, pos):
    """Read one protobuf field. Returns (field_number, wire_type, value, new_pos)."""
    if pos >= len(data):
        return None, None, None, pos

    tag, pos = _read_varint(data, pos)
    field_number = tag >> 3
    wire_type = tag & 0x07

    if wire_type == VARINT:
        value, pos = _read_varint(data, pos)
    elif wire_type == FIXED64:
        value = data[pos:pos + 8]
        pos += 8
    elif wire_type == LENGTH_DELIMITED:
        length, pos = _read_varint(data, pos)
        value = data[pos:pos + length]
        pos += length
    elif wire_type == FIXED32:
        value = data[pos:pos + 4]
        pos += 4
    else:
        # Unknown wire type, skip
        value = None

    return field_number, wire_type, value, pos


def _iter_fields(data):
    """Iterate over all fields in a protobuf message."""
    pos = 0
    while pos < len(data):
        fn, wt, val, pos = _read_field(data, pos)
        if fn is None:
            break
        yield fn, wt, val


def _parse_stop_time_update(data):
    """
    Parse a StopTimeUpdate message.
    Field 4: stop_id (string)
    Field 2: arrival (StopTimeEvent)
      Field 2.2: time (int64 as varint in some feeds, or fixed64)
    Field 3: departure (StopTimeEvent) - used as fallback for arrival time
    """
    stop_id = None
    arrival_time = None

    for fn, wt, val in _iter_fields(data):
        if fn == 4 and wt == LENGTH_DELIMITED:
            # stop_id
            try:
                stop_id = val.decode("utf-8")
            except Exception:
                stop_id = str(val)
        elif fn == 2 and wt == LENGTH_DELIMITED:
            # arrival StopTimeEvent - parse its sub-fields
            for sfn, swt, sval in _iter_fields(val):
                if sfn == 2:  # time field
                    if swt == VARINT:
                        arrival_time = sval
                    elif swt == FIXED64:
                        # little-endian int64
                        arrival_time = int.from_bytes(sval, "little")
        elif fn == 3 and wt == LENGTH_DELIMITED and arrival_time is None:
            # departure StopTimeEvent - fallback if no arrival time
            for sfn, swt, sval in _iter_fields(val):
                if sfn == 2:  # time field
                    if swt == VARINT:
                        arrival_time = sval
                    elif swt == FIXED64:
                        arrival_time = int.from_bytes(sval, "little")

    return stop_id, arrival_time


def _parse_trip_update(data):
    """
    Parse a TripUpdate message.
    Field 1: trip descriptor (TripDescriptor)
      Field 1.1: trip_id (string) - contains route info
      Field 1.5: route_id (string)
    Field 2: stop_time_update (repeated) - NOT collected, iterate raw data instead

    Returns (route_id, trip_id, raw_data) - caller iterates field 2 entries
    lazily via _iter_stop_time_updates(raw_data) to avoid list allocation.
    """
    route_id = None
    trip_id = None

    for fn, wt, val in _iter_fields(data):
        if fn == 1 and wt == LENGTH_DELIMITED:
            # TripDescriptor
            for sfn, swt, sval in _iter_fields(val):
                if sfn == 1 and swt == LENGTH_DELIMITED:
                    try:
                        trip_id = sval.decode("utf-8")
                    except Exception:
                        pass
                elif sfn == 5 and swt == LENGTH_DELIMITED:
                    try:
                        route_id = sval.decode("utf-8")
                    except Exception:
                        pass
            break  # field 1 comes first; stop here, don't scan field 2s

    return route_id, trip_id, data


def _iter_stop_time_updates(trip_update_data):
    """Yield each StopTimeUpdate (field 2) from raw TripUpdate data.
    Generator - no list allocated."""
    for fn, wt, val in _iter_fields(trip_update_data):
        if fn == 2 and wt == LENGTH_DELIMITED:
            yield val


def _parse_feed_entity(data):
    """
    Parse a FeedEntity message.
    Field 1: id (string)
    Field 3: trip_update (TripUpdate)
    """
    trip_update_data = None
    for fn, wt, val in _iter_fields(data):
        if fn == 3 and wt == LENGTH_DELIMITED:
            trip_update_data = val
    return trip_update_data


def _parse_feed_message(data):
    """
    Parse the top-level FeedMessage as a generator.
    Field 1: header (FeedHeader) - skip
    Field 2: entity (repeated FeedEntity)
    Yields entity data one at a time to avoid holding all in memory.
    """
    for fn, wt, val in _iter_fields(data):
        if fn == 2 and wt == LENGTH_DELIMITED:
            yield val


def _direction_from_stop(stop_id_full):
    """
    MTA stop IDs end in 'N' (northbound) or 'S' (southbound).
    Returns 'N' or 'S'.
    """
    if stop_id_full and len(stop_id_full) > 1:
        last = stop_id_full[-1].upper()
        if last in ("N", "S"):
            return last
    return "?"


# ---------------------------------------------------------------
# Common destination names (abbreviated for the 128px display)
# ---------------------------------------------------------------
DESTINATION_NAMES = {
    # 7 train
    "7": {
        "N": "34 St-Hudson Yards",
        "S": "Flushing-Main St",
    },
    # G train
    "G": {
        "N": "Court Sq",
        "S": "Church Ave",
    },
    # A train
    "A": {
        "N": "Inwood-207 St",
        "S": "Far Rockaway",
    },
    # C train
    "C": {
        "N": "168 St",
        "S": "Euclid Ave",
    },
    # E train
    "E": {
        "N": "Jamaica Center",
        "S": "World Trade Ctr",
    },
    # 1 train
    "1": {
        "N": "Van Cortlandt Park",
        "S": "South Ferry",
    },
    # 2 train
    "2": {
        "N": "Wakefield-241 St",
        "S": "Flatbush Ave",
    },
    # 3 train
    "3": {
        "N": "Harlem-148 St",
        "S": "New Lots Ave",
    },
    # N train
    "N": {
        "N": "Astoria",
        "S": "Coney Island",
    },
    # Q train
    "Q": {
        "N": "96 St",
        "S": "Coney Island",
    },
    # R train
    "R": {
        "N": "Forest Hills",
        "S": "Bay Ridge",
    },
    # W train
    "W": {
        "N": "Astoria",
        "S": "Whitehall St",
    },
    # L train
    "L": {
        "N": "8 Ave",
        "S": "Canarsie",
    },
    # B train
    "B": {
        "N": "Bedford Pk Blvd",
        "S": "Brighton Beach",
    },
    # D train
    "D": {
        "N": "Norwood-205 St",
        "S": "Coney Island",
    },
    # F train
    "F": {
        "N": "Jamaica",
        "S": "Coney Island",
    },
    # M train
    "M": {
        "N": "Forest Hills",
        "S": "Middle Village",
    },
    # J train
    "J": {
        "N": "Jamaica Center",
        "S": "Broad St",
    },
    # Z train
    "Z": {
        "N": "Jamaica Center",
        "S": "Broad St",
    },
    # 4 train
    "4": {
        "N": "Woodlawn",
        "S": "Crown Hts-Utica",
    },
    # 5 train
    "5": {
        "N": "Eastchester-Dyre",
        "S": "Flatbush Ave",
    },
    # 6 train
    "6": {
        "N": "Pelham Bay Park",
        "S": "Brooklyn Bridge",
    },
    # Shuttles
    "GS": {
        "N": "Grand Central",
        "S": "Times Sq",
    },
    "FS": {
        "N": "Franklin Av",
        "S": "Prospect Park",
    },
    "H": {
        "N": "Broad Channel",
        "S": "Rockaway Park",
    },
}


def get_destination(route_id, direction):
    """Get the destination name for a route and direction."""
    route = DESTINATION_NAMES.get(route_id, {})
    return route.get(direction, direction)


def _parse_row_config(config_str):
    """
    Parse a row config string like 'stop_id:line:direction'.
    Returns (stop_id, line_filter, direction_filter).
    Any part can be omitted:
      '721:7:S'  → ('721', '7', 'S')
      '721:7'    → ('721', '7', None)
      'G22'      → ('G22', None, None)
    """
    parts = config_str.strip().split(":")
    stop_id = parts[0]
    line_filter = parts[1].upper() if len(parts) > 1 and parts[1] else None
    direction_filter = parts[2].upper() if len(parts) > 2 and parts[2] else None
    return stop_id, line_filter, direction_filter


def fetch_arrivals_multi(requests_session, row_configs, max_results=2):
    """
    Fetch upcoming arrivals matching any of the row configs.
    Returns the soonest `max_results` arrivals sorted by time,
    merged across all configs.

    Args:
        requests_session: An adafruit_requests.Session object.
        row_configs: list of config strings, e.g. ['721:7:N', 'G24:G:S']
        max_results: max number of arrivals to return.

    Returns:
        List of dicts sorted by arrival_time (may be shorter than max_results):
            - route_id, direction, destination, arrival_time, minutes
    """
    now = _now_unix()
    parsed = [_parse_row_config(c) for c in row_configs]

    # Pre-build target stop IDs for fast lookup during parsing
    # target_stops maps "721N" -> [(line_filter, dir_filter), ...]
    target_stops = {}
    for stop_id, line_filter, direction_filter in parsed:
        for suffix in ("N", "S"):
            key = stop_id + suffix
            if key not in target_stops:
                target_stops[key] = []
            target_stops[key].append((line_filter, direction_filter))

    # Keep top arrivals as a sorted list of (arrival_time, route_id, stop_id_full)
    # We keep at most max_results entries, pruning as we go
    top = []  # sorted by arrival_time
    cutoff = None  # arrival time of the last entry in top (for fast rejection)

    # Determine which feed URLs we need
    urls_needed = set()
    for stop_id, line_filter, _ in parsed:
        if line_filter and line_filter in LINE_TO_FEED:
            group = LINE_TO_FEED[line_filter]
            urls_needed.add(FEED_URLS[group])
        else:
            urls_needed.update(FEED_URLS.values())
            break

    # Fetch and parse feeds
    for url in urls_needed:
        try:
            response = requests_session.get(url)
            data = response.content
            response.close()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        for entity_data in _parse_feed_message(data):
            trip_update_data = _parse_feed_entity(entity_data)
            if trip_update_data is None:
                continue

            route_id, trip_id, raw_tu = _parse_trip_update(
                trip_update_data
            )

            if route_id is None and trip_id:
                parts = trip_id.split("_")
                if len(parts) >= 2:
                    route_part = parts[1].split(".")[0]
                    if route_part:
                        route_id = route_part

            if route_id is None:
                continue

            for stu_data in _iter_stop_time_updates(raw_tu):
                stu_stop_id, stu_arrival = _parse_stop_time_update(stu_data)
                if stu_stop_id is None or stu_arrival is None:
                    continue
                if stu_arrival < now:
                    continue
                # Fast reject: if we already have enough and this is later
                if cutoff is not None and stu_arrival >= cutoff:
                    continue

                # Check if this stop_id matches any config
                matches = target_stops.get(stu_stop_id)
                if matches is None:
                    continue

                matched = False
                for line_filter, direction_filter in matches:
                    if line_filter and route_id.upper() != line_filter:
                        continue
                    direction = _direction_from_stop(stu_stop_id)
                    if direction_filter and direction != direction_filter:
                        continue
                    matched = True
                    break

                if not matched:
                    continue

                # Check for duplicate (same route + same arrival time)
                dup = False
                for t_arr, t_rid, t_sid in top:
                    if t_arr == stu_arrival and t_rid == route_id:
                        dup = True
                        break
                if dup:
                    continue

                # Insert into sorted top list
                inserted = False
                for j in range(len(top)):
                    if stu_arrival < top[j][0]:
                        top.insert(j, (stu_arrival, route_id, stu_stop_id))
                        inserted = True
                        break
                if not inserted:
                    top.append((stu_arrival, route_id, stu_stop_id))

                # Prune to max_results
                if len(top) > max_results:
                    top.pop()
                if len(top) >= max_results:
                    cutoff = top[-1][0]

        # Free feed data memory before fetching next feed
        data = None
        gc.collect()

    # Build result dicts
    results = []
    for stu_arrival, route_id, stu_stop_id in top:
        direction = _direction_from_stop(stu_stop_id)
        minutes = int((stu_arrival - now) / 60)
        results.append({
            "route_id": route_id,
            "direction": direction,
            "destination": get_destination(route_id, direction),
            "arrival_time": stu_arrival,
            "minutes": minutes,
        })

    return results
