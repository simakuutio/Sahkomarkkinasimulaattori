#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Final version

import random as ra
import csv
import sys
try:
    from libs.kirjasto import gen_id, gen_timestamp, add_check_digit
except ImportError:
    print('Error: kirjasto.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

try:
    from libs.fconfig import jakeluverkkoyhtio, MGA, dealers, id_range, limit
except ImportError:
    print('Error: fconfig.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

storage = {}

def random_supplier(): # DDQ
    """
    Input: None
    Output: String
    """
    return ra.choice(dealers)

def random_address():
    """
    Input: None
    Output: String
    """
    return ra.choice(list(open('libs/osoitteet.txt','r',encoding ='latin-1')))

def selector():
    """
    Input: None
    Output: String
    """
    if jakeluverkkoyhtio:
        for count, DSO_id in enumerate(jakeluverkkoyhtio, 1):
            if DSO_id == '':
                print('Error: please add at least one DSO to fconfig.py!')
                exit()
            else:
                print (str(count),'-', DSO_id)
        ans = 0
        while not ans:
            try:
                ans = int(input("Select DSO (1-{}): ".format(count)))
                if ans <= 0 or ans > len(jakeluverkkoyhtio):
                    raise ValueError
            except ValueError:
                ans = 0
                print("Select between 1 - {}".format(count))
            except SyntaxError or NameError:
                ans = 0
                print("Only numbers accepted.")
        storage['DSO'] = jakeluverkkoyhtio[ans-1]
        return (jakeluverkkoyhtio[ans-1])
    else:
        try:
            storage['DSO'] = jakeluverkkoyhtio[0]
            return (jakeluverkkoyhtio[0])
        except:
            print('Error: please add at least one DSO to fconfig.py!')
            exit()

def input_mga():
    if MGA:
        for count, MGA_id in enumerate(MGA, 1):
            if MGA_id == '':
                print('Error: please add at least one MGA to fconfig.py!')
                exit()
            else:
                print(str(count),'-',MGA_id)
        ans = 0
        while not ans:
            try:
                ans = int(input("Select MGA (1-{}): ".format(count)))
                if ans <= 0 or ans > len(MGA):
                    raise ValueError
            except ValueError:
                ans = 0
                print("Select between 1 - {}".format(count))
            except SyntaxError:
                ans = 0
                print("Only numbers accepted.")
            except NameError:
                ans = 0
                print("Only numbers accepted.")
        storage['MGA'] = MGA[ans-1]
    else:
        try:
            storage['MGA'] = MGA[0]
        except:
            print('Error: please add at least one MGA to fconfig.py!')
            exit()

def ap_type():
    types = [('Non-production','AG01'), ('Production','AG02')]
    for count, aptype in enumerate(types, 1):
        print(str(count),'-',aptype[0])

    ans = 0
    while not ans:
        try:
            ans = int(input("Select accounting point type (1-{}): ".format(count)))
        except ValueError:
            ans = 0
            print("Select between 1 - {}".format(count))
        except SyntaxError:
            ans = 0
            print("Only numbers accepted.")
        except NameError:
            ans = 0
            print("Only numbers accepted.")
    storage['type'] = types[ans-1][1]

def remote_readable():
    readable = [('Readable','1'),('Non-readable','0')]
    for count, modes in enumerate(readable, 1):
        print(str(count),'-',modes[0])

    ans = 0
    while not ans:
        try:
            ans = int(input("Select accounting point mode (1-{}): ".format(count)))
        except ValueError:
            ans = 0
            print("Select between 1 - {}".format(count))
        except SyntaxError:
            ans = 0
            print("Only numbers accepted.")
        except NameError:
            ans = 0
            print("Only numbers accepted.")
    storage['remote'] = readable[ans-1][1]

def metering_method():
    methods = [('Continunous metering','E13'),('Reading metering','E14'),('Unmetered','E16')]
    for count, method in enumerate(methods, 1):
        print(str(count),'-',method[0])

    ans = 0
    while not ans:
        try:
            ans = int(input("Select accounting point metering method (1-{}): ".format(count)))
        except ValueError:
            ans = 0
            print("Select between 1 - {}".format(count))
        except SyntaxError:
            ans = 0
            print("Only numbers accepted.")
        except NameError:
            ans = 0
            print("Only numbers accepted.")
    storage['method'] = methods[ans-1][1]

def csv_filler():   
    """
    Input: None
    Output: string
    """

    return random_supplier()

def get_input():
    """
    Input: None
    Output: integer
    """
    ans = 0
    while not ans:
        try:
            ans = int(input("Amount of accounting points: "))
            if ans <= 0 or ans > limit:
                raise ValueError
        except ValueError:
            ans = 0
            print("Value should be between 1 - {}".format(limit))
        except SyntaxError:
            ans = 0
            print("Only numbers accepted.")
        except NameError:
            ans = 0
            print("Only numbers accepted.")
    return ans

def apoint_gen(jvy=None, kp_lkm=None, mga=None, aptype=None, remote =None, method=None):
    """
    Input: string (default: function call)
    Output: list of strings
    """
    if not jvy: # cmd-line parameter test
        prefix=selector()[:8]
    else:
        prefix=jvy[:8]
    if not kp_lkm: # cmd-line parameter test
        amount=get_input()
    else:
        amount=int(kp_lkm)
    if not mga: # cmd-line parameter test
        input_mga()
    if not aptype: # cmd-line parameter test
        ap_type()
    if not remote: # cmd-line parameter test
        remote_readable()
    if not method: # cmd-line parameter test
        metering_method()

    if id_range: # config-file test
        if id_range <= 90000000:
            vakio = id_range
        else:
            raise ValueError("Configuration error: id_range in fconfig.py exceeds the maximum value of 90000000.")
    else:
        vakio = ra.randint(1,90000000)
    klista = []
    for i in range(vakio, amount + vakio):
        # produces fixed length formatted string including checksum
        output = str(prefix)+str(i).zfill(9)
        klista.append(add_check_digit(int(output)))
    return klista

def produce_xml(prefix, apoint):
    """
    Input: integer, integer
    Output: file
    """
    try:
        from xml.etree import ElementTree as et
        import os
        ns2 = './/{urn:fi:Datahub:mif:masterdata:E58_MasterDataMPEvent:elements:v1}'
        ns3 = './/{urn:fi:Datahub:mif:common:HDR_Header:elements:v1}'
        ns5 = './/{urn:fi:Datahub:mif:masterdata:E58_MasterDataMPEvent:elements:v1}'
        datafile = 'libs/xml_template.xml'

        if 'address' not in storage:
            osoite = random_address().split(',')
            storage['address'] = osoite
        if not os.path.exists('xml'):
            os.makedirs('xml')
        tree = et.parse(datafile)
        tree.find(ns3+'Identification').text = gen_id(True)
        tree.find(ns3+'PhysicalSenderEnergyParty')[0].text = storage['DSO']
        tree.find(ns3+'JuridicalSenderEnergyParty')[0].text = storage['DSO']
        tree.find(ns3+'Creation').text = gen_timestamp() # Now
        tree.find(ns5+'StartOfOccurrence').text = gen_timestamp('True') # Last midnight
        tree.find(ns5+'MeteringPointUsedDomainLocation')[0].text = apoint
        tree.find(ns5+'MeteringGridAreaUsedDomainLocation')[0].text = storage['MGA']
        tree.find(ns5+'MeteringPointAddress')[1].text = storage['address'][1] # streetname
        tree.find(ns5+'MeteringPointAddress')[2].text = str(ra.randint(1,100))
        tree.find(ns5+'MeteringPointAddress')[5].text = storage['address'][0] # zip code
        tree.find(ns5+'MeteringPointAddress')[6].text = storage['address'][2].strip() # City
        tree.find(ns5+'MPDetailMeteringPointCharacteristic')[0].text = storage['remote']
        tree.find(ns5+'MPDetailMeteringPointCharacteristic')[1].text = storage['method']
        tree.find(ns5+'MeteringPointUsedDomainLocation')[2].text = storage['type']
 
        datafile = 'xml/apoint_{}.xml'.format(apoint)
        tree.write(datafile)
    except FileNotFoundError:
        print("osoitteet.txt missing from libs directory.")
        exit()

def output_apoint(jvy, kp_lkm, mga, aptype, remote, method):
    """
    Input: list of integers
    Output: file
    """
    import os.path

    if not jvy and kp_lkm: # cmd-line parameter test for jvy
        print('Accounting point missing.')
        exit()
    elif not kp_lkm and jvy: # cmd-line parameter test for kp_lkm
        print('Amount missing.')
        exit()
    elif not mga and jvy:
        print('MGA missing.')
        exit()
    elif not aptype and jvy:
        print('Accountin point type missing.')
        exit()
    elif not remote and jvy:
        print('Remote readable status missing.')
        exit()
    elif not method and jvy:
        print('Read method missing.')
        exit()

    try:
        if not dealers:
            print("Error: No dealers configured in fconfig.py. Please check the 'dealers' list.")
            exit()
        kplista = apoint_gen(jvy, kp_lkm, mga, aptype, remote, method)
        if os.path.exists('kp.csv'):
            kp_done = True
        else:
            kp_done = False
        with open('kp.csv','a') as f:
            if kp_done:
                pass
            else:
                f.write('Accounting point,Metering Area,Supplier,DSO,MGA,ZIP,Street,City,AP type,Remote readable,Metering method\n')
            prefix = kplista[0][:8]
            ma = str(prefix) + '00000000' # Metering area
            for apoint in kplista:
                produce_xml(prefix, apoint)
                supplier = csv_filler()
                f.write("{},{},{},{},{},{},{},{},{},{},{}\n".format(apoint,ma,supplier,
                                                                    storage['DSO'],
                                                                    storage['MGA'],
                                                                    storage['address'][0],
                                                                    storage['address'][1],
                                                                    storage['address'][2].strip(),
                                                                    storage['type'],
                                                                    storage['remote'],
                                                                    storage['method'] ))
    # The TypeError was primarily for ra.choice(dealers) if dealers is empty.
    # The explicit check for dealers above should cover this.
    # If other TypeErrors are possible, they should be caught more specifically.
    # For now, removing the broad TypeError catch.
    # except TypeError:
    #     print('Error: please add at least one dealer to config file!')
    #     exit()

def main(argv):
    import getopt
    jvy = 0
    kp_lkm = 0
    mga = 0
    aptype = 0
    remote = 0
    method = 0
    if len(sys.argv) >1:
        try:
            opts, args = getopt.getopt(argv,"hl:j:m:t:r:M:",["kp_lkm=","jvy=","mga=", "aptype=", "remote=", "method="])
        except getopt.GetoptError:
            print('Usage:')
            print ('kpgen.py -j <DSO> -m <MGA> -l <number of accounting points> -t type (AG01/AG02) -r remote readable (0/1) -M metering method (E13/E14/E16)')
            exit()
        for opt, arg in opts:
            if opt in ('-l'):
                kp_lkm = arg
            elif opt in ('-j'):
                jvy = arg
                storage['DSO'] = jvy
            elif opt in ('-m'):
                mga = arg
                storage['MGA'] = mga
            elif opt in ('-t'):
                aptype = arg
                storage['type'] = aptype
            elif opt in ('-r'):
                remote = arg
                storage['remote'] = remote
            elif opt in ('-M'):
                method = arg
                storage['method'] = method

            elif opt in ('-h'):
                print('Usage:')
                print('kpgen.py -j <DSO> -m <MGA> -l <number of accounting points> -t type (AG01/AG02) -r remote readable (0/1) -M metering method (E13/E14/E16)')
                exit()
        try:
            output_apoint(jvy, kp_lkm, mga, aptype, remote, method)
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)
    else:
        try:
            output_apoint(None, None, None, None, None, None)
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user!")
        exit()

    except EOFError:
        print("\n\nProgram cancelled by user!")
        exit()
