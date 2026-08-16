#!/usr/bin/env python3
"""Temporary deterministic port helper for FreeCAD issue #6587.

This script ports the useful parts of the historical ordinate-dimension WIP onto
current FreeCAD main without carrying the unrelated PropertyEnumeration helper
or the stale smart-dimension state machine changes.
"""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} matches, got {count}")
    return text.replace(old, new)


# ---------------------------------------------------------------------------
# App model: make OrdinateX/OrdinateY first-class dimension types.
# ---------------------------------------------------------------------------
rel = "src/Mod/TechDraw/App/DrawViewDimension.h"
text = read(rel)
text = replace_once(
    text,
    "        DistanceZ,\n        Radius,",
    "        DistanceZ,\n        OrdinateX,\n        OrdinateY,\n        Radius,",
    "DrawViewDimension.h enum",
)
write(rel, text)

rel = "src/Mod/TechDraw/App/DrawViewDimension.cpp"
text = read(rel)
text = replace_once(
    text,
    '                                              "DistanceZ",\n                                              "Radius",',
    '                                              "DistanceZ",\n                                              "OrdinateX",\n                                              "OrdinateY",\n                                              "Radius",',
    "DrawViewDimension.cpp TypeEnums",
)
linear_old = 'Type.isValue("Distance") || Type.isValue("DistanceX") || Type.isValue("DistanceY")'
linear_new = (
    'Type.isValue("Distance") || Type.isValue("DistanceX") || Type.isValue("DistanceY")\n'
    '        || Type.isValue("OrdinateX") || Type.isValue("OrdinateY")'
)
text = replace_count(text, linear_old, linear_new, 4, "DrawViewDimension linear predicates")
text = replace_once(
    text,
    '        else if (Type.isValue("DistanceX")) {\n            result = fabs(dimVec.x) / scale;\n        }',
    '        else if (Type.isValue("DistanceX") || Type.isValue("OrdinateX")) {\n            result = fabs(dimVec.x) / scale;\n        }',
    "DrawViewDimension projected ordinate X",
)
write(rel, text)


# ---------------------------------------------------------------------------
# Renderer: route ordinate types and draw a single-ended leader.
# ---------------------------------------------------------------------------
rel = "src/Mod/TechDraw/Gui/QGIViewDimension.cpp"
text = read(rel)
text = replace_once(
    text,
    '''        if (strcmp(dimType, "Distance") == 0 || strcmp(dimType, "DistanceX") == 0
            || strcmp(dimType, "DistanceY") == 0) {
            drawDistance(dim, vp);
        }
        else if (strcmp(dimType, "Diameter") == 0) {''',
    '''        if (strcmp(dimType, "Distance") == 0 || strcmp(dimType, "DistanceX") == 0
            || strcmp(dimType, "DistanceY") == 0) {
            drawDistance(dim, vp);
        }
        else if (strcmp(dimType, "OrdinateX") == 0 || strcmp(dimType, "OrdinateY") == 0) {
            drawOrdinate(dim, vp);
        }
        else if (strcmp(dimType, "Diameter") == 0) {''',
    "QGIViewDimension ordinate dispatch",
)

