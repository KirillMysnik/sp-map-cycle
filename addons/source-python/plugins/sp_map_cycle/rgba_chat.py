import re

# Based on http://www.teamfortress.com/post.php?id=7946
SIGN_RGB = '\x07'
SIGN_RGBA = '\x08'

p1 = re.compile(r'#[0-9a-f]{8}', re.I)  # #RRGGBBAA (hex)
p2 = re.compile(r'#[0-9a-f]{6}', re.I)  # #RRGGBB	(hex)
p3 = re.compile('#' + ','.join((r'[0-9]{1,3}',) * 4), re.I)  # #R,G,B,A	(dec)
p4 = re.compile('#' + ','.join((r'[0-9]{1,3}',) * 3), re.I)  # #R,G,B	(dec)


def process_string(string):
    for color in p1.findall(string):
        rep = SIGN_RGBA + color[1:].upper()
        string = string.replace(color, rep)

    for color in p2.findall(string):
        rep = SIGN_RGB + color[1:].upper()
        string = string.replace(color, rep)

    for color in p3.findall(string):
        rep = SIGN_RGBA + ('%02X' * 4 % tuple(map(int, color[1:].split(','))))
        string = string.replace(color, rep)

    for color in p4.findall(string):
        rep = SIGN_RGB + ('%02X' * 3 % tuple(map(int, color[1:].split(','))))
        string = string.replace(color, rep)

    return '\x01%s' % string
