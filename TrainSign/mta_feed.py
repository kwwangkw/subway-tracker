# SPDX-License-Identifier: MIT
# mta_feed.py — Fetch MTA subway realtime arrival data
#
# The MTA GTFS-RT feeds use Protocol Buffers. CircuitPython doesn't have a
# protobuf library, so we do minimal manual parsing of the binary format to
# extract trip_update → stop_time_update entries for our target stop.

import time
import os

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


def get_feed_urls_for_stop(stop_id):
    """
    Given a stop_id like 'G22', determine which GTFS-RT feeds might serve it.
    Since we don't know which lines serve a stop without static GTFS, we fetch
    all feeds for the configured lines. If lines_filter is set in settings,
    we only fetch those feeds.
    Returns a list of feed URLs to query.
    """
    # If user has configured specific lines, only fetch those feeds
    lines_filter = os.getenv("MTA_LINES_FILTER", "")
    if lines_filter:
        groups = set()
        for line in lines_filter.split(","):
            line = line.strip().upper()
            if line in LINE_TO_FEED:
                groups.add(LINE_TO_FEED[line])
        return [FEED_URLS[g] for g in groups if g in FEED_URLS]

    # Default: fetch all feeds (works but slower)
    return list(FEED_URLS.values())


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
    Field 3: stop_id (string)
    Field 2: arrival (StopTimeEvent)
      Field 2.1: time (int64 as varint in some feeds, or fixed64)
    """
    stop_id = None
    arrival_time = None

    for fn, wt, val in _iter_fields(data):
        if fn == 3 and wt == LENGTH_DELIMITED:
            # stop_id
            try:
                stop_id = val.decode("utf-8")
            except Exception:
                stop_id = str(val)
        elif fn == 2 and wt == LENGTH_DELIMITED:
            # arrival StopTimeEvent — parse its sub-fields
            for sfn, swt, sval in _iter_fields(val):
                if sfn == 2:  # time field
                    if swt == VARINT:
                        arrival_time = sval
                    elif swt == FIXED64:
                        # little-endian int64
                        arrival_time = int.from_bytes(sval, "little")

    return stop_id, arrival_time


def _parse_trip_update(data):
    """
    Parse a TripUpdate message.
    Field 1: trip descriptor (TripDescriptor)
      Field 1.1: trip_id (string) — contains route info
      Field 1.5: route_id (string)
    Field 2: stop_time_update (repeated)
    """
    route_id = None
    trip_id = None
    stop_time_updates = []

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
        elif fn == 2 and wt == LENGTH_DELIMITED:
            stop_time_updates.append(val)

    return route_id, trip_id, stop_time_updates


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
    Parse the top-level FeedMessage.
    Field 1: header (FeedHeader) — skip
    Field 2: entity (repeated FeedEntity)
    """
    entities = []
    for fn, wt, val in _iter_fields(data):
        if fn == 2 and wt == LENGTH_DELIMITED:
            entities.append(val)
    return entities


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
}


def get_destination(route_id, direction):
    """Get the destination name for a route and direction."""
    route = DESTINATION_NAMES.get(route_id, {})
    return route.get(direction, direction)


