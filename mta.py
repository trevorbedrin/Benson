import csv
import glob
import codecs
import random


from bs4 import BeautifulSoup
import pandas
import urllib2
import re

from collections import defaultdict
from pprint import pprint
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


DATA_DIRECTORY = "data/"
FILENAME_FORMAT = DATA_DIRECTORY + "turnstile_??????.txt"
EXTREME_COUNT_LIMIT = 1e6


def download(file_url, destination=None, filename=None):

    if destination is None:
        destination = '.'
    page = urllib2.urlopen(file_url)
    if filename is None: 
        filename = destination + '/' + file_url.split('/')[-1]
    local = open(filename, 'w')
    local.write(page.read())
    local.close()


def xls_to_csv(xls_filename, csv_filename = None, delimiter=None):

    xls =  pandas.ExcelFile(xls_filename)
    sheet = xls.sheet_names[0]
    data_frame = xls.parse(sheet)
    if csv_filename is None:
        csv_filename = xls_filename.rsplit('.xls',1)[0] + '.csv'
    if delimiter is None:
        delimiter = ','
    data_frame.to_csv(csv_filename, index=False, sep=delimiter)


def get_turnstile_data(num_files=None,
                       data_url="http://web.mta.info/developers/turnstile.html",
                       destination = None):

    # connect
    page  = urllib2.urlopen(data_url)
    soup = BeautifulSoup(page)
    base_url = data_url.strip('/').rsplit('/',1)[0]

    # get the turnstile key file
    turnstile_key_text = soup.find(text=re.compile("Remote Unit/Control Area/Station Name Key"))
    turnstile_key_file_url = base_url + '/' + turnstile_key_text.parent['href']
    print "Downloading turnstile key from %s" % turnstile_key_file_url
    download(turnstile_key_file_url, destination=destination, filename='turnstile_key.xls')
    xls_to_csv('turnstile_key.xls', 'turnstile_key.csv')

    # get the turnstile data files
    data_h2 = soup.find(text=re.compile("Data Files"))
    data_div = data_h2.parent.parent
    data_file_links = data_div.find_all("a")
    if num_files is not None:
        data_file_links = data_file_links[:num_files]
    total_file_num = len(data_file_links)
    for current_file_num, link in enumerate(data_file_links):
        data_file_url = base_url + '/' + link['href']
        print 'Downloading %i of %i: %s' % (current_file_num+1, 
                                            total_file_num,
                                            data_file_url)
        download(data_file_url, destination=destination)
    print 'Done.'


def get_glob(file_format=FILENAME_FORMAT):
    filenames = glob.glob(file_format)
    return filenames

def extract_turnstile_data_from_csvs(filenames):
    ts = defaultdict(list)
    for filename in filenames:
        with open(filename,'r') as infile:
            print 'extracting ',filename
            reader = csv.reader(infile)

            for line in reader:
                b,r,t = line[:3]
                entries = line[3:]
                ts[(b,r,t)].extend(entries)
    return ts

def get_ts_counts_fastawesome(ts):
    turnstile_counts = defaultdict(list)
    print 'calculating turnstile counts for %d turnstiles.'%len(ts.items())

    for turnstile,tlist in ts.iteritems():
        
        tlist = np.array(tlist).reshape(len(tlist)/5,5)
        days = sorted(list(set(tlist[:,0])))

        bookmark = 0
        for day in days:
            day_rows = np.array([tlist[bookmark]])
            entries = [int(tlist[bookmark][3])]
            while tlist[bookmark][0]==day and bookmark<tlist.shape[0]-1:
                #print bookmark,tlist[bookmark]
                bookmark += 1
                if tlist[bookmark][2]=='REGULAR':
                    day_rows = np.vstack((day_rows,tlist[bookmark]))
                    entries.append(int(tlist[bookmark][3]))
            entries = np.array(entries)

            diffs = np.diff(entries)
            day_count = sum(diffs[np.where((diffs>=0)&(diffs<10000))])
            date = datetime.strptime(day,'%m-%d-%y')

            turnstile_counts[turnstile].append((date,day_count))
            if day_count>20000: 
               print 'REALLY BIG!'
               print day 
               print entries
               print diffs
               print sum(diffs),np.max(entries)-np.min(entries),sum(diffs[np.where(diffs>=0)])

    return turnstile_counts


