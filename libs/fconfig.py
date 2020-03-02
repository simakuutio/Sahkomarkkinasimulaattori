###########################################
# Fingrid Sähkömarkkina simulaattori (MaSi)
###########################################

#------------------- Käyttöpaikka generator tool settings ----------------------------

##################################################################
# DSO                                                            #
#                                                                #
# Jakeluverkkoyhtiö ID                                           #
#                                                                #
# Example: jakeluverkkoyhtio = ["6427020100000","6427020200007"] #
# Default value: None                                            #
##################################################################

# jakeluverkkoyhtio = None
jakeluverkkoyhtio = ["6427020100000","6427020200000"]
MGA = ["6427020100000000","6427020100000100","6427020100000200"]

##################################################################
# DDQ                                                            #
#                                                                #
# Dealer ID, generator selects randomly from list                #
# Example: dealers = ['6427010100003','6427010200000']           #
# Default value: None                                            #
##################################################################

#dealers = None
dealers = ['6427010100003','6427010200000', "6427010300007"]

# Limit for kpaikka, shouldn't be changed without good reason.
limit = 10000

##################################################################
#                                                                #
# Range defines where ID range (prefix + range) begins.          #
# If not defined, range is random.                               #
# Example: id_range = 20                                         #
# Default value: None                                            #
#                                                                #
##################################################################
id_range = None

#--------------------- Soap request tool settings ----------------------------

# Datahub API destination URL
# url = None
#url = 'https://dh-fingrid-ven01-b2b.azurewebsites.net/soap/FGR?organisationuser='
#url = 'https://dh-fingrid-conv01-b2b.azurewebsites.net/soap/FGR?organisationuser='
url = 'https://dh-fingrid-sat01-b2b.azurewebsites.net/soap/FGR?organisationuser='

# Url for seek & dequeue
putsiurl = 'https://dh-fingrid-sat01-b2b.azurewebsites.net/soap/FGR?organisationuser=B2BFGdso27AAdmin'

# DSO = {}
# DSO = {}

DSO = {'6427020100000': 'B2BFGdso27AAdmin',
       '6427020200000': 'B2BFGdso27BAdmin'}
DDQ = {'6427010100003': 'B2BFGddq27AAdmin',
       '6427010200000': 'B2BFGddq27BAdmin',
       '6427010300007': 'B2BFGddq27CAdmin'}

# Option to set static value for production (accounting point and exchange point)
# None = random
# other than None sets static value

prod_ap = None
prod_ep = None

# Use with caution. Not recommended for normal testing
# disabled by default
thread = False
