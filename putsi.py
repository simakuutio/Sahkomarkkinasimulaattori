#!/usr/bin/python3

from xml.etree import ElementTree as et
import requests
import re
import os

try:
    from libs.fconfig import putsiurl
except ImportError:
    print('Error: fconfig.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

headers = {'content-type': 'text/xml'}

storage = {}
counter = 0
OK = 0
FAIL = 0
OTHER = 0

def peek(xml):
    global OK, FAIL, OTHER
    response = requests.post(putsiurl,data=xml,headers=headers, cert=("certs/cert.pem", "certs/key_nopass.pem"))
    Resp = response.content.decode("utf-8")

    regex = re.compile('(?<=urn2:Identification\\>)(.*?)(?=\\</urn2)')
    docref = regex.findall(Resp)

    status = re.search('(?:BA01|BA02)', Resp)

    regex = re.compile('(?<=urn3:EnergyBusinessProcess\\>)(.*?)(?=\\</urn3)')
    process = regex.findall(Resp)
    
    try:
        storage['docref'] = docref[0]
        storage['process'] = process[0]
    except IndexError:
        print('Queue empty')
        return False

    try:
        storage['status'] = status.group(0)
        if storage['status'] == 'BA01':
            OK += 1
        else:
            FAIL += 1
    except AttributeError:
        storage['status'] = "None"
        OTHER += 1
        pass
    with open('peeks/'+storage['status']+'_'+storage['process']+'_'+storage['docref']+'.xml','w') as peeks:
        peeks.write("{}".format(str(Resp)))
    return True

def dequeue():
    ns = './/{urn:cms:b2b:v01}'
    target = 'clean.xml'
    tree = et.parse('libs/dequeue_one.xml')
    tree.find(ns+'DocumentReferenceNumber').text = storage['docref']
    tree.write(target)
    with open(target, 'r') as f:
        dequeuexml = f.read()
        response = requests.post(putsiurl,data=dequeuexml,headers=headers, cert=("certs/cert.pem", "certs/key_nopass.pem"))
        Response1 = response.content.decode("utf-8")
    print (storage['docref'],'peeked and dequeued.')

if not os.path.exists('peeks'):
    os.makedirs('peeks')

with open('libs/peek.xml', 'r') as f:
    peekxml = f.read()
    while peek(peekxml):
        dequeue()
        counter += 1
        f.seek(0)
    
    print(counter,'peeks processed.')
    print('BA01:', OK)
    print('BA02:', FAIL)
    print('Other:', OTHER)