def fetch_arrivals(requests_session, stop_id, max_results=4):
    """
    Fetch upcoming arrivals for a given stop_id.

    Args:
        requests_session: An adafruit_requests.Session (or compatible) object.
        stop_id: Base stop ID (e.g., 'G22'). Both N and S variants are checked.
        max_results: Maximum number of arrivals to return.

    Returns:
        List of dicts with keys:
            - route_id: str (e.g., '7', 'G')
            - direction: str ('N' or 'S')
            - destination: str (human-readable)
            - arrival_time: int (unix timestamp)
            - minutes: int (minutes until arrival)
    """
    now = time.time()
    stop_n = stop_id + "N"
    stop_s = stop_id + "S"
    target_stops = {stop_n, stop_s}

    arrivals = []
    feed_urls = get_feed_urls_for_stop(stop_id)

    for url in feed_urls:
        try:
            response = requests_session.get(url)
            data = response.content
            response.close()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        try:
            entities = _parse_feed_message(data)
        except Exception as e:
            print(f"Error parsing feed: {e}")
            continue

        for entity_data in entities:
            trip_update_data = _parse_feed_entity(entity_data)
            if trip_update_data is None:
                continue

            route_id, trip_id, stop_time_updates = _parse_trip_update(
                trip_update_data
            )

            if route_id is None and trip_id:
                # Try to extract route from trip_id
                # Format is often like "064350_7..N03R" → route is "7"
                parts = trip_id.split("_")
                if len(parts) >= 2:
                    route_part = parts[1].split(".")[0]
                    if route_part:
                        route_id = route_part

            if route_id is None:
                continue

            for stu_data in stop_time_updates:
                stu_stop_id, stu_arrival = _parse_stop_time_update(stu_data)
                if stu_stop_id not in target_stops:
                    continue
                if stu_arrival is None:
                    continue
                if stu_arrival < now:
                    continue  # Already passed

                direction = _direction_from_stop(stu_stop_id)
                minutes = int((stu_arrival - now) / 60)

                arrivals.append({
                    "route_id": route_id,
                    "direction": direction,
                    "destination": get_destination(route_id, direction),
                    "arrival_time": stu_arrival,
                    "minutes": minutes,
                })

    # Sort by arrival time
    arrivals.sort(key=lambda a: a["arrival_time"])

    return arrivals[:max_results]


def parse_row_config(config_str):
    """
    Parse a row config string like '721:7:S' into components.
    Format: stop_id[:line[:direction]]
    Returns (stop_id, line_filter, direction_filter).
    line_filter and direction_filter may be None.
    """
    parts = config_str.strip().split(":")
    stop_id = parts[0]
    line_filter = parts[1].upper() if len(parts) > 1 else None
    direction_filter = parts[2].upper() if len(parts) > 2 else None
    return stop_id, line_filter, direction_filter


