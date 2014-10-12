#!/usr/bin/python3

# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
#
# This file is part of Azrael (https://github.com/olitheolix/azrael)
#
# Azrael is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Azrael is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Azrael. If not, see <http://www.gnu.org/licenses/>.

"""
Plot timing statistics to console.

The timing statistics are collected with the ``azrael.util.Timeit`` class.
"""

import io
import sys
import time
import IPython
import pymongo
import numpy as np
import pandas as pd

ipshell = IPython.embed


def main():
    # Mongo collection with timing data.
    db = pymongo.MongoClient()['timing']['timing']

    # Change the floating point display format.
    pd.options.display.float_format = '{:5,.3f}'.format

    last = 0
    while True:
        # Query all entries added between last call and now.
        query = {'start': {'$gt': last}}
        last = time.time()
        data = list(db.find(query))

        if len(data) > 0:
            # Create a temporary CSV file with the timing data for Pandas.
            s = '{} | {} | {}\n'
            csv = [s.format(_['name'], _['start'], _['elapsed']) for _ in data]
            csv = 'Name|Start|Elapsed\n' + ''.join(csv)
            csv = io.StringIO(csv)
            del s

            # Load the data into Pandas.
            df = pd.read_csv(csv, sep='|')
    
            # Convert the elapsed time to ms.
            df.Elapsed *= 1000

            # Compute various metrics for every measurement name.
            agg = [np.sum, np.mean, len]
            out = df[['Name', 'Elapsed']].groupby('Name').agg(agg)

            # Remove the top-level group and change the format of the 'len'
            # column to integer. Neither command changes the data but makes the
            # printout look nicer.
            out = out.Elapsed
            out['len'] = out['len'].astype(np.int64)

            # Display the results.
            print(out)
    
        print('---')
        time.sleep(2)
    

if __name__ == '__main__':
    main()
