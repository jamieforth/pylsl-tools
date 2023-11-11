def parse_match_props(match_props):
    match_props = {prop: value for prop, value in
                   [match_prop.split('=') for match_prop in match_props]}
    return match_props

dev_map = {
    'eeg-a': 'DESKTOP-3R7C1PH',
    'eeg-b': 'DESKTOP-2TI6RBU',
    'eeg-c': 'DESKTOP-MN7K6RM',
    'eeg-d': 'DESKTOP-URRV98M',
    'eeg-e': 'DESKTOP-DATOEVU',
    'eeg-f': 'TABLET-9I44R1AR',
    'eeg-g': 'DESKTOP-SLAKFQE',
    'eeg-h': 'DESKTOP-6FJTJJN',
    'eeg-i': 'DESKTOP-HDOESKS',
    'eeg-j': 'DESKTOP-LIA3G09',
    'eeg-k': 'DESKTOP-V6779I4',
    'eeg-l': 'DESKTOP-PLV2A7L',
    'eeg-m': 'DESKTOP-SSSOE1L',
    'eeg-n': 'DESKTOP-RM16J67',
    'eeg-o': 'DESKTOP-N2RA68S',
    'eeg-p': 'DESKTOP-S597Q21',
    'eeg-q': 'DESKTOP-OE9298C',
    'eeg-r': 'DESKTOP-MK0GQFM',
    'eeg-s': 'DESKTOP-7GV3RJU',
    'eeg-t': 'DESKTOP-S5A1PPK',
    'eeg-u': 'TABLET-3BS4NTP2',
    'eeg-v': 'DESKTOP-QG4CNEV',
    'eeg-w': 'TABLET-STDTE3Q6',
    'eeg-x': 'DESKTOP-T3RKRMH'
}

map_dev = {dev_map[d]: d for d in dev_map.keys()}


def dev_to_name(hostname):
    """ convert hostname to device letter """
    try:
        dev = map_dev[hostname]
    except KeyError:
        dev = ''
    return dev


def name_to_dev(name):
    """ convert hostname to device letter """
    return dev_map[name]
