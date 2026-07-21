from collections import Counter
from pathlib import Path
import json
import struct
import olefile

source = Path(__file__).parent.parent / "goblins3 v.1.0 LAUNCH.pps"
ole = olefile.OleFileIO(source)
rows = []
for parts in ole.listdir(streams=True, storages=False):
    rows.append({"path": "/".join(parts), "size": ole.get_size(parts)})

def records(data, start=0, end=None, depth=0):
    end = len(data) if end is None else end
    pos = start
    while pos + 8 <= end:
        verinst, rec_type, rec_len = struct.unpack_from("<HHI", data, pos)
        record_end = pos + 8 + rec_len
        if record_end > end:
            return
        yield (pos, depth, verinst & 0xF, verinst >> 4, rec_type, rec_len)
        if (verinst & 0xF) == 0xF:
            yield from records(data, pos + 8, record_end, depth + 1)
        pos = record_end

powerpoint = ole.openstream("PowerPoint Document").read()
parsed = list(records(powerpoint))
types = Counter(record[4] for record in parsed)
print(json.dumps({
    "streams": rows,
    "total_records": len(parsed),
    "record_type_counts": {str(k): v for k, v in sorted(types.items())},
    "top_level_records": [
        {"offset": r[0], "version": r[2], "instance": r[3], "type": r[4], "length": r[5]}
        for r in parsed if r[1] == 0
    ],
    "slide_records": [
        {"offset": r[0], "depth": r[1], "length": r[5]}
        for r in parsed if r[4] == 1006
    ],
    "named_record_counts": {
        "Document": types[1000], "Slide": types[1006], "SlideAtom": types[1007],
        "SlideListWithText": types[4080], "UserEditAtom": types[4085],
        "InteractiveInfoAtom": types[4083], "TextInteractiveInfoAtom": types[4084],
        "ExHyperlink": types[4055], "ExHyperlinkAtom": types[4051],
        "Sound": types[2022], "SoundData": types[2023]
    }
}, indent=2))
