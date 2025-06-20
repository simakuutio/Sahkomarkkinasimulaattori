#!/usr/bin/python3

import os
import sys
# Removed re, shutil, datetime, timeit as they are now in req_utils
# Removed requests import as it's in req_utils

try:
    from libs.fconfig import thread # url, DSO, DDQ are used by req_utils
except ImportError:
    print('Error: fconfig.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

# Import shared utilities from req_utils
try:
    from libs.req_utils import send_generic, Printer, DEBUG as RU_DEBUG, dprint as ru_dprint, xml_path
except ImportError:
    print('Error: req_utils.py missing from libs directory. soapreq.py cannot function.')
    exit()

# DEBUG is now controlled by req_utils.DEBUG if needed for dprint/Printer from there
# For local dprint, it would need its own DEBUG or use RU_DEBUG
DEBUG = RU_DEBUG # Use the DEBUG from req_utils for consistency

def dprint(*s): # Local dprint for this file's specific debug messages
    if DEBUG: # This DEBUG refers to the one set from RU_DEBUG
        # Prefix to distinguish from req_utils dprint
        print(("[soapreq_local] ",) + s if isinstance(s, tuple) else ("[soapreq_local] ", s))


# xml_dir still uses xml_path, which is now imported from req_utils
def xml_dir(xml_type=None):
    # Using ru_dprint for consistency if we want req_utils to handle all dprints
    # For now, let's assume xml_dir specific debugging can use local dprint
    dprint(f'xml_dir({xml_type})')
    xml_files = []
    # Use os.walk directly on the imported xml_path
    for _,_ , files in os.walk(xml_path):
        if xml_type == 'apoint':
            for file in files:
                if file.startswith('apoint_'):
                    xml_files.append(file)
        elif xml_type == 'sopimus':
            for file in files:
                if file.startswith('sopimus_'):
                    xml_files.append(file)
    return sorted(xml_files)

# Printer is imported from req_utils
# send_generic is imported from req_utils
# find_error, read_file_to_list, parse_for_uri, uri_gen, gen_url are in req_utils and used by its send_generic

def replace_error(error_string, errors=[], err_num=1): # This seems unused, keeping for now.
    dprint('replace_error()') # Uses local dprint
    if not errors:
        print(error_string)
        return
    error = errors.pop(0)
    tmp_string = "'<%s>'" % err_num
    error_string = error_string.replace(tmp_string, error)
    return replace_error(error_string, errors, err_num + 1)


def send_loop():
    dprint('send_loop()') # Uses local dprint
    try:
        # log directory creation is handled by req_utils.send_generic
        if len(xml_dir("apoint")) and len(xml_dir("sopimus")):
            for apoint, sopimus in zip(xml_dir("apoint"), xml_dir("sopimus")):
                if send_generic(apoint, 'DSO') != 1: # succesfully sent apoint
                    send_generic(sopimus, 'DDQ') # Using imported send_generic
                else:
                    print('\nProblem with {}, skipping {}'.format(apoint, sopimus))
        elif len(xml_dir("apoint")):
            for apoint in xml_dir("apoint"):
                if send_generic(apoint, 'DSO') == 1: # Using imported send_generic
                    print('\nProblem with {}'.format(apoint))
        elif len(xml_dir("sopimus")):
            for sopimus in xml_dir("sopimus"):
                if send_generic(sopimus, 'DDQ') == 1: # Using imported send_generic
                    print('\nProblem with {}'.format(sopimus))
        Printer('\n*** All done! ***\n') # Using imported Printer
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user.")
        exit()
        
def fake(n): # This function seems to be for testing only, can be kept or removed.
    # for dry testing
    import time # time was not imported at the top, add if needed
    import random as ra # random was not imported, add if needed
    time.sleep(ra.randint(2,9))
    print(n)

# send_generic is now imported from req_utils.py

def thread_loop(block_size):
    dprint('thread_loop({})'.format(block_size)) # Uses local dprint
    from threading import Thread, Lock # threading was not imported at top
    import time # time was not imported at top
    counter = 0
    success = 0
    lock = Lock()

    paikat = []
    for apoint in sorted(xml_dir("apoint")):
        paikat.append(apoint)

    dprint(f'Paikkoja: {len(paikat)}') # Uses local dprint
    if len(paikat) != 0:
        with lock:
            uusi = iter(paikat)
            for i in range(1,len(paikat)+1):
                n = next(uusi)
                t1 = Thread(target=send_generic, args=(n,'DSO')) # Using imported send_generic
                # t1 = Thread(target=fake, args=(n,)) # for dry testing
                t1.start()
                counter += 1
                print(f'Thread {counter} started, sending {n}')
                if counter == block_size:
                    counter = 0
        print('\n')
        success = 1
    else:
        exit()
   
    sopimukset = []
    for sopimus in sorted(xml_dir("sopimus")):
        sopimukset.append(sopimus)

    if len(sopimukset) != 0 and success:
        print('Waiting few moments before next phase...')
        time.sleep(30)
        with lock:
            try:
                uusi = iter(sopimukset)
                counter = 0
                for i in range(1, len(sopimukset)+1):
                    n = next(uusi)
                    t2 = Thread(target=send_generic, args=(n,'DDQ')) # Using imported send_generic
                    #t2 = Thread(target=fake, args=(n,)) # for dry testing
                    t2.start()
                    counter += 1
                    print(f'Thread {counter} started, sending {n}')
                    if counter == block_size:
                        counter = 0
            except StopIteration:
                print('\n')
        
if __name__ == "__main__":
    try:
        if thread:
            thread_loop(10)
        else:
            send_loop()
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user.")
        exit()
    except KeyError as error:
        print("\n\nParameter",error.args[0],"not in fconfig.")
        exit()