def collapse_data_to_booth_remote(turnstile_counts,stop_after=0):
    '''
    original data is listed by turnstile
    collapses and sums all turnstiles for each booth-remote 
    '''
    br_data_dict = defaultdict(list)
    # reduce to new indexes using only booth and remote, and put all the [date,counts] from the
    # different turnstiles in one big list
    for turnstile in turnstile_counts.iteritems():
        (b,r,t),counts = turnstile
        br_data_dict[(b,r)].extend(counts)

    # take each big list and sum up the counts for each date
    brcount = 1
    collapsed_dict = defaultdict(list)
    for br,c in br_data_dict.iteritems():
        brcount += 1
        collapsed = [[date,sum([tcount for d,tcount in c if d==date])] for date in set([date for date,count in c])]    
        #br_data_dict[br] = sorted(collapsed)
        collapsed_dict[br] = sorted(collapsed)    
        if brcount == stop_after: break
            
    return br_data_dict,collapsed_dict


def dates_and_counts(br_counts):
    dates,counts = ([d for d,c in br_counts],[c for d,c in br_counts])
    return dates,counts


def read_turnstile_data_from_filenames(filenames,verbose=False):
    """ given a glob (filename pattern with wildcards), this reads all the files """

    turnstile_data = defaultdict(list)    
    for filename in filenames:
        turnstile_data = add_week_to_data(turnstile_data, filename, stop_after=0,verbose=verbose)
    
    turnstile_data = remove_trailing_counts(turnstile_data)
    #turnstile_data = check_for_gnarly_data(turnstile_data)
    
    return turnstile_data


def convert_datestring_to_datetime(datestring_list):
    converted_list = []
    for datestr in datestring_list:
        date = datetime.strptime(datestr,'%m-%d-%y')
        converted_list.append(date)
    return converted_list


def plot_boothremote(boothremote):
    br_id,br_dates,br_counts = parse_boothremote(boothremote)
    p = plt.plot(br_dates,br_counts)
    return

def plot_boothremote_weekly(boothremote):
    br_id,dates,counts = parse_boothremote(boothremote)
    counts_by_week = shape_counts_to_weeks(counts)

    for week in counts_by_week:
        plt.plot(week)
    xl = plt.xlabel('Day of the week')
    yl = plt.ylabel('Number of turnstile entries')
    xt = plt.xticks(np.arange(7),['S','S','M','T','W','R','F'])    
    
def shape_counts_to_weeks(counts):
    # trim data down to even weeks
    flat_counts = counts[:]
    while len(flat_counts)%7:
        flat_counts.pop()
    flat_counts = np.array(flat_counts)

    counts_by_week = flat_counts.reshape(len(flat_counts)/7,7)
    return counts_by_week

def reshape_flat_counts_to_weekly(counts):
    # first let's trim this down to an even number of weeks so we can have a rectangle 
    flat_counts = counts[:]
    while len(flat_counts)%7:
        flat_counts.pop()
    # now convert it to a numpy array
    flat_counts = np.array(flat_counts)

    #reshape it into a rectangle 7 columns wide with a row for each week you have
    counts_by_week = flat_counts.reshape(len(flat_counts)/7,7)
    return counts_by_week


def parse_boothremote(boothremote):
    br_id,br_datecounts = boothremote
    
    dates = [d for d,c in br_datecounts]
    if type(dates[0])==type('a'):
        dates = convert_datestring_to_datetime(dates)
    counts = [c for d,c in br_datecounts]
    return br_id,dates,counts


