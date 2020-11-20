# -*- coding: utf-8 -*-
from __future__ import print_function

import csv
import math
import random
import tools as gem

from collections import defaultdict
from datetime import datetime
from simanneal import Annealer
from os.path import join

def distance(a, b):
    """Calculates distance between two latitude-longitude coordinates."""
    R = 3963  # radius of Earth (miles)
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    return math.acos(math.sin(lat1) * math.sin(lat2) +
                     math.cos(lat1) * math.cos(lat2) * math.cos(lon1 - lon2)) * R


class TravellingSalesmanProblem(Annealer):

    """Test annealer with a travelling salesman problem.
    """

    # pass extra data (the distance matrix) into the constructor
    def __init__(self, state, distance_matrix):
        self.distance_matrix = distance_matrix
        super(TravellingSalesmanProblem, self).__init__(state)  # important!

    def move(self):
        """Swaps two cities in the route."""
        # no efficiency gain, just proof of concept
        # demonstrates returning the delta energy (optional)
        initial_energy = self.energy()

        a = random.randint(0, len(self.state) - 1)
        b = random.randint(0, len(self.state) - 1)
        self.state[a], self.state[b] = self.state[b], self.state[a]

        return self.energy() - initial_energy

    def energy(self):
        """Calculates the length of the route."""
        e = 0
        for i in range(len(self.state)):
            e += self.distance_matrix[self.state[i-1]][self.state[i]]
        return e


if __name__ == '__main__':

    # # latitude and longitude for the twenty largest U.S. cities
    # cities = {
    #     'New York City': (40.72, 74.00),
    #     'Los Angeles': (34.05, 118.25),
    #     'Chicago': (41.88, 87.63),
    #     'Houston': (29.77, 95.38),
    #     'Phoenix': (33.45, 112.07),
    #     'Philadelphia': (39.95, 75.17),
    #     'San Antonio': (29.53, 98.47),
    #     'Dallas': (32.78, 96.80),
    #     'San Diego': (32.78, 117.15),
    #     'San Jose': (37.30, 121.87),
    #     'Detroit': (42.33, 83.05),
    #     'San Francisco': (37.78, 122.42),
    #     'Jacksonville': (30.32, 81.70),
    #     'Indianapolis': (39.78, 86.15),
    #     'Austin': (30.27, 97.77),
    #     'Columbus': (39.98, 82.98),
    #     'Fort Worth': (32.75, 97.33),
    #     'Charlotte': (35.23, 80.85),
    #     'Memphis': (35.12, 89.97),
    #     'Baltimore': (39.28, 76.62)
    # }

    data_dir = join('..', 'data')
    counties_csv_fnm = 'counties.csv'
    county_seat_csv_fnm = 'county-seats.csv'
    rand = 10

    counties = gem.getcounties(join(data_dir, counties_csv_fnm))
    seats = gem.getcounty_seats(join(data_dir, county_seat_csv_fnm))
    cands = gem.join_counties_seats(counties, seats)
    cands = gem.visit_data(cands)
    # rand_slice = gem.rand_slice(cands[['v_id', 'v_lat', 'v_lon']], rand)
    # cands_dict = gem.dict_data(rand_slice)
    cands_dict = gem.dict_data(cands[['v_id', 'v_lat', 'v_lon']])
    cities = cands_dict

    # initial state, a randomly-ordered itinerary
    init_state = list(cities)
    random.shuffle(init_state)

    # create a distance matrix
    distance_matrix = defaultdict(dict)
    for ka, va in cities.items():
        for kb, vb in cities.items():
            distance_matrix[ka][kb] = 0.0 if kb == ka else distance(va, vb)

    tsp = TravellingSalesmanProblem(init_state, distance_matrix)
    tsp.set_schedule(tsp.auto(minutes=20))
    # since our state is just a list, slice is the fastest way to copy
    tsp.copy_strategy = "slice"
    state, e = tsp.anneal()

    # while state[0] != 'New York City':
    #     state = state[1:] + state[:1]  # rotate NYC to start

    print()
    print("%i mile route:" % e)
    # print(" -->  ".join(state))

fin_time = datetime.now().strftime("%Y%m%d_%H%M%S")
out_fnm = format('anneal_out_{}.csv'.format(fin_time))
outfile_fp = join(data_dir, out_fnm)

with open(outfile_fp, 'w', encoding='utf8') as outcsv:
    print('Writing results to {}'.format(outfile_fp))
    writer = csv.writer(outcsv, lineterminator="\n")
    writer.writerow(['v_ids'])
    for row in state:
        row = [row]
        writer.writerow(row)

print('Created and added data to {}'.format(outfile_fp))