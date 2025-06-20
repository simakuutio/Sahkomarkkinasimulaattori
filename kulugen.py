#!/usr/bin/python3
# -*- coding: utf-8 -*-

import datetime
import random as ra
import sys
import os.path
import sqlite3
import csv
from os import name
from getopt import getopt
from cmd import Cmd
import xml.etree.ElementTree as ET

# Colors works properly on *nix
if name == 'posix':
    bold = '\u001b[1m'
    underline = '\u001b[4m'
    reverse = '\u001b[7m'

    red = '\u001b[31m'
    green = '\u001b[32m'
    yellow = '\u001b[33m'
    blue = '\u001b[34m'
    magenta = '\u001b[35m'
    cyan = '\u001b[36m'
    white = '\u001b[37m'
    reset = '\u001b[0m'
else: # Windows etc broken systems get NO colors.
    red = green = yellow = blue = magenta = cyan = white = reset = bold = underline = reverse = ''

try:
    from libs.kirjasto import gen_timestamp, add_check_digit
except ImportError:
    print(red + bold, 'Error: kirjasto.py missing, please consult Fingrid Datahub test team to get new one!',reset)
    exit()

try:
    from libs.fconfig import prod_ap, prod_ep
except ImportError:
    print('Error: fconfig.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

apoint_csv = 'kp.csv'
rpoint_csv = 'rp.csv'

database = 'fingrid.db'

# Global temp storage dictionary
storage = {'hours': 24, 'start_time': '00:00', 'xml_file': None, 'metric': 'kWh', 'metric_id': '8716867000030'}

# https://pythonprogramming.net/sqlite-part-2-dynamically-inserting-database-timestamps/
# https://stackoverflow.com/questions/3247183/variable-table-name-in-sqlite


# tables: APOINT, RPOINT
def createSQL(db, name, key):
    try:
        with sqlite3.connect(db) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS {}
            (SESSION_ID     INT  NOT NULL UNIQUE,
            APOINT_ID       INT,
            RPOINT_ID       INT,
            R_IN            INT,
            R_OUT           INT,
            METERINGPOINT   INT,
            TIMESTAMP       TEXT NOT NULL,
            DSO             INT,
            MGA             INT,
            SUPPLIER        INT,
            KULUTUS         INT,
            AP_TYPE         TEXT,
            REMOTE_READ     INT,
            METHOD          TEXT,
            PRIMARY KEY({}, TIMESTAMP));
            '''.format(name, key))
    except sqlite3.OperationalError as e:
        print(e)

def insertSQL_apoint(table,
                     cursor,
                     sessionid,
                     id,
                     meteringpoint,
                     timestamp,
                     dso,
                     mga,
                     supplier,
                     usage,
                     ap_type,
                     remote_read,
                     method):
    dd,mm,yy = timestamp[:10].split('-')
    aika = timestamp[11:19]
    method = method.strip()
    # YYYY-MM-DD HH:MM:SS
    timestamp = yy + '-' + mm + '-' + dd + ' ' + aika

    try:
        cursor.execute('''INSERT INTO {}(SESSION_ID,
        APOINT_ID,
        METERINGPOINT,
        TIMESTAMP,
        DSO,
        MGA,
        SUPPLIER,
        KULUTUS,
        AP_TYPE,
        REMOTE_READ,
        METHOD)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)'''.format(table),
                       (sessionid,
                        id,
                        meteringpoint,
                        timestamp,
                        int(dso),
                        mga,
                        supplier,
                        usage,
                        ap_type,
                        remote_read,
                        method))
    except sqlite3.IntegrityError:
        print(cyan,'Accounting point {} with timestamp {} already in database'.format(id, timestamp))
        print(reset, end='')
        return 1

def insertSQL_rpoint(table, cursor, sessionid, r_id, timestamp, dso, r_in, r_out, usage):
    dd,mm,yy = timestamp[:10].split('-')
    aika = timestamp[11:19]

    # YYYY-MM-DD HH:MM:SS
    timestamp = yy + '-' + mm + '-' + dd + ' ' + aika

    try:
        cursor.execute('''INSERT INTO {}(SESSION_ID, RPOINT_ID, TIMESTAMP, DSO, R_IN, R_OUT, KULUTUS)
        VALUES(?,?,?,?,?,?,?)'''.format(table), (sessionid, r_id, timestamp, int(dso), r_in, r_out, usage))
    except sqlite3.IntegrityError:
        print(cyan,'Exchange point {} with timestamp {} already in database'.format(r_id, timestamp))
        print(reset, end='')
        return 1

def generate_apoint_xml(apoint, date, insert_string):
    in_file = 'libs/kulutus_template.xml'
    out_file = 'xml/kulutus' + '_' + apoint + '_' + ''.join(date.split('-', 3)) + '.xml'
    storage['out_file'] = out_file
    if not os.path.exists('xml'):
        os.makedirs('xml')
    with open(out_file, 'w') as outfile, open(in_file, 'r') as infile:
        for row in infile:
            if 'Kulutus' in row:
                outfile.write(insert_string)
            else:
                outfile.write(row)
    storage['xml_file'] = out_file
    finalize_xml(out_file, storage['dso'], apoint)

def finalize_xml(datafile, dso, apoint):
    """
    Input: integer, integer, integer
    Output: file
    """
    import xml.etree.ElementTree as ET
    import random as ra
    ns1 = './/{urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:v1}'
    ns3 = './/{urn:fi:Datahub:mif:common:HDR_Header:elements:v1}'
    ns4 = './/{urn:fi:Datahub:mif:common:PEC_ProcessEnergyContext:elements:v1}'
    ns5 = './/{urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:elements:v1}'
    try:
        tree = ET.parse(datafile)
        tree.find(ns3+'Identification').text = generate_id(32)
        tree.find(ns1+'Transaction')[0].text = generate_id(32)
        tree.find(ns3+'PhysicalSenderEnergyParty')[0].text = dso
        tree.find(ns3+'JuridicalSenderEnergyParty')[0].text = dso
        tree.find(ns3+'Creation').text = gen_timestamp() # Now
        tree.find(ns5+'Start').text = storage['start_date']
        tree.find(ns5+'End').text = storage['end_date']
        tree.find(ns5+'ProductIncludedProductCharacteristic')[0].text = storage['metric_id']
        tree.find(ns5+'ProductIncludedProductCharacteristic')[1].text = storage['metric']
        tree.find(ns5+'MeteringPointUsedDomainLocation')[0].text = apoint
        tree.find(ns5+'MeteringGridAreaUsedDomainLocation')[0].text = storage['mga']

        tree.write(datafile)
    except FileNotFoundError:
        print(red, f"Error: File not found - {datafile}", reset)
    except ET.ParseError as e:
        print(red, f"Error: XML parsing error in {datafile} - {e}", reset)
    except IOError:
        print(red, f"Error: File I/O error with {datafile}", reset)

def generate_rpoint_xml(rpoint, date, insert_string):
    in_file = 'libs/rajapiste_template.xml'
    out_file = 'xml/rajapiste' + '_' + rpoint + '_' + ''.join(date.split('-', 3)) + '.xml'
    storage['out_file'] = out_file
    if not os.path.exists('xml'):
        os.makedirs('xml')
    with open(out_file, 'w') as outfile, open(in_file, 'r') as infile:
        for row in infile:
            if 'Kulutus' in row:
                outfile.write(insert_string)
            else:
                outfile.write(row)
    storage['xml_file'] = out_file
    finalize_rpoint_xml(out_file, storage['dso'], rpoint)

def finalize_rpoint_xml(datafile, dso, rpoint):
    """
    Input: integer, integer, integer
    Output: file
    """
    import random as ra
    ns1 = './/{urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:v1}'
    ns3 = './/{urn:fi:Datahub:mif:common:HDR_Header:elements:v1}'
    ns4 = './/{urn:fi:Datahub:mif:common:PEC_ProcessEnergyContext:elements:v1}'
    ns5 = './/{urn:fi:Datahub:mif:metering:E66_EnergyTimeSeries:elements:v1}'
    try:
        tree = ET.parse(datafile)
        tree.find(ns3+'Identification').text = generate_id(32)
        tree.find(ns1+'Transaction')[0].text = generate_id(32)
        tree.find(ns3+'PhysicalSenderEnergyParty')[0].text = dso
        tree.find(ns3+'JuridicalSenderEnergyParty')[0].text = dso
        tree.find(ns3+'Creation').text = gen_timestamp() # Now
        tree.find(ns5+'Start').text = storage['start_date']
        tree.find(ns5+'End').text = storage['end_date']
        tree.find(ns5+'MeteringPointUsedDomainLocation')[0].text = rpoint
        tree.find(ns5+'InAreaUsedDomainLocation')[0].text = storage['in']
        tree.find(ns5+'OutAreaUsedDomainLocation')[0].text = storage['out']

        tree.write(datafile)
    except FileNotFoundError:
        print(red, f"Error: File not found - {datafile}", reset)
    except ET.ParseError as e:
        print(red, f"Error: XML parsing error in {datafile} - {e}", reset)
    except IOError:
        print(red, f"Error: File I/O error with {datafile}", reset)

def generate_id(length):
    import random as rand
    symbols = "abcdef1234567890"
    id = ""
    for i in range (0, length):
        id += rand.choice(symbols)
    return id

def date_input():
    """
    Input: None
    Output: formatted datestring
    """
    try:
        date_entry = input('Start date (for example: 1.7.2019): ')
        day, month, year = date_entry.split('.')
        date = datetime.datetime(day=int(day), month=int(month), year=int(year))
        return date.strftime("%d.%m.%Y")
    except ValueError:
        print(red,'Error: Invalid date format.',reset)
        exit()

def dategen(dateinput=None, nro_days=None):
    """
    Input: None
    Output: list of strings
    """
    try:
        Days = 0
        paivat = []
        if not (os.path.isfile(apoint_csv)):
            from kpgen import output_apoint
            output_apoint(None, None, None, None, None, None)

        if nro_days == None:
            while Days < 1:
                Days = int(input('Number of days: '))
        else:
            Days = nro_days

        if dateinput == None: # ask from user
            Day, Month, Year = date_input().split('.')
            start_date = datetime.datetime(day=int(Day), month=int(Month), year=int(Year))
            end_date = start_date + datetime.timedelta(days=int(Days))
            storage['start_date'] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            storage['end_date'] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            Day, Month, Year = dateinput.split('.') # cmd-line value
            start_date = datetime.datetime(day=int(Day), month=int(Month), year=int(Year))
            if storage['hours'] == 24 and nro_days: # whole days
                end_date = start_date + datetime.timedelta(days=int(Days))
            elif 'hours' in storage.keys() and not nro_days: # by hours
                start_date = datetime.datetime(day=int(Day), month=int(Month), year=int(Year), hour=int(storage['start_time'][0:2]), minute=int(storage['start_time'][3:]), second=0)
                end_date = start_date + datetime.timedelta(hours=int(storage['hours']))
            storage['start_date'] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            storage['end_date'] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
 
        while start_date < end_date:
            paivat.append(start_date.strftime("%d-%m-%YT%H:%M:%SZ"))
            start_date += datetime.timedelta(hours=1)
 
        return paivat

    except ValueError:
        print(red,'Error: Invalid number of days value',reset)
        exit()

def n_hours(dateinput, timeinput, Hours):
    output=[]
    Day, Month, Year = dateinput.split('.')
    Hour, Minute = timeinput.split(':')
    start_date = datetime.datetime(day=int(Day), month=int(Month), year=int(Year), hour=int(Hour), minute=int(Minute), second=0)
    for tunnit in range(Hours):
        start_date += datetime.timedelta(hours=1)
        print(start_date.strftime("%d-%m-%YT%H:%M:%SZ"))

class Printer():
    """Print things to stdout on one line"""
    def __init__(self,data):
        sys.stdout.write("\r\x1b[K"+data.__str__())
        sys.stdout.flush()

def kulutus(range_min=None, range_max=None):
    """
    Input: integer
    Output: integer
    """
    if range_min and range_max and (range_min < range_max):
        return ra.randint(int(range_min),int(range_max))/10
    else:
        return ra.randint(0,100)/10

def kpaikat():
    lista = []

    if not (os.path.isfile(apoint_csv)):
        from kpgen import output_apoint
        output_apoint(None, None, None, None, None, None)
    try:
        with open(apoint_csv,'r') as f:
            next(f)
            for y in f:
                lista.append(y.split(',')[0])
            return lista
    except FileNotFoundError:
        print(magenta,'kp.csv not found. Please run kpgen and try again',reset)
        exit()

def luo_kulutus(dateinput, days, db, apoint=None, state=''): # SQL
    """
    Input: string, integer, string, integer
    Output: File
    """

    dates = dategen(dateinput, days)
    if not state:
        createSQL(db, 'apoint', 'APOINT_ID')
        createSQL(db, 'rpoint', 'RPOINT_ID')
    xml_string = ''
    count = 0

    try:
        if apoint: # for single accounting point
                with open('xml/'+str(apoint)+'.txt','a') as f_out, open(apoint_csv,'r') as f_in:
                    for row in f_in:
                        if str(apoint) in row:
                            meteringpoint = row.split(',')[1]
                            dso = row.split(',')[3]
                            storage['supplier'] = row.split(',')[2]
                            storage['dso'] = dso
                            storage['mga'] = row.split(',')[4]
                            storage['ap_type'] = row.split(',')[8]
                            storage['remote_read'] = row.split(',')[9]
                            storage['method'] = row.split(',')[10]
                            break
                        print("==== Processing {} ====".format(apoint))
                        with sqlite3.connect(database) as conn:
                            cursor = conn.cursor()
                            for hour in dates:
                                count += 1
                                if not prod_ap: # random
                                    Kulutus = kulutus(None, None)
                                else: #static
                                    Kulutus = prod_ap
                                f_out.write(hour +' '+ str(Kulutus)+'\n')
                                xml_string += 8*'\t' + '<urn4:OBS><urn4:SEQ>{}</urn4:SEQ><urn4:EOBS>\
<urn4:QTY>{}</urn4:QTY><urn4:QQ>{}</urn4:QQ>\
</urn4:EOBS></urn4:OBS>\n'.format(count, Kulutus, state)
                                sessionid = generate_id(32)
                                if not state:
                                    result = insertSQL_apoint('apoint',
                                                              cursor,
                                                              sessionid,
                                                              apoint,
                                                              meteringpoint,
                                                              hour,
                                                              storage['dso'],
                                                              storage['mga'],
                                                              storage['supplier'],
                                                              Kulutus,
                                                              storage['ap_type'],
                                                              storage['remote_read'],
                                                              storage['method'].strip())
                            generate_apoint_xml(str(apoint), dates[0][:10], xml_string)
                            xml_string = ''
                            count = 0
                            conn.commit()
                Printer("==== {} processed succesfully ====\n".format(apoint))

        else: # for all accounting points in kp.csv and rajapiste in rp.csv
            with open(apoint_csv,'r') as apoint, open(rpoint_csv,'r') as rpoint:
                next(apoint)
                for line in apoint:
                    storage['dso'] = line.split(',')[3]
                    storage['supplier'] = line.split(',')[2]
                    storage['mga'] = line.split(',')[4]
                    storage['ap_type'] = line.split(',')[8]
                    storage['remote_read'] = line.split(',')[9]
                    storage['method'] = line.split(',')[10]
                    with open('xml/'+line.split(',')[0]+'.txt','a') as output:
                        print("==== Processing {} ====".format(line.split(',')[0]))
                        with sqlite3.connect(database) as conn:
                            cursor = conn.cursor()
                            for hour in dates:
                                count += 1
                                if not prod_ap: #random
                                    Kulutus = kulutus(None, None)
                                else: #static
                                    Kulutus = prod_ap
                                output.write(hour +' '+ str(Kulutus)+'\n')
                                xml_string += 8*'\t' + '<urn4:OBS><urn4:SEQ>{}</urn4:SEQ><urn4:EOBS>\
<urn4:QTY>{}</urn4:QTY></urn4:EOBS></urn4:OBS>\n'.format(count, Kulutus)
                                sessionid = generate_id(32)
                                result = insertSQL_apoint('apoint',
                                                          cursor,
                                                          sessionid,
                                                          line.split(',')[0],
                                                          line.split(',')[1],
                                                          hour, 
                                                          storage['dso'],
                                                          storage['mga'],
                                                          storage['supplier'],
                                                          Kulutus,
                                                          storage['ap_type'],
                                                          storage['remote_read'],
                                                          storage['method'])
                            generate_apoint_xml(line.split(',')[0], dates[0][:10], xml_string)
                            xml_string = ''
                            count = 0
                            conn.commit()
                    Printer("==== {} processed succesfully ====\n".format(line.split(',')[0]))
                apoint.seek(0)
                print('\n')
                next(apoint)

                print('Exchange points:')
                next(rpoint)
                for line in rpoint:
                    storage['min'] = line.split(',')[4]
                    storage['max'] = line.split(',')[5]
                    storage['in'] = line.split(',')[2]
                    storage['out'] = line.split(',')[3]
                    storage['dso'] = line.split(',')[1]
                    with open('xml/r'+line.split(',')[0]+'.txt','a') as output:
                        print("==== Processing {} ====".format(line.split(',')[0]))
                        with sqlite3.connect(database) as conn:
                            cursor = conn.cursor()
                            for hour in dates:
                                count += 1
                                if not prod_ep: #random
                                    Kulutus = kulutus(storage['min'], storage['max'])
                                else: #static
                                    Kulutus = prod_ep
                                output.write(hour +' '+ str(Kulutus)+'\n')
                                xml_string += 8*'\t' + '<urn4:OBS><urn4:SEQ>{}</urn4:SEQ><urn4:EOBS>\
<urn4:QTY>{}</urn4:QTY></urn4:EOBS></urn4:OBS>\n'.format(count, Kulutus)
                                sessionid = generate_id(32)
                                # id, dso, in, out, min, max
                                result = insertSQL_rpoint('rpoint',
                                                          cursor,
                                                          sessionid,
                                                          line.split(',')[0],
                                                          hour,
                                                          storage['dso'],
                                                          storage['in'],
                                                          storage['out'],
                                                          Kulutus)
                            generate_rpoint_xml(line.split(',')[0], dates[0][:10], xml_string)
                            xml_string = ''
                            count = 0
                            conn.commit()
                    Printer("==== {} processed succesfully ====\n".format(line.split(',')[0]))
                rpoint.seek(0)
                print('\n')
                next(rpoint)

    except FileNotFoundError:
        print(magenta,'{} missing, run kpgen.py to create new one.'.format(apoint_csv))
        print(reset, end='')

def find_id(apoint, index):
    with open(apoint_csv, 'r') as f:
        myData = csv.reader(f)
        for row in myData:
            if apoint in row:
                return row[index]

set_commands = ('apoint','startdate','days','hours','starttime','metering_state','metric','mga')
list_commands = ('apoint', 'mga')

class Prompt(Cmd):

    def __init__(self):
        Cmd.__init__(self)
        self.prompt = '<Command> '
        self.intro = '\nWelcome! Type ? or 2 x <tab> to list available commands\nWith help <command> small help for each command.'
        self. __hidden_methods = ('do_EOF',)
        self.apoint = None
        self.supplier = None
        self.dso = None
        self.mga = None
        self.startdate = None
        self.days = 0
        self.hours = 24
        self.starttime = '00:00'
        self.state = ''
        self.metric = 'kWh'

    def emptyline(self):
        pass

    def completenames(self, text, *ignored):
        dotext = 'do_'+text
        return [a[3:]+' ' for a in self.get_names() if a.startswith(dotext) and a not in self.__hidden_methods]

    def default(self, line):
        self.stdout.write('*** Unknown command: %s\n'%line)

    def do_send(self, args = None):
        from libs.fconfig import url, DSO
        from requests import post
        from shutil import move

        headers = {'content-type': 'text/xml;charset=UTF-8', 'User-Agent': 'Apache-HttpClient/4.5.2 (FingridTesttool)'}
        if storage.get('dso',None) and storage.get('xml_file',None):
            with open(storage['xml_file'], 'r') as source_xml:
                input_xml = source_xml.read()
                req_url = url + DSO[storage['dso']]
                resp = post(req_url, data=input_xml, headers=headers, cert=("certs/cert.pem", "certs/key_nopass.pem"))
                print(cyan,resp.text,reset)
                if not os.path.exists('log'):
                    os.makedirs('log')
                with open('log/'+'resp_' + storage['xml_file'][4:],'w') as db:
                    Response = resp.content.decode("utf-8")
                    db.write("{}".format(str(Response)))
                move(storage['xml_file'], 'xml/'+'DONE_' + storage['xml_file'][4:])
                print(green,storage['xml_file'][4:], 'sent!',reset)
        else:
            print(magenta,'Create request XML first!',reset)
    
    def help_send(self, args = None):
        print(cyan,'Sends single usage xml request.',reset)
        print(cyan,'If you want to send more at once, please use soapreq.py',reset)

    def help_help(self, args = None):
        print(cyan,'Gives short help for each command.',reset)
        print(cyan,'Usage: help command',reset)

    def do_list_apoint(self, args = None):
        'Lists all accounting points generated with kpgen'
        paikka = (x for x in kpaikat())
        count = 1
        total = 0
        for line in paikka:
            total +=1
            if count != 10:
                print('{} '.format(line), end='')
                count +=1
            else:
                print('{}'.format(line))
                count = 1
        if count <= 10:
            print('\n'+189*'='+'\nTotal: {}'.format(total))
        else:
            print('\n'+189*'='+'\nTotal: {}'.format(total))

    def help_list_apoint(self, args = None):
        print(cyan,'Lists all available accounting points',reset)

    def do_kulutus(self, args):
        'Produces kulutus for all APOINT'
        if len(args.split(' ')) == 2:
            date, days = args.split(' ')
            luo_kulutus(date, days, database, None)
        else:
            print(cyan,'Usage: kulutus <date> <number of days>',reset)
            print(cyan,'Example: kulutus 1.1.2019 10',reset)
            print(cyan,'Produces usage for all accounting points found from kp.csv',reset)
            print(cyan,'Usage begins from 1.1.2019 for 10 days (24 hours per day)',reset)

    def help_kulutus(self, args = None):
        print(cyan,'Produces usage for all accounting points',reset)

    def do_single_kulutus(self, arg = None):
        if self.apoint and self.startdate and self.days:
            luo_kulutus(self.startdate, self.days, database, self.apoint, self.state)
        elif not self.apoint:
            print(green,'Set accounting point with "set apoint apoint_id"',reset)
        elif not self.startdate:
            print(green,'Set start date with "set startdate dd.mm.yyyy"',reset)
        elif not self.days and not storage['hours']:
            print(green,'Set number of days with "set days n"',reset)
        elif storage['hours']:
            luo_kulutus(self.startdate, self.days, database, self.apoint, self.state)

    def help_single_kulutus(self, args = None):
        print(cyan,'When proper arguments are given with set command, this command',reset)
        print(cyan,'creates usage xml for specific single accounting point.',reset)

    def do_reset(self, args = None):
        self.prompt = '<Command> '
        self.apoint = None
        self.supplier = None
        self.dso = None
        self.mga = None
        self.startdate = None
        self.days = 0
        self.hours = 24
        self.starttime = '00:00'
        self.state = ''
        self.metric = 'kWh'
        self.metric_id = '8716867000030'

    def help_reset(self, args = None):
        print(cyan,'Reset all values to default',reset)
            
    def do_set(self, args):
        params = args.split()
        if len(params) == 0:
            print(cyan,'\tDSO:\t\t' + green + '  {}'.format(self.dso))
            print(cyan,'\tMGA:\t\t' + green + '  {}'.format(self.mga))
            print(cyan,'\tAccounting point:' + green + ' {}'.format(self.apoint))
            print(cyan,'\tSupplier:\t' + green + '  {}'.format(self.supplier))
            print(cyan,'\tStart date:\t' + green + '  {}'.format(self.startdate))
            print(cyan,'\tNumber of days:\t' + green + '  {}'.format(self.days))
            print(cyan,'\tHours:\t\t' + green + '  {}'.format(self.hours))
            print(cyan,'\tStart time:\t' + green + '  {}'.format(self.starttime))
            if self.state:
                print(cyan,'\tMetering state:\t' + green + '  {}'.format(self.state))
            else:
                print(cyan,'\tMetering state:\t' + green + '  OK')
            print(cyan, '\tMetric:\t\t' + green +'  {}'.format(self.metric))
            print(reset, end='')
        else:
            if params[0] in set_commands:
                # Sets accounting point, have to be set first.
                if params[0] == set_commands[0]:
                    try:               
                        if len(params) == 2 and len(params[1]) == 18 and params[1] in kpaikat():
                            self.apoint = int(params[1])
                            self.supplier = find_id(params[1], 2)
                            self.dso = find_id(params[1], 3)
                            self.mga = find_id(params[1], 4)
                            storage['supplier'] = self.supplier
                            storage['dso'] = self.dso
                            storage['mga'] = self.mga
                            self.prompt = '<Command [#{}]> '.format(self.apoint)
                        elif len(params) == 1:
                            print(green,'Usage: set apoint <apoint_id>',reset)
                            print(green,'Example: set apoint 1234567890',reset)
                            print(green,'To list available accounting points, use command: list_apoint',reset)
                        else:
                            print(magenta,'{} is not valid accounting point.'.format(params[1]))
                            print(reset, end='')
                    except (FileNotFoundError, ValueError, IndexError) as e:
                        print(red, f'Error setting accounting point: {e}', reset)

                # Sets day to start (format dd.mm.yyyy)
                elif params[0] == set_commands[1]:
                    try:
                        if self.apoint: # Accounting point have to be set first
                            day,month,year = params[1].split('.')
                            datetime.datetime(int(year),int(month),int(day)) # date validation
                            if len(params) == 2 and len(params[1].split('.')) == 3:
                                self.startdate = params[1]
                                print(cyan,'Start date set to: ',green,'{}'.format(self.startdate))
                                print(reset, end='')
                            elif len(params[1].split(' ')) == 0 and not self.startdate:
                                print(cyan,'Start date set to: ',green,'{}'.format(self.startdate))
                                print(reset, end='')
                            else:
                                print(green,'Usage: set startdate dd.mm.yyyy',reset)
                        else:
                            print(magenta,'Accounting point have to set first',reset)
                    except ValueError:
                        print(red,'Date format incorrect.',reset)
                    except IndexError:
                        print(green,'Usage: set startdate dd.mm.yyyy',reset)

                # Sets number of days
                elif params[0] == set_commands[2]:
                    if self.apoint: # Accounting point have to be set first
                        if len(params) == 2:
                            try:
                                self.days = int(params[1].split(".")[0])
                                print(cyan,'Number of days set to: ',green,'{}'.format(self.days))
                                print(reset, end='')
                            except ValueError as err:
                                print(magenta,err,'not valid value for days',reset)
                        else:
                            print(green,'Usage: set days n',reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)

                # Sets hours to generate, default 24
                elif params[0] == set_commands[3]:
                    if self.apoint: # Accounting point have to be set first
                        if len(params) == 2:
                            try:
                                if int(params[1]) != 0 and int(params[1]) <= 10000:
                                    self.hours = int(params[1])
                                    storage['hours'] = self.hours
                                    print(cyan,'Hours set to: ',green,'{}'.format(self.hours))
                                    print(reset, end='')
                                else:
                                    print(magenta,'Hours should be between 1 - 10000',reset)
                            except ValueError:
                                print(red,err,'not valid value for hours',reset)
                        else:
                            print(cyan,'Usage: set hours n',reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)

                elif params[0] == set_commands[4]:
                    if self.apoint: # Accounting point have to be set first
                        # Start time
                        if len(params) == 2:
                            try:
                                Hour, Minute = params[1].split(':')
                                datetime.datetime(day = 1, month = 1, year = 2019, hour=int(Hour),minute=int(Minute)) # date validation
                                self.starttime = Hour[-2:].zfill(2) + ':' + Minute[-2:].zfill(2)
                                print(cyan,'Start time set to: ',green,'{}'.format(self.starttime))
                                print(reset, end='')
                                storage['start_time'] = self.starttime
                            except ValueError as err:
                                print(red,err,reset)
                            except OverflowError:
                                print(magenta,'Time value too large',reset)
                        else:
                            print(cyan,'Usage: set starttime n',reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)

                elif params[0] == set_commands[5]:
                    if self.apoint: # Accounting point have to be set first
                        # Metering state
                        states = {'OK': '',
                                  'Revised': 'Z01', 
                                  'Uncertain': 'Z02', 
                                  'Estimated': '99'}
                        if len(params) == 2:
                            try:
                                self.state = states[params[1]]
                                storage['state'] = self.state
                                print(cyan,'Metering state set as',green,'{} ({})'.format(self.state,params[1]))
                                print(reset, end='')
                            except KeyError as err:
                                print(magenta,'Metering state',err,'not valid, please select from:',green,str(list(states)).strip('[]'),reset)
                                self.state = ''
                        else:
                            print(cyan,'Usage: set metering_state <state>',reset)
                            print(cyan,'Example: set metering_state Uncertain',reset)
                            print(cyan,'Sets all values for state Uncertain',reset)
                            print(cyan,'Valid options for metering state:',green,str(list(states)).strip('[]'),reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)

                elif params[0] == set_commands[6]:
                    if self.apoint: # Accounting point have to be set first
                        # Metric
                        states = {'Wh': '8716867000030',
                                  'kWh': '8716867000030', 
                                  'MWh': '8716867000030', 
                                  'GWh': '8716867000030', 
                                  'varh': '8716867000139', 
                                  'kvarh': '8716867000139',
                                  'Mvarh': '8716867000139'}
                        if len(params) == 2:
                            try:
                                self.metric = params[1]
                                self.metric_id = states[params[1]]
                                storage['metric'] = self.metric
                                storage['metric_id'] = self.metric_id
                                print(green,'Metric set as {}'.format(self.metric))
                                print(reset, end='')
                            except KeyError as err:
                                print(magenta,err,'is not valid, please select from:',green,str(list(states)).strip('[]'),reset)
                                self.metric = 'kWh'
                        else:
                            print(cyan,'Usage: set metric <metric>',reset)
                            print(cyan,'Example: set metric MWh',reset)
                            print(cyan,'Sets metering metric to MWh',reset)
                            print(cyan,'Valid options for metric:',green,str(list(states)).strip('[]'),reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)

                if params[0] == set_commands[7]:
                    if self.apoint: # Accounting point have to be set first
                        try: # MGA              
                            if len(params) == 2 and len(params[1]) == 16:
                                self.mga = params[1]
                                storage['mga'] = self.mga
                                print(green,'MGA set as {}'.format(self.mga))
                                print(reset, end='')
                            elif len(params) == 1:
                                print(green,'Usage: set mga <mga_id>',reset)
                                print(green,'Example: set mga 1234567890',reset)
                            else:
                                print(magenta,'{} is not valid MGA.'.format(params[1]))
                                print(reset, end='')
                        except IndexError as e:
                            print(red, f'Error setting MGA: {e}', reset)
                    else:
                        print(magenta,'Accounting point have to set first',reset)
            else:
                print(cyan,'Usage:',reset)
                print(cyan,'set <setting> <value>',reset)
                print(cyan,'Type "set" for settings and their current value',reset)
                print(cyan,'Possible settings:',green,str(list(set_commands)).strip('[]'),reset)

    def complete_set(self, text, line, start_index, end_index):
        if text:
            return [
                address+' ' for address in set_commands
                if address.startswith(text)
            ]
        else:
            return set_commands

    def help_set(self, args = None):
        print(cyan,'Basic usage for set:',reset)
        print(cyan,'Available variables for set:',str(list(set_commands)).strip('[]'),reset)
        print(cyan,'apoint         ',green,'- accounting point for single usage',reset)
        print(cyan,'mga            ',green,'- MGA for accounting point',reset)
        print(cyan,'startdate      ',green,'- start date for usage',reset)
        print(cyan,'days           ',green,'- number of days for usage',reset)
        print(cyan,'hours          ',green,'- number of hours for usage, default 24',reset)
        print(cyan,'starttime      ',green,'- start time for usage, default 00:00',reset)
        print(cyan,'metering_state ',green,'- status for usage data quality, default OK',reset)
        print(cyan,'metric         ',green,'- metric for usage, default kWH',reset)
        print(magenta,'Note: Values cannot be set if accounting point is not defined.',reset)
        
    def do_exit(self, inp):
        'Exits this program'
        print(green,'All done!',reset)
        return True

    def help_exit(self, inp = None):
        print(cyan,'Exits program',reset)

    def do_EOF(self, inp):
        'For ctrl-d exit'
        print(green,'\nAll done!',reset)
        return True

    def help_EOF(self, args=None):
        print(green,'Exits program with CTRL-D',reset)

def main(argv):
    date = None
    days = 1

    if len(sys.argv)>1:
        try:
            opts, args = getopt(argv,"chs:d:",["date=","days="])
        except getopt.GetoptError as e:
            print(red, f'Error parsing arguments: {e}', reset)
            print (cyan,'kulugen.py -s <start date> -d <number of days>',reset)
            exit()
        
        for opt, arg in opts:
            try:
                if opt == '-h' or len(opt) <2 or len(opt) >2:
                    print(cyan,'Usage:',reset)
                    print(cyan,'kulugen.py -s <start date> -d <number of days>',reset)
                    print(cyan,'kulugen.py -c for interactive mode (shell)',reset)
                    exit()
                elif opt == "-c":
                    Prompt().cmdloop()
                    exit()
                elif opt in ("-s"):
                    day,month,year = arg.split('.')
                    datetime.datetime(int(year),int(month),int(day)) # date validation
                    date = arg
                elif opt in ("-d"):
                    try:
                        if int(arg) >= 1:
                            days = arg
                            luo_kulutus(date, days, database, None)
                        else:
                            print(magenta,'Error: Number of days should be at least 1',reset)
                    except ValueError:
                        print(magenta,'Error: Invalid number of days',reset)
            except ValueError:
                print(magenta,'Date format incorrect.',reset)
                exit()
            except UnboundLocalError:
                pass
    else:
        luo_kulutus(None, None, database, None)

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print(green,'\n\nProgram cancelled by user.',reset)
        exit()
    except EOFError:
        print(green,'\n\nProgram cancelled by user.',reset)
        exit()