ordinate_renderer = r'''
void QGIViewDimension::drawOrdinate(TechDraw::DrawViewDimension* dimension,
                                    ViewProviderDimension* viewProvider) const
{
    Base::BoundBox2d labelRectangle(
        fromQtGui(mapRectFromItem(datumLabel, datumLabel->tightBoundingRect())));

    pointPair linePoints = dimension->getLinearPoints();
    Base::Vector2d attachPoint = fromQtApp(linePoints.extensionLineSecond());
    Base::Vector2d center = labelRectangle.GetCenter();

    std::vector<Base::Vector2d> points(4);
    points[3] = center;

    double lineAngle = 0.0;
    double labelAngle = 0.0;
    double rotationDelta = (labelRectangle.Width() - labelRectangle.Height()) / 2.0;

    if (dimension->Type.isValue("OrdinateX")) {
        if (attachPoint.y < center.y) {
            lineAngle = std::numbers::pi / 2.0;
            labelAngle = std::numbers::pi / 2.0;
            points[3].y = labelRectangle.MinY - rotationDelta;
        }
        else {
            lineAngle = -std::numbers::pi / 2.0;
            labelAngle = std::numbers::pi / 2.0;
            points[3].y = labelRectangle.MaxY + rotationDelta;
        }
    }
    else {
        if (attachPoint.x < center.x) {
            points[3].x = labelRectangle.MinX;
        }
        else {
            lineAngle = std::numbers::pi;
            points[3].x = labelRectangle.MaxX;
        }
    }

    double gapFactor {};
    switch (viewProvider->StandardAndStyle.getValue()) {
        case ViewProviderDimension::STD_STYLE_ASME_INLINED:
        case ViewProviderDimension::STD_STYLE_ASME_REFERENCING:
            gapFactor = viewProvider->GapFactorASME.getValue();
            break;
        default:
            gapFactor = viewProvider->GapFactorISO.getValue();
            break;
    }
    double gapSize = Rez::appX(m_lineWidth * gapFactor);

    QPainterPath path;
    points[0] = attachPoint + Base::Vector2d::FromPolar(gapSize, lineAngle);
    points[1] = points[0] + Base::Vector2d::FromPolar(10.0, lineAngle);
    points[2] = points[3] + Base::Vector2d::FromPolar(-10.0, lineAngle);

    const double alignTolerance = Rez::appX(std::max(1.0, m_lineWidth));
    const bool alreadyVertical = std::abs(points[0].x - points[3].x) <= alignTolerance;
    const bool alreadyHorizontal = std::abs(points[0].y - points[3].y) <= alignTolerance;

    path.moveTo(toQtGui(points[0]));
    if ((dimension->Type.isValue("OrdinateX") && !alreadyVertical)
        || (dimension->Type.isValue("OrdinateY") && !alreadyHorizontal)) {
        path.lineTo(toQtGui(points[1]));
        path.lineTo(toQtGui(points[2]));
    }
    path.lineTo(toQtGui(points[3]));

    dimLines->setPath(path);
    datumLabel->setTransformOriginPoint(datumLabel->tightBoundingRect().center());
    datumLabel->setRotation(toQtDeg(labelAngle));

    Base::Vector2d arrowPositions[2] {attachPoint, Base::Vector2d()};
    double arrowAngles[2] {lineAngle, 0.0};
    drawArrows(1, arrowPositions, arrowAngles, viewProvider->FlipArrowheads.getValue());
}

'''
text = replace_once(
    text,
    "void QGIViewDimension::drawRadius(TechDraw::DrawViewDimension* dimension,",
    ordinate_renderer + "void QGIViewDimension::drawRadius(TechDraw::DrawViewDimension* dimension,",
    "QGIViewDimension drawOrdinate insertion",
)
write(rel, text)


