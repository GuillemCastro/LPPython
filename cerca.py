"""
Copyright (C) 2018  Guillem Castro

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import argparse, ast, datetime, collections, re, pprint
import math, urllib.request, os
from xml.etree import ElementTree
from datetime import date, datetime, time
import html

MONTHLY_EVENTS_URL = 'http://w10.bcn.es/APPS/asiasiacache/peticioXmlAsia?id=103'
TODAY_EVENTS_URL = 'http://w10.bcn.es/APPS/asiasiacache/peticioXmlAsia?id=199'
BICING_URL = 'https://wservice.viabicing.cat/v1/getstations.php?v=1'

LatLong = collections.namedtuple('LatLong', 'latitude longitude')

def haversine_distance(origin, destination):
    """ 
    Calculate the approx. distance between two point in the Earth.

    The parameters must be "instances" of `LatLong`, using the WGS84 coordinate system with decimal degrees

    More info: https://en.wikipedia.org/wiki/Haversine_formula
    """
    earth_radius = 6371e3 # approx. radius
    o_lon = math.radians(origin.longitude)
    o_lat = math.radians(origin.latitude)
    d_lon = math.radians(destination.longitude)
    d_lat = math.radians(destination.latitude)
    delta_lat = math.radians(destination.latitude - origin.latitude)
    delta_long = math.radians(destination.longitude - origin.longitude)
    a = math.sin(delta_lat/2.0) ** 2 + math.cos(o_lat) * math.cos(d_lat) * math.sin(delta_long/2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1.0-a))
    return earth_radius * c

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--key', type=str, required=True, help='Search terms')
    parser.add_argument('--distance', type=int, required=False, help='Max. distance to the bicing stations', default=300)
    parser.add_argument('--date', type=str, required=False, help='Event date', default=argparse.SUPPRESS)
    return vars(parser.parse_args())

def get_bicing_stations():
    """
    Load the list of Bicing stations and return a list of `Station` instances
    """
    stations = urllib.request.urlopen(BICING_URL).read().decode('utf-8')
    stations_tree = ElementTree.fromstring(str(stations))
    res= []
    for station_tree in stations_tree.iter('station'):
        station = Station.fromElementTree(station_tree)
        res.append(station)
    return res

def set_nearest_stations(events, stations, max_distance):
    """
    For every event set the stations with available bikes and slots that are
    in a distance less or equal to `max_distance`
    """
    for event in events:
        if event.coords is None:
            continue
        for station in stations:
            distance = haversine_distance(event.coords, station.coords)
            if  distance <= max_distance:
                if station.slots > 0:
                    event.stations_with_slots.append((station, distance))
                elif station.bikes > 0:
                    event.stations_with_bikes.append((station, distance))
        event.stations_with_slots.sort(key=lambda e: e[1])
        event.stations_with_bikes.sort(key=lambda e: e[1])

def check_event(event, search_terms):
    """
    Returns if the event matches the passed `search_terms`
    """
    if isinstance(search_terms, str):
        return (search_terms in event.name or search_terms in event.place or search_terms in event.address)
    elif isinstance(search_terms, list):
        #conjuncions
        for elem in search_terms:
            if not check_event(event, elem):
                return False
        return True
    elif isinstance(search_terms, tuple):
        #disjuncions
        for elem in search_terms:
            if check_event(event, elem):
                return True
        return False
    return False

def find_monthly_events(search_terms, date):
    """
    Search in the list of montly events the events for a given date and terms and return a list of `Event` instances
    """
    events = urllib.request.urlopen(MONTHLY_EVENTS_URL).read().decode('iso-8859-1')
    events_tree = ElementTree.fromstring(str(events))
    res = []
    for event_tree in events_tree.iter('acte'):
        event = Event.fromElementTree(event_tree)
        if event.date == date and check_event(event, search_terms):
            res.append(event)
    return res

def find_today_events(search_terms):
    """
    Search in the list of events for today the events that match a set of terms and return a list of `Event` instances
    """
    events = urllib.request.urlopen(TODAY_EVENTS_URL).read().decode('iso-8859-1')
    events_tree = ElementTree.fromstring(str(events))
    res = []
    for event_tree in events_tree.iter('acte'):
        event = Event.fromElementTree(event_tree)
        if check_event(event, search_terms):
            res.append(event)
    return res

def write_html(events):
    """
    Write a list of `Event` instances into a index.html file
    """
    html = ElementTree.Element('html')
    html_tree = ElementTree.ElementTree(html)
    body = ElementTree.SubElement(html, 'body')
    table = ElementTree.SubElement(body, 'table')
    table.set('style', 'width: 100%; border: 1px solid black;')
    row = ElementTree.SubElement(table, 'tr')
    name = ElementTree.SubElement(row, 'th')
    name.text = 'Name'
    address = ElementTree.SubElement(row, 'th')
    address.text = 'Address'
    place = ElementTree.SubElement(row, 'th')
    place.text = 'Place'
    date = ElementTree.SubElement(row, 'th')
    date.text = 'Date'
    stations_with_bikes = ElementTree.SubElement(row, 'th')
    stations_with_bikes.set('style', 'width: 25%')
    stations_with_bikes.text = 'Stations with bikes'
    stations_with_slots = ElementTree.SubElement(row, 'th')
    stations_with_slots.set('style', 'width: 25%')
    stations_with_slots.text = 'Stations with slots'
    for event in events:
        row = ElementTree.SubElement(table, 'tr')
        name = ElementTree.SubElement(row, 'td')
        name.text = event.name
        address = ElementTree.SubElement(row, 'td')
        address.text = event.address
        place = ElementTree.SubElement(row, 'td')
        place.text = event.place
        date = ElementTree.SubElement(row, 'td')
        date.text = event.date.strftime('%d/%m/%Y') + ' ' + (event.hour.strftime('%H:%M') if event.hour else '')
        stations_with_bikes = ElementTree.SubElement(row, 'td')
        bikes_list = ElementTree.SubElement(stations_with_bikes, 'ul')
        for i in range(len(event.stations_with_bikes)):
            station = event.stations_with_bikes[i][0]
            distance = event.stations_with_bikes[i][1]
            bike = ElementTree.SubElement(bikes_list, 'li')
            bike.text = station.street + ', ' + str(station.number) + '. Bikes: ' + str(station.bikes) + '. Distance: ' + str(round(distance, 2)) + 'm'
        stations_with_slots = ElementTree.SubElement(row, 'td')
        slots_list = ElementTree.SubElement(stations_with_slots, 'ul')
        for i in range(len(event.stations_with_slots)):
            station = event.stations_with_slots[i][0]
            distance = event.stations_with_slots[i][1]
            slot = ElementTree.SubElement(slots_list, 'li')
            slot.text = station.street + ', ' + str(station.number) + '. Slots: ' + str(station.slots) + '. Distance: ' + str(round(distance, 2)) + 'm'
    style = ElementTree.SubElement(html, 'style')
    style.text = """
    table {
        border-collapse: collapse;
        width: 100%;
    }
    th, td {
        text-align: left;
        padding: 8px;
    }
    tr:nth-child(even){
        background-color: #f2f2f2
    }
    th {
        background-color: #4CAF50;
        color: white;
    }
    """
    html_tree.write(open('index.html', 'wb'), method='html')
    print('Results saved into {}'.format(os.path.abspath('./index.html')))

def main():
    args = parse_args()
    search_terms = ast.literal_eval(args['key'])
    if 'date' in args:
        date = datetime.strptime(args['date'], '%d/%m/%Y')
        events = find_monthly_events(search_terms, date)
        #pprint.pprint(events)
    else:
        events = find_today_events(search_terms)
        stations = get_bicing_stations()
        set_nearest_stations(events, stations, args['distance'])
        #pprint.pprint(events)
    write_html(events)

class Event:

    def __init__(self, **kwargs):
        allowed_keys = set(['name', 'address', 'date', 'hour', 'place', 'coords'])
        self.__dict__.update((key, None) for key in allowed_keys)
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in allowed_keys)
        self.stations_with_bikes = []
        self.stations_with_slots = []
    
    @staticmethod
    def fromElementTree(tree):
        data_proper_acte = tree.find('data').find('data_proper_acte').text
        match = re.match('[0-9]{2}\/[0-9]{2}\/[0-9]{4}', data_proper_acte)
        date = match.group(0) 
        date = datetime.strptime(date, '%d/%m/%Y')
        hour = tree.find('data').find('hora_inici')
        if hour is not None:
            hour = hour.text
        else:
            match = re.search('[0-9]{2}\.[0-9]{2}', data_proper_acte)
            if match is not None:
                hour = match.group(0)
        hour = datetime.strptime(hour, '%H.%M').time() if hour is not None else None
        name = html.unescape(tree.find('nom').text)
        place = html.unescape(tree.find('lloc_simple').find('nom').text)
        address_tree = tree.find('lloc_simple').find('adreca_simple')
        address = ""
        for item in address_tree.iter():
            if item.tag != 'coordenades' and item.text:
                address = address + ' ' + item.text
        address = html.unescape(address.strip())
        coords = address_tree.find('coordenades').find('googleMaps')
        if coords is not None:
            try:
                lat = float(coords.get('lat'))
                lon = float(coords.get('lon'))
                latlong = LatLong(latitude=lat, longitude=lon)
            except:
                latlong = None
        else:
            latlong = None
        return Event(date=date, hour=hour, name=name, place=place, address=address, coords=latlong)

    def __repr__(self):
        return str(self.__dict__)

class Station:

    def __init__(self, **kwargs):
        allowed_keys = set(['coords', 'slots', 'bikes', 'street', 'number'])
        self.__dict__.update((key, None) for key in allowed_keys)
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in allowed_keys)

    @staticmethod
    def fromElementTree(tree):
        slots = int(tree.find('slots').text)
        bikes = int(tree.find('bikes').text)
        lat = float(tree.find('lat').text)
        lon = float(tree.find('long').text)
        latlong = LatLong(latitude=lat, longitude=lon)
        street = html.unescape(tree.find('street').text)
        number = tree.find('streetNumber').text
        return Station(slots=slots, bikes=bikes, coords=latlong, street=street, number=number)

    def __repr__(self):
        return str(self.__dict__)

if __name__ == "__main__":
    main()