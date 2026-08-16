#!/usr/bin/env python3
"""Apply the duplicate-zero guard for TechDraw ordinate dimensions.

This is an internal MONEY_AGENT helper. It adapts the duplicate checking from
bguest/FreeCAD commit 15be1ee54bd22ac9201b4c26b54451d64ffb96ff to the
current #6587 candidate without touching unrelated TechDraw code.
"""

from pathlib import Path

# The helper is intentionally copied to /tmp by CI before the workflow switches
# branches. Use the checked-out repository working directory, not __file__, as
# the source root so the patch is applied to the candidate branch checkout.
ROOT = Path.cwd()
PATH = ROOT / "src/Mod/TechDraw/Gui/CommandExtensionDims.cpp"
text = PATH.read_text(encoding="utf-8-sig")

horizontal_old = '''        auto* zeroDim = _createLinDimension(
            objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateX");
        zeroDim->X.setValue(allVertexes[0].point.x);
        zeroDim->Y.setValue(-yMaster);
'''

horizontal_new = '''        bool hasZeroDimension = false;
        if (TechDraw::DrawPage* page = objFeat->findParentPage()) {
            for (auto* view : page->Views.getValues()) {
                auto* dim = dynamic_cast<TechDraw::DrawViewDimension*>(view);
                if (!dim || !dim->Type.isValue("OrdinateX")) {
                    continue;
                }
                TechDraw::pointPair pp = dim->getLinearPoints();
                const Base::Vector3d& origin = allVertexes[0].point;
                if (std::abs(pp.first().x - origin.x) < 1e-6
                    && std::abs(pp.first().y - origin.y) < 1e-6
                    && std::abs(pp.second().x - origin.x) < 1e-6
                    && std::abs(pp.second().y - origin.y) < 1e-6) {
                    hasZeroDimension = true;
                    break;
                }
            }
        }

        if (!hasZeroDimension) {
            auto* zeroDim = _createLinDimension(
                objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateX");
            zeroDim->X.setValue(allVertexes[0].point.x);
            zeroDim->Y.setValue(-yMaster);
        }
'''

vertical_old = '''        auto* zeroDim = _createLinDimension(
            objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateY");
        zeroDim->X.setValue(xMaster);
        zeroDim->Y.setValue(-allVertexes[0].point.y);
'''

vertical_new = '''        bool hasZeroDimension = false;
        if (TechDraw::DrawPage* page = objFeat->findParentPage()) {
            for (auto* view : page->Views.getValues()) {
                auto* dim = dynamic_cast<TechDraw::DrawViewDimension*>(view);
                if (!dim || !dim->Type.isValue("OrdinateY")) {
                    continue;
                }
                TechDraw::pointPair pp = dim->getLinearPoints();
                const Base::Vector3d& origin = allVertexes[0].point;
                if (std::abs(pp.first().x - origin.x) < 1e-6
                    && std::abs(pp.first().y - origin.y) < 1e-6
                    && std::abs(pp.second().x - origin.x) < 1e-6
                    && std::abs(pp.second().y - origin.y) < 1e-6) {
                    hasZeroDimension = true;
                    break;
                }
            }
        }

        if (!hasZeroDimension) {
            auto* zeroDim = _createLinDimension(
                objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateY");
            zeroDim->X.setValue(xMaster);
            zeroDim->Y.setValue(-allVertexes[0].point.y);
        }
'''

for label, old, new in (
    ("horizontal", horizontal_old, horizontal_new),
    ("vertical", vertical_old, vertical_new),
):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one zero-marker block, got {count}")
    text = text.replace(old, new, 1)

PATH.write_text(text, encoding="utf-8")
print("Applied duplicate-zero guards for OrdinateX and OrdinateY")
