import random as ra

def gen_id(backdoor=False):
    """
    Input: True/False, default: False
    Output: string [32]
    """
    symbols = "abcdef1234567890"
    id = ""
    for i in range (0, 24):
        id += ra.choice(symbols)

    id = 'MaSi' + id
    if not backdoor:
        return id
    else:
        return '[TT]'+id

def add_check_digit(upc_str):
    """
    Input: string
    Output: string
    """
    upc_str = str(upc_str)

    odd_sum = 0
    even_sum = 0
    for i, char in enumerate(upc_str):
        j = i+1
        if j % 2 == 0:
            even_sum += int(char)
        else:
            odd_sum += int(char)

    total_sum = (odd_sum * 3) + even_sum
    mod = total_sum % 10
    check_digit = 10 - mod
    if check_digit == 10:
        check_digit = 0
    return upc_str + str(check_digit)

def gen_timestamp(midnight=False):
    """
    Input: True/False, default: False
    Output: Formatted date string
    """
    from datetime import datetime, date, time, timedelta
    import pytz
    tz = pytz.timezone("Europe/Helsinki")
    now = datetime.now()

    date_past2week = now - timedelta(weeks=2)

    utc_midnight = tz.localize(datetime.combine(date.today()-timedelta(weeks=2), time())).astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not midnight:
         return date_past2week.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        return utc_midnight
