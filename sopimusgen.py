#!/usr/bin/python3
# -*- coding: utf-8 -*-

try:
    from libs.kirjasto import gen_id, gen_timestamp, add_check_digit
except ImportError:
    print('Error: kirjasto.py missing, please consult Fingrid Datahub test team to get new one!')
    exit()

storage = {}

def main():
    selector()

def produce_xml():
    """
    Input: integer, integer
    Output: file
    """
    from xml.etree import ElementTree as et
    import random as ra
    import os
    ns2 = './/{urn:fi:Datahub:mif:common:HDR_Header:elements:v1}'
    ns3 = './/{urn:fi:Datahub:mif:common:PEC_ProcessEnergyContext:elements:v1}'
    ns11 = './/{urn:fi:Datahub:mif:masterdata:F04_MasterDataContractEvent:v1}'
    ns12 = './/{urn:fi:Datahub:mif:masterdata:F04_MasterDataContractEvent:elements:v1}'
    datafile = 'libs/sopimus_template.xml'
    if not os.path.exists('xml'):
        os.makedirs('xml')
    tree = et.parse(datafile)
    tree.find(ns2+'Identification').text = gen_id(True)
    tree.find(ns2+'PhysicalSenderEnergyParty')[0].text = storage['ddq']
    tree.find(ns2+'JuridicalSenderEnergyParty')[0].text = storage['ddq']
    tree.find(ns2+'Creation').text = gen_timestamp() # Now
    tree.find(ns12+'StartOfOccurrence').text = gen_timestamp('True') # Last midnight
    tree.find(ns12+'MeteringPointOfContract')[0].text = storage['ap']
    tree.find(ns12+'MeteringGridAreaUsedDomainLocation')[0].text = storage['mga']
    tree.find(ns12+'SupplierOfContract')[0].text = storage['ddq']
    tree.find(ns12+'MasterDataContract')[1].text = str(ra.randint(1,9999999999))
    #    tree.find(ns12+'MasterDataContract')[1].text = str(int(str(hex(zlib.crc32(myyja.encode('utf8')) & 0xffffffff)[2:]),16))
    tree.find(ns12+'ConsumerInvolvedCustomerParty')[0].text = hetu()
    tree.find(ns12+'Name').text = henkilo()
    
    datafile = 'xml/sopimus_{}.xml'.format(storage['ap'])
    tree.write(datafile)

def hetu(start=1900, end=1999):
    """
    Input: integer, integer
    Output: string
    """
    from random import randint
    from calendar import monthrange

    CHECK_KEYS = "0123456789ABCDEFHJKLMNPRSTUVWXY"
    CENTURIES = {'18':'+','19':'-','20':'A'}

    year = randint(start, end)
    month = randint(1, 12)
    day = randint(1, monthrange(year, month)[1])
    century_sep = CENTURIES[str(year)[0:2]]

    order_num = randint(900, 999) # testirange
    check_number = "%02d%02d%s%03d" % (day, month, str(year)[0:2], order_num)

    check_number_index = int(check_number)%31
    key = CHECK_KEYS[check_number_index]

    return "%02d%02d%s%s%03d%s" % (day, month, str(year)[2:4], century_sep, order_num, key)

def henkilo():
    """
    Input: string
    Output: string
    """
    from random import choice, randint
    if randint(0,1):
        etunimi = choice(list(open('libs/mies.txt'))).strip()
    else: 
        etunimi = choice(list(open('libs/nainen.txt'))).strip()
    sukunimi = choice(list(open('libs/sukunimet.txt'))).strip()
    return("{} {}".format(etunimi, sukunimi))

def puhelin():
    """
    Input: None
    Output: string
    """
    from random import randint, sample
    prefix=['040','050','01','02','03','04','05','06','07','08','09']
    suunta = sample(prefix,1)
    numero = str(suunta[0]) + str(randint(1000000,9999999))
    return(numero)

def selector():
    """
    Input: None
    Output: xml
    """
    kp_file = 'kp.csv'

    try:
        with open(kp_file,'r') as f:
            next(f)
            for line in f:
                storage['ap'] = line.split(',')[0]
                storage['ddq'] = line.split(',')[2]
                storage['dso'] = line.split(',')[3]
                storage['mga'] = line.split(',')[4]
                produce_xml()

    except FileNotFoundError:
        print('Error: kp.csv missing, please run kpgen to create new one.')

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram cancelled by user!")
        exit()
    except EOFError:
        print("\n\nProgram cancelled by user!")
        exit()