def create_booth_remote_station_key(filename):

    booth_remote_to_station = {}
    with open(filename,'r') as infile:
        reader = csv.reader(infile)
        for line in reader:
            remote, booth, station, lines, div = line
            if remote == 'Remote': continue
            br = (booth, remote)
            # yell out if there are any duplicates                                                                                                                                   
            if br in booth_remote_to_station:
                print 'WARNING, MULTIPLE STATIONS FOR BOOTH-REMOTE %s' % br
            booth_remote_to_station[br] = station

    return booth_remote_to_station

def plot_weeks(br,station_name):
    br_id = br[0]
    dates,counts = dates_and_counts(br[1])
    for week in reshape_flat_counts_to_weekly(counts):
        plt.plot(week)
    
    xl = plt.xlabel('Day of the week')
    yl = plt.ylabel('Number of turnstile entries')
    xt = plt.xticks(np.arange(7),['S','S','M','T','W','R','F'])
    tt = plt.title('Ridership per day for station %s'%station_name)
    return

def get_a_random_boothremote(boothremotes):
    br = random.sample(boothremotes.items(),1)
    # random.sample gives us a list and we just want the item in that list
    return br[0]

def plot_timeseries_and_weeklies(br,station_key):
    f = plt.figure(figsize=(16,4)) 
    plt.subplot(121)
    plot_boothremote(br)
    tt = plt.title(station_key[br[0]])
    plt.subplot(122)
    plot_boothremote_weekly(br)
    tt = plt.title(station_key[br[0]])
    return


# def convert_datetime_in_time_series_collection(time_series_collection):
#     """ converts date strings to datetime objects.
#         assumes the time series collection format of:
#         {id: [(date_str, value), ... ]} 
#     """
#     converted_collection = {}
#     for _id, time_series in time_series_collection.items():
#         converted_time_series = []
#         for date_str, value in time_series:
#             date = datetime.strptime(date_str, '%m-%d-%y')
#             converted_time_series.append( (date, value) )
#         converted_collection[_id] = converted_time_series
#     return converted_collection

# def convert_time_series_into_x_and_y(time_series):
#     """ takes a list of tuples [(time, value), ...]
#         and returns two lists of same length,
#         one for the times, the other for values
#     """
#     days, values = [], []
#     for day, value in time_series:
#         days.append(day)
#         values.append(value)
#     return days, values


# def add_week_to_data(data_dict, filename, stop_after=100, verbose=True):
#     ''' don't use this one'''
#     #use stop_after = 0 to not stop                                                                                                                                                  
#     counter = 1
#     faulty_data_counter = 0

#     with open(filename,'r') as infile:
#         reader = csv.reader(infile)
#         for line in reader:
#             counter += 1
#             booth,remote,turnstile = line[:3]

#             for i in range(4,len(line),5):
#                 irr = False
#                 if line[i]=='00:00:00':
#                     #print line[i-1:i+4]
                                                                                                                              
#                     date,time,regular,today_cumulative,exits = line[i-1:i+4]
#                     if regular != 'REGULAR':
#                         irr = True
#                         continue
#                     if irr: print 'oops'
#                     today_cumulative = int(today_cumulative)

#                     # check for a previous entry      
                                                                                                                 
#                     if data_dict[(booth,remote,turnstile)] != []:
#                         yesterday,yesterday_cumulative = data_dict[(booth,remote,turnstile)].pop()
 
#                         yesterdays_count = today_cumulative-yesterday_cumulative
#                         #data_dict[(booth,remote,turnstile)].append([yesterday,yesterdays_count])
#                         if  0 <= yesterdays_count:
#                             data_dict[(booth,remote,turnstile)].append([yesterday,yesterdays_count])
#                         else:

#                             faulty_data_counter += 1
 
#                     # add the new entry to the dict      
                                                                                                               
