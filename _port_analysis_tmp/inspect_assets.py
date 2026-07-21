from collections import Counter
from pathlib import Path
import struct
import olefile

source = Path(__file__).parent.parent / "goblins3 v.1.0 LAUNCH.pps"
ole = olefile.OleFileIO(source)
data = ole.openstream("Pictures").read()

def u32_positions(signature):
    found, start = [], 0
    while (index := data.find(signature, start)) != -1:
        found.append(index)
        start = index + 1
    return found

print("pictures_stream_bytes=", len(data))
print("first_headers=", [struct.unpack_from("<HHI", data, i) for i in range(0, min(len(data), 96), 8)])
for label, signature in {
    "jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n", "gif": b"GIF8",
    "bmp": b"BM", "wmf": b"\xd7\xcd\xc6\x9a", "emf": b"\x01\x00\x00\x00",
}.items():
    positions = u32_positions(signature)
    print(f"{label}={len(positions)} positions={positions[:20]}")

# OfficeArt blip record types found in the Pictures stream.
records, pos = [], 0
while pos + 8 <= len(data):
    verinst, rec_type, rec_len = struct.unpack_from("<HHI", data, pos)
    end = pos + 8 + rec_len
    if end > len(data):
        break
    records.append((pos, verinst & 0xF, verinst >> 4, rec_type, rec_len))
    pos = end
print("top_level_record_types=", Counter(record[3] for record in records))
print("top_level_records=", records[:30])