# ---------------------------------------------------------------------------
# Commands: horizontal/vertical ordinate dimensions with an explicit zero
# dimension at the first selected vertex.
# ---------------------------------------------------------------------------
rel = "src/Mod/TechDraw/Gui/CommandExtensionDims.cpp"
text = read(rel)
ordinate_commands = r'''
//===========================================================================
// TechDraw_ExtensionCreateHorizOrdinateDimension
//===========================================================================

void execCreateHorizOrdinateDimension(Gui::Command* cmd)
{
    std::vector<Gui::SelectionObject> selection;
    TechDraw::DrawViewPart* objFeat = nullptr;
    if (!_checkSelObjAndSubs(cmd, selection, objFeat,
                            QT_TRANSLATE_NOOP("QObject", "TechDraw Create Horizontal Ordinate Dimension"))) {
        return;
    }

    cmd->openCommand(QT_TRANSLATE_NOOP("Command", "Create Horizontal Ordinate Dimensions"));
    const std::vector<std::string> subNames = selection[0].getSubNames();
    std::vector<dimVertex> allVertexes = _getVertexInfo(objFeat, subNames);
    if (allVertexes.size() > 1) {
        double dimDistance = activeDimAttributes.getCascadeSpacing();
        double yMaster = allVertexes[0].point.y - dimDistance;
        if (std::signbit(yMaster)) {
            dimDistance = -dimDistance;
        }

        auto* zeroDim = _createLinDimension(
            objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateX");
        zeroDim->X.setValue(allVertexes[0].point.x);
        zeroDim->Y.setValue(-yMaster);

        for (std::size_t n = 1; n < allVertexes.size(); ++n) {
            auto* dim = _createLinDimension(
                objFeat, allVertexes[0].name, allVertexes[n].name, "OrdinateX");
            TechDraw::pointPair pp = dim->getLinearPoints();
            dim->X.setValue(pp.second().x);
            dim->Y.setValue(-yMaster);
        }
    }
    objFeat->refreshCEGeoms();
    objFeat->requestPaint();
    cmd->getSelection().clearSelection();
    cmd->commitCommand();
}

DEF_STD_CMD_A(CmdTechDrawExtensionCreateHorizOrdinateDimension)

CmdTechDrawExtensionCreateHorizOrdinateDimension::CmdTechDrawExtensionCreateHorizOrdinateDimension()
    : Command("TechDraw_ExtensionCreateHorizOrdinateDimension")
{
    sAppModule = "TechDraw";
    sGroup = QT_TR_NOOP("TechDraw");
    sMenuText = QT_TR_NOOP("Horizontal Ordinate Dimensions");
    sToolTipText = QT_TR_NOOP("Creates horizontal ordinate dimensions from the first selected vertex as the zero origin");
    sWhatsThis = "TechDraw_ExtensionCreateHorizOrdinateDimension";
    sStatusTip = sMenuText;
    sPixmap = "TechDraw_ExtensionCreateHorizOrdinateDimension";
}

void CmdTechDrawExtensionCreateHorizOrdinateDimension::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    execCreateHorizOrdinateDimension(this);
}

bool CmdTechDrawExtensionCreateHorizOrdinateDimension::isActive()
{
    return DrawGuiUtil::needPage(this) && DrawGuiUtil::needView(this);
}

//===========================================================================
// TechDraw_ExtensionCreateVertOrdinateDimension
//===========================================================================

void execCreateVertOrdinateDimension(Gui::Command* cmd)
{
    std::vector<Gui::SelectionObject> selection;
    TechDraw::DrawViewPart* objFeat = nullptr;
    if (!_checkSelObjAndSubs(cmd, selection, objFeat,
                            QT_TRANSLATE_NOOP("QObject", "TechDraw Create Vertical Ordinate Dimension"))) {
        return;
    }

    cmd->openCommand(QT_TRANSLATE_NOOP("Command", "Create Vertical Ordinate Dimensions"));
    const std::vector<std::string> subNames = selection[0].getSubNames();
    std::vector<dimVertex> allVertexes = _getVertexInfo(objFeat, subNames);
    if (allVertexes.size() > 1) {
        double dimDistance = activeDimAttributes.getCascadeSpacing();
        double xMaster = allVertexes[0].point.x - dimDistance;
        if (std::signbit(xMaster)) {
            dimDistance = -dimDistance;
        }

        auto* zeroDim = _createLinDimension(
            objFeat, allVertexes[0].name, allVertexes[0].name, "OrdinateY");
        zeroDim->X.setValue(xMaster);
        zeroDim->Y.setValue(-allVertexes[0].point.y);

        for (std::size_t n = 1; n < allVertexes.size(); ++n) {
            auto* dim = _createLinDimension(
                objFeat, allVertexes[0].name, allVertexes[n].name, "OrdinateY");
            TechDraw::pointPair pp = dim->getLinearPoints();
            dim->X.setValue(xMaster);
            dim->Y.setValue(-pp.second().y);
        }
    }
    objFeat->refreshCEGeoms();
    objFeat->requestPaint();
    cmd->getSelection().clearSelection();
    cmd->commitCommand();
}

DEF_STD_CMD_A(CmdTechDrawExtensionCreateVertOrdinateDimension)

CmdTechDrawExtensionCreateVertOrdinateDimension::CmdTechDrawExtensionCreateVertOrdinateDimension()
    : Command("TechDraw_ExtensionCreateVertOrdinateDimension")
{
    sAppModule = "TechDraw";
    sGroup = QT_TR_NOOP("TechDraw");
    sMenuText = QT_TR_NOOP("Vertical Ordinate Dimensions");
    sToolTipText = QT_TR_NOOP("Creates vertical ordinate dimensions from the first selected vertex as the zero origin");
    sWhatsThis = "TechDraw_ExtensionCreateVertOrdinateDimension";
    sStatusTip = sMenuText;
    sPixmap = "TechDraw_ExtensionCreateVertOrdinateDimension";
}

void CmdTechDrawExtensionCreateVertOrdinateDimension::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    execCreateVertOrdinateDimension(this);
}

bool CmdTechDrawExtensionCreateVertOrdinateDimension::isActive()
{
    return DrawGuiUtil::needPage(this) && DrawGuiUtil::needView(this);
}

//===========================================================================
// TechDraw_ExtensionCreateOrdinateDimensionGroup
//===========================================================================

DEF_STD_CMD_ACL(CmdTechDrawExtensionCreateOrdinateDimensionGroup)

CmdTechDrawExtensionCreateOrdinateDimensionGroup::CmdTechDrawExtensionCreateOrdinateDimensionGroup()
    : Command("TechDraw_ExtensionCreateOrdinateDimensionGroup")
{
    sAppModule = "TechDraw";
    sGroup = QT_TR_NOOP("TechDraw");
    sMenuText = QT_TR_NOOP("Horizontal Ordinate Dimensions");
    sToolTipText = QT_TR_NOOP("Creates ordinate dimensions from the first selected vertex as the zero origin");
    sWhatsThis = "TechDraw_ExtensionCreateOrdinateDimensionGroup";
    sStatusTip = sMenuText;
}

void CmdTechDrawExtensionCreateOrdinateDimensionGroup::activated(int iMsg)
{
    Gui::TaskView::TaskDialog* dlg = Gui::Control().activeDialog();
    if (dlg) {
        QMessageBox::warning(Gui::getMainWindow(), QObject::tr("Task in progress"),
                             QObject::tr("Close active task dialog and try again"));
        return;
    }

    auto* action = qobject_cast<Gui::ActionGroup*>(_pcAction);
    action->setIcon(action->actions().at(iMsg)->icon());
    if (iMsg == 0) {
        execCreateHorizOrdinateDimension(this);
    }
    else if (iMsg == 1) {
        execCreateVertOrdinateDimension(this);
    }
}

Gui::Action* CmdTechDrawExtensionCreateOrdinateDimensionGroup::createAction()
{
    auto* action = new Gui::ActionGroup(this, Gui::getMainWindow());
    action->setDropDownMenu(true);
    applyCommandData(this->className(), action);

    QAction* horizontal = action->addAction(QString());
    horizontal->setIcon(Gui::BitmapFactory().iconFromTheme("TechDraw_ExtensionCreateHorizOrdinateDimension"));
    horizontal->setObjectName(QStringLiteral("TechDraw_ExtensionCreateHorizOrdinateDimension"));
    horizontal->setWhatsThis(QStringLiteral("TechDraw_ExtensionCreateHorizOrdinateDimension"));

    QAction* vertical = action->addAction(QString());
    vertical->setIcon(Gui::BitmapFactory().iconFromTheme("TechDraw_ExtensionCreateVertOrdinateDimension"));
    vertical->setObjectName(QStringLiteral("TechDraw_ExtensionCreateVertOrdinateDimension"));
    vertical->setWhatsThis(QStringLiteral("TechDraw_ExtensionCreateVertOrdinateDimension"));

    _pcAction = action;
    languageChange();
    action->setIcon(horizontal->icon());
    action->setProperty("defaultAction", QVariant(0));
    return action;
}

void CmdTechDrawExtensionCreateOrdinateDimensionGroup::languageChange()
{
    Command::languageChange();
    if (!_pcAction) {
        return;
    }
    auto* action = qobject_cast<Gui::ActionGroup*>(_pcAction);
    QList<QAction*> actions = action->actions();
    actions[0]->setText(QApplication::translate(
        "CmdTechDrawExtensionCreateHorizOrdinateDimension", "Horizontal Ordinate Dimensions"));
    actions[0]->setToolTip(QApplication::translate(
        "CmdTechDrawExtensionCreateHorizOrdinateDimension",
        "Creates horizontal ordinate dimensions from the first selected vertex as the zero origin"));
    actions[0]->setStatusTip(actions[0]->text());

    actions[1]->setText(QApplication::translate(
        "CmdTechDrawExtensionCreateVertOrdinateDimension", "Vertical Ordinate Dimensions"));
    actions[1]->setToolTip(QApplication::translate(
        "CmdTechDrawExtensionCreateVertOrdinateDimension",
        "Creates vertical ordinate dimensions from the first selected vertex as the zero origin"));
    actions[1]->setStatusTip(actions[1]->text());
}

bool CmdTechDrawExtensionCreateOrdinateDimensionGroup::isActive()
{
    return DrawGuiUtil::needPage(this) && DrawGuiUtil::needView(this, true);
}

'''
text = replace_once(
    text,
    "//===========================================================================\n// TechDraw_ExtensionCreateHorizCoordDimension\n//===========================================================================\n",
    ordinate_commands
    + "//===========================================================================\n// TechDraw_ExtensionCreateHorizCoordDimension\n//===========================================================================\n",
    "CommandExtensionDims ordinate command insertion",
)
text = replace_once(
    text,
    "    rcCmdMgr.addCommand(new CmdTechDrawExtensionCreateObliqueCoordDimension());\n",
    "    rcCmdMgr.addCommand(new CmdTechDrawExtensionCreateObliqueCoordDimension());\n"
    "    rcCmdMgr.addCommand(new CmdTechDrawExtensionCreateOrdinateDimensionGroup());\n"
    "    rcCmdMgr.addCommand(new CmdTechDrawExtensionCreateHorizOrdinateDimension());\n"
    "    rcCmdMgr.addCommand(new CmdTechDrawExtensionCreateVertOrdinateDimension());\n",
    "CommandExtensionDims registrations",
)
write(rel, text)


