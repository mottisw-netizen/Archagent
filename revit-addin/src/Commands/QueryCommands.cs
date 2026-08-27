using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;

namespace Archagent.Revit.Commands
{
    /// <summary>Everything the agent reads: elements, geometry, sheets, measurements.</summary>
    internal static class QueryCommands
    {
        public static Dictionary<string, object> Health(Document doc)
        {
            var app = doc?.Application;
            return new Dictionary<string, object>
            {
                { "protocol", Protocol.Version },
                { "host", "revit" },
                { "host_version", app == null ? "" : app.VersionNumber + " (" + app.VersionBuild + ")" },
                { "document", doc?.Title ?? string.Empty },
                { "units", "m" },
                { "read_only", doc == null || doc.IsReadOnly },
                { "project_north", ProjectNorth(doc) },
                { "element_count", doc == null ? 0 : ElementView.Collect(doc, null).Count() },
            };
        }

        private static double ProjectNorth(Document doc)
        {
            if (doc == null) return 0.0;
            var position = doc.ActiveProjectLocation?.GetProjectPosition(XYZ.Zero);
            return position == null ? 0.0 : Math.Round(position.Angle * 180.0 / Math.PI, 4);
        }

        public static Dictionary<string, object> Find(Document doc, Dictionary<string, object> request)
        {
            var filter = Json.Dict(request, "filter");
            bool full = Json.String(request, "detail", "") == "full";
            string category = Json.String(filter, "type", Json.String(filter, "category", ""));

            var matches = ElementView.Collect(doc, category)
                .Where(element => Matches(doc, element, filter))
                .ToList();

            if (!full)
                return new Dictionary<string, object>
                    { { "elements", matches.Select(e => (object)e.UniqueId).ToList() } };

            return new Dictionary<string, object>
            {
                { "elements", matches.Select(e => (object)ElementView.Describe(doc, e)).ToList() },
            };
        }

        private static bool Matches(Document doc, Element element, Dictionary<string, object> filter)
        {
            foreach (var pair in filter)
            {
                string expected = Convert.ToString(pair.Value) ?? string.Empty;
                string actual;
                switch (pair.Key)
                {
                    case "type":
                    case "category":
                        actual = ElementView.CategoryOf(element);
                        break;
                    case "id":
                    case "element_id":
                        actual = element.UniqueId;
                        break;
                    case "label":
                        actual = ElementView.MarkOf(element);
                        break;
                    case "label_contains":
                        if (!ElementView.MarkOf(element).ToLowerInvariant()
                                .Contains(expected.ToLowerInvariant()))
                            return false;
                        continue;
                    case "level":
                        actual = ElementView.LevelOf(doc, element);
                        break;
                    default:
                    {
                        var parameter = element.LookupParameter(pair.Key);
                        actual = parameter == null
                            ? string.Empty
                            : (parameter.StorageType == StorageType.String
                                ? parameter.AsString()
                                : parameter.AsValueString());
                        break;
                    }
                }
                if (!string.Equals(actual ?? string.Empty, expected,
                        StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            return true;
        }

        public static Dictionary<string, object> Element(Document doc, Dictionary<string, object> request)
        {
            var element = Resolve(doc, Json.String(request, "id", ""));
            return ElementView.Describe(doc, element);
        }

        public static Dictionary<string, object> Geometry(Document doc, Dictionary<string, object> request)
        {
            var element = Resolve(doc, Json.String(request, "id", ""));
            var bbox = element.get_BoundingBox(null);
            var box = ElementView.BoxOf(bbox);
            return new Dictionary<string, object>
            {
                { "bbox", box },
                { "area", Units.Tidy(Convert.ToDouble(box["w"]) * Convert.ToDouble(box["h"])) },
                { "width", box["w"] },
                { "length", box["h"] },
                { "level", ElementView.LevelOf(doc, element) },
            };
        }

        public static Dictionary<string, object> Properties(Document doc, Dictionary<string, object> request)
        {
            var element = Resolve(doc, Json.String(request, "id", ""));
            return new Dictionary<string, object> { { "properties", ElementView.Parameters(element) } };
        }

        public static Dictionary<string, object> Sheets(Document doc)
        {
            var sheets = new FilteredElementCollector(doc)
                .OfClass(typeof(ViewSheet))
                .Cast<ViewSheet>()
                .Select(sheet => (object)new Dictionary<string, object>
                {
                    { "id", sheet.SheetNumber }, { "name", sheet.Name },
                    { "unique_id", sheet.UniqueId },
                })
                .ToList();

            var schedules = new Dictionary<string, object>();
            foreach (ViewSchedule schedule in new FilteredElementCollector(doc)
                         .OfClass(typeof(ViewSchedule)).Cast<ViewSchedule>())
            {
                if (schedule.IsTemplate) continue;
                var body = schedule.GetTableData().GetSectionData(SectionType.Body);
                schedules[schedule.Name] = new Dictionary<string, object>
                {
                    { "title", schedule.Name },
                    { "unique_id", schedule.UniqueId },
                    { "rows", body.NumberOfRows },
                    { "columns", body.NumberOfColumns },
                };
            }
            return new Dictionary<string, object>
                { { "sheets", sheets }, { "schedules", schedules } };
        }

        // ------------------------------------------------------------------
        public static Element Resolve(Document doc, string uniqueId)
        {
            var element = doc.GetElement(uniqueId);
            if (element == null) throw HostException.NotFound(uniqueId);
            return element;
        }
    }
}
