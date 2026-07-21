import java.awt.Color;
import java.awt.Dimension;
import java.awt.Insets;
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
import org.apache.poi.hslf.usermodel.HSLFTextParagraph;
import org.apache.poi.hslf.usermodel.HSLFTextRun;
import org.apache.poi.sl.usermodel.ColorStyle;
import org.apache.poi.sl.usermodel.PaintStyle;
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
                System.out.printf(
                    Locale.ROOT,
                    "SLIDEMETA\t%d\t%s\t%s\t%s\t%s\t%b\t%b\t%b\t%b%n",
                    slideNo,
                    safe(slide.getTitle()),
                    safe(slide.getSlideName()),
                    safe(String.valueOf(slide.getMasterSheet())),
                    safe(String.valueOf(slide.getSlideLayout())),
                    slide.getFollowMasterBackground(),
                    slide.getFollowMasterObjects(),
                    slide.getFollowMasterScheme(),
                    slide.isHidden()
                );
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
                    System.out.printf(
                        Locale.ROOT,
                        "GEOMETRY\t%d\t%d\t%d\t%s\t%.3f\t%b\t%b\t%b%n",
                        slideNo,
                        i,
                        shape.getShapeId(),
                        safe(String.valueOf(shape.getShapeType())),
                        shape.getRotation(),
                        shape.getFlipHorizontal(),
                        shape.getFlipVertical(),
                        shape.isPlaceholder()
                    );

                    if (shape instanceof HSLFSimpleShape) {
                        HSLFSimpleShape simple = (HSLFSimpleShape) shape;
                        System.out.printf(
                            Locale.ROOT,
                            "STYLE\t%d\t%d\t%d\t%s\t%s\t%.3f\t%s\t%s\t%s%n",
                            slideNo,
                            i,
                            shape.getShapeId(),
                            color(simple.getFillColor()),
                            color(simple.getLineColor()),
                            simple.getLineWidth(),
                            safe(String.valueOf(simple.getLineDash())),
                            safe(String.valueOf(simple.getLineCap())),
                            safe(String.valueOf(simple.getLineCompound()))
                        );
                    }

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
                        Insets clipping = picture.getClipping();
                        if (clipping == null) {
                            clipping = new Insets(0, 0, 0, 0);
                        }
                        System.out.printf(
                            Locale.ROOT,
                            "CLIP\t%d\t%d\t%d\t%d\t%d\t%d\t%d%n",
                            slideNo,
                            i,
                            shape.getShapeId(),
                            clipping.top,
                            clipping.right,
                            clipping.bottom,
                            clipping.left
                        );
                    }

                    if (shape instanceof HSLFTextShape) {
                        textShapes++;
                        HSLFTextShape textShape = (HSLFTextShape) shape;
                        String text = textShape.getText().replace("\r", "\\r").replace("\n", "\\n");
                        System.out.printf(Locale.ROOT, "TEXT\t%d\t%d\t%d\t%s%n", slideNo, i, shape.getShapeId(), field(text));
                        System.out.printf(
                            Locale.ROOT,
                            "TEXTSTYLE\t%d\t%d\t%d\t%b\t%d\t%s\t%s\t%s\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f%n",
                            slideNo,
                            i,
                            shape.getShapeId(),
                            textShape.getWordWrap(),
                            textShape.getWordWrapEx(),
                            safe(String.valueOf(textShape.getVerticalAlignment())),
                            safe(String.valueOf(textShape.getTextDirection())),
                            safe(String.valueOf(textShape.getTextRotation())),
                            textShape.getLeftInset(),
                            textShape.getRightInset(),
                            textShape.getTopInset(),
                            textShape.getBottomInset(),
                            textShape.getTextHeight()
                        );
                        printTextRuns(slideNo, i, shape.getShapeId(), textShape);
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

    private static void printTextRuns(int slideNo, int shapeIndex, int shapeId, HSLFTextShape textShape) {
        int paragraphStart = 0;
        List<HSLFTextParagraph> paragraphs = textShape.getTextParagraphs();
        for (int paragraphIndex = 0; paragraphIndex < paragraphs.size(); paragraphIndex++) {
            HSLFTextParagraph paragraph = paragraphs.get(paragraphIndex);
            int paragraphLength = 0;
            for (HSLFTextRun run : paragraph.getTextRuns()) {
                paragraphLength += run.getLength();
            }
            System.out.printf(
                Locale.ROOT,
                "PARAGRAPH\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%b\t%s\t%s\t%s%n",
                slideNo,
                shapeIndex,
                shapeId,
                paragraphIndex,
                paragraphStart,
                paragraphLength,
                safe(String.valueOf(paragraph.getTextAlign())),
                safe(String.valueOf(paragraph.getFontAlign())),
                paragraph.getIndentLevel(),
                safe(String.valueOf(paragraph.getLeftMargin())),
                safe(String.valueOf(paragraph.getRightMargin())),
                safe(String.valueOf(paragraph.getIndent())),
                safe(String.valueOf(paragraph.getLineSpacing())),
                safe(String.valueOf(paragraph.getSpaceBefore())),
                safe(String.valueOf(paragraph.getSpaceAfter())),
                paragraph.isBullet(),
                safe(String.valueOf(paragraph.getBulletChar())),
                safe(paragraph.getBulletFont()),
                safe(String.valueOf(paragraph.getBulletSize()))
            );
            int runStart = paragraphStart;
            int runIndex = 0;
            for (HSLFTextRun run : paragraph.getTextRuns()) {
                PaintStyle.SolidPaint paint = run.getFontColor();
                System.out.printf(
                    Locale.ROOT,
                    "TEXTRUN\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%b\t%b\t%b\t%b\t%s%n",
                    slideNo,
                    shapeIndex,
                    shapeId,
                    paragraphIndex,
                    runIndex,
                    runStart,
                    run.getLength(),
                    safe(run.getRawText()),
                    safe(run.getFontFamily()),
                    safe(String.valueOf(run.getFontSize())),
                    run.isBold(),
                    run.isItalic(),
                    run.isUnderlined(),
                    run.isStrikethrough(),
                    solidColor(paint)
                );
                runStart += run.getLength();
                runIndex++;
            }
            paragraphStart += paragraphLength;
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
            field(link.getLabel()),
            field(link.getAddress())
        );
    }

    private static String safe(String value) {
        return value == null ? "" : value.replace("\t", " ").replace("\r", "\\r").replace("\n", "\\n");
    }

    private static String field(String value) {
        String safeValue = safe(value);
        return safeValue.isEmpty() ? "null" : safeValue;
    }

    private static String color(Color value) {
        if (value == null) {
            return "";
        }
        return String.format(
            Locale.ROOT,
            "#%02x%02x%02x%02x",
            value.getRed(),
            value.getGreen(),
            value.getBlue(),
            value.getAlpha()
        );
    }

    private static String solidColor(PaintStyle.SolidPaint paint) {
        if (paint == null) {
            return "";
        }
        ColorStyle style = paint.getSolidColor();
        return style == null ? "" : color(style.getColor());
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
