# Apache POI evaluation

This evaluation checks whether Apache POI can replace Aspose on the critical path for the PowerPoint 97-2003 `.pps` port.

## Local toolchain

- Portable JDK: `_port_analysis_tmp/jdk21/jdk-21.0.11+10/`
- Apache POI: `_port_analysis_tmp/poi-5.2.3/poi-bin-5.2.3/`
- Both directories are intentionally gitignored.

Apache POI 5.2.3 is used because Apache's download page says it was the last release with an all-in-one binary zip. Newer POI releases are distributed through Maven Central.

## What works through POI

`tools/poi/PoiAudit.java` compiles and runs against the original `.pps` with the portable JDK and POI jars.

The POI audit confirms:

- 201 slides
- 720x540 page size
- 116 unique embedded pictures
- 532 picture instances on slides
- 5 embedded sounds
- 1182 slide shapes
- 194 hyperlinks/actions exposed through text or shape hyperlink APIs
- 201 slide transition atoms exposed through `SSSlideInfoAtom`

The POI transition data is directly usable for JavaScript slide transitions: slide time, sound reference, effect direction, effect type, transition flags, speed, manual advance, and auto advance.

## What does not work directly through POI

POI has `AnimationInfoAtom` and `AnimationInfo` classes, but for this file HSLF does not expose the 4081/4082/4083 animation/action atoms through `HSLFSlide`, `HSLFShape.getClientDataRecord()`, or the POI root record tree.

Observed POI raw-record counts from the audit:

- `rootTransitionAtoms=202`
- `rootAnimationInfoContainers=0`
- `rootAnimationInfoAtoms=0`
- `rootRaw4080=2`
- `rootRaw4081=0`
- `rootRaw4082=0`
- `rootRaw4083=0`

Our Python OLE parser still sees those records inside OfficeArt/client-data bytes:

- 341 shape animation atoms (`4081`)
- 217 interactive containers (`4082`)
- 217 interactive atoms (`4083`)

## Cross-check result

`tools/extract_timing.py` extracts:

- 201 slide transitions
- 341 shape animation atoms

`tools/verify_poi_audit.py` verifies that every extracted animation atom maps to a POI-recognized `(slide, shapeId)` pair:

- missing animation shapes: 0

This means the data is real and mappable, but POI is not enough by itself for animation extraction in this deck.

## Conclusion

Use Apache POI as the validation/reference layer for:

- slide count and page size
- image assets and image instances
- shape IDs, bounds, and z-order
- text
- hyperlinks
- embedded sounds
- slide transitions

Keep the project Python OLE parser as the authoritative extractor for:

- shape animation atoms
- interactive action atoms
- OfficeArt/client-data records POI does not surface

This is workable with additional effort. The practical implementation path is a hybrid extractor: POI validates and fills high-level shape/transition data, while the Python parser extracts the raw animation/action records and maps them to the same POI shape IDs.
