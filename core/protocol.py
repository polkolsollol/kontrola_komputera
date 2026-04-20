import struct

# NAGŁÓWEK (Header):
# [4 bajty - rozmiar danych (I)] + [1 bajt - typ wiadomości (B)]
# Łącznie: 5 bajtów
HEADER_FORMAT = "!IB" 
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# TYPY WIADOMOŚCI
MSG_TYPE_FRAME = 1    # Klatka obrazu
MSG_TYPE_COMMAND = 2  # Np. ruch myszką (przyszłościowo)

def pack_message(msg_type, data):
    """Pakuje dane w format: [Rozmiar][Typ][Dane]"""
    data_size = len(data)
    header = struct.pack(HEADER_FORMAT, data_size, msg_type)
    return header + data