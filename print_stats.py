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
Compute and print statistics for all metrics recorded by Azrael.
"""

import io
import sys
import time
import pymongo
import argparse
import numpy as np
import pandas as pd
from IPython import embed as ipshell


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Demo Script'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--interval', metavar='N', type=int, default=2,
         help='Update interval in seconds')

    # Run the parser.
    return parser.parse_args()


def printHeader(name):
    print('--- ' + name + ' ---')


def printDataframe(df):
    # Capitalize the headers and replace 'sum' by 'Total'.
    col = [_.capitalize() for _ in df.columns]
    df.columns = [_ if _ != 'Sum' else 'Total' for _ in col]

    # Convert data frame to string and prefix every line with some white space.
    out = df.to_string(index_names=False)
    out = ['  ' + _ for _ in out.splitlines()]
    out = '\n'.join(out)

    # Print the formatted data frame.
    print(out + '\n')


def printTimings(df):
    # Slice out all Time metrics.
    df = df[df.Type == 'Time'].copy()

    # Conver to Micro seconds.
    df['Value'] = 1000000 * df['Value']

    # Compute various statistics over all metric values.
    agg = ['count', 'min', 'max', 'mean', 'std', 'sum']
    out = df[['Metric', 'Value']].groupby('Metric').agg(agg)

    # Remove the top-level group (results in nicer printouts).
    out = out.Value

    # Print the stats.
    printHeader('Timings (us)')
    printDataframe(out)


def printQuantities(df):
    # Slice out all Quantity metrics.
    df = df[df.Type == 'Quantity'].copy()

    # Re-cast the values as integers.
    df['Value'] = df['Value'].astype(np.int64)

    # Compute various statistics over all metric values.
    agg = ['count', 'min', 'max', 'mean', 'std', 'sum']
    out = df[['Metric', 'Value']].groupby('Metric').agg(agg)

    # Remove the top-level group (results in nicer printouts).
    out = out.Value

    # Print the stats.
    printHeader('Quantity')
    printDataframe(out)


def main():
    # Parse command line arguments.
    param = parseCommandLine()

    # Mongo collection with timing data.
    db = pymongo.MongoClient()['timing']['timing']

    # Change the floating point display format.
    pd.options.display.float_format = '  {:5,.0f}'.format

    cntEmpty, last = 0, 0
    while True:
        # Query all entries added between last call and now.
        query = {'Timestamp': {'$gt': last}}
        last = time.time()
        data = list(db.find(query))

        if len(data) > 0:
            # Reset the empty counter and print a new header.
            cntEmpty = 0
            print('\r' + '*' * 78)
            print('Updated: {}'.format(time.ctime(last)))
            print('\r' + '*' * 78 + '\n')

            # Convert the metrics to an in-memory CSV file.
            s = '{}|{}|{}\n'
            csv = [s.format(_['Metric'], _['Value'], _['Type']) for _ in data]
            csv = 'Metric|Value|Type\n' + ''.join(csv)
            csv = io.StringIO(csv)
            del s

            # Load the CSV into Pandas.
            df = pd.read_csv(csv, sep='|')

            # Compute and print the metrics.
            printTimings(df)
            printQuantities(df)

        # Print line separator.
        print('\r' + '*' * 70 + ' {}'.format(cntEmpty), end='', flush=True)
        cntEmpty += 1

        # Wait for the specified interval.
        time.sleep(param.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
