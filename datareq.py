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
    print('Error: req_utils.py missing from libs directory. datareq.py cannot function.')
    exit()

DEBUG = RU_DEBUG # Use the DEBUG from req_utils for consistency

def dprint(*s): # Local dprint for this file's specific debug messages
    if DEBUG:
        print(("[datareq_local] ",) + s if isinstance(s, tuple) else ("[datareq_local] ", s))

# xml_dir still uses xml_path, which is now imported from req_utils
def xml_dir(xml_type=None):
    dprint(f'xml_dir({xml_type})')
    xml_files = []
    for _,_ , files in os.walk(xml_path): # Using imported xml_path
        if xml_type == 'kulutus':
            for file in files:
                if file.startswith('kulutus_'):
                    xml_files.append(file)
        elif xml_type == 'rajapiste':
            for file in files:
                if file.startswith('rajapiste_'):
                    xml_files.append(file)
    return sorted(xml_files)

# Printer is imported from req_utils
# send_generic is imported from req_utils
# find_error, read_file_to_list, parse_for_uri, uri_gen, gen_url are in req_utils

def replace_error(error_string, errors=[], err_num=1): # This seems unused
    dprint('replace_error()')
    if not errors:
        print(error_string)
        return
    error = errors.pop(0)
    tmp_string = "'<%s>'" % err_num
    error_string = error_string.replace(tmp_string, error)
    return replace_error(error_string, errors, err_num + 1)

def send_loop():
    dprint('send_loop()')
    try:
        # log directory creation is handled by req_utils.send_generic
        if len(xml_dir("kulutus")):
            for kulutus in xml_dir("kulutus"):
                if send_generic(kulutus, 'DSO') == 1: # Using imported send_generic
                    print('\nProblem with {}'.format(kulutus))
        if len(xml_dir("rajapiste")):
            for rajapiste in xml_dir("rajapiste"):
                if send_generic(rajapiste, 'DSO') == 1: # Using imported send_generic
                    print('\nProblem with {}'.format(rajapiste))
        Printer('\n*** All done! ***\n') # Using imported Printer
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user.")
        exit()
        
def fake(n): # Test function, can be kept or removed.
    # for dry testing
    import time # time was not imported at top
    import random as ra # random was not imported at top
    time.sleep(ra.randint(2,9))
    print(n)

# send_generic is now imported from req_utils.py
# Note: The response checking for datareq.py ("DocumentReferenceNumber")
# will now use the logic from soapreq.py ("BA01" and find_error)
# as send_generic from req_utils.py is based on soapreq.py's version.

def thread_loop(block_size):
    dprint('thread_loop({})'.format(block_size)) # Uses local dprint
    from threading import Thread, Lock # threading was not imported at top
    import time # time was not imported at top
    counter = 0
    success = 0
    lock = Lock()

    paikat = []
    for kulutus in sorted(xml_dir("kulutus")):
        paikat.append(kulutus)

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

def main():
    if thread:
        thread_loop(10)
    else:
        send_loop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user!")
        exit()
    except EOFError:
        print("\n\nProgram cancelled by user!")
        exit()
