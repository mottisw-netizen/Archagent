using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace Archagent.Revit.Commands
{
    /// <summary>
    /// The two things that turn a change into something a person can check: a
    /// picture of the view, and a new file that is not the architect's original.
    /// </summary>
    internal static class ExportCommand
    {
        public static Dictionary<string, object> Run(
            UIApplication app, Document doc, Dictionary<string, object> request)
        {
            string viewName = Json.String(request, "view", "");
            string path = Json.String(request, "path", "");
            if (string.IsNullOrWhiteSpace(path))
                path = Path.Combine(Path.GetTempPath(),
                    "archagent-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".png");

            View view = FindView(doc, viewName) ?? doc.ActiveView;
            if (view == null) throw HostException.NotFound(viewName);

            var options = new ImageExportOptions
            {
                FilePath = path,
                ExportRange = ExportRange.SetOfViews,
                HLRandWFViewsFileType = ImageFileType.PNG,
                ImageResolution = ImageResolution.DPI_150,
                ZoomType = ZoomFitType.FitToPage,
                PixelSize = 1600,
            };
            options.SetViewsAndSheets(new List<ElementId> { view.Id });
            doc.ExportImage(options);

            // Revit appends the view name to the file it writes.
            string written = Directory
                .GetFiles(Path.GetDirectoryName(path),
                    Path.GetFileNameWithoutExtension(path) + "*")
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault() ?? path;

            return new Dictionary<string, object>
                { { "path", written }, { "format", "png" }, { "view", view.Name } };
        }

        private static View FindView(Document doc, string name)
        {
            if (string.IsNullOrWhiteSpace(name)) return null;
            return new FilteredElementCollector(doc)
                .OfClass(typeof(View))
                .Cast<View>()
                .FirstOrDefault(view => !view.IsTemplate &&
                                        string.Equals(view.Name, name,
                                            StringComparison.OrdinalIgnoreCase));
        }

        /// <summary>
        /// Save a copy under a new name: the architect's file is never the file
        /// the agent writes (SKILL.md 16).
        /// </summary>
        public static Dictionary<string, object> SaveAs(
            Document doc, Dictionary<string, object> request)
        {
            string path = Json.String(request, "path", "");
            if (string.IsNullOrWhiteSpace(path))
                throw HostException.Unsupported("save_as needs a path");
            if (string.Equals(Path.GetFullPath(path), doc.PathName,
                    StringComparison.OrdinalIgnoreCase))
                throw HostException.Unsupported(
                    "refusing to overwrite the open document; a version is a new file");

            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            var options = new SaveAsOptions { OverwriteExistingFile = false, Compact = true };
            doc.SaveAs(ModelPathUtils.ConvertUserVisiblePathToModelPath(path), options);
            return new Dictionary<string, object> { { "path", path } };
        }
    }
}
