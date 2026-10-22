"""Relative major / mode helpers (port of ``const/relative-major.js``)."""

import re

# All these keys have the same number of accidentals
keys = {
    'C': {'modes': ['CMaj', 'CIon', 'Amin', 'AAeo', 'Am', 'GMix', 'DDor', 'EPhr', 'FLyd', 'BLoc'], 'stepsFromC': 0},
    'Db': {'modes': ['DbMaj', 'DbIon', 'Bbmin', 'BbAeo', 'Bbm', 'AbMix', 'EbDor', 'FPhr', 'GbLyd', 'CLoc'], 'stepsFromC': 1},
    'D': {'modes': ['DMaj', 'DIon', 'Bmin', 'BAeo', 'Bm', 'AMix', 'EDor', 'F#Phr', 'GLyd', 'C#Loc'], 'stepsFromC': 2},
    'Eb': {'modes': ['EbMaj', 'EbIon', 'Cmin', 'CAeo', 'Cm', 'BbMix', 'FDor', 'GPhr', 'AbLyd', 'DLoc'], 'stepsFromC': 3},
    'E': {'modes': ['EMaj', 'EIon', 'C#min', 'C#Aeo', 'C#m', 'BMix', 'F#Dor', 'G#Phr', 'ALyd', 'D#Loc'], 'stepsFromC': 4},
    'F': {'modes': ['FMaj', 'FIon', 'Dmin', 'DAeo', 'Dm', 'CMix', 'GDor', 'APhr', 'BbLyd', 'ELoc'], 'stepsFromC': 5},
    'Gb': {'modes': ['GbMaj', 'GbIon', 'Ebmin', 'EbAeo', 'Ebm', 'DbMix', 'AbDor', 'BbPhr', 'CbLyd', 'FLoc'], 'stepsFromC': 6},
    'G': {'modes': ['GMaj', 'GIon', 'Emin', 'EAeo', 'Em', 'DMix', 'ADor', 'BPhr', 'CLyd', 'F#Loc'], 'stepsFromC': 7},
    'Ab': {'modes': ['AbMaj', 'AbIon', 'Fmin', 'FAeo', 'Fm', 'EbMix', 'BbDor', 'CPhr', 'DbLyd', 'GLoc'], 'stepsFromC': 8},
    'A': {'modes': ['AMaj', 'AIon', 'F#min', 'F#Aeo', 'F#m', 'EMix', 'BDor', 'C#Phr', 'DLyd', 'G#Loc'], 'stepsFromC': 9},
    'Bb': {'modes': ['BbMaj', 'BbIon', 'Gmin', 'GAeo', 'Gm', 'FMix', 'CDor', 'DPhr', 'EbLyd', 'ALoc'], 'stepsFromC': 10},
    'B': {'modes': ['BMaj', 'BIon', 'G#min', 'G#Aeo', 'G#m', 'F#Mix', 'C#Dor', 'D#Phr', 'ELyd', 'A#Loc'], 'stepsFromC': 11},
    # Enharmonic keys
    'C#': {'modes': ['C#Maj', 'C#Ion', 'A#min', 'A#Aeo', 'A#m', 'G#Mix', 'D#Dor', 'E#Phr', 'F#Lyd', 'B#Loc'], 'stepsFromC': 1},
    'F#': {'modes': ['F#Maj', 'F#Ion', 'D#min', 'D#Aeo', 'D#m', 'C#Mix', 'G#Dor', 'A#Phr', 'BLyd', 'E#Loc'], 'stepsFromC': 6},
    'Cb': {'modes': ['CbMaj', 'CbIon', 'Abmin', 'AbAeo', 'Abm', 'GbMix', 'DbDor', 'EbPhr', 'FbLyd', 'BbLoc'], 'stepsFromC': 11},
}

mode_names = ['maj', 'ion', 'min', 'aeo', 'm', 'mix', 'dor', 'phr', 'lyd', 'loc']


def is_legal_mode(mode):
    return mode.lower() in mode_names


_key_reverse = None


def _create_key_reverse():
    global _key_reverse
    _key_reverse = {}
    for k, key_obj in keys.items():
        _key_reverse[k.lower()] = k
        for mode in key_obj['modes']:
            _key_reverse[mode.lower()] = k


_mode_re = re.compile(r"([a-g][b#]?)(maj|ion|min|aeo|mix|dor|phr|lyd|loc|m)?")
_mode_start_re = re.compile(r"^(maj|ion|min|aeo|mix|dor|phr|lyd|loc|m)")


def relative_major(key):
    """Translate a key to its relative major. If it doesn't exist, return the original key."""
    if _key_reverse is None:
        _create_key_reverse()
    mode = _mode_re.search(key.lower())
    if not mode or not mode.group(2):
        return key
    mode = mode.group(1) + mode.group(2)
    maj = _key_reverse.get(mode)
    if maj:
        return maj
    return key


def relative_mode(major_key, mode):
    """The reverse of relative_major: translate it back to the original mode."""
    group = keys.get(major_key)
    if not group:
        return major_key
    if mode == '':
        return major_key
    match = _mode_start_re.match(mode.lower())
    if not match:
        return major_key
    reg_mode = match.group(1)
    for this_mode in group['modes']:
        ind = this_mode.lower().find(reg_mode)
        if ind != -1 and ind == len(this_mode) - len(reg_mode):
            return this_mode[0:len(this_mode) - len(reg_mode)]
    return major_key


def transpose_key(key, steps):
    """Take a major key and add the desired number of half steps."""
    match = keys.get(key)
    if not match:
        return key
    while steps < 0:
        steps += 12
    from_c = (match['stepsFromC'] + steps) % 12
    for k in keys:
        if keys[k]['stepsFromC'] == from_c:
            return k
    return key
