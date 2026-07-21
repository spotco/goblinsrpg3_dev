import java.awt.Dimension;
import java.awt.geom.Rectangle2D;
import java.io.FileInputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.apache.poi.hslf.record.AnimationInfo;
import org.apache.poi.hslf.record.AnimationInfoAtom;
import org.apache.poi.hslf.record.Record;
import org.apache.poi.hslf.record.RecordContainer;
import org.apache.poi.hslf.record.SSSlideInfoAtom;
import org.apache.poi.hslf.usermodel.HSLFHyperlink;
import org.apache.poi.hslf.usermodel.HSLFPictureData;
import org.apache.poi.hslf.usermodel.HSLFPictureShape;
import org.apache.poi.hslf.usermodel.HSLFShape;
import org.apache.poi.hslf.usermodel.HSLFSimpleShape;
import org.apache.poi.hslf.usermodel.HSLFSlide;
import org.apache.poi.hslf.usermodel.HSLFSlideShow;
import org.apache.poi.hslf.usermodel.HSLFTextShape;
import org.apache.poi.sl.usermodel.PictureData;

public final class PoiAudit {
    private static final class Counts {
        int transitions;
        int animationInfo;
        int animationAtoms;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: PoiAudit <file.pps>");
        }

        try (FileInputStream input = new FileInputStream(args[0]);
             HSLFSlideShow show = new HSLFSlideShow(input)) {
            Dimension pageSize = show.getPageSize();
            System.out.println("pageSize=" + pageSize.width + "x" + pageSize.height);
            System.out.println("slides=" + show.getSlides().size());
            System.out.println("pictures=" + show.getPictureData().size());
            System.out.println("sounds=" + show.getSoundData().length);
            Counts rootCounts = new Counts();
            int[] rawCounts = new int[5000];
            for (Record record : show.getSlideShowImpl().getRecords()) {
                walkRootRecords(record, rawCounts, rootCounts);
            }
            System.out.println("rootTransitionAtoms=" + rootCounts.transitions);
            System.out.println("rootAnimationInfoContainers=" + rootCounts.animationInfo);
            System.out.println("rootAnimationInfoAtoms=" + rootCounts.animationAtoms);
            System.out.println("rootRaw4080=" + rawCounts[4080]);
            System.out.println("rootRaw4081=" + rawCounts[4081]);
            System.out.println("rootRaw4082=" + rawCounts[4082]);
            System.out.println("rootRaw4083=" + rawCounts[4083]);

            int shapeCount = 0;
            int pictureInstances = 0;
            int textShapes = 0;
            int simpleHyperlinks = 0;
            int textHyperlinks = 0;
            Counts counts = new Counts();

            for (HSLFSlide slide : show.getSlides()) {
                int slideNo = slide.getSlideNumber();
                List<HSLFShape> shapes = slide.getShapes();
                shapeCount += shapes.size();
                System.out.printf(Locale.ROOT, "SLIDE\t%d\tshapes\t%d%n", slideNo, shapes.size());
                for (int i = 0; i < shapes.size(); i++) {
                    HSLFShape shape = shapes.get(i);
                    Rectangle2D anchor = shape.getAnchor();
                    String kind = shape.getClass().getSimpleName();
                    System.out.printf(
                        Locale.ROOT,
                        "SHAPE\t%d\t%d\t%d\t%s\t%s\t%.3f\t%.3f\t%.3f\t%.3f%n",
                        slideNo,
                        i,
                        shape.getShapeId(),
                        kind,
                        shape.getShapeName(),
                        anchor.getX(),
                        anchor.getY(),
                        anchor.getWidth(),
                        anchor.getHeight()
                    );

                    if (shape instanceof HSLFPictureShape) {
                        pictureInstances++;
                        HSLFPictureShape picture = (HSLFPictureShape) shape;
                        HSLFPictureData data = picture.getPictureData();
                        PictureData.PictureType type = data.getType();
                        System.out.printf(
                            Locale.ROOT,
                            "PICTURE\t%d\t%d\t%d\t%d\t%s\t%d%n",
                            slideNo,
                            i,
                            shape.getShapeId(),
                            picture.getPictureIndex(),
                            type,
                            data.getData().length
                        );
                    }

                    if (shape instanceof HSLFTextShape) {
                        textShapes++;
                        HSLFTextShape textShape = (HSLFTextShape) shape;
                        String text = textShape.getText().replace("\r", "\\r").replace("\n", "\\n");
                        System.out.printf(Locale.ROOT, "TEXT\t%d\t%d\t%d\t%s%n", slideNo, i, shape.getShapeId(), text);
                        List<HSLFHyperlink> links = HSLFHyperlink.find(textShape);
                        textHyperlinks += links.size();
                        for (HSLFHyperlink link : links) {
                            printHyperlink("TEXTLINK", slideNo, i, shape.getShapeId(), link);
                        }
                    }

                    AnimationInfoAtom shapeAnimation = shape.getClientDataRecord(4081);
                    if (shapeAnimation != null) {
                        printAnimation("ANIMATION_SHAPE", slideNo, i, shape.getShapeId(), shapeAnimation);
                    }

                    if (shape instanceof HSLFSimpleShape) {
                        HSLFHyperlink link = ((HSLFSimpleShape) shape).getHyperlink();
                        if (link != null) {
                            simpleHyperlinks++;
                            printHyperlink("SHAPELINK", slideNo, i, shape.getShapeId(), link);
                        }
                    }
                }

                walkRecords(slide.getSlideRecord(), slideNo, counts);
            }

            System.out.println("shapeCount=" + shapeCount);
            System.out.println("pictureInstances=" + pictureInstances);
            System.out.println("textShapes=" + textShapes);
            System.out.println("simpleHyperlinks=" + simpleHyperlinks);
            System.out.println("textHyperlinks=" + textHyperlinks);
            System.out.println("transitionAtoms=" + counts.transitions);
            System.out.println("animationInfoContainers=" + counts.animationInfo);
            System.out.println("animationInfoAtoms=" + counts.animationAtoms);
        }
    }

    private static void printHyperlink(String prefix, int slideNo, int shapeIndex, int shapeId, HSLFHyperlink link) {
        System.out.printf(
            Locale.ROOT,
            "%s\t%d\t%d\t%d\t%d\t%s\t%s\t%s%n",
            prefix,
            slideNo,
            shapeIndex,
            shapeId,
            link.getId(),
            link.getType(),
            safe(link.getLabel()),
            safe(link.getAddress())
        );
    }

    private static String safe(String value) {
        return value == null ? "" : value.replace("\t", " ").replace("\r", "\\r").replace("\n", "\\n");
    }

    private static void walkRecords(Record record, int slideNo, Counts counts) {
        if (record instanceof SSSlideInfoAtom) {
            counts.transitions++;
            SSSlideInfoAtom atom = (SSSlideInfoAtom) record;
            System.out.printf(
                Locale.ROOT,
                "TRANSITION\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%b\t%b%n",
                slideNo,
                atom.getSlideTime(),
                atom.getSoundIdRef(),
                atom.getEffectDirection(),
                atom.getEffectType(),
                atom.getEffectTransitionFlags(),
                atom.getSpeed(),
                atom.getEffectTransitionFlagByBit(SSSlideInfoAtom.MANUAL_ADVANCE_BIT),
                atom.getEffectTransitionFlagByBit(SSSlideInfoAtom.AUTO_ADVANCE_BIT)
            );
        }

        if (record instanceof AnimationInfo) {
            counts.animationInfo++;
        }

        if (record instanceof AnimationInfoAtom) {
            counts.animationAtoms++;
            AnimationInfoAtom atom = (AnimationInfoAtom) record;
            printAnimation("ANIMATION", slideNo, -1, -1, atom);
        }

        if (record instanceof RecordContainer) {
            for (Record child : ((RecordContainer) record).getChildRecords()) {
                walkRecords(child, slideNo, counts);
            }
        }
    }

    private static void walkRootRecords(Record record, int[] rawCounts, Counts counts) {
        long type = record.getRecordType();
        if (type >= 0 && type < rawCounts.length) {
            rawCounts[(int) type]++;
        }
        if (record instanceof SSSlideInfoAtom) {
            counts.transitions++;
        }
        if (record instanceof AnimationInfo) {
            counts.animationInfo++;
        }
        if (record instanceof AnimationInfoAtom) {
            counts.animationAtoms++;
        }
        Record[] children = record.getChildRecords();
        if (children == null) {
            return;
        }
        for (Record child : children) {
            walkRootRecords(child, rawCounts, counts);
        }
    }

    private static void addFlag(List<String> flags, AnimationInfoAtom atom, int flag, String name) {
        if (atom.getFlag(flag)) {
            flags.add(name);
        }
    }

    private static void printAnimation(String prefix, int slideNo, int shapeIndex, int shapeId, AnimationInfoAtom atom) {
        List<String> flags = new ArrayList<>();
        addFlag(flags, atom, AnimationInfoAtom.Reverse, "Reverse");
        addFlag(flags, atom, AnimationInfoAtom.Automatic, "Automatic");
        addFlag(flags, atom, AnimationInfoAtom.Sound, "Sound");
        addFlag(flags, atom, AnimationInfoAtom.StopSound, "StopSound");
        addFlag(flags, atom, AnimationInfoAtom.Play, "Play");
        addFlag(flags, atom, AnimationInfoAtom.Synchronous, "Synchronous");
        addFlag(flags, atom, AnimationInfoAtom.Hide, "Hide");
        addFlag(flags, atom, AnimationInfoAtom.AnimateBg, "AnimateBg");
        System.out.printf(
            Locale.ROOT,
            "%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s%n",
            prefix,
            slideNo,
            shapeIndex,
            shapeId,
            atom.getDimColor(),
            atom.getMask(),
            atom.getSoundIdRef(),
            atom.getDelayTime(),
            atom.getOrderID(),
            atom.getSlideCount(),
            String.join(",", flags)
        );
    }
}
