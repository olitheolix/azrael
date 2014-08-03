"""AMQP Table Encoding/Decoding"""
import struct
import decimal
import calendar
from datetime import datetime

from pika import exceptions


def encode_table(pieces, table):
    """Encode a dict as an AMQP table appending the encded table to the
    pieces list passed in.

    :param list pieces: Already encoded frame pieces
    :param dict table: The dict to encode
    :rtype: int

    """
    table = table or dict()
    length_index = len(pieces)
    pieces.append(None)  # placeholder
    tablesize = 0
    for (key, value) in table.items():
        pieces.append(struct.pack('B', len(key)))
        pieces.append(key.encode("utf-8"))
        tablesize = tablesize + 1 + len(key)
        tablesize += encode_value(pieces, value)

    pieces[length_index] = struct.pack('>I', tablesize)
    return tablesize + 4


def encode_value(pieces, value):
    """Encode the value passed in and append it to the pieces list returning
    the the size of the encoded value.

    :param list pieces: Already encoded values
    :param any value: The value to encode
    :rtype: int

    """
    if isinstance(value, str):
        value = value.encode('utf-8')
        pieces.append(struct.pack('>cI', b'S', len(value)))
        pieces.append(value)
        return 5 + len(value)
    elif isinstance(value, bool):
        pieces.append(struct.pack('>cB', b't', int(value)))
        return 2
    elif isinstance(value, int) and value >= -2 ** 31 and value < 2 ** 31:
        pieces.append(struct.pack('>ci', b'I', value))
        return 5
    elif isinstance(value, int):
        pieces.append(struct.pack('>cq', b'l', value))
        return 9
    elif isinstance(value, float):
        pieces.append(struct.pack('>cd', b'd', value))
        return 9
    elif isinstance(value, decimal.Decimal):
        value = value.normalize()
        def my_exp(value):
                '''Substitute for missing Decimal._exp property'''
                total_len = len(str(value))
                integral_len = len(str(value.to_integral_value(rounding=decimal.ROUND_FLOOR)))
                if(total_len == integral_len):
                    return 0
                else:
                    return int(-1*(total_len - integral_len -1))
        value_exp = my_exp(value)
        if value_exp < 0:
            decimals = -value_exp
            raw = int(value * (decimal.Decimal(10) ** decimals))
            pieces.append(struct.pack('>cBi', b'D', decimals, raw))
        else:
            # per spec, the "decimals" octet is unsigned (!)
            pieces.append(struct.pack('>cBi', b'D', 0, int(value)))
        return 6
    elif isinstance(value, datetime):
        pieces.append(struct.pack('>cQ', b'T',
                                  calendar.timegm(value.utctimetuple())))
        return 9
    elif isinstance(value, dict):
        pieces.append(struct.pack('>c', b'F'))
        return 1 + encode_table(pieces, value)
    elif isinstance(value, list):
        p = []
        for v in value:
            encode_value(p, v)
        piece = b''.join(p)
        pieces.append(struct.pack('>cI', b'A', len(piece)))
        pieces.append(piece)
        return 5 + len(piece)
    elif value is None:
        pieces.append(struct.pack('>c', b'V'))
        return 1
    else:
        raise exceptions.UnspportedAMQPFieldException(pieces, value)


def decode_table(encoded, offset):
    """Decode the AMQP table passed in from the encoded value returning the
    decoded result and the number of bytes read plus the offset.

    :param str encoded: The binary encoded data to decode
    :param int offset: The starting byte offset
    :rtype: tuple

    """
    result = {}
    tablesize = struct.unpack_from('>I', encoded, offset)[0]
    offset += 4
    limit = offset + tablesize
    while offset < limit:
        keylen = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        key = encoded[offset: offset + keylen].decode("utf-8")
        offset += keylen
        value, offset = decode_value(encoded, offset)
        result[key] = value
    return result, offset


def decode_value(encoded, offset):
    """Decode the value passed in returning the decoded value and the number
    of bytes read in addition to the starting offset.

    :param str encoded: The binary encoded data to decode
    :param int offset: The starting byte offset
    :rtype: tuple
    :raises: pika.exceptions.InvalidFieldTypeException

    """
    kind = bytes([encoded[offset]])
    offset += 1
    # Bool
    if kind == b't':
        value = struct.unpack_from('>B', encoded, offset)[0]
        value = bool(value)
        offset += 1

    # Short-Short Int
    elif kind == b'b':
        value = struct.unpack_from('>B', encoded, offset)[0]
        offset += 1

    # Short-Short Unsigned Int
    elif kind == b'B':
        value = struct.unpack_from('>b', encoded, offset)[0]
        offset += 1

    # Short Int
    elif kind == b'U':
        value = struct.unpack_from('>h', encoded, offset)[0]
        offset += 2

    # Short Unsigned Int
    elif kind == b'u':
        value = struct.unpack_from('>H', encoded, offset)[0]
        offset += 2

    # Long Int
    elif kind == b'I':
        value = struct.unpack_from('>i', encoded, offset)[0]
        offset += 4

    # Long Unsigned Int
    elif kind == b'i':
        value = struct.unpack_from('>I', encoded, offset)[0]
        offset += 4

    # Long-Long Int
    elif kind == b'L':
        value = int(struct.unpack_from('>q', encoded, offset)[0])
        offset += 8

    # Long-Long Unsigned Int
    elif kind == b'l':
        value = int(struct.unpack_from('>Q', encoded, offset)[0])
        offset += 8

    # Float
    elif kind == b'f':
        value = int(struct.unpack_from('>f', encoded, offset)[0])
        offset += 4

    # Double
    elif kind == b'd':
        value = int(struct.unpack_from('>d', encoded, offset)[0])
        offset += 8

    # Decimal
    elif kind == b'D':
        decimals = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        raw = struct.unpack_from('>i', encoded, offset)[0]
        offset += 4
        value = decimal.Decimal(raw) * (decimal.Decimal(10) ** -decimals)

    # Short String
    elif kind == b's':
        length = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        value = encoded[offset: offset + length].decode('utf8')
        try:
            value = str(value)
        except UnicodeEncodeError:
            pass
        offset += length

    # Long String
    elif kind == b'S':
        length = struct.unpack_from('>I', encoded, offset)[0]
        offset += 4
        value = encoded[offset: offset + length].decode('utf8')
        try:
            value = str(value)
        except UnicodeEncodeError:
            pass
        offset += length

    # Field Array
    elif kind == b'A':
        length = struct.unpack_from('>I', encoded, offset)[0]
        offset += 4
        offset_end = offset + length
        value = []
        while offset < offset_end:
            v, offset = decode_value(encoded, offset)
            value.append(v)

    # Timestamp
    elif kind == b'T':
        value = datetime.utcfromtimestamp(struct.unpack_from('>Q', encoded,
                                                             offset)[0])
        offset += 8

    # Field Table
    elif kind == b'F':
        (value, offset) = decode_table(encoded, offset)

    # Null / Void
    elif kind == b'V':
        value = None
    else:
        raise exceptions.InvalidFieldTypeException(kind)

    return value, offset
