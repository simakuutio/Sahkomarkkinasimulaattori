#!/usr/bin/python3

import os
import re
import sys

try:
    from libs.fconfig import thread, url, DSO, DDQ
except ImportError:
    print('Error: fconfig.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

xml_path = 'xml/'
headers = {'content-type': 'text/xml'}

DEBUG = False

def dprint(*s):
    if DEBUG:
        print (s)

def uri_gen(gen_id, mode):
    dprint('uri_gen({}, {})'.format(gen_id, mode))
    if mode == 'DSO':
        # käyttöpaikka
        return DSO[gen_id]

def parse_for_uri(xml):
    dprint('parse_for_uri(xml)')
    gen_id = re.search(r'(?<=schemeAgencyIdentifier\=\"9\"\>)(.*)(?=\<\/ns3:Identification)', xml)
    return gen_id.group(1)

def gen_url(group, xml):
    dprint('gen_url({}, xml)'.format(group))
    org_id = parse_for_uri(xml)
    org_group = uri_gen(org_id, group)
    return url + org_group
    
def replace_error(error_string, errors=[], err_num=1):
    dprint('replace_error()')
    if not errors:
        print(error_string)
        return
    error = errors.pop(0)
    tmp_string = "'<%s>'" % err_num
    error_string = error_string.replace(tmp_string, error)
    return replace_error(error_string, errors, err_num + 1)

def read_file_to_list(input_file):
    dprint('read_file_to_list({})'.format(input_file))
    lista = []
    with open(input_file, 'r') as f:
        for line in f:
            lista.append(line.strip())
    return lista

def find_error(error_code):
    dprint('find_error({})'.format(error_code))
    virhe = read_file_to_list('libs/Error_code.txt').index(error_code)
    koodi = read_file_to_list('libs/Error_string.txt')
    return (koodi[virhe])

def xml_dir(xml_type=None):
    dprint('xml_dir({})'.format(xml_type))
    xml_files = []
    for _,_ , files in os.walk(xml_path):
        if xml_type == 'kulutus':
            for file in files:
                if file.startswith('kulutus_'):
                    xml_files.append(file)
        elif xml_type == 'rajapiste':
            for file in files:
                if file.startswith('rajapiste_'):
                    xml_files.append(file)
    return sorted(xml_files)

def Printer(data):
    """Print things to stdout on one line"""
    if DEBUG:
        sys.stdout.write("\r\x1b[K"+data.__str__())
        sys.stdout.flush()
       
def send_loop():
    dprint('send_loop()')
    try:
        if not os.path.exists('log'):
            os.makedirs('log')
        if len(xml_dir("kulutus")):
            for kulutus in xml_dir("kulutus"):
                if send_generic(kulutus, 'DSO') == 1:
                    print('\nProblem with {}'.format(kulutus))
        if len(xml_dir("rajapiste")):
            for rajapiste in xml_dir("rajapiste"):
                if send_generic(rajapiste, 'DSO') == 1:
                    print('\nProblem with {}'.format(rajapiste))
        Printer('\n*** All done! ***\n')
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user.")
        exit()
        
def fake(n):
    # for dry testing
    import time
    import random as ra
    time.sleep(ra.randint(2,9))
    print(n)

def send_generic(source, source_type):
    dprint('send_generic({},{})'.format(source, source_type))
    from requests import post
    from timeit import default_timer as timer
    from datetime import timedelta
    from time import sleep
    from shutil import move

    if source:
        if not os.path.exists('log'):
            os.makedirs('log')
        with open(xml_path + source, 'r') as source_xml:
            if DEBUG: start = timer()
            Printer('--> Sending {}'.format(source))
            input_xml = source_xml.read()
            req_url = gen_url(source_type, input_xml)
            k_response = post(req_url, data=input_xml, headers=headers, cert=("certs/cert.pem", "certs/key_nopass.pem"))
            if DEBUG: end = timer()
            if DEBUG: aika = str(timedelta(seconds = end - start))
            if DEBUG: print(' Process time for {} : {}'.format(source, aika.split('.')[0][2:]))
            with open('log/'+'resp_' + source,'w') as db:
                Response = k_response.content.decode("utf-8")
                db.write("{}".format(str(Response)))
                if "DocumentReferenceNumber" not in str(Response):
                    print('Error: Problem with response error parsing, please check log file for request')
                    return 1
                elif "Unavailable" in str(Response):
                    print('\nDatahub backend not available, please try later again!')
                    print('Possible reason: blocked by firewall')
                    exit()
                else:
                    Printer("*** {} sent succesfully.".format(source))
                    source_xml.close() # windows hack
                    move('xml/' + source, 'xml/'+'DONE_' + source)
                    return 0
                
def thread_loop(block_size):
    dprint('thread_loop({})'.format(block_size))
    from threading import Thread, Lock
    import time
    counter = 0
    success = 0
    lock = Lock()

    paikat = []
    for kulutus in sorted(xml_dir("kulutus")):
        paikat.append(kulutus)

    dprint('Paikkoja: {}'.format(len(paikat)))
    if len(paikat) != 0:
        with lock:
            uusi = iter(paikat)
            for i in range(1,len(paikat)+1):
                n = next(uusi)
                t1 = Thread(target=send_generic, args=(n,'DSO'))
                # t1 = Thread(target=fake, args=(n,)) # for dry testing
                t1.start()
                counter += 1
                print('Thread {} started, sending {}'.format(counter, n))
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
