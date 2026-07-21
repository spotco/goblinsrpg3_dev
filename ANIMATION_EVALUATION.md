# PowerPoint animation data evaluation

## Question

The source game appears to use more than simple "appear/disappear" animations. This evaluation checks whether the original `.pps` contains the richer PowerPoint timing data needed to recreate chained animations, click-triggered animation sequences, easing-like modifiers, motion paths, text/image visibility changes, and animation-related sound commands in JavaScript.

## Result

Yes: the complex animation data is real and is present in the file.

The critical data is stored in PowerPoint 2002/2003 `___PPT10` slide programmable tag binary blobs, not in the older legacy `AnimationInfoAtom` records alone. The project can access those records with the Python OLE/MS-PPT parser in `tools/audit_timing_tree.py`.

Apache POI remains useful for validating slides, shapes, text, images, hyperlinks, sounds, and slide transitions, but it does not expose these PP10 timing trees through a high-level HSLF API for this deck. The animation extractor therefore needs a dedicated Python PP10 timing-tree decoder.

## Local evidence

`generated/timing_tree_audit.json` was regenerated from the original `goblins3 v.1.0 LAUNCH.pps` file.

Key findings:

- 197 slides contain PP10 timing-tree binary blobs.
- 2,407 `RT_TimeExtTimeNodeContainer` records are present. These are the hierarchical time nodes for nested/chained animation playback.
- 2,533 `RT_TimeNode` atoms are present. These include node type, fill mode, restart mode, duration, and explicit-property flags.
- 2,093 `RT_TimeCondition` atoms are present. These include trigger object, trigger event, target id, and delay.
- 135 `RT_TimeSequenceData` atoms are present. These specify sequence traversal behavior for child time nodes.
- 478 `RT_TimeModifier` atoms are present. Observed modifier types include `3`, `4`, and `5`; Microsoft examples identify these as acceleration, deceleration, and auto-reverse style modifiers.
- 18 `RT_TimeAnimateBehavior` atoms are present, all with `calcMode = 1` and `valueType = 1`. Microsoft's shape-animation example identifies `calcMode = 1` as linear interpolation for numeric property values.
- 35 `RT_TimeAnimationValue` atoms are present, with keyframe times at 0 ms, 500 ms, and 1000 ms.
- 1,004 behavior containers are present:
  - 18 generic animate behavior containers
  - 291 effect behavior containers
  - 215 motion behavior containers
  - 3 scale behavior containers
  - 466 set behavior containers
  - 11 command behavior containers
- 6,078 `RT_TimeVariant` records are present. These contain properties, formulas, effect names, and animation values such as `style.visibility`, `visible`, `fade`, `ppt_x`, `ppt_y`, `#ppt_x`, and `#ppt_y`.
- 1,022 visual target references were found:
  - 1,015 shape references
  - 7 sound references
  - 0 unresolved shape references after mapping them back to Apache POI-recognized slide shape ids

Observed trigger events:

| Event value | Meaning from MS-PPT | Count |
| --- | --- | ---: |
| `0` | No condition / true immediately | 1,538 |
| `1` | OnBegin | 130 |
| `3` | Start of referenced time node | 7 |
| `4` | End of referenced time node | 108 |
| `9` | OnNext; can be triggered by mouse click on the slide | 146 |
| `10` | OnPrev | 146 |
| `11` | Stop audio event | 18 |

This proves that the file contains the data needed for chained animation state and click-driven sequence traversal. It also shows that audio commands are part of the animation model and must be handled by the browser runtime.

For the "lerp mode" concern specifically: the deck has explicit `TimeAnimateBehaviorAtom.calcMode` values, and the observed value is linear interpolation. The acceleration/deceleration modifiers are separate timing modifiers that still need to be applied by the JavaScript scheduler around the base interpolation.

## What is proven versus remaining work

Proven:

- The complex PowerPoint 10 timing trees exist in the original `.pps`.
- The data is accessible with local Python code; no Aspose dependency is needed for this extraction.
- Shape animation targets can be mapped back to real slide shapes.
- Sound animation targets are distinguishable from shape targets.
- Trigger, duration, sequence, modifier, behavior-type, property, and value records are present.

Remaining implementation work:

- Build a full decoder that preserves the parent/child timing-tree structure rather than only counting records.
- Decode every behavior atom into a normalized JS-ready manifest: effect type/direction, property path, keyframe list, motion path, set value, command, target shape/sound, duration, delay, fill, restart, acceleration, deceleration, and auto-reverse.
- Decode and map time-node ids so `Start of referenced time node` and `End of referenced time node` conditions trigger the correct JS animations.
- Implement the JavaScript scheduler/player for parallel and sequential time nodes, `OnNext`/`OnPrev`, delays, end conditions, and sound commands.
- Validate playback visually against PowerPoint reference output for representative slides before applying the player globally.

## Verification commands

```powershell
.\_port_analysis_tmp\venv\Scripts\python.exe tools\audit_timing_tree.py "goblins3 v.1.0 LAUNCH.pps" --output generated\timing_tree_audit.json
.\_port_analysis_tmp\venv\Scripts\python.exe tools\verify_timing_tree.py
.\_port_analysis_tmp\venv\Scripts\python.exe tools\verify_poi_audit.py
```

## References

- Microsoft MS-PPT: [`SlideProgTagsContainer`](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/c2263e42-180e-4249-bd93-a421efd8719b) specifies slide programmable tags with additional slide data.
- Microsoft MS-PPT: [`___PPT10` slide programmable tags](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/669d0590-c882-4263-8aa1-5a9fb88fa053) contain `SlideTime10Atom`, `HashCode10Atom`, `ExtTimeNodeContainer`, and `BuildListContainer`.
- Microsoft MS-PPT: [`ExtTimeNodeContainer`](https://learn.microsoft.com/en-au/openspecs/office_file_formats/ms-ppt/83d39c58-0d30-46a4-bffb-188d792cb5a7) stores the time/action effect hierarchy, behavior containers, condition records, modifiers, subordinate effects, and child time nodes.
- Microsoft MS-PPT: [`TimeConditionAtom`](https://learn.microsoft.com/de-at/openspecs/office_file_formats/ms-ppt/6d793884-73f2-4b87-b8b1-a1b0e6310ad6) stores trigger object, trigger event, target id, and delay; trigger events include mouse click/OnNext, OnPrev, start/end of a referenced time node, and stop-audio.
- Microsoft MS-PPT: [`TimeSequenceDataAtom`](https://learn.microsoft.com/en-nz/openspecs/office_file_formats/ms-ppt/342b92a2-73df-4b0b-9878-862f3532d570) stores sequencing information for child nodes.
- Microsoft MS-PPT: [`TimeMotionBehaviorContainer`](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-ppt/40b9860a-04a5-4946-ae4b-51fdd1176cec) stores motion-animation behavior and path data.
- Microsoft MS-PPT: [Shape animation example](https://learn.microsoft.com/pt-br/openspecs/office_file_formats/ms-ppt/13b03cf8-e193-4d7c-bece-efee91ea40bd) documents `TimeAnimateBehaviorAtom.calcMode = 1` as linear interpolation and shows acceleration/deceleration `TimeModifierAtom` records.
