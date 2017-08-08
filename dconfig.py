"""
A module for configuring with external configuration files.

dconfig.py

Updated: 2016-01-12

Specifically, this module aims at making it easy to have default values
built into a program which can be overridden by a configuration file
in the classic format:

# This is a sample configuration file. Blank lines and lines beginning
# with the octothorpe character (#) will be ignored.
HOST=192.168.1.1
# use default port
#PORT=12345
CONNECT_TIMEOUT=15
RETRY_ON_FAIL=True
SIZE=6.4, 4.8
BANNER=     *** WeLcOmE ***     
FG_COLOR=GOLDENROD
BG_COLOR=#222244
"""

import os.path
import re
import sys

STRING = 1
INT = 2
FLOAT = 4
BOOL = 8
TUPLE = 64

STRIP = 2048
UPPER = 4096
LOWER = 8192

_ALL_TYPES = STRING | INT | FLOAT | BOOL
_UP_AND_LOW = UPPER | LOWER

_COMMENT_RE = re.compile(r'^(\s*)#')
_HAS_TEXT_RE = re.compile(r'\S')
_OPTION_RE = re.compile(r'^([^:]+)=(.*)$')
_BOOL_FALSES = ['0', 'f', 'false', 'n', 'no', 'nil', '-']
_BOOL_TRUES = ['1', 't', 'true', 'y', 'yes', '+']

class FlagError(ValueError):
    pass

def _cmp(val, attrib):
    """Do a bitwise AND of val and attrib (return True or False).
    This function is meant for comparing a bitmask of attributes (val)
    to a single attribute (attrib) to see if val has the bit set for
    that attribute."""
    if (val & attrib) == 0:
        return False
    else:
        return True

def _bool_read(txt):
    tmp = txt.lower()
    if tmp in _BOOL_TRUES:
        return True
    elif tmp in _BOOL_FALSES:
        return False
    else:
        raise ValueError('"{}" is not a recognized boolean indicator.'.format(txt))

def _process(txt, flags):
    """Process a file-read config value based on that option's flags.
    txt is the string read from the file; flags is the bitmask of attributes
    associated with the option."""
    temp_str = txt
    if _cmp(flags, STRING) and not _cmp(flags, STRIP):
        pass
    else:
        temp_str = temp_str.strip()

    if _cmp(flags, UPPER):
        temp_str = temp_str.upper()
    elif _cmp(flags, LOWER):
        temp_str = temp_str.lower()

    if _cmp(flags, TUPLE):
        chunks = temp_str.split(',')
        if _cmp(flags, STRING) and not _cmp(flags, STRIP):
            pass
        else:
            chunks = [x.strip() for x in chunks]

        if _cmp(flags, INT):
            chunks = [int(x) for x in chunks]
        elif _cmp(flags, FLOAT):
            chunks = [float(x) for x in chunks]
        elif _cmp(flags, BOOL):
            chunks = [_bool_read(x) for x in chunks]

        return tuple(chunks)

    else:
        if _cmp(flags, INT):
            return int(temp_str)
        elif _cmp(flags, FLOAT):
            return float(temp_str)
        elif _cmp(flags, BOOL):
            return _bool_read(temp_str)
        else:
            return temp_str

def _sum_of_bits(n):
    """Sum the bits in the binary representation of n.
    Used to determine how many attributes are set in a given bitmask."""
    return sum([int(c) for c in '{:b}'.format(n)])

_cfg_vals = {}
_cfg_flags = {}