def fetch_arrivals_multi(requests_session, row_configs, max_results=4):
    """
    Fetch upcoming arrivals from multiple stop/line/direction configs.
    Merges results from all configs, sorted by soonest arrival.

    Args:
        requests_session: An adafruit_requests.Session (or compatible).
        row_configs: list of config strings, e.g. ['721:7:S', 'G29:G:N']
        max_results: Maximum number of arrivals to return.

    Returns:
        List of dicts (same format as fetch_arrivals).
    """
    now = time.time()

    # Parse configs and figure out which feeds we need
    parsed = []  # list of (stop_id, line_filter, direction_filter)
    feeds_needed = set()  # set of feed URLs to fetch
    for cfg in row_configs:
        stop_id, line_filter, dir_filter = parse_row_config(cfg)
        parsed.append((stop_id, line_filter, dir_filter))
        if line_filter and line_filter in LINE_TO_FEED:
            group = LINE_TO_FEED[line_filter]
            feeds_needed.add(FEED_URLS[group])
        else:
            # Unknown line — fetch all feeds
            feeds_needed.update(FEED_URLS.values())

    # Build target stop sets per config
    # Each entry: ({stop_n, stop_s}, line_filter, dir_filter)
    targets = []
    for stop_id, line_filter, dir_filter in parsed:
        stop_set = set()
        if dir_filter == "N":
            stop_set.add(stop_id + "N")
        elif dir_filter == "S":
            stop_set.add(stop_id + "S")
        else:
            stop_set.add(stop_id + "N")
            stop_set.add(stop_id + "S")
        targets.append((stop_set, line_filter, dir_filter))

    # All target stop IDs (union) for quick filtering
    all_target_stops = set()
    for stop_set, _, _ in targets:
        all_target_stops.update(stop_set)

    arrivals = []

    for url in feeds_needed:
        try:
            response = requests_session.get(url)
            data = response.content
            response.close()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        try:
            entities = _parse_feed_message(data)
        except Exception as e:
            print(f"Error parsing feed: {e}")
            continue

        for entity_data in entities:
            trip_update_data = _parse_feed_entity(entity_data)
            if trip_update_data is None:
                continue

            route_id, trip_id, stop_time_updates = _parse_trip_update(
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

            for stu_data in stop_time_updates:
                stu_stop_id, stu_arrival = _parse_stop_time_update(stu_data)
                if stu_stop_id not in all_target_stops:
                    continue
                if stu_arrival is None:
                    continue
                if stu_arrival < now:
                    continue

                # Check if this matches any of our configs
                matched = False
                for stop_set, line_filter, dir_filter in targets:
                    if stu_stop_id not in stop_set:
                        continue
                    if line_filter and route_id.upper() != line_filter:
                        continue
                    matched = True
                    break

                if not matched:
                    continue

                direction = _direction_from_stop(stu_stop_id)
                minutes = int((stu_arrival - now) / 60)

                arrivals.append({
                    "route_id": route_id,
                    "direction": direction,
                    "destination": get_destination(route_id, direction),
                    "arrival_time": stu_arrival,
                    "minutes": minutes,
                })

    arrivals.sort(key=lambda a: a["arrival_time"])
    return arrivals[:max_results]


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


def fetch_arrivals_multi(requests_session, row_configs):
    """
    Fetch the soonest arrival for each row config.

    Args:
        requests_session: An adafruit_requests.Session object.
        row_configs: list of config strings, e.g. ['721:7:S', 'G29:G:N']

    Returns:
        List of dicts (one per row config, or None if no arrival found):
            - route_id, direction, destination, arrival_time, minutes
    """
    now = time.time()
    parsed = [_parse_row_config(c) for c in row_configs]

    # Determine which feed URLs we need
    urls_needed = set()
    for stop_id, line_filter, _ in parsed:
        if line_filter and line_filter in LINE_TO_FEED:
            group = LINE_TO_FEED[line_filter]
            urls_needed.add(FEED_URLS[group])
        else:
            # No line filter — need all feeds
            urls_needed.update(FEED_URLS.values())
            break

    # Fetch and parse all needed feeds
    all_updates = []  # list of (route_id, stop_id_full, arrival_time)
    for url in urls_needed:
        try:
            response = requests_session.get(url)
            data = response.content
            response.close()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        try:
            entities = _parse_feed_message(data)
        except Exception as e:
            print(f"Error parsing feed: {e}")
            continue

        for entity_data in entities:
            trip_update_data = _parse_feed_entity(entity_data)
            if trip_update_data is None:
                continue

            route_id, trip_id, stop_time_updates = _parse_trip_update(
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

            for stu_data in stop_time_updates:
                stu_stop_id, stu_arrival = _parse_stop_time_update(stu_data)
                if stu_stop_id is None or stu_arrival is None:
                    continue
                if stu_arrival < now:
                    continue
                all_updates.append((route_id, stu_stop_id, stu_arrival))

    # Match each row config to the soonest arrival
    results = []
    for stop_id, line_filter, direction_filter in parsed:
        stop_n = stop_id + "N"
        stop_s = stop_id + "S"
        best = None
        for route_id, stu_stop_id, stu_arrival in all_updates:
            # Must match stop
            if stu_stop_id != stop_n and stu_stop_id != stop_s:
                continue
            # Must match line filter if set
            if line_filter and route_id.upper() != line_filter:
                continue
            # Must match direction filter if set
            direction = _direction_from_stop(stu_stop_id)
            if direction_filter and direction != direction_filter:
                continue
            # Keep soonest
            if best is None or stu_arrival < best[2]:
                best = (route_id, stu_stop_id, stu_arrival)

        if best:
            route_id, stu_stop_id, stu_arrival = best
            direction = _direction_from_stop(stu_stop_id)
            minutes = int((stu_arrival - now) / 60)
            results.append({
                "route_id": route_id,
                "direction": direction,
                "destination": get_destination(route_id, direction),
                "arrival_time": stu_arrival,
                "minutes": minutes,
            })
        else:
            results.append(None)

    return results