# ---------------------------------------------------------------------------
# Workbench placement and Qt resources.
# ---------------------------------------------------------------------------
rel = "src/Mod/TechDraw/Gui/Workbench.cpp"
text = read(rel)
text = replace_once(
    text,
    '    *tooldimensions << "TechDraw_ExtensionCreateObliqueCoordDimension";\n',
    '    *tooldimensions << "TechDraw_ExtensionCreateObliqueCoordDimension";\n'
    '    *tooldimensions << "TechDraw_ExtensionCreateHorizOrdinateDimension";\n'
    '    *tooldimensions << "TechDraw_ExtensionCreateVertOrdinateDimension";\n',
    "Workbench ordinate menu",
)
write(rel, text)

rel = "src/Mod/TechDraw/Gui/Resources/TechDraw.qrc"
text = read(rel)
text = replace_once(
    text,
    "        <file>icons/TechDraw_ExtensionCreateHorizCoordDimension.svg</file>\n",
    "        <file>icons/TechDraw_ExtensionCreateHorizCoordDimension.svg</file>\n"
    "        <file>icons/TechDraw_ExtensionCreateHorizOrdinateDimension.svg</file>\n",
    "TechDraw.qrc horizontal ordinate icon",
)
text = replace_once(
    text,
    "        <file>icons/TechDraw_ExtensionCreateVertCoordDimension.svg</file>\n",
    "        <file>icons/TechDraw_ExtensionCreateVertCoordDimension.svg</file>\n"
    "        <file>icons/TechDraw_ExtensionCreateVertOrdinateDimension.svg</file>\n",
    "TechDraw.qrc vertical ordinate icon",
)
write(rel, text)

# Reuse the historical SVGs only; source code is ported against current main.
subprocess.run(
    ["git", "fetch", "origin", "money-agent-6587-legacy-port:refs/remotes/origin/money-agent-6587-legacy-port"],
    cwd=ROOT,
    check=True,
)
for name in (
    "TechDraw_ExtensionCreateHorizOrdinateDimension.svg",
    "TechDraw_ExtensionCreateVertOrdinateDimension.svg",
):
    rel = f"src/Mod/TechDraw/Gui/Resources/icons/{name}"
    data = subprocess.check_output(
        ["git", "show", f"origin/money-agent-6587-legacy-port:{rel}"], cwd=ROOT
    )
    (ROOT / rel).write_bytes(data)

print("FreeCAD #6587 ordinate-dimension port applied successfully")