#                     data_dict[(booth,remote,turnstile)].append([date,today_cumulative])
#             if counter == stop_after: break

#         if verbose:
#             print '%i turnstile-days are skipped due to faulty data' % faulty_data_counter

#     return data_dict


# def remove_trailing_counts(data_dict):
#     # remove the last date/entries list from each list (raw cumulative leftovers)                                                                                                    
#     for tstile,count_list in data_dict.iteritems():
# 	if len(count_list) > 0:
#             count_list.pop()
#     return data_dict

# def get_gnarly_data(data_dict):
#     gnarly_dict = defaultdict(list)
#     for tstile, count_list in data_dict.iteritems():
#         neg_counts = [(d,c) for d,c in count_list if c < 0]
#         if neg_counts: gnarly_dict[tstile]=neg_counts

#     return gnarly_dict


# def collapse_booth_remote_data_to_stations(br_time_series, br_to_station_key):
#     """ Take the {booth-remote : timeseries} data and collapse it to                                                                                                                 
#         stations """
#     station_time_series = {}
#     for booth_remote, time_series in br_time_series.iteritems():
#         try:
#             station = br_to_station_key[booth_remote]
#         except KeyError:
#             print 'WARNING. Booth %s (remote %s) IS NOT IN STATION KEY. SKIPPING.' % booth_remote
#             continue
#         if station not in station_time_series:
#             station_time_series[station] = time_series
#         else:
#             # combine the new time series with the existing one                                                                                                                      
#             existing_series = station_time_series[station]
#             existing_counts = dict(existing_series)
#             for date, new_count in time_series:
#                 if date in existing_counts:
#                     existing_counts[date] += new_count
#                 else:
#                     existing_counts[date] = new_count
#             combined_series = sorted(existing_counts.items())
#             station_time_series[station] = combined_series

#     return station_time_series


# def get_daily_turnstile_counts(ts):
#     turnstile_counts = defaultdict(list)
#     #print 'this is how many: probably 4542.'
#     for turnstile,tlist in ts.iteritems():

#         tlist = np.array(tlist).reshape(len(tlist)/5,5)
#         #tlist[:,3]=tlist[:,3].astype(int)
#         #tlist[:,4]=tlist[:,4].astype(int)    

#         days = sorted(list(set(tlist[:,0])))
    
#         bookmark = 0
#         for day in days:
#             # # find the indices for all the rows for your day 
#             # day_inds = np.where(tlist[:,0]==day)
#             # # add one more index for the first row from tomorrow if you aren't at the end of the file
#             # if np.max(day_inds)+1 < tlist.shape[0]:
#             #     day_inds = np.append(day_inds,np.max(day_inds)+1)

#             day_rows_raw = [tlist[bookmark]]
#             while tlist[book
            
#             # extract the rows from your indices
#             day_rows_raw = tlist[day_inds]
#             # get rid of the ones that aren't coded "REGULAR"
#             day_rows = day_rows_raw[np.where(day_rows_raw[:,2]=='REGULAR')]

#             # pull the column with the ticker counts for entries
#             day_entries = day_rows[:,3].astype(int)

#             # this says, if the ticker number only goes up and never down, the range of the ticker values is your count for the day
#             if len(day_entries)>0 and not sum(np.diff(day_entries)<0):
#                 day_count = np.max(day_entries)-np.min(day_entries)
                
#             # otherwise, 
#             else:
#                 # there might not be any REGULAR rows on your day
#                 day_count = 0
#                 # or you can just sum up the positive increases while ignoring the decreases. I'm not sure yet if this is a terrible idea.
#                 if len(day_entries)>0:
#                     day_count = sum(np.diff(day_entries)[np.where(np.diff(day_entries)>0)])

#             date = datetime.strptime(day,'%m-%d-%y')
#             turnstile_counts[turnstile].append((date,day_count))

#     return turnstile_counts



