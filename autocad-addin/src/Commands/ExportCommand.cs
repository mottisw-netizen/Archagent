using System;
using System.Collections.Generic;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.PlottingServices;

namespace Archagent.Acad.Commands
{
    /// <summary>
    /// The two things that turn a change into something a person can check: a
    /// picture of the layout, and a new file that is not the architect's
    /// original. Same intent as <c>revit-addin/src/Commands/ExportCommand.cs</c>;
    /// the mechanism differs because AutoCAD has no single "export image" call -
    /// it plots, same as printing, to the built-in raster plot device.
    /// </summary>
    internal static class ExportCommand
    {
        public static Dictionary<string, object> Run(Document doc, Dictionary<string, object> request)
        {
            string layoutName = Json.String(request, "view", "");
            string path = Json.String(request, "path", "");
            if (string.IsNullOrWhiteSpace(path))
                path = Path.Combine(Path.GetTempPath(),
                    "archagent-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".png");

            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                Layout layout = FindLayout(tr, doc.Database, layoutName)
                    ?? (Layout)tr.GetObject(
                        ((DBDictionary)tr.GetObject(doc.Database.LayoutDictionaryId, OpenMode.ForRead))
                            .GetAt(doc.Database.CurrentLayout ?? "Model"), OpenMode.ForRead);

                PlotToPng(doc, layout, path);
                tr.Commit();
                return new Dictionary<string, object>
                    { { "path", path }, { "format", "png" }, { "view", layout.LayoutName } };
            }
        }

        private static Layout FindLayout(Transaction tr, Database db, string name)
        {
            if (string.IsNullOrWhiteSpace(name)) return null;
            var layouts = (DBDictionary)tr.GetObject(db.LayoutDictionaryId, OpenMode.ForRead);
            foreach (var entry in layouts)
            {
                var layout = (Layout)tr.GetObject(entry.Value, OpenMode.ForRead);
                if (string.Equals(layout.LayoutName, name, StringComparison.OrdinalIgnoreCase))
                    return layout;
            }
            return null;
        }

        /// <summary>
        /// Plots a layout to PNG via the built-in raster plot device - the
        /// standard, if verbose, way to get a picture out of AutoCAD
        /// programmatically. Best-effort: plot device names and defaults vary
        /// by AutoCAD version and locale, and this is the one part of the
        /// add-in most likely to need adjustment on first real use.
        /// </summary>
        private static void PlotToPng(Document doc, Layout layout, string path)
        {
            if (!PlotFactory.ProcessPlotState.Equals(PlotFactory.ProcessPlotState.NotPlotting))
                throw HostException.Unsupported("AutoCAD is already plotting something else");

            using (var info = new PlotInfo { Layout = layout.ObjectId })
            {
                var settings = new PlotSettings(layout.ModelType);
                settings.CopyFrom(layout);
                var validator = PlotSettingsValidator.Current;
                validator.SetPlotConfigurationName(settings, "PublishToWeb PNG.pc3", null);
                validator.RefreshLists(settings);
                validator.SetPlotType(settings, Autodesk.AutoCAD.DatabaseServices.PlotType.Extents);
                validator.SetUseStandardScale(settings, true);
                validator.SetStdScaleType(settings, StdScaleType.ScaleToFit);
                validator.SetPlotCentered(settings, true);
                info.OverrideSettings = settings;

                using (var validatorInfo = new PlotInfoValidator { MediaMatchingPolicy = MatchingPolicy.MatchEnabled })
                {
                    validatorInfo.Validate(info);
                }

                using (var engine = PlotFactory.CreatePublishEngine())
                {
                    var progress = new PlotProgressDialog(false, 1, true);
                    engine.BeginPlot(progress, null);
                    engine.BeginDocument(info, doc.Name, null, 1, true, path);
                    var pageInfo = new PlotPageInfo();
                    engine.BeginPage(pageInfo, info, true, null);
                    engine.BeginGenerateGraphics(null);
                    engine.EndGenerateGraphics(null);
                    engine.EndPage(null);
                    engine.EndDocument(null);
                    engine.EndPlot(null);
                }
            }
        }

        /// <summary>
        /// Save a copy under a new name: the architect's file is never the
        /// file the agent writes (SKILL.md 16).
        /// </summary>
        public static Dictionary<string, object> SaveAs(Document doc, Dictionary<string, object> request)
        {
            string path = Json.String(request, "path", "");
            if (string.IsNullOrWhiteSpace(path))
                throw HostException.Unsupported("save_as needs a path");
            if (string.Equals(Path.GetFullPath(path), doc.Name, StringComparison.OrdinalIgnoreCase))
                throw HostException.Unsupported(
                    "refusing to overwrite the open document; a version is a new file");

            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            doc.Database.SaveAs(path, DwgVersion.Current);
            return new Dictionary<string, object> { { "path", path } };
        }
    }
}