def add_option(name, default, flags):
    """Give an option a default value and specify how the value read from a
    configuration file should be treated.

    name is the option's name, and will always be forced upper-case.
    default is the default value to use for that option if it's not overridden
    in a configuration file.
    flags is a bitwise-OR'd bitmask specifying how the string of text read
    from a configuration file should be treated to produce a value.

    To produce the defaults listed in the module overview, one would use the
    following calls:

    dconfig.add_option('HOST', '192.168.1.1', dconfig.STRING | dconfig.STRIP)
    dconfig.add_option('PORT', 12345, dconfig.INT)
    dconfig.add_option('CONNECT_TIMEOUT', 15, dconfig.INT)
    dconfig.add_option('RETRY_ON_FAIL', True, dconfig.BOOL)
    dconfig.add_option('SIZE', (6.4, 4.8), dconfig.FLOAT | dconfig.TUPLE)
    dconfig.add_option('BANNER', '     *** WeLcOmE ***     ', dconfig.STRING)
    dconfig.add_option('FG_COLOR', 'GOLDENROD', dconfig.STRING | dconfig.UPPER)
    dconfig.add_option('BG_COLOR', '#222244', dconfig.STRING | dconfig.UPPER)

    Incompatible flags used together (like dconfig.INT | dconfig.STRING)
    will raise a dconfig.FlagError exception."""

    name = name.upper()
    num_of_types = _sum_of_bits(flags & _ALL_TYPES)
    if num_of_types == 0:
        raise FlagError('Option "{}": must specify a type (STRING, INT, FLOAT, or BOOL).'.format(name))
    elif num_of_types > 1:
        raise FlagError('Option "{}": may ONLY specify ONE type (of STRING, INT, FLOAT, or BOOL)'.format(name))
    attribs = _sum_of_bits(flags & _UP_AND_LOW)
    if attribs > 1:
        raise FlagError('Option "{}": May not specify both UPPER and LOWER.'.format(name))

    _cfg_vals[name] = default
    _cfg_flags[name] = flags

def add_options(list_of_tuples):
    """Add multiple options, specified as a list or tuple of lists or tuples.
    For example:

    dconfig.add_options(
        [
            ('HOST', '192.168.1.1', dconfig.STRING | dconfig.STRIP),
            ('PORT', 12345, dconfig.INT),
            ('CONNECT_TIMEOUT', 15, dconfig.INT),
            # ...etc.
        ])"""
    for t in list_of_tuples:
        add_option(*t)

def get(option):
    """Return the configuration value associated with option.

    If we had set everything up according to add_option()'s help text,
    dconfig.get('HOST') should return '192.168.1.1'."""
    try:
        return _cfg_vals[option.upper()]
    except KeyError:
        raise ValueError('Option "{}" not configured.'.format(option))

def external_config(list_of_files):
    """Search for the paths provided in list_of_files and read the first
    one found as the configuration file.

    dconfig.external_config(['frogs.cfg',
                             '~/.frogs.cfg',
                             '/usr/etc/frogs/default.cfg'])
    will look for 'frogs.cfg' first; if it exists, it will read configuration
    information from it. If not, it will look for '~/.frogs.cfg', and if it
    can't find that, will use '/usr/etc/frogs/default.cfg'. If none of those
    files exist, it will just use the given default configuration values
    for all options."""
    cfg_file = None
    for fname in list_of_files:
        if os.path.isfile(fname):
            cfg_file = fname
            break

    tmps = {}
    if cfg_file:
        with open(cfg_file, 'r') as f:
            for line in f.readlines():
                if (not _COMMENT_RE.match(line)) and _HAS_TEXT_RE.match(line):
                    m = _OPTION_RE.match(line)
                    if m:
                        opt = m.group(1).strip().upper()
                        val = m.group(2)
                        tmps[opt] = val
                    else:
                        sys.stderr.write('skipping malfomred config file line: {}'.format(
                            line.rstrip()))

    for opt, val in tmps.iteritems():
        try:
            v = _process(val, _cfg_flags[opt])
            _cfg_vals[opt] = v
        except KeyError:
            sys.stderr.write('unrecognized config option "{}"\n'.format(opt))
        except Exception:
            sys.stderr.write('malformed config value "{}" for option "{}"\n'.format(
                val, opt))